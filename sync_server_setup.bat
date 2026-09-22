@echo off
setlocal

set SERVER=tuan@192.168.31.104
set REPO_DIR=~/dashboard-alpha-score
set BRANCH=%1

if "%BRANCH%"=="" set BRANCH=dev

echo ========================================
echo Remote sync + setup script
echo Server : %SERVER%
echo Folder : %REPO_DIR%
echo Branch : %BRANCH%
echo ========================================
echo.
echo Pulling latest code and running venv setup...

ssh %SERVER% "cd %REPO_DIR% && git fetch origin %BRANCH% && git checkout %BRANCH% && git pull --ff-only origin %BRANCH% && chmod +x setup_server_venv.sh && ./setup_server_venv.sh"

if errorlevel 1 (
    echo.
    echo Sync/setup failed. Check SSH access, repo path, git status, or server package availability.
) else (
    echo.
    echo Sync/setup completed successfully.
)

echo.
pause

endlocal
