[CmdletBinding()]
param(
    [switch]$Update
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Jobs = if ($env:JOBS) { $env:JOBS } else { "2" }

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "==> Checking build tools"
if (-not (Test-Command git)) {
    if (Test-Command winget) {
        Write-Host "==> Installing Git"
        winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "Git installation failed." }
    } else {
        throw "Git is required. Install Git for Windows and try again."
    }
}
if (-not (Test-Command cmake)) {
    if (Test-Command winget) {
        Write-Host "==> Installing CMake"
        winget install --id Kitware.CMake -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "CMake installation failed." }
    } else {
        throw "CMake is required. Install CMake and enable PATH integration."
    }
}
if (-not (Test-Command py) -and -not (Test-Command python) -and -not (Test-Command python3)) {
    if (Test-Command winget) {
        Write-Host "==> Installing Python 3"
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "Python 3 installation failed." }
    } else {
        throw "Python 3 is required. Install Python 3 and enable PATH integration."
    }
}

$LLama = Join-Path $PSScriptRoot "llama.cpp"
if (-not (Test-Path $LLama)) {
    Write-Host "==> Cloning llama.cpp"
    git clone --depth 1 https://github.com/ggml-org/llama.cpp.git $LLama
} elseif ($Update) {
    Write-Host "==> Updating llama.cpp"
    git -C $LLama pull --ff-only
}

$Cli = Join-Path $LLama "build\bin\llama-cli.exe"
$Server = Join-Path $LLama "build\bin\llama-server.exe"
if ((Test-Path $Cli) -and (Test-Path $Server) -and -not $Update) {
    Write-Host "==> llama.cpp already built, skipping"
} else {
    Write-Host "==> Building llama.cpp (this can take 10-30+ minutes)"
    cmake -S $LLama -B (Join-Path $LLama "build") -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DLLAMA_CURL=OFF
    if ($LASTEXITCODE -ne 0) { throw "CMake configuration failed." }
    cmake --build (Join-Path $LLama "build") --config Release -j $Jobs --target llama-server llama-cli
    if ($LASTEXITCODE -ne 0) { throw "llama.cpp build failed." }
}

if (-not (Test-Command cloudflared)) {
    Write-Host "==> Installing cloudflared"
    $arch = if ($env:PROCESSOR_ARCHITECTURE -match "ARM64") { "arm64" } else { "amd64" }
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-$arch.exe"
    $destination = Join-Path $env:USERPROFILE "bin\cloudflared.exe"
    New-Item -ItemType Directory -Force (Split-Path $destination) | Out-Null
    Invoke-WebRequest -Uri $url -OutFile $destination
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($userPath -split ";") -notcontains (Split-Path $destination)) {
        [Environment]::SetEnvironmentVariable("Path", (($userPath.TrimEnd(";") + ";" + (Split-Path $destination)).Trim(";")), "User")
    }
    Write-Host "==> cloudflared installed. Restart the terminal if it is not found."
}

if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $PSScriptRoot ".env")
    Write-Host "==> Created .env"
}
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "models") | Out-Null
Write-Host "==> Done. Run: py model_server.py"
