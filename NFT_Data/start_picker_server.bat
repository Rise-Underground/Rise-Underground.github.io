@echo off
cd /d "%~dp0"
echo Starting local server for item_picker.html...
start "RISE Picker Server" /min cmd /c "python -m http.server 8000"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000/item_picker.html"
echo.
echo Server is running in a separate minimized window titled "RISE Picker Server".
echo To stop it, find that window in your taskbar and close it.
echo.
pause
