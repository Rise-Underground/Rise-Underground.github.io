@echo off
cd /d "%~dp0"
echo Running post_to_x.py in DRY RUN mode (nothing will be posted)...
echo.
python post_to_x.py
echo.
pause
