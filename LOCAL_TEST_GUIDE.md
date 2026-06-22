# 💎 DIAMOND TRADER — Local Testing Guide

**Goal:** ทดสอบ WebSocket connection ระหว่าง TradingView Alert → Backend → Dashboard (local machine)

---

## 📋 Checklist

- [ ] Python 3.8+ installed
- [ ] pip พร้อมใช้
- [ ] Terminal / Command Prompt
- [ ] Web browser (Chrome/Firefox/Safari)

---

## 🚀 Step 1: Setup Backend (Local)

### 1.1 Install Dependencies
```bash
cd /path/to/your/project
pip install -r backend_requirements.txt
```

**Expected output:**
```
Successfully installed fastapi==0.115.0 uvicorn[standard]==0.30.6 aiofiles==24.1.0
```

### 1.2 Start Backend Server
```bash
python backend_main.py
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

✅ **Backend is LIVE at `http://localhost:8000`**

---

## 🌐 Step 2: Open Dashboard

### 2.1 Open HTML File
```bash
# Option A: Open in browser directly
open diamond_trader_dashboard_live.html

# Option B: Use simple HTTP server (better for cross-origin testing)
python -m http.server 8001
# Then visit: http://localhost:8001/diamond_trader_dashboard_live.html
```

**Expected behavior:**
- Dashboard loads
- "CONNECTING..." turns to "LIVE" (green dot)
- 6-TF grid shows demo candles

---

## 📤 Step 3: Send Test Alert

### 3.1 Using curl (Terminal)

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
    "grid": 3200,
    "entry": 3201.5,
    "sl": 3198.5,
    "tp": 3210.5,
    "regime": "TRENDING",
    "sideway": "NONE"
  }'
```

**Expected response:**
```json
{"ok": true, "ts": "2026-06-22T19:35:00.123456"}
```

### 3.2 Check Dashboard

Watch for:
- ✅ New row in "Alert Log" (top row)
- ✅ Entry/SL/TP updated in "Execution" card
- ✅ Price display updated to 3201.50

---

## 🔍 Step 4: Verify Connection

### 4.1 Check WebSocket Status

**Terminal (backend):**
```
INFO:     connection open
WebSocket connected, sending history...
Broadcast alert to 1 client
```

**Browser Console (F12 → Console tab):**
```
✓ Connected to DIAMOND TRADER
📊 History loaded: 4
🔔 Alert: Pat3.2 BUY
```

### 4.2 REST Endpoint Test

```bash
curl http://localhost:8000/alerts?limit=10
```

**Expected output:** JSON array of recent alerts

```bash
curl http://localhost:8000/health
```

**Expected output:**
```json
{"status": "ok", "total_alerts": 1}
```

---

## 🔴 Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Connection refused"** | Verify backend is running (`python backend_main.py`) on port 8000 |
| **Dashboard says "OFFLINE"** | Check browser console (F12) for WebSocket errors; verify `BACKEND_URL = "ws://localhost:8000/ws"` |
| **"Forbidden" on webhook** | Verify header: `X-Secret: diamond2026` matches `WEBHOOK_SECRET` in code |
| **No alerts in log** | Check browser console for errors; try curl test first |
| **Candles not rendering** | Refresh page (F5) and wait 1 second |

---

## 📝 Alert Payload Reference

**Minimal alert (required fields):**
```json
{
  "symbol": "XAUUSDm",
  "tf": "M5",
  "pat": "Pat3.2 BUY",
  "side": 1,
  "verdict": "READY"
}
```

**Full alert (all fields):**
```json
{
  "symbol": "XAUUSDm",
  "tf": "M5",
  "pat": "Pat3.2 BUY",
  "side": 1,
  "verdict": "READY",
  "ovl": 150,
  "cf_count": 3,
  "spread": 160,
  "grid": 3200.00,
  "entry": 3201.50,
  "sl": 3198.50,
  "tp": 3210.50,
  "regime": "TRENDING",
  "sideway": "NONE"
}
```

**Field mappings:**
- `side`: 1 = BUY, -1 = SELL, 0 = none
- `verdict`: "READY" | "WAIT" | "NO-TRADE"
- `tf`: "M5" | "M15" | "M30" | "H1" | "H4" | "D1"
- `pat`: "Pat3.3 BUY" | "Pat3.2 BUY" | "Pat3.1 BUY" | "Pat2 BUY" | "Pat1 BUY" (+ SELL variants)

---

## 🎯 Full Test Scenario

**Time: ~5 minutes**

1. **Start backend** (Terminal A)
   ```bash
   python backend_main.py
   ```

2. **Open dashboard** (Browser)
   ```
   http://localhost:8001/diamond_trader_dashboard_live.html
   ```
   Verify: Green dot + "LIVE"

3. **Send BUY alert** (Terminal B)
   ```bash
   curl -X POST http://localhost:8000/webhook \
     -H "Content-Type: application/json" \
     -H "X-Secret: diamond2026" \
     -d '{...Pat3.2 BUY...}'
   ```
   Verify: Alert appears in log + execution card updates

4. **Send SELL alert** (Terminal B)
   ```bash
   curl -X POST http://localhost:8000/webhook \
     -H "Content-Type: application/json" \
     -H "X-Secret: diamond2026" \
     -d '{...Pat3.3 SELL...}'
   ```
   Verify: New alert in log, verdict changes

5. **Check DB**
   ```bash
   sqlite3 diamond_trader.db "SELECT COUNT(*) FROM alerts;"
   ```
   Should return: 2

---

## 📱 Next: TradingView Integration

Once local testing passes:

1. **Get your public IP or ngrok tunnel**
   ```bash
   ngrok http 8000
   ```
   → Get URL like `https://abc123.ngrok.io`

2. **Update TradingView webhook**
   - Chart → Alert → Webhook URL: `https://abc123.ngrok.io/webhook`
   - Header: `X-Secret: diamond2026`
   - Message: Use payload from section above

3. **Test with real Pine Script alerts**
   - Pan chart to new candle
   - Wait for alert trigger
   - Check dashboard live update

---

## 🚢 Ready to Deploy?

Once local testing confirms:
- ✅ WebSocket connects
- ✅ Alerts received
- ✅ Dashboard updates real-time

→ **Next step:** Deploy to Railway (see `DEPLOY_GUIDE.md`)

---

**Test Date:** _______  
**Status:** ☐ PASS ☐ FAIL  
**Notes:** ________________________________
