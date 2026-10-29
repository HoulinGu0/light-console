@echo off
chcp 65001 >nul
cd /d "%~dp0scripts"
echo ============================================
echo   机箱灯光控制台  (ASUS Aura / OpenRGB)
echo   浏览器将自动打开 http://127.0.0.1:8099/
echo   关闭此窗口即可停止控制
echo ============================================
echo.
python server.py
echo.
echo 控制台已停止。
pause
