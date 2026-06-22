@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM TEST WEBHOOK — DIAMOND TRADER PA Alerts
REM ═══════════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

REM Config
set BACKEND_URL=http://localhost:8000/alerts
set DASHBOARD_URL=http://localhost:8000

echo.
echo ╔════════════════════════════════════════════════════════════════════════╗
echo ║ DIAMOND TRADER — Webhook Test Suite                                   ║
echo ╚════════════════════════════════════════════════════════════════════════╝
echo.

REM Check backend
echo [1/4] ตรวจว่า Backend รันอยู่...
timeout /t 1 /nobreak >nul

curl -s %BACKEND_URL:alerts=health% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ ERROR: Backend ไม่ตอบสนอง ที่ %BACKEND_URL%
    echo 📌 ต้องรัน: uvicorn backend_main:app --host 0.0.0.0 --port 8000
    pause
    exit /b 1
)
echo ✓ Backend พร้อม

echo.
echo [2/4] ตรวจสอบ Dashboard...
timeout /t 1 /nobreak >nul

curl -s %DASHBOARD_URL% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ ERROR: Dashboard ไม่เปิด
) else (
    echo ✓ Dashboard เปิด → %DASHBOARD_URL%
)

echo.
echo [3/4] ยิง Test Alerts...
echo.

REM Test 1: Pat3.2 BUY
echo.
echo 📤 Test 1: Pat3.2 BUY @ 3200.50
echo.
curl -X POST %BACKEND_URL% ^
  -H "Content-Type: application/json" ^
  -d "{\"pattern\":\"Pat3.2\",\"direction\":\"BUY\",\"entry_price\":3200.50,\"grid\":3200.00,\"sl\":3199.50,\"tp\":3203.50,\"symbol\":\"XAUUSDm\",\"timestamp\":\"2026-06-22 10:30:00\",\"tf\":\"M5\"}"

echo.
timeout /t 2 /nobreak >nul

REM Test 2: Pat3.3 SELL
echo.
echo 📤 Test 2: Pat3.3 SELL @ 3205.25
echo.
curl -X POST %BACKEND_URL% ^
  -H "Content-Type: application/json" ^
  -d "{\"pattern\":\"Pat3.3\",\"direction\":\"SELL\",\"entry_price\":3205.25,\"grid\":3205.00,\"sl\":3205.75,\"tp\":3203.00,\"symbol\":\"XAUUSDm\",\"timestamp\":\"2026-06-22 10:35:00\",\"tf\":\"M5\"}"

echo.
timeout /t 2 /nobreak >nul

REM Test 3: Pat2 BUY
echo.
echo 📤 Test 3: Pat2 BUY @ 3195.80
echo.
curl -X POST %BACKEND_URL% ^
  -H "Content-Type: application/json" ^
  -d "{\"pattern\":\"Pat2\",\"direction\":\"BUY\",\"entry_price\":3195.80,\"grid\":3195.00,\"sl\":3195.30,\"tp\":3196.80,\"symbol\":\"XAUUSDm\",\"timestamp\":\"2026-06-22 10:40:00\",\"tf\":\"M5\"}"

echo.
timeout /t 2 /nobreak >nul

REM Test 4: Pat1 SELL (LOW-EDGE)
echo.
echo 📤 Test 4: Pat1 SELL @ 3210.40 [LOW-EDGE]
echo.
curl -X POST %BACKEND_URL% ^
  -H "Content-Type: application/json" ^
  -d "{\"pattern\":\"Pat1\",\"direction\":\"SELL\",\"entry_price\":3210.40,\"grid\":3210.00,\"sl\":3211.00,\"tp\":3209.00,\"symbol\":\"XAUUSDm\",\"timestamp\":\"2026-06-22 10:45:00\",\"tf\":\"M5\"}"

echo.
echo.
echo [4/4] ตรวจสอบผล
echo.
echo ✓ Test ส่งเสร็จแล้ว
echo.
echo 📊 ไปดู Dashboard → %DASHBOARD_URL%
echo 🔔 ดูกล่อง ALERTS section
echo.
echo ═══════════════════════════════════════════════════════════════════════════
pause
