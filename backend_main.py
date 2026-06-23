"""
DIAMOND TRADER — backend_main.py v2.1
FastAPI + Cyberpunk HUD Dashboard (inline)
SSOT: PA_SPEC_MASTER_v2.1 + SNIPER_HUD_BIBLE_v1.1
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import sqlite3, json, os, httpx

DB_PATH      = os.getenv("DB_PATH", "diamond_trader.db")
BINANCE_BASE = "https://api.binance.com/api/v3"
PAXG_SYMBOL  = "PAXGUSDT"

last_price: dict = {"price": 0.0, "updated_at": None}
cf_state: dict = {
    "cf_count": 0, "cf_pass": False, "cf_dir": "neutral",
    "cf_status": "WAIT", "grid_level": 0.0, "close": 0.0,
    "ticker": "", "updated_at": None,
}

def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    # Drop table เก่าที่ schema ไม่ตรง แล้วสร้างใหม่
    conn.execute("DROP TABLE IF EXISTS alerts")
    conn.execute("""CREATE TABLE alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        ticker TEXT, interval TEXT, pattern TEXT,
        direction TEXT, price REAL, verdict TEXT, raw TEXT)""")
    conn.commit()
    conn.close()

def _cf_display(count, passed, direction):
    d = "BUY" if direction=="buy" else "SELL" if direction=="sell" else "—"
    if count==0: return "— 0/3"
    if passed:   return f"✓ {d} 3/3 READY"
    return f"⏳ {d} {count}/3"

@asynccontextmanager
async def lifespan(app):
    init_db(); yield

app = FastAPI(title="DIAMOND TRADER", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>💎 DIAMOND TRADER — HUD v2.1</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg-dark: #080a10; --bg-main: #0d111a; --bg-card: #141a29;
    --border: #222d42; --border-glow: #384c6e;
    --green: #00e676; --red: #ff3d00; --yellow: #ffea00;
    --white: #f8f9fa; --text-muted: #707e94;
    --ready: #00c853; --wait: #ff9100; --notrade: #d50000;
  }
  body { background: var(--bg-main); color: var(--white); font-family: 'Inter', sans-serif;
    font-size: 13px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
  #topbar { height: 45px; background: var(--bg-dark); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; padding: 0 20px; gap: 20px; flex-shrink: 0; }
  .brand { font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 15px; color: var(--yellow); letter-spacing: 1px; }
  .status-wrapper { display: flex; align-items: center; gap: 6px; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); }
  .dot.live { background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
  .nav-spacer { flex: 1; }
  #price-hud { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 16px;
    background: var(--bg-card); padding: 4px 12px; border-radius: 6px; border: 1px solid var(--border); }
  #price-hud.up { color: var(--green); border-color: var(--green); }
  #price-hud.down { color: var(--red); border-color: var(--red); }
  #main-layout { display: grid; grid-template-columns: 1fr 1.1fr 1fr; gap: 14px; padding: 14px; flex: 1; min-height: 0; }
  .hud-container { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
  .hud-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; }
  .panel-title { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
    color: var(--text-muted); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 12px; }
  #tf-vertical-list { flex: 1; display: flex; flex-direction: column; gap: 6px; overflow-y: auto; }
  .tf-list-item { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; transition: all 0.2s; }
  .tf-list-item.active-buy { border-color: var(--green); background: rgba(0,230,118,0.03); }
  .tf-list-item.active-sell { border-color: var(--red); background: rgba(255,61,0,0.03); }
  .tf-name { font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 13px; color: var(--white); }
  .tf-status-text { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-muted); font-weight: 700; }
  .tf-list-item.active-buy .tf-status-text { color: var(--green); }
  .tf-list-item.active-sell .tf-status-text { color: var(--red); }
  .tf-price { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); }
  #filter-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .filter-mini { background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 12px; font-family: 'JetBrains Mono', monospace; }
  .fm-label { font-size: 9px; color: var(--text-muted); letter-spacing: .1em; text-transform: uppercase; margin-bottom: 4px; }
  .fm-val { font-size: 14px; font-weight: 800; color: var(--text-muted); }
  .fm-val.ready { color: var(--green); }
  .fm-val.wait  { color: var(--yellow); }
  .fm-val.notrade { color: var(--red); }
  #log-card { flex: 1; min-height: 0; overflow: hidden; }
  #alert-list { display: flex; flex-direction: column; gap: 6px; overflow-y: auto; max-height: 260px; }
  .alert-item { background: var(--bg-dark); border: 1px solid var(--border); padding: 8px 12px;
    border-radius: 6px; display: flex; align-items: center; justify-content: space-between;
    font-family: 'JetBrains Mono', monospace; font-size: 11px; }
  .alert-item.buy { border-left: 3px solid var(--green); }
  .alert-item.sell { border-left: 3px solid var(--red); }
  .at-pat { font-weight: 700; }
  .at-pat.b { color: var(--green); }
  .at-pat.s { color: var(--red); }
  .at-time { color: var(--text-muted); font-size: 10px; }
  .at-price { font-weight: 700; color: var(--yellow); }
  #verdict-box { font-family: 'JetBrains Mono', monospace; font-size: 26px; font-weight: 800;
    padding: 12px; border-radius: 6px; background: var(--bg-dark); border: 1px solid var(--border);
    color: var(--text-muted); letter-spacing: 2px; text-align: center; }
  #verdict-box.v-ready { color: var(--white); background: var(--ready); border-color: var(--green); box-shadow: 0 4px 15px rgba(0,200,83,.3); }
  #verdict-box.v-wait  { color: var(--bg-dark); background: var(--wait); border-color: var(--wait); }
  #verdict-box.v-notrade { color: var(--white); background: var(--notrade); border-color: var(--red); }
  .metric-row { display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,.02); }
  .metric-row:last-child { border-bottom: none; }
  .m-label { color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 11px; }
  .m-val { font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 14px; }
  .m-val.g { color: var(--green); } .m-val.r { color: var(--red); } .m-val.y { color: var(--yellow); }
  #cf-counter-box { display: flex; align-items: center; justify-content: space-between;
    background: var(--bg-dark); border-radius: 6px; padding: 12px 14px; border: 1px solid var(--border); }
  #cf-num { font-size: 26px; font-weight: 800; font-family: 'JetBrains Mono', monospace; color: var(--text-muted); }
  #cf-num.active { color: var(--green); }
  #cf-badge { font-weight: 700; font-size: 11px; padding: 3px 8px; border-radius: 4px; background: rgba(255,255,255,.05); }
  #cf-badge.pass { background: rgba(0,230,118,.15); color: var(--green); border: 1px solid var(--green); }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: var(--bg-dark); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
</style>
</head>
<body>
<div id="topbar">
  <div class="brand">💎 DIAMOND TRADER</div>
  <div class="status-wrapper">
    <div id="ws-dot" class="dot"></div>
    <span id="ws-status">CONNECTING</span>
  </div>
  <div class="nav-spacer"></div>
  <div id="price-hud">
    <span style="font-size:11px;color:var(--text-muted)">PAXG:</span>
    <span id="paxg-price">0.00</span>
  </div>
</div>

<div id="main-layout">
  <!-- COL 1: TF LIST -->
  <div class="hud-container" id="tf-vertical-list"></div>

  <!-- COL 2: FILTERS + LOG -->
  <div class="hud-container">
    <div class="hud-card">
      <div class="panel-title">⚡ Filter Status</div>
      <div id="filter-grid">
        <div class="filter-mini">
          <div class="fm-label">CF M5</div>
          <div class="fm-val wait" id="f-cf">0/3</div>
        </div>
        <div class="filter-mini">
          <div class="fm-label">Grid OVL</div>
          <div class="fm-val" id="f-ovl">—</div>
        </div>
        <div class="filter-mini">
          <div class="fm-label">Sideway</div>
          <div class="fm-val" id="f-sw">—</div>
        </div>
        <div class="filter-mini">
          <div class="fm-label">MTF Align</div>
          <div class="fm-val" id="f-mtf">—</div>
        </div>
      </div>
    </div>
    <div class="hud-card" id="log-card">
      <div class="panel-title">📜 Live Signal Feed</div>
      <div id="alert-list">
        <div style="color:var(--text-muted);text-align:center;margin-top:20px;font-family:'JetBrains Mono';font-size:11px">Waiting for signals...</div>
      </div>
    </div>
  </div>

  <!-- COL 3: EXECUTION -->
  <div class="hud-container">
    <div class="hud-card">
      <div class="panel-title">📡 Action Verdict</div>
      <div id="verdict-box">STANDBY</div>
    </div>
    <div class="hud-card">
      <div class="panel-title">🎯 Target Parameters</div>
      <div class="metric-row"><span class="m-label">ENTRY</span><span class="m-val y" id="ex-entry">—</span></div>
      <div class="metric-row"><span class="m-label">STOP LOSS</span><span class="m-val r" id="ex-sl">—</span></div>
      <div class="metric-row"><span class="m-label">TAKE PROFIT</span><span class="m-val g" id="ex-tp">—</span></div>
      <div class="metric-row"><span class="m-label">PATTERN</span><span class="m-val" id="ex-pattern" style="color:var(--text-muted);font-size:12px">WAITING...</span></div>
    </div>
    <div class="hud-card">
      <div class="panel-title">🛡️ CF M5 Counter</div>
      <div id="cf-counter-box">
        <div id="cf-num">0 / 3</div>
        <div id="cf-badge">WAITING</div>
      </div>
    </div>
  </div>
</div>

<script>
// TF_LIST — id ตรงกับ interval ที่ TradingView ส่งมา
const TF_LIST = [
  {id:'M',   name:'MN'},  {id:'W',   name:'W1'}, {id:'D',   name:'D1'},
  {id:'240', name:'H4'},  {id:'60',  name:'H1'}, {id:'30',  name:'M30'},
  {id:'15',  name:'M15'}, {id:'5',   name:'M5'}, {id:'1',   name:'M1'}
];
const TF_DISPLAY = {};
TF_LIST.forEach(t => TF_DISPLAY[t.id] = t.name);

function initTfList() {
  const c = document.getElementById('tf-vertical-list');
  c.innerHTML = '';
  TF_LIST.forEach(tf => {
    c.innerHTML += `<div class="tf-list-item" id="item-${tf.id}">
      <span class="tf-name">${tf.name}</span>
      <span class="tf-status-text" id="status-${tf.id}">— STANDBY</span>
      <span class="tf-price" id="price-${tf.id}"></span></div>`;
  });
}

function updateTfCard(interval, d) {
  const card = document.getElementById('item-' + interval);
  const st   = document.getElementById('status-' + interval);
  const pr   = document.getElementById('price-'  + interval);
  if (!card) return;
  if (d.direction === 'BUY') {
    card.className = 'tf-list-item active-buy';
    st.textContent = d.pattern ? '▲ ' + d.pattern : '▲ BUY';
  } else {
    card.className = 'tf-list-item active-sell';
    st.textContent = d.pattern ? '▼ ' + d.pattern : '▼ SELL';
  }
  if (d.price) pr.textContent = parseFloat(d.price).toFixed(2);
}

function updateExec(d) {
  const v = document.getElementById('verdict-box');
  const price = parseFloat(d.close || d.price || 0);
  document.getElementById('ex-pattern').textContent = d.pattern || '—';
  document.getElementById('ex-entry').textContent = price ? price.toFixed(2) : '—';
  if (d.direction === 'BUY') {
    v.textContent = 'READY BUY'; v.className = 'v-ready';
    document.getElementById('ex-pattern').style.color = 'var(--green)';
    document.getElementById('ex-sl').textContent = (price - 3.0).toFixed(2);
    document.getElementById('ex-tp').textContent = (price + 9.0).toFixed(2);
  } else if (d.direction === 'SELL') {
    v.textContent = 'READY SELL'; v.className = 'v-notrade';
    document.getElementById('ex-pattern').style.color = 'var(--red)';
    document.getElementById('ex-sl').textContent = (price + 3.0).toFixed(2);
    document.getElementById('ex-tp').textContent = (price - 9.0).toFixed(2);
  } else {
    v.textContent = d.verdict || 'STANDBY'; v.className = 'v-wait';
  }
}

function addAlert(d, prepend) {
  const list = document.getElementById('alert-list');
  if (list.querySelector('div[style]')) list.innerHTML = '';
  const div  = document.createElement('div');
  const buy  = d.direction === 'BUY';
  const tfLbl = TF_DISPLAY[d.interval] || d.interval || 'M5';
  const ts   = (d.timestamp || '').substring(11, 19) || '—';
  div.className = 'alert-item ' + (buy ? 'buy' : 'sell');
  div.innerHTML = `<div><span class="at-pat ${buy?'b':'s'}">${buy?'▲':'▼'} [${tfLbl}] ${d.pattern||'PA'}</span><br>
    <span class="at-time">${ts}</span></div>
    <span class="at-price">${d.price ? parseFloat(d.price).toFixed(2) : '—'}</span>`;
  if (prepend && list.firstChild) list.insertBefore(div, list.firstChild);
  else list.appendChild(div);
  while (list.children.length > 15) list.removeChild(list.lastChild);
}

// MTF confluence
function updateMtfFilter(rows) {
  let bull=0, bear=0, seen=new Set();
  rows.slice(0,9).forEach(d => {
    if (!d.interval || seen.has(d.interval)) return;
    seen.add(d.interval);
    if (d.direction==='BUY') bull++; else if (d.direction==='SELL') bear++;
  });
  const el = document.getElementById('f-mtf');
  el.textContent = `${bull}B/${bear}S`;
  el.className = 'fm-val ' + (bull>=4||bear>=4 ? 'ready' : 'wait');
}

// OVL (client-side)
function updateOvl(price) {
  const grid = Math.round(price / 5.0) * 5.0;
  const dist = Math.abs(price - grid) * 100;
  const el = document.getElementById('f-ovl');
  el.textContent = Math.round(dist) + 'pts';
  el.className = 'fm-val ' + (dist<=150 ? 'ready' : dist<=300 ? 'wait' : 'notrade');
}

let lastPrice = 0;
async function pollPrice() {
  try {
    const d = await (await fetch('/price')).json();
    if (d.price) {
      const p = parseFloat(d.price);
      const el = document.getElementById('paxg-price');
      const hud = document.getElementById('price-hud');
      el.textContent = p.toLocaleString(undefined, {minimumFractionDigits:2});
      hud.className = p > lastPrice ? 'up' : p < lastPrice ? 'down' : '';
      lastPrice = p;
      updateOvl(p);
    }
  } catch(e){}
}

async function pollCf() {
  try {
    const d = await (await fetch('/cf-status')).json();
    const num   = document.getElementById('cf-num');
    const badge = document.getElementById('cf-badge');
    const fCf   = document.getElementById('f-cf');
    num.textContent = d.cf_count + ' / 3';
    if (d.cf_pass) {
      num.className = 'active'; badge.className = 'pass';
      badge.textContent = 'PASS (' + (d.cf_dir||'').toUpperCase() + ')';
      fCf.className = 'fm-val ready'; fCf.textContent = '✓ 3/3';
    } else {
      num.className = ''; badge.className = '';
      badge.textContent = d.cf_status || 'WAITING';
      fCf.className = 'fm-val wait';
      fCf.textContent = d.cf_count + '/3';
    }
  } catch(e){}
}

let lastId = 0;
async function pollAlerts() {
  const dot = document.getElementById('ws-dot');
  const lbl = document.getElementById('ws-status');
  try {
    const rows = await (await fetch('/alerts?limit=30')).json();
    dot.className = 'dot live'; lbl.textContent = 'LIVE';
    if (lastId===0 && rows.length>0) {
      document.getElementById('alert-list').innerHTML = '';
      rows.slice(0,15).forEach(d => addAlert(d, false));
      updateExec(rows[0]);
      if (rows[0].interval) updateTfCard(rows[0].interval, rows[0]);
      lastId = rows[0].id;
      updateMtfFilter(rows);
      return;
    }
    const news = rows.filter(d => d.id > lastId);
    if (news.length > 0) {
      news.reverse().forEach(d => { addAlert(d, true); updateExec(d); if(d.interval) updateTfCard(d.interval, d); });
      lastId = news[news.length-1].id;
      updateMtfFilter(rows);
    }
  } catch(e) { dot.className='dot'; lbl.textContent='OFFLINE'; }
}

initTfList();
setInterval(pollPrice,  2000);
setInterval(pollCf,     2000);
setInterval(pollAlerts, 1000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard(): return DASHBOARD_HTML

@app.get("/health")
async def health(): return {"status":"ok","service":"DIAMOND TRADER","version":"2.1"}

@app.get("/price")
async def get_price():
    if last_price["price"] > 0:
        return {"price": last_price["price"], "symbol": "XAUUSD", "updated_at": last_price["updated_at"]}
    return JSONResponse({"error": "price"}, status_code=503)

@app.get("/cf-status")
async def get_cf_status():
    return {**cf_state, "display": _cf_display(cf_state["cf_count"], cf_state["cf_pass"], cf_state["cf_dir"])}

@app.get("/alerts")
async def get_alerts(limit: int = 30):
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    cols = ["id","timestamp","ticker","interval","pattern","direction","price","verdict","raw"]
    return [dict(zip(cols,r)) for r in rows]

@app.post("/alerts")
async def post_alert(request: Request):
    try: body = await request.json()
    except: return JSONResponse({"status":"error","msg":"invalid JSON"}, status_code=400)

    if body.get("type") == "CF_UPDATE":
        cf_state.update({
            "cf_count":   int(body.get("cf_count",0)),
            "cf_pass":    bool(body.get("cf_pass",False)),
            "cf_dir":     str(body.get("cf_dir","neutral")),
            "cf_status":  str(body.get("cf_status","WAIT")),
            "grid_level": float(body.get("grid_level",0.0)),
            "close":      float(body.get("close",0.0)),
            "ticker":     str(body.get("ticker","")),
            "updated_at": datetime.utcnow().isoformat(),
        })
        return {"status":"ok","type":"CF_UPDATE","cf_count":cf_state["cf_count"],
                "display":_cf_display(cf_state["cf_count"],cf_state["cf_pass"],cf_state["cf_dir"])}

    last_price["price"] = float(body.get("close", body.get("price", 0)))
    last_price["updated_at"] = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.execute("INSERT INTO alerts (timestamp,ticker,interval,pattern,direction,price,verdict,raw) VALUES (?,?,?,?,?,?,?,?)",
        (now, body.get("ticker","XAUUSD"), body.get("interval",""),
         body.get("pattern",body.get("type","UNKNOWN")), body.get("direction",""),
         float(body.get("close",body.get("price",0))), body.get("verdict","WAIT"), json.dumps(body)))
    conn.commit(); conn.close()
    return {"status":"ok","type":"PA_SIGNAL","pattern":body.get("pattern","")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT",8000)))
