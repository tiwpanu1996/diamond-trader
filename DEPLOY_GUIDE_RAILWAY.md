# 🚀 DIAMOND TRADER — Railway Deployment Guide

**Deploy FastAPI Backend + WebSocket Server to Railway (Free Tier)**

---

## 📋 Requirements

- [Railway.app](https://railway.app) account (free)
- Git installed
- Terminal / Command Prompt
- TradingView Account (for webhook setup)

---

## 🔑 Step 1: Create Railway Project

### 1.1 Login to Railway
```bash
railway login
```
Browser opens → Authenticate with GitHub/Email

### 1.2 Initialize Project
```bash
cd /path/to/your/diamond_trader_backend
railway init
```

**Follow prompts:**
- Project name: `DIAMOND TRADER`
- Environment: `production`

### 1.3 Verify Connection
```bash
railway status
```

Expected output:
```
✓ Connected to Railway
 Project: DIAMOND TRADER
 Environment: production
```

---

## 📦 Step 2: Prepare Files

### 2.1 Directory Structure
```
diamond_trader_backend/
├── backend_main.py              (main FastAPI app)
├── backend_requirements.txt      (Python dependencies)
├── Procfile                      (Railway runtime config)
└── runtime.txt                   (Python version)
```

### 2.2 Create Procfile (for Railway)
```bash
cat > Procfile << 'EOF'
web: uvicorn backend_main:app --host 0.0.0.0 --port $PORT
EOF
```

### 2.3 Create runtime.txt
```bash
cat > runtime.txt << 'EOF'
python-3.11.8
EOF
```

### 2.4 Verify backend_requirements.txt
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
aiofiles==24.1.0
```

---

## 🔐 Step 3: Environment Variables

### 3.1 Set Secret on Railway
```bash
railway variable add WEBHOOK_SECRET=diamond2026
```

### 3.2 Set Port (auto-detected, but verify)
```bash
railway variable list
```

Should include:
- `PORT=8000` (auto-set by Railway)
- `WEBHOOK_SECRET=diamond2026`

---

## 🚢 Step 4: Deploy

### 4.1 Push to Railway
```bash
git add .
git commit -m "🚀 Deploy DIAMOND TRADER backend"
railway up
```

Railway automatically:
- Installs dependencies from `backend_requirements.txt`
- Runs `Procfile` (uvicorn server)
- Assigns public URL (e.g., `https://diamond-trader-prod.up.railway.app`)

### 4.2 Monitor Deployment
```bash
railway logs
```

Look for:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

✅ **Backend is LIVE!**

### 4.3 Get Public URL
```bash
railway domain
```

Returns:
```
https://diamond-trader-prod.up.railway.app
```

---

## 🔗 Step 5: Update Dashboard URL

### 5.1 Edit dashboard_live.html
Find line:
```javascript
const BACKEND_URL = "ws://localhost:8000/ws"
```

Replace with:
```javascript
const BACKEND_URL = "wss://diamond-trader-prod.up.railway.app/ws"
```

(Change `ws://` to `wss://` for HTTPS security)

### 5.2 Deploy Dashboard
- **Option A:** Upload to Vercel / Netlify
- **Option B:** Host on simple web server
- **Option C:** Embed in Canva Doc (if Canva supports external iframes)

---

## 🎯 Step 6: TradingView Alert Setup

### 6.1 Create Alert on Chart
```
Pine Script Alert Trigger:
  alertcondition(buyPat33, "▲ Pat3.3 BUY", "...")
```

### 6.2 Configure Webhook
1. Right-click chart → Alert
2. Condition: Select any of the 12 alertconditions
3. Notification: **Webhook**
4. URL: `https://diamond-trader-prod.up.railway.app/webhook`
5. Message:
```json
{
  "symbol": "{{ticker}}",
  "tf": "{{interval}}",
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
}
```

6. Add custom header:
```
X-Secret: diamond2026
```

### 6.3 Test
1. Wait for next M5 candle close (if on M5 TF)
2. Check TradingView alert history
3. Check backend logs: `railway logs`
4. Watch dashboard for real-time update

---

## 🔍 Verification

### 7.1 Test Webhook Endpoint
```bash
curl -X POST https://diamond-trader-prod.up.railway.app/webhook \
  -H "Content-Type: application/json" \
  -H "X-Secret: diamond2026" \
  -d '{
    "symbol": "XAUUSDm",
    "tf": "M5",
    "pat": "Pat3.2 BUY",
    "side": 1,
    "verdict": "READY"
  }'
```

Expected response:
```json
{"ok": true, "ts": "2026-06-22T19:35:00.123456"}
```

### 7.2 Test WebSocket Connection
Open browser console on dashboard:
```javascript
// In Console tab (F12):
console.log(ws.readyState)  // 1 = OPEN, 0 = CONNECTING
```

Should return: `1` (connected)

### 7.3 Test Health Endpoint
```bash
curl https://diamond-trader-prod.up.railway.app/health
```

Expected:
```json
{"status": "ok", "total_alerts": 0}
```

### 7.4 Fetch Alert History
```bash
curl https://diamond-trader-prod.up.railway.app/alerts?limit=5
```

Returns JSON array of recent alerts (test only if you've sent some)

---

## 💾 Database & Persistence

### 8.1 SQLite on Railway
- Database file: `diamond_trader.db`
- Stored in container filesystem
- **⚠️ WARNING:** Data persists only until container restart
- For production: Upgrade to PostgreSQL add-on

### 8.2 PostgreSQL (Optional)
To add database persistence:
```bash
railway add postgres
railway variable add DATABASE_URL  # Auto-linked
```

Then update `backend_main.py` to use PostgreSQL instead of SQLite.

---

## 🆘 Troubleshooting

| Error | Solution |
|-------|----------|
| **"Deployment failed"** | Check `railway logs` for error messages; verify `Procfile` and `runtime.txt` exist |
| **"ModuleNotFoundError"** | Verify all imports in `backend_main.py` are in `backend_requirements.txt` |
| **"Connection refused" in browser** | Verify WebSocket URL is correct: `wss://YOUR-APP.up.railway.app/ws` (with `s`) |
| **Webhook returns 403** | Check `X-Secret` header matches `WEBHOOK_SECRET` in Railway variables |
| **No data in `/alerts` endpoint** | Send a test alert first via curl or TradingView |

---

## 📊 Monitoring

### 9.1 View Logs
```bash
railway logs -f  # Follow mode (live)
```

### 9.2 Monitor CPU/Memory
```bash
railway metrics
```

### 9.3 Check Uptime
```bash
curl https://diamond-trader-prod.up.railway.app/health
```

Should return within 1 second.

---

## 🔄 Updates & Redeployment

### 10.1 After Code Changes
```bash
git add .
git commit -m "fix: update alert handler"
railway up
```

Railway auto-redeploys.

### 10.2 Rollback
```bash
railway rollback
```

Reverts to previous deployment.

---

## 💡 Pro Tips

1. **Free Tier Limits**
   - 500 hours/month compute
   - Sufficient for 24/7 trading (720 hours/month requires paid plan)
   - No data transfer limits

2. **Cost Estimate**
   - Free: $0/month (fits within free tier)
   - Paid: $5/month + overage

3. **Scaling**
   - If needed: Railway auto-scales horizontally (multi-instance)
   - Enable under "Project Settings → Scaling"

4. **Backups**
   - Create daily export: `railway exec sqlite3 diamond_trader.db .dump > backup.sql`
   - Store backup in GitHub

---

## 📝 Checklist

- [ ] Railway account created
- [ ] `Procfile` and `runtime.txt` in directory
- [ ] `railway init` completed
- [ ] `WEBHOOK_SECRET=diamond2026` set
- [ ] `railway up` deployed successfully
- [ ] Public URL obtained
- [ ] Dashboard URL updated to `wss://YOUR-APP.up.railway.app/ws`
- [ ] TradingView webhook configured
- [ ] Curl test successful
- [ ] Browser WebSocket status: LIVE
- [ ] Test alert delivered and logged

---

## 🎯 Next Steps

1. Monitor backend logs for 24 hours
2. Test with real TradingView alerts
3. Track alert latency (should be <1 second)
4. Scale database if needed (PostgreSQL)
5. Set up automated backups

---

**Deployment Date:** _______  
**Railway URL:** `https://_____.up.railway.app`  
**Status:** ☐ LIVE ☐ TESTING ☐ FAILED  

---

**Support:**
- Railway Docs: https://docs.railway.app
- FastAPI Docs: https://fastapi.tiangolo.com
- TradingView Webhook: https://www.tradingview.com/chart/docs/webhooks/
