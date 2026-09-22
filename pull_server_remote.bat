@echo off
setlocal

set SERVER=tuan@192.168.31.104
set REPO_DIR=~/dashboard-alpha-score
set BRANCH=%1

if "%BRANCH%"=="" set BRANCH=dev

echo ========================================
echo Remote pull script
echo Server : %SERVER%
echo Folder : %REPO_DIR%
echo Branch : %BRANCH%
echo ========================================
echo.
echo Connecting to server and pulling latest code...

ssh %SERVER% "cd %REPO_DIR% && git fetch origin %BRANCH% && git checkout %BRANCH% && git pull --ff-only origin %BRANCH%"

if errorlevel 1 (
    echo.
    echo Pull failed. Check SSH access, repo path, or git status on server.
) else (
    echo.
    echo Pull completed successfully.
)

echo.
pause

endlocal
