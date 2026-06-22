╔════════════════════════════════════════════════════════════╗
║                                                            ║
║  💎 DIAMOND TRADER — LOCAL TEST PACKAGE                  ║
║  Real-time WebSocket Integration Testing                 ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝

FILES IN THIS PACKAGE:
══════════════════════════════════════════════════════════════

📄 LOCAL_TEST_STEPS.md ............... Step-by-step guide (START HERE)
📄 LOCAL_TEST_GUIDE.md ............... Detailed reference
📄 DEPLOY_GUIDE_RAILWAY.md ........... Deploy to production after testing

🔧 SCRIPTS:
  setup_local.sh (macOS/Linux) ....... Install dependencies + show next steps
  test_alert.sh (macOS/Linux) ....... Send 4 test alerts to backend
  test_alert.bat (Windows) .......... Send 4 test alerts to backend

💻 CODE FILES:
  backend_main.py .................... FastAPI WebSocket server
  backend_requirements.txt ........... Python dependencies
  diamond_trader_dashboard_live.html . Real-time dashboard with WebSocket

📊 SYSTEM FLOW:
  TradingView Alert
      ↓
  Backend (localhost:8000)
      ↓ WebSocket
  Browser Dashboard (updates live)


QUICK START (5 minutes):
══════════════════════════════════════════════════════════════

1. Install dependencies:
   $ pip install -r backend_requirements.txt

2. Start backend (Terminal A):
   $ python backend_main.py
   → You should see: "Uvicorn running on http://127.0.0.1:8000"

3. Open dashboard (Browser):
   → Open: diamond_trader_dashboard_live.html
   → Check topbar: should show 🟢 LIVE (green dot)

4. Send test alert (Terminal B):
   macOS/Linux:  bash test_alert.sh
   Windows:      test_alert.bat
   OR manual:    curl -X POST http://localhost:8000/webhook ...

5. Verify in browser:
   ✓ New row in Alert Log
   ✓ Execution card updated
   ✓ Console (F12) shows "🔔 Alert: ..."


REQUIREMENTS:
══════════════════════════════════════════════════════════════

✓ Python 3.8+
✓ pip
✓ Modern web browser (Chrome/Firefox/Safari)
✓ curl or PowerShell (for sending test alerts)

No database setup needed - SQLite auto-creates on first alert.


EXPECTED RESULTS:
══════════════════════════════════════════════════════════════

✓ Backend starts without errors
✓ Browser shows "LIVE" connection status
✓ Test alerts appear in log within 1 second
✓ Execution card values update
✓ Browser console shows alert notifications
✓ SQLite database stores alerts

If ALL pass → Ready for Railway deployment!


TROUBLESHOOTING:
══════════════════════════════════════════════════════════════

Q: "Connection refused"
A: Make sure backend is running in Terminal A

Q: Dashboard shows "OFFLINE"
A: Check browser console (F12). Backend must be on port 8000

Q: curl command not found (Windows)
A: Install from https://curl.se/download.html

Q: No alerts in dashboard
A: Check X-Secret header matches "diamond2026" (case-sensitive)


NEXT STEPS AFTER TESTING:
══════════════════════════════════════════════════════════════

1. If all tests PASS:
   → Read DEPLOY_GUIDE_RAILWAY.md
   → Deploy backend to Railway (free tier)
   → Update WebSocket URL in dashboard
   → Setup TradingView webhook

2. If any tests FAIL:
   → Check LOCAL_TEST_STEPS.md troubleshooting section
   → Review browser console + backend logs
   → Re-run test_alert script


SUPPORT:
══════════════════════════════════════════════════════════════

FastAPI Docs: https://fastapi.tiangolo.com
WebSocket: https://fastapi.tiangolo.com/advanced/websockets/
Railway: https://docs.railway.app
TradingView Alerts: https://www.tradingview.com/chart/docs/webhooks/


═══════════════════════════════════════════════════════════════
Ready? Open LOCAL_TEST_STEPS.md and follow along!
═══════════════════════════════════════════════════════════════
