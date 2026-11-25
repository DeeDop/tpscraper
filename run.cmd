@echo off
setlocal
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 "%~dp0launch.py" %*
goto finished
:use_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python "%~dp0launch.py" %*
goto finished
:missing_python
echo Python 3.11 or newer is required. Install Python, then run this file again.
pause
exit /b 2
:finished
set "result=%errorlevel%"
if not "%result%"=="0" (
    echo.
    echo tpscraper exited with code %result%.
    pause
)
exit /b %result%
