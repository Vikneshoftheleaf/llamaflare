[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)
Set-Location $PSScriptRoot
$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Host "Python 3 was not found."
    Write-Host "Install it from https://www.python.org/downloads/windows/"
    Write-Host 'Enable "Add python.exe to PATH" during installation.'
    exit 1
}
& $python.Source model_server.py @Args
exit $LASTEXITCODE
