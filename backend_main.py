"""
DIAMOND TRADER — backend_main.py v3.0
FastAPI + War Room HUD Dashboard (3-Column)
SSOT: PA_SPEC_MASTER_v2.1 + SNIPER_HUD_BIBLE_v1.1
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import sqlite3, json, os, httpx, asyncio, math

DB_PATH      = os.getenv("DB_PATH", "diamond_trader.db")
BINANCE_BASE = "https://api.binance.com/api/v3"
PAXG_SYMBOL  = "PAXGUSDT"
FINNHUB_KEY  = os.getenv("FINNHUB_KEY", "")  # optional — free tier

# ── In-memory state ──────────────────────────────────────────────
last_price: dict  = {"price": 0.0, "updated_at": None}
usdthb_rate: dict = {"rate": 36.5, "updated_at": None}

cf_state: dict = {
    "cf_count": 0, "cf_pass": False, "cf_dir": "neutral",
    "cf_status": "WAIT", "grid_level": 0.0, "close": 0.0,
    "ticker": "", "updated_at": None,
}

# structure_state: keyed by interval
structure_state: dict = {}

# zones: list of active H4 DZ/SZ
zones: list = []

# news_guard
news_guard: dict = {"blocked": False, "reason": "", "unblock_at": None}

# economic news cache
news_cache: list = []

# ── DB init ──────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, ticker TEXT, interval TEXT, pattern TEXT,
        direction TEXT, price REAL, verdict TEXT, raw TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS economic_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_time TEXT, title TEXT, currency TEXT,
        impact TEXT, fetched_at TEXT)""")
    conn.commit()
    conn.close()

# ── Helpers ──────────────────────────────────────────────────────
def _cf_display(count, passed, direction):
    d = "BUY" if direction == "buy" else "SELL" if direction == "sell" else "—"
    if count == 0: return "— 0/3"
    if passed:     return f"✓ {d} 3/3 READY"
    return f"⏳ {d} {count}/3"

def _nearest_grid(price):
    return round(price / 5.0) * 5.0

def _ovl_points(price):
    grid = _nearest_grid(price)
    return round(abs(price - grid) * 100)

def _bias_vote(intervals, tf_state):
    """Return 'BUY','SELL','CONFLICT','NEUTRAL' for a group of intervals"""
    bull = sum(1 for i in intervals if tf_state.get(i, {}).get("direction") == "BUY")
    bear = sum(1 for i in intervals if tf_state.get(i, {}).get("direction") == "SELL")
    total = bull + bear
    if total == 0: return "NEUTRAL"
    if bull > bear: return "BUY"
    if bear > bull: return "SELL"
    return "CONFLICT"

def _compute_bias(tf_state):
    higher_bias       = _bias_vote(["MN", "W", "D"], tf_state)
    # Intermediate: H4 is tiebreaker
    h4_dir = tf_state.get("H4", {}).get("direction", "")
    h1_dir = tf_state.get("H1", {}).get("direction", "")
    if h4_dir == h1_dir and h4_dir: inter_bias = h4_dir
    elif h4_dir: inter_bias = h4_dir   # H4 wins conflict
    else: inter_bias = "NEUTRAL"
    # Lower: majority, M30 tiebreaker
    lower_intervals = ["M30", "M15", "M5", "M1"]
    bull = sum(1 for i in lower_intervals if tf_state.get(i, {}).get("direction") == "BUY")
    bear = sum(1 for i in lower_intervals if tf_state.get(i, {}).get("direction") == "SELL")
    if bull > bear:   lower_bias = "BUY"
    elif bear > bull: lower_bias = "SELL"
    else:             lower_bias = tf_state.get("M30", {}).get("direction", "CONFLICT") or "CONFLICT"
    # Bias Now: Intermediate anchor
    if inter_bias == higher_bias and inter_bias not in ("NEUTRAL", "CONFLICT"):
        bias_now = inter_bias
    elif inter_bias not in ("NEUTRAL", "CONFLICT"):
        bias_now = inter_bias + "?"   # signal but conflicted with higher
    else:
        bias_now = "CONFLICT"
    return {
        "higher": higher_bias, "intermediate": inter_bias,
        "lower": lower_bias,   "bias_now": bias_now,
    }

def _check_news_guard():
    now = datetime.now(timezone.utc)
    if news_guard.get("unblock_at"):
        ub = datetime.fromisoformat(news_guard["unblock_at"])
        if now >= ub:
            news_guard["blocked"] = False
            news_guard["reason"]  = ""
            news_guard["unblock_at"] = None
    for item in news_cache:
        try:
            event_dt = datetime.fromisoformat(item["event_time"])
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            diff = (event_dt - now).total_seconds()
            if item.get("impact") == "high" and -300 <= diff <= 900:
                news_guard["blocked"]    = True
                news_guard["reason"]     = item.get("title", "High Impact News")
                news_guard["unblock_at"] = (event_dt + timedelta(minutes=5)).isoformat()
                return
        except Exception:
            pass

def _compute_verdict(direction):
    if news_guard.get("blocked"): return "NEWS BLOCK"
    if cf_state["cf_pass"] and cf_state["cf_dir"] == direction.lower():
        return f"READY {direction}"
    return "STANDBY"

def _zone_tag(width):
    if width <= 500: return "TIGHT_SL"
    return "WIDE_REFINE"


# ── Background Tasks ─────────────────────────────────────────────
async def fetch_paxg_price():
    while True:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{BINANCE_BASE}/ticker/price", params={"symbol": PAXG_SYMBOL})
                last_price["price"]      = float(r.json()["price"])
                last_price["updated_at"] = datetime.utcnow().isoformat()
        except Exception:
            pass
        await asyncio.sleep(10)

async def fetch_usdthb():
    while True:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://api.exchangerate-api.com/v4/latest/USD")
                rate = r.json()["rates"].get("THB", 36.5)
                usdthb_rate["rate"]       = float(rate)
                usdthb_rate["updated_at"] = datetime.utcnow().isoformat()
        except Exception:
            pass
        await asyncio.sleep(300)  # every 5 min

async def fetch_economic_news():
    while True:
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            fetched = []
            # Try Finnhub if key provided
            if FINNHUB_KEY:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(
                        "https://finnhub.io/api/v1/calendar/economic",
                        params={"token": FINNHUB_KEY}
                    )
                    data = r.json().get("economicCalendar", [])
                    for item in data:
                        if item.get("country") != "US": continue
                        impact = item.get("impact", "").lower()
                        if impact not in ("high", "medium"): continue
                        t = item.get("time", "") or item.get("date", "")
                        fetched.append({
                            "event_time": t, "title": item.get("event", ""),
                            "currency": "USD", "impact": impact
                        })
            # Fallback: forex-news-scraper free endpoint
            if not fetched:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(
                        "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
                    )
                    data = r.json()
                    for item in data:
                        if item.get("country") != "USD": continue
                        impact = item.get("impact", "").lower()
                        if impact not in ("high", "medium"): continue
                        t = item.get("date", "")
                        fetched.append({
                            "event_time": t, "title": item.get("title", ""),
                            "currency": "USD", "impact": impact
                        })
            news_cache.clear()
            news_cache.extend(fetched)
            # persist to DB
            conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
            conn.execute("DELETE FROM economic_news")
            now_str = datetime.utcnow().isoformat()
            for item in fetched:
                conn.execute(
                    "INSERT INTO economic_news (event_time,title,currency,impact,fetched_at) VALUES (?,?,?,?,?)",
                    (item["event_time"], item["title"], item["currency"], item["impact"], now_str)
                )
            conn.commit()
            conn.close()
        except Exception:
            pass
        await asyncio.sleep(3600)  # every 1 hour

async def cleanup_breakout():
    """Clear BREAKOUT state after 15 min TTL"""
    while True:
        now = datetime.utcnow()
        for iv, st in list(structure_state.items()):
            if st.get("structure") == "BREAKOUT":
                ts = st.get("updated_at", "")
                try:
                    dt = datetime.fromisoformat(ts)
                    if (now - dt).total_seconds() > 900:  # 15 min
                        structure_state[iv]["structure"] = "SIDEWAY"
                except Exception:
                    pass
        await asyncio.sleep(60)

async def cleanup_old_alerts():
    """E2: ลบ alerts เก่า — เก็บแค่ 500 rows ล่าสุด, รันทุก 30 นาที"""
    while True:
        await asyncio.sleep(1800)  # รอ 30 นาทีก่อน (ไม่ cleanup ตอนเริ่ม)
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
            # นับ rows ปัจจุบัน
            count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            if count > 500:
                # ลบ rows เก่าเกิน 500
                conn.execute("""
                    DELETE FROM alerts WHERE id NOT IN (
                        SELECT id FROM alerts ORDER BY id DESC LIMIT 500
                    )
                """)
                deleted = count - 500
                conn.commit()
            conn.close()
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app):
    init_db()
    asyncio.create_task(fetch_paxg_price())
    asyncio.create_task(fetch_usdthb())
    asyncio.create_task(fetch_economic_news())
    asyncio.create_task(cleanup_breakout())
    asyncio.create_task(cleanup_old_alerts())
    yield

app = FastAPI(title="DIAMOND TRADER v3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── API Endpoints ─────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "DIAMOND TRADER", "version": "3.0"}

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
    return [dict(zip(cols, r)) for r in rows]

@app.get("/news")
async def get_news():
    _check_news_guard()
    return {"news": news_cache, "guard": news_guard}

@app.get("/dashboard-state")
async def dashboard_state():
    _check_news_guard()
    price = last_price["price"]
    ovl   = _ovl_points(price) if price > 0 else None
    bias  = _compute_bias({iv: s for iv, s in structure_state.items()})

    # Active zone proximity
    zone_proximity = []
    for z in zones:
        mid    = (z["upper"] + z["lower"]) / 2
        dist   = round(abs(price - mid) * 100) if price > 0 else None
        alert  = dist is not None and dist < 100
        width  = round((z["upper"] - z["lower"]) * 100)
        zone_proximity.append({**z, "dist_pts": dist, "proximity_alert": alert,
                                "width_pts": width, "tag": _zone_tag(width)})

    # TF summary for bias count
    tf_rows = []
    for iv in ["MN","W","D","H4","H1","M30","M15","M5","M1"]:
        s = structure_state.get(iv, {})
        tf_rows.append({"interval": iv, "direction": s.get("direction",""),
                         "pattern": s.get("pattern",""), "price": s.get("price",0),
                         "structure": s.get("structure","")})
    bull = sum(1 for t in tf_rows if t["direction"] == "BUY")
    bear = sum(1 for t in tf_rows if t["direction"] == "SELL")

    return {
        "price":          price,
        "usdthb":         usdthb_rate["rate"],
        "ovl_pts":        ovl,
        "grid":           _nearest_grid(price) if price > 0 else 0,
        "cf":             cf_state,
        "cf_display":     _cf_display(cf_state["cf_count"], cf_state["cf_pass"], cf_state["cf_dir"]),
        "bias":           bias,
        "tf_rows":        tf_rows,
        "bull_count":     bull,
        "bear_count":     bear,
        "structure":      structure_state,
        "zones":          zone_proximity,
        "news_guard":     news_guard,
        "news":           news_cache[:5],
        "verdict":        "NEWS BLOCK" if news_guard.get("blocked") else "STANDBY",
    }

@app.post("/alerts")
async def post_alert(request: Request):
    try: body = await request.json()
    except: return JSONResponse({"status":"error","msg":"invalid JSON"}, status_code=400)

    msg_type = body.get("type", "PA_SIGNAL")

    # ── CF_UPDATE ──
    if msg_type == "CF_UPDATE":
        cf_state.update({
            "cf_count":   int(body.get("cf_count", 0)),
            "cf_pass":    bool(body.get("cf_pass", False)),
            "cf_dir":     str(body.get("cf_dir", "neutral")),
            "cf_status":  str(body.get("cf_status", "WAIT")),
            "grid_level": float(body.get("grid_level", 0.0)),
            "close":      float(body.get("close", 0.0)),
            "ticker":     str(body.get("ticker", "")),
            "updated_at": datetime.utcnow().isoformat(),
        })
        return {"status":"ok","type":"CF_UPDATE",
                "display": _cf_display(cf_state["cf_count"], cf_state["cf_pass"], cf_state["cf_dir"])}

    # ── STRUCT_UPDATE ──
    if msg_type == "STRUCT_UPDATE":
        iv = body.get("interval", "")
        if iv:
            structure_state[iv] = {
                "structure":    body.get("structure", ""),
                "direction":    body.get("direction", ""),
                "pattern":      body.get("pattern", ""),
                "price":        float(body.get("price", body.get("close", 0))),
                "hh":           body.get("hh"), "hl": body.get("hl"),
                "lh":           body.get("lh"), "ll": body.get("ll"),
                "sw_high_wick": body.get("sw_high_wick"),
                "sw_low_wick":  body.get("sw_low_wick"),
                "sw_high_body": body.get("sw_high_body"),
                "sw_low_body":  body.get("sw_low_body"),
                "updated_at":   datetime.utcnow().isoformat(),
            }
        return {"status":"ok","type":"STRUCT_UPDATE","interval":iv}

    # ── ZONE_UPDATE ──
    if msg_type == "ZONE_UPDATE":
        zone = {
            "zone_type": body.get("zone_type", "DZ"),
            "interval":  body.get("interval", "H4"),
            "upper":     float(body.get("upper", 0)),
            "lower":     float(body.get("lower", 0)),
            "updated_at": datetime.utcnow().isoformat(),
        }
        # Replace zone of same type+interval
        zones[:] = [z for z in zones if not (z["zone_type"]==zone["zone_type"] and z["interval"]==zone["interval"])]
        zones.append(zone)
        return {"status":"ok","type":"ZONE_UPDATE","zone":zone}

    # ── PA_SIGNAL (default) ──
    now = datetime.utcnow().isoformat()
    price_val = float(body.get("close", body.get("price", 0)))
    last_price["price"]      = price_val
    last_price["updated_at"] = now

    # Update structure state from PA signal
    iv = body.get("interval", "")
    if iv and body.get("direction"):
        prev = structure_state.get(iv, {})
        structure_state[iv] = {
            **prev,
            "direction":  body.get("direction", ""),
            "pattern":    body.get("pattern", body.get("type", "")),
            "price":      price_val,
            "updated_at": now,
        }

    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    # Dedup: same pattern+direction+interval within same minute
    window = now[:16] + ":00"
    recent = conn.execute(
        "SELECT id FROM alerts WHERE pattern=? AND direction=? AND interval=? AND timestamp>?",
        (body.get("pattern",""), body.get("direction",""), iv, window)
    ).fetchone()
    if recent:
        conn.close()
        return {"status":"skip","reason":"duplicate","id":recent[0]}

    conn.execute(
        "INSERT INTO alerts (timestamp,ticker,interval,pattern,direction,price,verdict,raw) VALUES (?,?,?,?,?,?,?,?)",
        (now, body.get("ticker","XAUUSD"), iv,
         body.get("pattern", body.get("type","UNKNOWN")), body.get("direction",""),
         price_val, body.get("verdict","WAIT"), json.dumps(body))
    )
    conn.commit()
    conn.close()
    return {"status":"ok","type":"PA_SIGNAL","pattern":body.get("pattern","")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))


# ═══════════════════════════════════════════════════════════════════
#  DASHBOARD HTML — War Room HUD v3.0
# ═══════════════════════════════════════════════════════════════════
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>💎 DIAMOND TRADER — War Room v3.0</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#060810;--bg1:#0a0e1a;--bg2:#101828;--bg3:#141e2e;
  --border:#1e2d44;--border2:#2a3d5a;
  --green:#00e676;--green2:#00c853;--red:#ff3d00;--red2:#d50000;
  --yellow:#ffea00;--orange:#ff9100;--cyan:#00e5ff;
  --white:#f0f4ff;--muted:#5a6e88;--muted2:#3a4d64;
  --font:'JetBrains Mono',monospace;
}
body{background:var(--bg);color:var(--white);font-family:var(--font);
  font-size:12px;height:100vh;display:flex;flex-direction:column;overflow:hidden}

/* TOPBAR */
#topbar{height:42px;background:var(--bg1);border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 16px;gap:16px;flex-shrink:0}
.brand{font-weight:800;font-size:14px;color:var(--yellow);letter-spacing:2px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}
.dot.live{background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:.4}50%{opacity:1}}
#price-hud{font-weight:700;font-size:15px;padding:3px 10px;border-radius:5px;
  border:1px solid var(--border);color:var(--muted)}
#price-hud.up{color:var(--green);border-color:var(--green)}
#price-hud.down{color:var(--red);border-color:var(--red)}
.topbar-item{font-size:11px;color:var(--muted);display:flex;align-items:center;gap:5px}
.topbar-item span{color:var(--white);font-weight:700}
.sp{flex:1}

/* NEWS GUARD BANNER */
#news-banner{display:none;background:var(--orange);color:#000;font-weight:800;
  text-align:center;padding:5px;font-size:12px;letter-spacing:1px;flex-shrink:0;
  animation:blink-bg 1s infinite}
@keyframes blink-bg{0%,100%{opacity:1}50%{opacity:.6}}

/* MAIN 3-COLUMN GRID */
#war-room{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;
  padding:10px;flex:1;min-height:0;overflow:hidden}

/* CARD */
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;
  padding:10px 12px;display:flex;flex-direction:column;gap:6px;overflow:hidden}
.card-title{font-size:10px;font-weight:700;color:var(--muted);letter-spacing:1.5px;
  text-transform:uppercase;border-bottom:1px solid var(--border);padding-bottom:5px;margin-bottom:2px}

/* ═══ COL 1 ═══════════════════════════════════════════════════ */
#col1{display:flex;flex-direction:column;gap:8px;overflow-y:auto}

/* TF Pattern Status */
.tf-group-label{font-size:9px;color:var(--cyan);letter-spacing:1px;
  padding:2px 0;margin-top:4px;border-bottom:1px solid var(--muted2)}
.tf-row{display:flex;align-items:center;gap:6px;padding:5px 6px;
  border-radius:4px;border:1px solid transparent;transition:.2s}
.tf-row.buy{border-color:rgba(0,230,118,.25);background:rgba(0,230,118,.04)}
.tf-row.sell{border-color:rgba(255,61,0,.25);background:rgba(255,61,0,.04)}
.tf-label{width:30px;font-weight:800;font-size:11px}
.tf-arrow{width:14px;text-align:center;font-size:13px}
.tf-arrow.b{color:var(--green)}
.tf-arrow.s{color:var(--red)}
.tf-pat{flex:1;font-size:11px;color:var(--muted)}
.tf-row.buy .tf-pat{color:var(--green)}
.tf-row.sell .tf-pat{color:var(--red)}
.tf-px{font-size:10px;color:var(--muted2)}
.tf-footer{display:flex;justify-content:space-between;padding:6px 6px 2px;
  border-top:1px solid var(--border);margin-top:2px;font-weight:700;font-size:11px}
.tf-bull{color:var(--green)}.tf-bear{color:var(--red)}

/* Bias Status */
.bias-group{display:flex;flex-direction:column;gap:3px}
.bias-row{display:flex;justify-content:space-between;align-items:center;
  padding:5px 8px;border-radius:4px;background:var(--bg3);border:1px solid var(--border)}
.bias-tf-label{font-size:10px;color:var(--muted);width:90px}
.bias-val{font-weight:800;font-size:12px}
.bias-val.buy{color:var(--green)}.bias-val.sell{color:var(--red)}
.bias-val.conflict{color:var(--orange)}.bias-val.neutral{color:var(--muted)}
#bias-now-box{margin-top:4px;padding:8px;border-radius:6px;text-align:center;
  background:var(--bg3);border:2px solid var(--border)}
#bias-now-val{font-size:20px;font-weight:800;color:var(--muted)}
#bias-now-val.buy{color:var(--green)}.#bias-now-val.sell{color:var(--red)}

/* ═══ COL 2 ═══════════════════════════════════════════════════ */
#col2{display:flex;flex-direction:column;gap:8px;overflow-y:auto}

/* Structure Monitor */
.struct-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px}
.struct-cell{background:var(--bg3);border:1px solid var(--border);
  border-radius:5px;padding:6px 8px;min-height:56px}
.sc-tf{font-size:10px;font-weight:800;color:var(--muted);margin-bottom:3px}
.sc-state{font-size:11px;font-weight:800}
.sc-state.up{color:var(--green)}.sc-state.down{color:var(--red)}
.sc-state.sw{color:var(--yellow)}.sc-state.brk{color:var(--red);animation:blink-txt .7s infinite}
@keyframes blink-txt{0%,100%{opacity:1}50%{opacity:.2}}
.sc-range{font-size:9px;color:var(--muted);margin-top:2px;line-height:1.4}

/* News Panel */
.news-item{padding:5px 8px;border-radius:4px;background:var(--bg3);
  border-left:3px solid var(--muted2);margin-bottom:4px}
.news-item.high{border-left-color:var(--red)}.news-item.medium{border-left-color:var(--orange)}
.news-title{font-size:11px;font-weight:700;margin-bottom:1px}
.news-meta{font-size:10px;color:var(--muted);display:flex;gap:8px}
.news-countdown{font-weight:800;color:var(--orange)}
#no-news{color:var(--muted);font-size:11px;text-align:center;padding:10px}

/* ═══ COL 3 ═══════════════════════════════════════════════════ */
#col3{display:flex;flex-direction:column;gap:8px;overflow-y:auto}

/* Verdict Box */
#verdict-box{font-size:22px;font-weight:800;letter-spacing:2px;
  padding:14px;border-radius:7px;text-align:center;
  background:var(--bg3);border:2px solid var(--border);color:var(--muted)}
#verdict-box.ready-buy{color:#000;background:var(--green2);border-color:var(--green);
  box-shadow:0 0 20px rgba(0,200,83,.4)}
#verdict-box.ready-sell{color:var(--white);background:var(--red2);border-color:var(--red);
  box-shadow:0 0 20px rgba(213,0,0,.4)}
#verdict-box.news-block{color:#000;background:var(--orange);border-color:var(--orange);animation:blink-bg 1s infinite}
#verdict-box.standby{color:var(--muted)}

/* Target Params */
.param-row{display:flex;justify-content:space-between;align-items:center;
  padding:6px 0;border-bottom:1px solid rgba(255,255,255,.03)}
.param-row:last-child{border-bottom:none}
.p-label{font-size:10px;color:var(--muted)}
.p-val{font-weight:800;font-size:13px}
.p-val.entry{color:var(--yellow)}.p-val.sl{color:var(--red)}.p-val.tp{color:var(--green)}
.p-val.pat{color:var(--cyan);font-size:11px}

/* Zone Panel */
.zone-row{padding:6px 8px;border-radius:5px;background:var(--bg3);
  border:1px solid var(--border);margin-bottom:4px}
.zone-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.zone-type{font-size:10px;font-weight:800}
.zone-type.DZ{color:var(--green)}.zone-type.SZ{color:var(--red)}
.zone-tag{font-size:9px;padding:1px 5px;border-radius:3px;font-weight:700}
.zone-tag.TIGHT_SL{background:rgba(0,230,118,.15);color:var(--green);border:1px solid var(--green)}
.zone-tag.WIDE_REFINE{background:rgba(255,145,0,.15);color:var(--orange);border:1px solid var(--orange)}
.zone-range{font-size:11px;font-weight:700;color:var(--white)}
.zone-dist{font-size:10px;color:var(--muted)}
.zone-dist.alert{color:var(--orange);font-weight:800;animation:blink-txt .7s infinite}

/* RR Calculator */
#rr-card .balance-row{display:flex;align-items:center;gap:6px;margin-bottom:8px}
#rr-card input{background:var(--bg3);border:1px solid var(--border);border-radius:4px;
  color:var(--white);font-family:var(--font);font-size:12px;padding:4px 8px;width:100px}
#rr-card select{background:var(--bg3);border:1px solid var(--border);border-radius:4px;
  color:var(--white);font-family:var(--font);font-size:12px;padding:4px 6px}
.rr-row{display:flex;justify-content:space-between;padding:4px 0;
  border-bottom:1px solid rgba(255,255,255,.03)}
.rr-label{font-size:10px;color:var(--muted)}
.rr-val{font-weight:800;font-size:12px}
.rr-risk{color:var(--red)}.rr-reward{color:var(--green)}.rr-lot{color:var(--cyan)}

/* CF Counter */
#cf-box{display:flex;align-items:center;justify-content:space-between;
  background:var(--bg3);border-radius:5px;padding:8px 12px;border:1px solid var(--border)}
#cf-num{font-size:22px;font-weight:800;color:var(--muted)}
#cf-num.active{color:var(--green)}
#cf-badge{font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;background:rgba(255,255,255,.05)}
#cf-badge.pass{background:rgba(0,230,118,.15);color:var(--green);border:1px solid var(--green)}

/* OVL Meter */
#ovl-bar-wrap{height:8px;border-radius:4px;background:var(--bg3);border:1px solid var(--border);overflow:hidden;margin-top:3px}
#ovl-bar{height:100%;width:0%;background:var(--green);border-radius:4px;transition:.4s}
#ovl-bar.warn{background:var(--orange)}
#ovl-bar.danger{background:var(--red)}

::-webkit-scrollbar{width:3px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
</style>
</head>
<body>

<div id="topbar">
  <div class="brand">💎 DIAMOND TRADER v3.0</div>
  <div class="topbar-item"><div id="ws-dot" class="dot"></div><span id="ws-status">CONNECTING</span></div>
  <div class="topbar-item">PAXG <div id="price-hud"><span id="paxg-price">—</span></div></div>
  <div class="topbar-item">GRID <span id="top-grid">—</span></div>
  <div class="topbar-item">OVL <span id="top-ovl">—</span></div>
  <div class="topbar-item">THB <span id="top-thb">—</span></div>
  <div class="sp"></div>
  <div class="topbar-item">UTC <span id="top-time">—</span></div>
</div>
<div id="news-banner">⛔ NEWS BLOCK — <span id="news-banner-txt"></span></div>

<div id="war-room">

  <!-- ══ COL 1: MATRIX PA & BIAS ══════════════════════════════ -->
  <div id="col1">
    <div class="card">
      <div class="card-title">📊 TF Pattern Status</div>
      <div class="tf-group-label">◆ HIGHER TIMEFRAME</div>
      <div id="tf-higher"></div>
      <div class="tf-group-label">◆ INTERMEDIATE TIMEFRAME</div>
      <div id="tf-inter"></div>
      <div class="tf-group-label">◆ LOWER TIMEFRAME</div>
      <div id="tf-lower"></div>
      <div class="tf-footer">
        <span class="tf-bull">▲ BULLISH: <span id="bull-count">0</span></span>
        <span class="tf-bear">▼ BEARISH: <span id="bear-count">0</span></span>
      </div>
    </div>
    <div class="card">
      <div class="card-title">🧭 Bias Status Engine</div>
      <div class="bias-group">
        <div class="bias-row">
          <span class="bias-tf-label">Higher TF (MN/W/D)</span>
          <span class="bias-val neutral" id="bias-higher">—</span>
        </div>
        <div class="bias-row">
          <span class="bias-tf-label">Intermediate (H4/H1)</span>
          <span class="bias-val neutral" id="bias-inter">—</span>
        </div>
        <div class="bias-row">
          <span class="bias-tf-label">Lower (M30–M1)</span>
          <span class="bias-val neutral" id="bias-lower">—</span>
        </div>
      </div>
      <div id="bias-now-box">
        <div style="font-size:9px;color:var(--muted);margin-bottom:4px">BIAS NOW</div>
        <div id="bias-now-val">—</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">🛡️ CF M5 Counter</div>
      <div id="cf-box">
        <div id="cf-num">0 / 3</div>
        <div id="cf-badge">WAITING</div>
      </div>
    </div>
  </div>

  <!-- ══ COL 2: STRUCTURE + NEWS ══════════════════════════════ -->
  <div id="col2">
    <div class="card">
      <div class="card-title">🏗️ Multi-TF Structure Monitor</div>
      <div class="struct-grid" id="struct-grid"></div>
    </div>
    <div class="card">
      <div class="card-title">📰 Economic News (USD)</div>
      <div id="news-list"><div id="no-news">Fetching news...</div></div>
    </div>
    <div class="card">
      <div class="card-title">📜 Live Signal Feed</div>
      <div id="alert-list" style="overflow-y:auto;max-height:200px"></div>
    </div>
  </div>

  <!-- ══ COL 3: EXECUTION COCKPIT ════════════════════════════ -->
  <div id="col3">
    <div class="card">
      <div class="card-title">⚡ Action Verdict</div>
      <div id="verdict-box" class="standby">STANDBY</div>
    </div>
    <div class="card">
      <div class="card-title">🎯 Target Parameters</div>
      <div class="param-row"><span class="p-label">PATTERN</span><span class="p-val pat" id="ex-pat">—</span></div>
      <div class="param-row"><span class="p-label">ENTRY</span><span class="p-val entry" id="ex-entry">—</span></div>
      <div class="param-row"><span class="p-label">STOP LOSS</span><span class="p-val sl" id="ex-sl">—</span></div>
      <div class="param-row"><span class="p-label">TAKE PROFIT</span><span class="p-val tp" id="ex-tp">—</span></div>
      <div class="param-row"><span class="p-label">SL (pts)</span><span class="p-val" id="ex-slpts" style="color:var(--muted)">—</span></div>
    </div>
    <div class="card" id="rr-card">
      <div class="card-title">💰 RR Calculator (THB)</div>
      <div class="balance-row">
        <span style="color:var(--muted);font-size:10px">Balance</span>
        <input type="number" id="balance-input" value="1000" min="100" step="100">
        <select id="currency-sel">
          <option value="USD">USD</option>
          <option value="THB">THB</option>
        </select>
      </div>
      <div class="rr-row"><span class="rr-label">USDTHB Rate</span><span class="rr-val" id="rr-thb-rate">36.50</span></div>
      <div class="rr-row"><span class="rr-label">RISK (THB)</span><span class="rr-val rr-risk" id="rr-risk">—</span></div>
      <div class="rr-row"><span class="rr-label">REWARD (THB)</span><span class="rr-val rr-reward" id="rr-reward">—</span></div>
      <div class="rr-row"><span class="rr-label">Suggest Lot</span><span class="rr-val rr-lot" id="rr-lot">—</span></div>
    </div>
    <div class="card">
      <div class="card-title">🏭 H4 Supply / Demand Zones</div>
      <div id="zone-list"><div style="color:var(--muted);font-size:11px;text-align:center;padding:10px">No zones yet</div></div>
    </div>
    <div class="card">
      <div class="card-title">📡 Grid OVL Meter</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span style="color:var(--muted);font-size:10px">Distance to grid</span>
        <span id="ovl-val" style="font-weight:800;font-size:13px;color:var(--green)">— pts</span>
      </div>
      <div id="ovl-bar-wrap"><div id="ovl-bar"></div></div>
      <div style="display:flex;justify-content:space-between;margin-top:2px;font-size:9px;color:var(--muted2)">
        <span>0</span><span>150</span><span>300+</span>
      </div>
    </div>
  </div>
</div>

<script>
// ── Constants ──────────────────────────────────────────────────
const TF_HIGHER = [{id:'MN',name:'MN'},{id:'W',name:'W1'},{id:'D',name:'D1'}];
const TF_INTER  = [{id:'H4',name:'H4'},{id:'H1',name:'H1'}];
const TF_LOWER  = [{id:'M30',name:'M30'},{id:'M15',name:'M15'},{id:'M5',name:'M5'},{id:'M1',name:'M1'}];
const STRUCT_TF = ['H4','H1','M30','M15','M5','M1'];
const TTS = window.speechSynthesis;

let state = {};
let lastAlertId = 0;
let lastZoneCheck = {};
let balanceUSD = 1000;
let usdthb = 36.5;
let slPts = 300;
let entryPrice = 0;
let direction = '';

// ── TF Row renderer ───────────────────────────────────────────
function renderTfGroup(tfs, containerId) {
  const c = document.getElementById(containerId);
  c.innerHTML = '';
  tfs.forEach(tf => {
    const d = (state.tf_rows||[]).find(r=>r.interval===tf.id) || {};
    const dir = d.direction || '';
    const cls = dir==='BUY'?'buy':dir==='SELL'?'sell':'';
    const arrow = dir==='BUY'?'▲':dir==='SELL'?'▼':'·';
    const acls  = dir==='BUY'?'b':dir==='SELL'?'s':'';
    const px = d.price ? parseFloat(d.price).toFixed(2) : '';
    c.innerHTML += `<div class="tf-row ${cls}">
      <span class="tf-label">${tf.name}</span>
      <span class="tf-arrow ${acls}">${arrow}</span>
      <span class="tf-pat">${d.pattern||'—'}</span>
      <span class="tf-px">${px}</span>
    </div>`;
  });
}

// ── Bias renderer ─────────────────────────────────────────────
function biasClass(v){
  if(!v||v==='NEUTRAL'||v==='—') return 'neutral';
  if(v==='CONFLICT'||v.endsWith('?')) return 'conflict';
  if(v==='BUY') return 'buy'; return 'sell';
}
function biasLabel(v){
  if(!v||v==='NEUTRAL') return '—';
  if(v==='BUY') return '▲ BUY'; if(v==='SELL') return '▼ SALE';
  if(v==='CONFLICT') return '⚡ CONFLICT';
  return v;
}
function renderBias(b){
  if(!b) return;
  ['higher','inter','lower'].forEach(k=>{
    const el = document.getElementById('bias-'+k);
    if(!el) return;
    const val = k==='inter'?b.intermediate:b[k]||'';
    el.className = 'bias-val '+biasClass(val);
    el.textContent = biasLabel(val);
  });
  const bnv = document.getElementById('bias-now-val');
  const box = document.getElementById('bias-now-box');
  const v = b.bias_now||'';
  bnv.className = 'bias-val '+biasClass(v);
  bnv.style.fontSize = '20px';
  bnv.style.fontWeight = '800';
  bnv.textContent = biasLabel(v);
  box.style.borderColor = v==='BUY'?'var(--green)':v==='SELL'?'var(--red)':'var(--border)';
}

// ── Structure Monitor ─────────────────────────────────────────
function structLabel(s){
  if(s==='TREND_UP')   return {text:'▲ TREND UP',cls:'up'};
  if(s==='TREND_DOWN') return {text:'▼ TREND DOWN',cls:'down'};
  if(s==='SIDEWAY')    return {text:'⇄ SIDEWAY',cls:'sw'};
  if(s==='BREAKOUT')   return {text:'💥 BREAKOUT',cls:'brk'};
  return {text:'—',cls:''};
}
function renderStructure(){
  const g = document.getElementById('struct-grid');
  g.innerHTML = '';
  STRUCT_TF.forEach(iv=>{
    const s = (state.structure||{})[iv]||{};
    const {text,cls} = structLabel(s.structure||'');
    let range = '';
    if(s.structure==='SIDEWAY'){
      const hw = s.sw_high_wick, lw = s.sw_low_wick;
      const hb = s.sw_high_body, lb = s.sw_low_body;
      if(hw&&lw) range += `<div>Wick: ${parseFloat(hw).toFixed(2)}↔${parseFloat(lw).toFixed(2)} (${Math.round((hw-lw)*100)}pts)</div>`;
      if(hb&&lb) range += `<div>Body: ${parseFloat(hb).toFixed(2)}↔${parseFloat(lb).toFixed(2)} (${Math.round((hb-lb)*100)}pts)</div>`;
    }
    if(s.structure==='TREND_UP'&&s.hh)   range=`<div>HH ${parseFloat(s.hh).toFixed(2)} / HL ${parseFloat(s.hl||0).toFixed(2)}</div>`;
    if(s.structure==='TREND_DOWN'&&s.ll) range=`<div>LH ${parseFloat(s.lh||0).toFixed(2)} / LL ${parseFloat(s.ll).toFixed(2)}</div>`;
    g.innerHTML += `<div class="struct-cell">
      <div class="sc-tf">${iv}</div>
      <div class="sc-state ${cls}">${text}</div>
      <div class="sc-range">${range}</div>
    </div>`;
  });
}

// ── News renderer ─────────────────────────────────────────────
function renderNews(news){
  const list = document.getElementById('news-list');
  if(!news||!news.length){list.innerHTML='<div id="no-news">No USD news found</div>';return;}
  list.innerHTML='';
  const now = Date.now();
  news.forEach(item=>{
    let countdown='';
    try{
      const dt = new Date(item.event_time).getTime();
      const diff = Math.round((dt-now)/1000);
      if(diff>0) countdown=`T-${Math.floor(diff/60)}m`;
      else countdown=`T+${Math.floor(-diff/60)}m`;
    }catch(e){}
    list.innerHTML+=`<div class="news-item ${item.impact}">
      <div class="news-title">${item.title}</div>
      <div class="news-meta">
        <span>${item.impact.toUpperCase()}</span>
        <span>${(item.event_time||'').substring(11,16)} UTC</span>
        <span class="news-countdown">${countdown}</span>
      </div>
    </div>`;
  });
}

// ── Verdict renderer ──────────────────────────────────────────
function renderVerdict(v, dir){
  const box = document.getElementById('verdict-box');
  if(v==='NEWS BLOCK'){box.className='news-block';box.textContent='⛔ NEWS BLOCK';return;}
  if(v&&v.startsWith('READY BUY')){box.className='ready-buy';box.textContent='✅ READY BUY';return;}
  if(v&&v.startsWith('READY SELL')){box.className='ready-sell';box.textContent='🔴 READY SELL';return;}
  box.className='standby';box.textContent='STANDBY';
}

// ── RR Calculator ─────────────────────────────────────────────
function calcRR(){
  const balInput = parseFloat(document.getElementById('balance-input').value)||1000;
  const cur = document.getElementById('currency-sel').value;
  const balUSD = cur==='THB' ? balInput/usdthb : balInput;
  const risk2pct = balUSD*0.02;
  const slUSD = slPts*0.01;
  const sugLot = slUSD>0 ? (risk2pct/(slUSD*100)) : 0;
  const riskUSD  = sugLot*slUSD*100;
  const riskTHB  = riskUSD*usdthb;
  const rewardTHB= riskTHB*3;
  document.getElementById('rr-thb-rate').textContent = usdthb.toFixed(2);
  document.getElementById('rr-risk').textContent   = riskTHB>0?`-${riskTHB.toFixed(0)} ฿`:'—';
  document.getElementById('rr-reward').textContent = rewardTHB>0?`+${rewardTHB.toFixed(0)} ฿`:'—';
  document.getElementById('rr-lot').textContent    = sugLot>0?sugLot.toFixed(2):'—';
}

// ── Zone renderer ─────────────────────────────────────────────
function renderZones(zones){
  const list = document.getElementById('zone-list');
  if(!zones||!zones.length){list.innerHTML='<div style="color:var(--muted);font-size:11px;text-align:center;padding:8px">No H4 zones received</div>';return;}
  list.innerHTML='';
  zones.forEach(z=>{
    const distCls = z.proximity_alert?'zone-dist alert':'zone-dist';
    const distTxt = z.dist_pts!=null?`${z.dist_pts} pts away`:'—';
    // TTS on proximity
    const key = z.zone_type+'_'+z.interval;
    if(z.proximity_alert && !lastZoneCheck[key]){
      speak(z.zone_type==='DZ'?'H4 Demand Check':'H4 Supply Check');
    }
    lastZoneCheck[key]=z.proximity_alert;
    list.innerHTML+=`<div class="zone-row">
      <div class="zone-header">
        <span class="zone-type ${z.zone_type}">${z.zone_type==='DZ'?'🟢 DEMAND':'🔴 SUPPLY'} [${z.interval}]</span>
        <span class="zone-tag ${z.tag}">${z.tag==='TIGHT_SL'?'🔥 TIGHT SL':'⚠️ WIDE'}</span>
      </div>
      <div class="zone-range">${parseFloat(z.lower).toFixed(2)} — ${parseFloat(z.upper).toFixed(2)}</div>
      <div class="${distCls}">${distTxt} · Width: ${z.width_pts}pts</div>
    </div>`;
  });
}

// ── OVL Bar ───────────────────────────────────────────────────
function updateOvl(pts){
  const el = document.getElementById('ovl-val');
  const bar= document.getElementById('ovl-bar');
  if(pts==null){el.textContent='— pts';return;}
  el.textContent = pts+' pts';
  const pct = Math.min(pts/300*100,100);
  bar.style.width = pct+'%';
  if(pts<=150){el.style.color='var(--green)';bar.className='';bar.style.background='var(--green)'}
  else if(pts<=300){el.style.color='var(--orange)';bar.className='warn';bar.style.background='var(--orange)'}
  else{el.style.color='var(--red)';bar.className='danger';bar.style.background='var(--red)'}
  document.getElementById('top-ovl').textContent=pts+'pts';
}

// ── Entry/SL/TP display ───────────────────────────────────────
function updateExec(alert){
  const p = parseFloat(alert.close||alert.price||0);
  if(!p) return;
  entryPrice=p; direction=alert.direction||'';
  const isBuy = direction==='BUY';
  const sl = isBuy ? p-3.0 : p+3.0;
  const tp = isBuy ? p+9.0 : p-9.0;
  slPts = 300;
  document.getElementById('ex-pat').textContent   = alert.pattern||'—';
  document.getElementById('ex-entry').textContent = p.toFixed(2);
  document.getElementById('ex-sl').textContent    = sl.toFixed(2);
  document.getElementById('ex-tp').textContent    = tp.toFixed(2);
  document.getElementById('ex-slpts').textContent = slPts+' pts';
  calcRR();
}

// ── Alert feed ────────────────────────────────────────────────
function addAlert(d, prepend){
  const list = document.getElementById('alert-list');
  const el = document.createElement('div');
  el.style.cssText='padding:5px 8px;border-radius:4px;margin-bottom:4px;font-size:11px;display:flex;justify-content:space-between;align-items:center;';
  const buy=d.direction==='BUY';
  el.style.borderLeft=`3px solid ${buy?'var(--green)':'var(--red)'}`;
  el.style.background='var(--bg3)';
  el.innerHTML=`<span style="color:${buy?'var(--green)':'var(--red)'};font-weight:700">${buy?'▲':'▼'} [${d.interval||'?'}] ${d.pattern||'PA'}</span>
    <span style="color:var(--yellow);font-weight:800">${d.price?parseFloat(d.price).toFixed(2):''}</span>`;
  if(prepend&&list.firstChild) list.insertBefore(el,list.firstChild);
  else list.appendChild(el);
  while(list.children.length>12) list.removeChild(list.lastChild);
}

// ── TTS ───────────────────────────────────────────────────────
function speak(txt){
  if(!TTS) return;
  const u=new SpeechSynthesisUtterance(txt);u.lang='en-US';u.rate=1.1;
  TTS.cancel(); TTS.speak(u);
}

// ── News guard banner ─────────────────────────────────────────
function updateNewsGuard(g){
  const b=document.getElementById('news-banner');
  const t=document.getElementById('news-banner-txt');
  if(g&&g.blocked){
    b.style.display='block';
    t.textContent=g.reason||'High Impact Event';
  } else {
    b.style.display='none';
  }
}

// ── Clock ─────────────────────────────────────────────────────
setInterval(()=>{
  document.getElementById('top-time').textContent=
    new Date().toUTCString().slice(17,25)+' UTC';
},1000);

// ── Main poll ─────────────────────────────────────────────────
let lastPrice=0;
async function pollState(){
  const dot=document.getElementById('ws-dot');
  const lbl=document.getElementById('ws-status');
  try{
    const d = await (await fetch('/dashboard-state')).json();
    state = d;
    dot.className='dot live'; lbl.textContent='LIVE';

    // Price
    if(d.price){
      const p=parseFloat(d.price);
      const el=document.getElementById('paxg-price');
      const hud=document.getElementById('price-hud');
      el.textContent=p.toLocaleString(undefined,{minimumFractionDigits:2});
      hud.className=p>lastPrice?'up':p<lastPrice?'down':'';
      lastPrice=p;
      document.getElementById('top-grid').textContent=(d.grid||0).toFixed(2);
    }

    // USDTHB
    if(d.usdthb){ usdthb=d.usdthb; document.getElementById('top-thb').textContent=usdthb.toFixed(2); }

    // TF rows
    renderTfGroup(TF_HIGHER,'tf-higher');
    renderTfGroup(TF_INTER,'tf-inter');
    renderTfGroup(TF_LOWER,'tf-lower');
    document.getElementById('bull-count').textContent=d.bull_count||0;
    document.getElementById('bear-count').textContent=d.bear_count||0;

    // Bias
    renderBias(d.bias);

    // Structure
    renderStructure();

    // OVL
    updateOvl(d.ovl_pts);

    // CF
    const cfn=document.getElementById('cf-num');
    const cfb=document.getElementById('cf-badge');
    const cf=d.cf||{};
    cfn.textContent=(cf.cf_count||0)+' / 3';
    if(cf.cf_pass){cfn.className='active';cfb.className='pass';cfb.textContent='PASS';}
    else{cfn.className='';cfb.className='';cfb.textContent=cf.cf_status||'WAITING';}

    // Verdict + news guard
    updateNewsGuard(d.news_guard);
    renderVerdict(d.verdict, direction);

    // News
    renderNews(d.news);

    // Zones
    renderZones(d.zones||[]);

  }catch(e){dot.className='dot';lbl.textContent='OFFLINE';}
}

async function pollAlerts(){
  try{
    const rows=await (await fetch('/alerts?limit=20')).json();
    if(!rows.length) return;
    if(lastAlertId===0&&rows.length){
      rows.slice(0,10).forEach(d=>addAlert(d,false));
      updateExec(rows[0]);
      lastAlertId=rows[0].id;
      calcRR();
      return;
    }
    const news=rows.filter(d=>d.id>lastAlertId);
    if(news.length){
      news.reverse().forEach(d=>{addAlert(d,true);updateExec(d);});
      lastAlertId=news[news.length-1].id;
      calcRR();
      // TTS for new signal
      const last=news[news.length-1];
      if(last.direction) speak(last.direction==='BUY'?'Buy signal':'Sell signal');
    }
  }catch(e){}
}

// ── Events ────────────────────────────────────────────────────
document.getElementById('balance-input').addEventListener('input', calcRR);
document.getElementById('currency-sel').addEventListener('change', calcRR);

// ── Init ──────────────────────────────────────────────────────
setInterval(pollState,  2000);
setInterval(pollAlerts, 1500);
pollState();
pollAlerts();
calcRR();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard(): return DASHBOARD_HTML
