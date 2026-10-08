@echo off
cd /d %~dp0
if exist "data\leaderboard.db" del /f /q "data\leaderboard.db"
echo Локальная база удалена. При следующем запуске будет заново импортировано 17 951 исходное учреждение.
pause
