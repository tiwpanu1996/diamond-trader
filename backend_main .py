"""
DIAMOND TRADER — backend_main.py v2.1
FastAPI Backend + Dashboard (inline HTML)
SSOT: PA_SPEC_MASTER_v2.1 + SNIPER_HUD_BIBLE_v1.1

Endpoints:
  GET  /           → Dashboard HTML
  GET  /health     → Health check
  GET  /price      → Binance PAXG price proxy
  GET  /candles/{interval} → 5-candle OHLC proxy
  POST /alerts     → TradingView webhook (PA Signal + CF_UPDATE)
  GET  /alerts     → Alert history (SQLite)
  GET  /cf-status  → Live CF M5 state

Deploy: Railway (HTTP polling, no WebSocket on free plan)
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import sqlite3
import json
import os
import httpx

# ── Config ───────────────────────────────────────────────────────
DB_PATH       = os.getenv("DB_PATH", "diamond_trader.db")
BINANCE_BASE  = "https://api.binance.com/api/v3"
PAXG_SYMBOL   = "PAXGUSDT"

# ── CF M5 State (in-memory, resets on restart) ───────────────────
cf_state: dict = {
    "cf_count":   0,
    "cf_pass":    False,
    "cf_dir":     "neutral",
    "cf_status":  "WAIT",
    "grid_level": 0.0,
    "close":      0.0,
    "ticker":     "",
    "updated_at": None,
}

# ── Database ─────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ticker    TEXT,
            interval  TEXT,
            pattern   TEXT,
            direction TEXT,
            price     REAL,
            verdict   TEXT,
            raw       TEXT
        )
    """)
    conn.commit()
    conn.close()

def _cf_display(count: int, passed: bool, direction: str) -> str:
    d = "BUY" if direction == "buy" else "SELL" if direction == "sell" else "—"
    if count == 0: return "— 0/3"
    if passed:     return f"✓ {d} 3/3 READY"
    return f"⏳ {d} {count}/3"

# ── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="DIAMOND TRADER", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Dashboard HTML ────────────────────────────────────────────────
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DIAMOND TRADER</title>
<style>
  :root {
    --bg:        #0b1120;
    --surface:   #131e35;
    --border:    #1e2d4a;
    --gold:      #f5a623;
    --green:     #22c55e;
    --red:       #ef4444;
    --yellow:    #f59e0b;
    --gray:      #64748b;
    --text:      #e2e8f0;
    --subtext:   #94a3b8;
    --ready:     #22c55e;
    --wait:      #f59e0b;
    --notrade:   #ef4444;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 13px;
    min-height: 100vh;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 18px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  .logo {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: .12em;
    color: var(--gold);
  }
  .logo span { color: var(--subtext); font-weight: 400; font-size: 11px; margin-left: 8px; }
  .live-price {
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: .04em;
  }
  .live-price small { font-size: 11px; color: var(--subtext); margin-left: 4px; }
  .conn-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--gray);
    display: inline-block;
    margin-right: 5px;
    transition: background .3s;
  }
  .conn-dot.live { background: var(--green); box-shadow: 0 0 6px var(--green); }

  /* ── TF Grid ── */
  #tf-grid {
    display: grid;
    grid-template-columns: repeat(9, 1fr);
    gap: 6px;
    padding: 10px 12px 6px;
  }
  .tf-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 7px 6px 5px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .tf-label {
    font-size: 10px;
    color: var(--gold);
    font-weight: 700;
    letter-spacing: .08em;
  }
  .tf-bias {
    font-size: 10px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    align-self: flex-start;
  }
  .tf-bias.bull { background: rgba(34,197,94,.18); color: var(--green); }
  .tf-bias.bear { background: rgba(239,68,68,.18);  color: var(--red); }
  .tf-bias.neut { background: rgba(100,116,139,.18); color: var(--gray); }
  .tf-pattern {
    font-size: 9px;
    color: var(--subtext);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tf-pattern.buy  { color: var(--green); }
  .tf-pattern.sell { color: var(--red); }
  canvas.mini-chart {
    width: 100%;
    height: 40px;
    display: block;
    margin-top: 2px;
  }

  /* ── Filter Bar ── */
  #filter-bar {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    padding: 6px 12px;
  }
  .filter-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
  }
  .filter-card .fc-label {
    font-size: 9px;
    color: var(--subtext);
    letter-spacing: .1em;
    text-transform: uppercase;
    margin-bottom: 5px;
  }
  .fc-value {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: .04em;
    line-height: 1.2;
  }
  .fc-sub { font-size: 10px; color: var(--subtext); margin-top: 3px; }

  .fc-value.ready    { color: var(--ready); }
  .fc-value.wait     { color: var(--wait); }
  .fc-value.notrade  { color: var(--notrade); }
  .fc-value.neutral  { color: var(--gray); }

  /* OVL bar */
  .ovl-bar-bg {
    width: 100%;
    height: 5px;
    background: var(--border);
    border-radius: 3px;
    margin-top: 6px;
    overflow: hidden;
  }
  .ovl-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width .4s, background .4s;
  }

  /* ── Alert Log ── */
  #alert-log {
    margin: 6px 12px 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }
  .log-header {
    padding: 8px 12px;
    font-size: 10px;
    color: var(--subtext);
    letter-spacing: .1em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .log-header .sound-btn {
    cursor: pointer;
    font-size: 13px;
    background: none;
    border: none;
    color: var(--subtext);
    padding: 0 4px;
  }
  .log-header .sound-btn.on { color: var(--gold); }
  table.alert-table {
    width: 100%;
    border-collapse: collapse;
  }
  table.alert-table th {
    font-size: 9px;
    color: var(--subtext);
    text-align: left;
    padding: 5px 12px;
    border-bottom: 1px solid var(--border);
    letter-spacing: .06em;
    text-transform: uppercase;
  }
  table.alert-table td {
    padding: 6px 12px;
    font-size: 11px;
    border-bottom: 1px solid rgba(30,45,74,.5);
  }
  table.alert-table tr:last-child td { border-bottom: none; }
  .alert-dir.buy  { color: var(--green); font-weight: 700; }
  .alert-dir.sell { color: var(--red);   font-weight: 700; }
  .alert-verdict.ready   { color: var(--ready); }
  .alert-verdict.wait    { color: var(--wait); }
  .alert-verdict.notrade { color: var(--notrade); }
  .no-alerts { padding: 16px; text-align: center; color: var(--gray); font-size: 11px; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
</head>
<body>

<!-- ── Header ── -->
<header>
  <div class="logo">◆ DIAMOND TRADER <span>v2.1 · XAUUSDm · Exness GMT+0</span></div>
  <div class="live-price" id="live-price">— <small>USD</small></div>
  <div style="display:flex;align-items:center;gap:6px;">
    <span class="conn-dot" id="conn-dot"></span>
    <span id="conn-label" style="font-size:10px;color:var(--subtext)">connecting…</span>
  </div>
</header>

<!-- ── TF Grid (9 panels) ── -->
<section id="tf-grid">
  <!-- generated by JS -->
</section>

<!-- ── Filter Bar ── -->
<section id="filter-bar">

  <!-- CF M5 -->
  <div class="filter-card">
    <div class="fc-label">CF M5 Counter</div>
    <div class="fc-value neutral" id="cf-value">— 0/3</div>
    <div class="fc-sub" id="cf-grid-lv">Grid: —</div>
    <div class="fc-sub" id="cf-updated">—</div>
  </div>

  <!-- Grid OVL -->
  <div class="filter-card">
    <div class="fc-label">Grid OVL Meter</div>
    <div class="fc-value neutral" id="ovl-value">—</div>
    <div class="ovl-bar-bg">
      <div class="ovl-bar-fill" id="ovl-bar" style="width:0%;background:var(--gray)"></div>
    </div>
    <div class="fc-sub" id="ovl-grid">Grid: —</div>
  </div>

  <!-- Sideway -->
  <div class="filter-card">
    <div class="fc-label">Sideway Detector</div>
    <div class="fc-value neutral" id="sw-value">—</div>
    <div class="fc-sub" id="sw-sub">รอสัญญาณจาก Pine</div>
  </div>

  <!-- MTF Confluence -->
  <div class="filter-card">
    <div class="fc-label">MTF Confluence</div>
    <div class="fc-value neutral" id="mtf-value">—</div>
    <div class="fc-sub" id="mtf-sub">Bull 0 / Bear 0</div>
  </div>

</section>

<!-- ── Alert Log ── -->
<section id="alert-log">
  <div class="log-header">
    <span>Recent Alerts</span>
    <button class="sound-btn" id="sound-btn" title="Sound Alert" onclick="toggleSound()">🔔</button>
  </div>
  <div id="alert-body">
    <div class="no-alerts">รอสัญญาณจาก TradingView…</div>
  </div>
</section>

<script>
// ═══════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════
const POLL_MS       = 3000
const CANDLE_MS     = 30000
const TF_LIST       = ['1m','3m','5m','15m','30m','1h','4h','1d','1w']
const TF_LABELS     = ['M1','M3','M5','M15','M30','H1','H4','D1','W1']
const OVL_MAX       = 300   // จุด
const GRID_STEP     = 5.0   // USD

// ═══════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════
let soundOn       = false
let lastAlertId   = 0
let currentPrice  = 0
let tfBias        = {}   // {interval: 'bull'|'bear'|'neut'}
let tfPattern     = {}   // {interval: {label, dir}}

// ═══════════════════════════════════════════════════════════════
// INIT TF PANELS
// ═══════════════════════════════════════════════════════════════
function initTfGrid() {
  const grid = document.getElementById('tf-grid')
  TF_LIST.forEach((tf, i) => {
    const panel = document.createElement('div')
    panel.className = 'tf-panel'
    panel.id = `tf-${tf}`
    panel.innerHTML = `
      <div class="tf-label">${TF_LABELS[i]}</div>
      <div class="tf-bias neut" id="bias-${tf}">—</div>
      <div class="tf-pattern" id="pat-${tf}">—</div>
      <canvas class="mini-chart" id="cv-${tf}" height="40"></canvas>
    `
    grid.appendChild(panel)
  })
}

// ═══════════════════════════════════════════════════════════════
// MINI CANDLE CHART
// ═══════════════════════════════════════════════════════════════
function drawCandles(canvasId, candles) {
  const canvas = document.getElementById(canvasId)
  if (!canvas) return
  const ctx  = canvas.getContext('2d')
  const W    = canvas.offsetWidth || 80
  const H    = canvas.height
  canvas.width = W

  ctx.clearRect(0, 0, W, H)

  if (!candles || candles.length === 0) return

  const highs  = candles.map(c => c.h)
  const lows   = candles.map(c => c.l)
  const maxH   = Math.max(...highs)
  const minL   = Math.min(...lows)
  const range  = maxH - minL || 1

  const toY = v => H - ((v - minL) / range) * (H - 4) - 2
  const n   = candles.length
  const W_C = W / n
  const W_B = W_C * 0.55

  candles.forEach((c, i) => {
    const isBull = c.c >= c.o
    const color  = isBull ? '#22c55e' : '#ef4444'
    const x      = i * W_C + W_C / 2

    ctx.strokeStyle = color
    ctx.lineWidth   = 1
    ctx.beginPath()
    ctx.moveTo(x, toY(c.h))
    ctx.lineTo(x, toY(c.l))
    ctx.stroke()

    ctx.fillStyle = color
    const y1 = toY(Math.max(c.o, c.c))
    const y2 = toY(Math.min(c.o, c.c))
    const bH = Math.max(y2 - y1, 1.5)
    ctx.fillRect(x - W_B / 2, y1, W_B, bH)
  })
}

// ═══════════════════════════════════════════════════════════════
// DERIVE BIAS FROM CANDLES
// ═══════════════════════════════════════════════════════════════
function deriveBias(candles) {
  if (!candles || candles.length < 2) return 'neut'
  const last = candles[candles.length - 1]
  const prev = candles[candles.length - 2]
  if (last.c > last.o && last.c > prev.h) return 'bull'
  if (last.c < last.o && last.c < prev.l) return 'bear'
  if (last.c > last.o) return 'bull'
  if (last.c < last.o) return 'bear'
  return 'neut'
}

// ═══════════════════════════════════════════════════════════════
// POLL CANDLES
// ═══════════════════════════════════════════════════════════════
async function pollCandles() {
  for (const tf of TF_LIST) {
    try {
      const res  = await fetch(`/candles/${tf}`)
      if (!res.ok) continue
      const data = await res.json()
      if (!data.candles) continue
      drawCandles(`cv-${tf}`, data.candles)
      const bias = deriveBias(data.candles)
      tfBias[tf] = bias
      updateTfBias(tf, bias)
    } catch (_) {}
  }
}

function updateTfBias(tf, bias) {
  const el = document.getElementById(`bias-${tf}`)
  if (!el) return
  el.className = `tf-bias ${bias}`
  el.textContent = bias === 'bull' ? '▲ BULL' : bias === 'bear' ? '▼ BEAR' : '— NEUT'
}

// ═══════════════════════════════════════════════════════════════
// POLL PRICE
// ═══════════════════════════════════════════════════════════════
async function pollPrice() {
  try {
    const res  = await fetch('/price')
    const data = await res.json()
    if (data.price) {
      currentPrice = parseFloat(data.price)
      document.getElementById('live-price').innerHTML =
        `${currentPrice.toFixed(2)} <small>USD</small>`
      updateOvl(currentPrice)
    }
    setConn(true)
  } catch (_) {
    setConn(false)
  }
}

// ═══════════════════════════════════════════════════════════════
// OVL METER (client-side)
// ═══════════════════════════════════════════════════════════════
function updateOvl(price) {
  const grid = Math.round(price / GRID_STEP) * GRID_STEP
  const dist = Math.abs(price - grid) * 100   // USD → points (× 100)
  const pct  = Math.min(dist / OVL_MAX, 1)

  const el   = document.getElementById('ovl-value')
  const bar  = document.getElementById('ovl-bar')
  const sub  = document.getElementById('ovl-grid')

  sub.textContent = `Grid: ${grid.toFixed(2)}`

  let cls, color
  if (dist <= 150)       { cls = 'ready';   color = 'var(--green)';  }
  else if (dist <= 300)  { cls = 'wait';    color = 'var(--yellow)'; }
  else                   { cls = 'notrade'; color = 'var(--red)';    }

  el.className = `fc-value ${cls}`
  el.textContent = `${Math.round(dist)} pts`
  bar.style.width      = `${pct * 100}%`
  bar.style.background = color
}

// ═══════════════════════════════════════════════════════════════
// POLL CF STATUS
// ═══════════════════════════════════════════════════════════════
async function pollCf() {
  try {
    const res  = await fetch('/cf-status')
    const data = await res.json()

    const el  = document.getElementById('cf-value')
    const gEl = document.getElementById('cf-grid-lv')
    const uEl = document.getElementById('cf-updated')

    el.textContent = data.display || '— 0/3'
    el.className   = `fc-value ${data.cf_pass ? 'ready' : data.cf_count > 0 ? 'wait' : 'neutral'}`

    gEl.textContent = data.grid_level ? `Grid: ${parseFloat(data.grid_level).toFixed(2)}` : 'Grid: —'
    if (data.updated_at) {
      const t = new Date(data.updated_at + 'Z')
      uEl.textContent = t.toLocaleTimeString('th-TH', { hour12: false })
    }
  } catch (_) {}
}

// ═══════════════════════════════════════════════════════════════
// POLL ALERTS
// ═══════════════════════════════════════════════════════════════
async function pollAlerts() {
  try {
    const res   = await fetch('/alerts?limit=8')
    const data  = await res.json()
    renderAlerts(data)
    updateMtf(data)
  } catch (_) {}
}

function renderAlerts(alerts) {
  const body = document.getElementById('alert-body')
  if (!alerts || alerts.length === 0) {
    body.innerHTML = '<div class="no-alerts">รอสัญญาณจาก TradingView…</div>'
    return
  }

  // Sound on new alert
  const newest = alerts[0]
  if (newest && newest.id > lastAlertId) {
    if (lastAlertId > 0 && soundOn) playBeep()
    lastAlertId = newest.id

    // Update TF pattern from latest alert
    if (newest.interval) {
      const tf = intervalToTf(newest.interval)
      if (tf) {
        tfPattern[tf] = { label: newest.pattern, dir: (newest.direction||'').toLowerCase() }
        const el = document.getElementById(`pat-${tf}`)
        if (el) {
          el.textContent = `${newest.pattern} ${newest.direction}`
          el.className   = `tf-pattern ${tfPattern[tf].dir}`
        }
      }
    }
  }

  let html = `<table class="alert-table">
    <tr><th>เวลา</th><th>Pattern</th><th>Dir</th><th>TF</th><th>ราคา</th><th>Verdict</th></tr>`

  alerts.slice(0, 6).forEach(a => {
    const t      = a.timestamp ? new Date(a.timestamp + 'Z').toLocaleTimeString('th-TH', {hour12:false}) : '—'
    const dirCls = (a.direction||'').toLowerCase()
    const vCls   = (a.verdict||'').toLowerCase().replace('-','')
    html += `<tr>
      <td>${t}</td>
      <td>${a.pattern || '—'}</td>
      <td class="alert-dir ${dirCls}">${a.direction || '—'}</td>
      <td>${a.interval ? tfLabel(a.interval) : '—'}</td>
      <td>${a.price ? parseFloat(a.price).toFixed(2) : '—'}</td>
      <td class="alert-verdict ${vCls}">${a.verdict || '—'}</td>
    </tr>`
  })

  html += '</table>'
  body.innerHTML = html
}

function updateMtf(alerts) {
  if (!alerts || alerts.length === 0) return
  let bull = 0, bear = 0
  const seen = new Set()
  alerts.slice(0, 9).forEach(a => {
    if (!a.interval || seen.has(a.interval)) return
    seen.add(a.interval)
    if ((a.direction||'').toLowerCase() === 'buy')  bull++
    if ((a.direction||'').toLowerCase() === 'sell') bear++
  })
  const total = bull + bear
  const el    = document.getElementById('mtf-value')
  const sub   = document.getElementById('mtf-sub')
  sub.textContent = `Bull ${bull} / Bear ${bear}`
  if (total >= 4) {
    const dominant = bull >= bear ? `BULL ${bull}TF` : `BEAR ${bear}TF`
    el.textContent  = dominant
    el.className    = `fc-value ${bull >= bear ? 'ready' : 'notrade'}`
  } else {
    el.textContent = `${total} / 9 TF`
    el.className   = 'fc-value wait'
  }
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════
function intervalToTf(interval) {
  const map = {'1':'1m','3':'3m','5':'5m','15':'15m','30':'30m',
               '60':'1h','240':'4h','D':'1d','1D':'1d','W':'1w','1W':'1w'}
  return map[interval] || null
}

function tfLabel(interval) {
  const map = {'1':'M1','3':'M3','5':'M5','15':'M15','30':'M30',
               '60':'H1','240':'H4','D':'D1','1D':'D1','W':'W1','1W':'W1'}
  return map[interval] || interval
}

function setConn(live) {
  const dot = document.getElementById('conn-dot')
  const lbl = document.getElementById('conn-label')
  dot.className = live ? 'conn-dot live' : 'conn-dot'
  lbl.textContent = live ? 'LIVE' : 'OFFLINE'
}

function toggleSound() {
  soundOn = !soundOn
  const btn = document.getElementById('sound-btn')
  btn.className = soundOn ? 'sound-btn on' : 'sound-btn'
  btn.textContent = soundOn ? '🔔' : '🔕'
}

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const osc = ctx.createOscillator()
    osc.connect(ctx.destination)
    osc.frequency.value = 880
    osc.start()
    osc.stop(ctx.currentTime + 0.15)
  } catch(_) {}
}

// ═══════════════════════════════════════════════════════════════
// POLLING LOOPS
// ═══════════════════════════════════════════════════════════════
async function tickFast() {
  await Promise.all([pollPrice(), pollCf(), pollAlerts()])
  setTimeout(tickFast, POLL_MS)
}

async function tickSlow() {
  await pollCandles()
  setTimeout(tickSlow, CANDLE_MS)
}

// ═══════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  initTfGrid()
  tickFast()
  tickSlow()
})
</script>
</body>
</html>"""

# ── API Endpoints ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

@app.get("/health")
async def health():
    return {"status": "ok", "service": "DIAMOND TRADER", "version": "2.1"}

@app.get("/price")
async def get_price():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{BINANCE_BASE}/ticker/price",
                params={"symbol": PAXG_SYMBOL}
            )
            data = r.json()
            return {"price": float(data["price"]), "symbol": PAXG_SYMBOL}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)

@app.get("/candles/{interval}")
async def get_candles(interval: str):
    # Map dashboard TF → Binance interval
    tf_map = {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"
    }
    bInterval = tf_map.get(interval, "5m")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{BINANCE_BASE}/klines",
                params={"symbol": PAXG_SYMBOL, "interval": bInterval, "limit": 5}
            )
            raw = r.json()
            candles = [
                {"o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])}
                for k in raw
            ]
            return {"interval": interval, "candles": candles}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)

@app.get("/cf-status")
async def get_cf_status():
    return {
        **cf_state,
        "display": _cf_display(
            cf_state["cf_count"],
            cf_state["cf_pass"],
            cf_state["cf_dir"]
        )
    }

@app.get("/alerts")
async def get_alerts(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    cols = ["id","timestamp","ticker","interval","pattern",
            "direction","price","verdict","raw"]
    return [dict(zip(cols, r)) for r in rows]

@app.post("/alerts")
async def post_alert(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "msg": "invalid JSON"}, status_code=400)

    # ── CF_UPDATE — อัป in-memory state ──────────────────────────
    if body.get("type") == "CF_UPDATE":
        cf_state["cf_count"]   = int(body.get("cf_count", 0))
        cf_state["cf_pass"]    = bool(body.get("cf_pass", False))
        cf_state["cf_dir"]     = str(body.get("cf_dir", "neutral"))
        cf_state["cf_status"]  = str(body.get("cf_status", "WAIT"))
        cf_state["grid_level"] = float(body.get("grid_level", 0.0))
        cf_state["close"]      = float(body.get("close", 0.0))
        cf_state["ticker"]     = str(body.get("ticker", ""))
        cf_state["updated_at"] = datetime.utcnow().isoformat()
        return {
            "status": "ok",
            "type": "CF_UPDATE",
            "cf_count": cf_state["cf_count"],
            "display": _cf_display(
                cf_state["cf_count"],
                cf_state["cf_pass"],
                cf_state["cf_dir"]
            )
        }

    # ── PA Signal — บันทึก DB ─────────────────────────────────────
    now       = datetime.utcnow().isoformat()
    ticker    = body.get("ticker", "XAUUSD")
    interval  = body.get("interval", "")
    pattern   = body.get("pattern", body.get("type", "UNKNOWN"))
    direction = body.get("direction", "")
    price     = float(body.get("close", body.get("price", 0)))
    verdict   = body.get("verdict", "WAIT")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO alerts
           (timestamp,ticker,interval,pattern,direction,price,verdict,raw)
           VALUES (?,?,?,?,?,?,?,?)""",
        (now, ticker, interval, pattern, direction, price, verdict, json.dumps(body))
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "type": "PA_SIGNAL", "pattern": pattern}

# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
