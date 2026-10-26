@echo off
title RouteCraft - Smart Travel Planner
echo.
echo  ==========================================
echo   RouteCraft - Smart Travel Planner
echo  ==========================================
echo.
echo  Starting server...
echo  Open your browser at: http://localhost:5000
echo.
cd /d "%~dp0"
python app.py
pause
