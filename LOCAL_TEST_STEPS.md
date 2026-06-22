# 💎 DIAMOND TRADER — Local Test Execution

**Time: ~10 minutes**  
**Goal:** Verify WebSocket connection + real-time alert updates

---

## 📋 Pre-Flight Checklist

- [ ] Python 3.8+ installed (`python --version`)
- [ ] pip installed (`pip --version`)
- [ ] Modern browser (Chrome/Firefox/Safari)
- [ ] Files downloaded:
  - ✓ `backend_main.py`
  - ✓ `backend_requirements.txt`
  - ✓ `diamond_trader_dashboard_live.html`
  - ✓ `test_alert.sh` (macOS/Linux) OR `test_alert.bat` (Windows)

---

## 🚀 PHASE 1: Install Dependencies (3 min)

### macOS / Linux
```bash
cd /path/to/diamond_trader

# Install requirements
pip install -r backend_requirements.txt

# Verify installation
python -c "import fastapi; print('✓ FastAPI OK')"
```

### Windows (Command Prompt / PowerShell)
```cmd
cd C:\path\to\diamond_trader

# Install requirements
pip install -r backend_requirements.txt

# Verify installation
python -c "import fastapi; print('✓ FastAPI OK')"
```

**Expected output:**
```
Successfully installed fastapi-0.115.0 uvicorn-0.30.6 aiofiles-24.1.0
✓ FastAPI OK
```

---

## 🔌 PHASE 2: Start Backend (1 min)

### Open Terminal A
```bash
cd /path/to/diamond_trader
python backend_main.py
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

✅ **Backend is LIVE**

Leave this terminal running (do NOT close it).

---

## 🌐 PHASE 3: Open Dashboard (1 min)

### Open New Browser Tab

**Option A: Direct file (safest)**
```
Drag & drop: diamond_trader_dashboard_live.html → Browser
OR
File → Open File → Select diamond_trader_dashboard_live.html
```

**Option B: HTTP Server (if direct fails)**
```bash
# Terminal B
cd /path/to/diamond_trader
python -m http.server 8001

# Then visit:
http://localhost:8001/diamond_trader_dashboard_live.html
```

**Check browser console** (Press F12 → Console tab):
```
✓ Connected to DIAMOND TRADER
📊 History loaded: 0
```

✅ **Green dot in topbar** = LIVE

---

## 📤 PHASE 4: Send Test Alerts (3 min)

### Option A: Use script (easiest)

#### macOS / Linux
```bash
# Terminal C
cd /path/to/diamond_trader
bash test_alert.sh
```

#### Windows
```cmd
# Command Prompt
cd C:\path\to\diamond_trader
test_alert.bat
```

### Option B: Manual curl (if script fails)

#### Send Test Alert #1: Pat3.2 BUY
```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Secret: diamond2026" \
  -d '{
    "symbol": "XAUUSDm",
    "tf": "M5",
    "pat": "Pat3.2 BUY",
    "side": 1,
    "verdict": "READY",
    "ovl": 150,
    "cf_count": 3,
    "spread": 160,
    "grid": 3200.0,
    "entry": 3201.5,
    "sl": 3198.5,
    "tp": 3210.5,
    "regime": "TRENDING"
  }'
```

**Expected response:**
```json
{"ok": true, "ts": "2026-06-22T19:35:12.123456"}
```

#### Send Test Alert #2: Pat3.3 SELL
```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Secret: diamond2026" \
  -d '{
    "symbol": "XAUUSDm",
    "tf": "M5",
    "pat": "Pat3.3 SELL",
    "side": -1,
    "verdict": "READY",
    "ovl": 150,
    "cf_count": 3,
    "spread": 160,
    "grid": 3200.0,
    "entry": 3198.5,
    "sl": 3201.5,
    "tp": 3189.5,
    "regime": "TRENDING"
  }'
```

---

## ✅ PHASE 5: Verify Results (2 min)

### Watch Dashboard

After sending each alert, check:

**Alert Log (bottom right):**
```
19:35  ▲ Pat3.2 BUY  READY
19:35  ▼ Pat3.3 SELL READY
```

**Execution Card (middle right):**
```
ENTRY:    3,201.50  (changed from 3,200.00)
SL:       3,198.50
TP (1:3): 3,210.50
```

**Browser Console (F12):**
```
✓ Connected to DIAMOND TRADER
📊 History loaded: 0
🔔 Alert: Pat3.2 BUY
🔔 Alert: Pat3.3 SELL
```

### Check Backend Logs (Terminal A)

You should see:
```
INFO:     connection open
Broadcast alert to 1 client
```

### Query Database

**Terminal B (new):**
```bash
sqlite3 diamond_trader.db "SELECT ts, pat, verdict FROM alerts ORDER BY id DESC LIMIT 5;"
```

**Expected output:**
```
2026-06-22T19:35:12.123456|Pat3.3 SELL|READY
2026-06-22T19:35:08.987654|Pat3.2 BUY|READY
```

---

## 🎯 Test Verdict

| Item | Expected | Result |
|------|----------|--------|
| **Browser connection** | Green dot "LIVE" | ☐ PASS ☐ FAIL |
| **Alert appears in log** | New row within 1 sec | ☐ PASS ☐ FAIL |
| **Execution card updates** | Entry/SL/TP change | ☐ PASS ☐ FAIL |
| **Browser console** | Shows `🔔 Alert: ...` | ☐ PASS ☐ FAIL |
| **Backend logs** | Shows `Broadcast alert` | ☐ PASS ☐ FAIL |
| **Database saved** | Alerts in `diamond_trader.db` | ☐ PASS ☐ FAIL |

---

## 🔴 Troubleshooting

### ❌ "Backend not responding"
**Problem:** Connection refused on port 8000

**Solution:**
1. Check Terminal A is still running: `python backend_main.py`
2. Kill any existing process on port 8000:
   ```bash
   # macOS/Linux
   lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9
   
   # Windows
   netstat -ano | findstr :8000
   taskkill /PID <PID> /F
   ```
3. Start backend again

---

### ❌ Dashboard says "OFFLINE" (red dot)
**Problem:** WebSocket not connecting

**Solution:**
1. Open browser **DevTools** (F12)
2. Go to **Console** tab
3. Look for error messages like:
   ```
   WebSocket is closed before the connection is established
   ```
4. Check that backend is running in Terminal A
5. Refresh page (F5)

---

### ❌ curl: command not found
**Problem:** curl not installed (usually Windows)

**Solution:**
1. Install curl from: https://curl.se/download.html
2. OR use PowerShell instead:
   ```powershell
   $body = @{...} | ConvertTo-Json
   Invoke-WebRequest -Uri "http://localhost:8000/webhook" `
     -Method Post `
     -Headers @{"X-Secret"="diamond2026"} `
     -Body $body
   ```

---

### ❌ No alerts in dashboard after curl
**Problem:** Alert sent but not received

**Solution:**
1. Check response from curl: did it return `{"ok": true}`?
2. Check X-Secret header matches: `diamond2026` (case-sensitive)
3. Check backend logs for errors
4. Try different field values (esp. `side`: use `1` not `"BUY"`)

---

### ❌ Database file not created
**Solution:** Database is created on first alert. If you don't see `diamond_trader.db`:
1. Verify curl returned `{"ok": true}`
2. Check backend logs
3. Try manual query:
   ```bash
   sqlite3 diamond_trader.db ".tables"
   # Should return: alerts
   ```

---

## 📊 What Happens Next

**If ALL tests PASS:**
1. Stop backend (Ctrl+C in Terminal A)
2. Move to **PHASE B: Deploy to Railway** (or proceed to Phase C features)
3. Update WebSocket URL from `ws://localhost:8000/ws` → `wss://your-app.up.railway.app/ws`
4. Set up TradingView alert webhook

**If ANY test FAILS:**
1. Check troubleshooting section above
2. Verify all 3 files are in same directory
3. Review error messages in Terminal A (backend logs)
4. Check browser console (F12 → Console)

---

## 💡 Tips

1. **Don't kill browser tabs** — WebSocket connection stays open
2. **Keep backend running** — Leave Terminal A open during entire test
3. **One alert at a time** — Wait 1 second between curl commands
4. **Check timestamps** — Alert `ts` in browser should match curl response
5. **Clear browser cache** (Cmd+Shift+R / Ctrl+Shift+R) if layout looks wrong

---

## ✨ Success Indicators

When everything works:

```
✓ Browser shows "LIVE" (green dot)
✓ New alerts appear in log instantly (<1 second)
✓ Execution card updates live
✓ Browser console shows: "🔔 Alert: Pat3.2 BUY"
✓ Backend logs show: "Broadcast alert to 1 client"
✓ SQLite database has alert entries
```

---

## 📝 Test Session Log

```
Date: ____________
Start time: ____________
Browser: ____________
OS: ____________

Terminal A (Backend):
  Start time: ______
  Any errors? NO / YES (describe: ___________________)

Terminal B/C (curl):
  Test 1 response: ✓ / ✗
  Test 2 response: ✓ / ✗
  Test 3 response: ✓ / ✗
  Test 4 response: ✓ / ✗

Browser Dashboard:
  "LIVE" status: ✓ / ✗
  Alerts visible: ✓ / ✗
  Execution card updated: ✓ / ✗
  Console no errors: ✓ / ✗

Database Check:
  diamond_trader.db exists: ✓ / ✗
  Alerts saved: ✓ / ✗ (count: ___)

OVERALL RESULT: ☐ PASS ☐ FAIL

Notes:
_____________________________________________________
_____________________________________________________
```

---

**Questions? Check:**
- `LOCAL_TEST_GUIDE.md` — Detailed reference
- Browser DevTools (F12) — Console + Network tabs
- Backend terminal — Error messages

Good luck! 🚀

