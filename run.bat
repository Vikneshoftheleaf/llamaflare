@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 goto use_py

where python >nul 2>&1
if not errorlevel 1 goto use_python

where python3 >nul 2>&1
if not errorlevel 1 goto use_python3

echo Python 3 was not found.
echo Install Python 3 from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH" during installation.
exit /b 1

:use_py
py model_server.py %*
exit /b %errorlevel%

:use_python
python model_server.py %*
exit /b %errorlevel%

:use_python3
python3 model_server.py %*
exit /b %errorlevel%
