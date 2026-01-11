@echo off
REM Cleanup NUL file that blocks OneDrive sync
cd /d "%~dp0"
echo Checking for nul file...
if exist nul (
    echo Found nul file, deleting...
    del /f /q nul 2>NUL
    if not exist nul (
        echo Success: nul file deleted
    ) else (
        echo Failed: nul file still exists
    )
) else (
    echo No nul file found
)
echo.
echo Also adding nul to .gitignore...
findstr /C:"nul" .gitignore >NUL 2>&1
if errorlevel 1 (
    echo nul>> .gitignore
    echo Added nul to .gitignore
) else (
    echo nul already in .gitignore
)
echo.
echo Done!
pause
