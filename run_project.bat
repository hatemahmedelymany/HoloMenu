@echo off
title HoloMenu Unified Runner
echo ====================================================
echo             HoloMenu Unified Runner
echo ====================================================
echo.

:: 1. Start Frontend Server
echo [+] Starting Frontend Server on http://127.0.0.1:8080/portal.html...
start "HoloHost: Frontend 8080" cmd /k "python -m http.server 8080"

:: 2. Start Backend API
echo [+] Starting FastAPI Backend on http://127.0.0.1:8081...
if exist .venv\Scripts\activate.bat (
    start "HoloHost: Backend 8081" cmd /k "call .venv\Scripts\activate.bat && uvicorn backend.main:app --port 8081 --reload"
) else (
    start "HoloHost: Backend 8081" cmd /k "uvicorn backend.main:app --port 8081 --reload"
)

:: 3. Start Gesture Recognition Engine
echo [+] Starting Gesture Engine on ws://localhost:8766...
if exist .venv\Scripts\activate.bat (
    start "HoloHost: Gesture Engine 8766" cmd /k "call .venv\Scripts\activate.bat && python gesture_engine.py"
) else (
    start "HoloHost: Gesture Engine 8766" cmd /k "python gesture_engine.py"
)

echo.
echo ====================================================
echo All components started!
echo - Gateway Portal Hub:  http://localhost:8080/portal.html
echo - Kiosk Screen:        http://localhost:8080/index.html
echo - Cashier Screen:      http://localhost:8080/cashier.html
echo - Admin Screen:        http://localhost:8080/admin.html
echo ====================================================
echo Press any key to exit this loader. Servers will stay open.
pause > nul
