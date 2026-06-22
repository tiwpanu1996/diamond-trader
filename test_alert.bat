@echo off
REM 💎 DIAMOND TRADER — Send Test Alerts (Windows)

setlocal enabledelayedexpansion

set BACKEND=http://localhost:8000
set SECRET=diamond2026

echo =========================================================
echo 💎 DIAMOND TRADER - Test Alert Sender (Windows)
echo =========================================================
echo.

REM Check if curl is available
curl --version >nul 2>&1
if errorlevel 1 (
    echo ❌ curl not found. Install from: https://curl.se/download.html
    pause
    exit /b 1
)

REM Check backend
echo 🔍 Checking backend connection...
curl -s "%BACKEND%/health" >nul 2>&1
if errorlevel 1 (
    echo ❌ Backend not responding at %BACKEND%
    echo    Make sure to run: python backend_main.py
    pause
    exit /b 1
)
echo ✓ Backend is LIVE
echo.

REM Function to send alert
setlocal enabledelayedexpansion

echo =========================================================
echo Test 1: Pat3.2 BUY (HIGH-EDGE)
echo =========================================================
echo 📤 Sending alert...
curl -X POST "%BACKEND%/webhook" ^
  -H "Content-Type: application/json" ^
  -H "X-Secret: %SECRET%" ^
  -d "{\"symbol\":\"XAUUSDm\",\"tf\":\"M5\",\"pat\":\"Pat3.2 BUY\",\"side\":1,\"verdict\":\"READY\",\"ovl\":150,\"cf_count\":3,\"spread\":160,\"grid\":3200.0,\"entry\":3201.5,\"sl\":3198.5,\"tp\":3210.5,\"regime\":\"TRENDING\"}"
echo ✓ Alert sent
echo.
timeout /t 1

echo =========================================================
echo Test 2: Pat3.3 SELL (HIGH-EDGE)
echo =========================================================
echo 📤 Sending alert...
curl -X POST "%BACKEND%/webhook" ^
  -H "Content-Type: application/json" ^
  -H "X-Secret: %SECRET%" ^
  -d "{\"symbol\":\"XAUUSDm\",\"tf\":\"M5\",\"pat\":\"Pat3.3 SELL\",\"side\":-1,\"verdict\":\"READY\",\"ovl\":150,\"cf_count\":3,\"spread\":160,\"grid\":3200.0,\"entry\":3198.5,\"sl\":3201.5,\"tp\":3189.5,\"regime\":\"TRENDING\"}"
echo ✓ Alert sent
echo.
timeout /t 1

echo =========================================================
echo Test 3: Pat1 BUY (LOW-EDGE)
echo =========================================================
echo 📤 Sending alert...
curl -X POST "%BACKEND%/webhook" ^
  -H "Content-Type: application/json" ^
  -H "X-Secret: %SECRET%" ^
  -d "{\"symbol\":\"XAUUSDm\",\"tf\":\"M5\",\"pat\":\"Pat1 BUY\",\"side\":1,\"verdict\":\"WAIT\",\"ovl\":250,\"cf_count\":2,\"spread\":180,\"grid\":3195.0,\"entry\":3195.5,\"sl\":3192.5,\"tp\":3204.5,\"regime\":\"RANGING\"}"
echo ✓ Alert sent
echo.
timeout /t 1

echo =========================================================
echo Test 4: Pat2 SELL (LOW-EDGE)
echo =========================================================
echo 📤 Sending alert...
curl -X POST "%BACKEND%/webhook" ^
  -H "Content-Type: application/json" ^
  -H "X-Secret: %SECRET%" ^
  -d "{\"symbol\":\"XAUUSDm\",\"tf\":\"M5\",\"pat\":\"Pat2 SELL\",\"side\":-1,\"verdict\":\"NO-TRADE\",\"ovl\":350,\"cf_count\":1,\"spread\":200,\"grid\":3205.0,\"entry\":3204.5,\"sl\":3207.5,\"tp\":3195.5,\"regime\":\"RANGING\"}"
echo ✓ Alert sent
echo.

echo =========================================================
echo ✓ All test alerts sent!
echo =========================================================
echo.
echo 📊 Check your browser dashboard:
echo    - Alert Log should show 4 new entries
echo    - Execution card updated
echo.
echo 📌 Browser Console (F12):
echo    🔔 Alert: Pat3.2 BUY
echo    🔔 Alert: Pat3.3 SELL
echo    🔔 Alert: Pat1 BUY
echo    🔔 Alert: Pat2 SELL
echo.
echo =========================================================
echo.
pause
