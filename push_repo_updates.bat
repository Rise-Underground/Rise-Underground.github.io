@echo off
REM push_repo_updates.bat
REM
REM Commits and pushes ALL changes currently sitting in the cloned
REM Rise-Underground.github.io folder -- new files, modified files,
REM everything not excluded by .gitignore (*.db, base_scan_state.json,
REM __pycache__/, *.pyc stay untouched).
REM
REM Run this manually, or point a Task Scheduler task at it after any
REM updater script (combined_dashboard_data.py, pool_history_updater.py,
REM new_unified_backfill_updater.py, etc.) finishes writing its output
REM into this same folder.

cd /d "C:\Users\19782\Desktop\Rise-Underground.github.io"

git add -A

git diff --cached --quiet
if %errorlevel% equ 0 (
    echo No changes to push.
    exit /b 0
)

git commit -m "Automated update: %date% %time%"

set retries=5
:push_loop
git pull --rebase origin main
git push
if %errorlevel% equ 0 (
    echo Push succeeded.
    exit /b 0
)

set /a retries-=1
if %retries% gtr 0 (
    echo Push failed -- retrying in 5 seconds ^(%retries% attempt^(s^) left^)...
    timeout /t 5 /nobreak >nul
    goto push_loop
)

echo Push failed after all retries.
exit /b 1
