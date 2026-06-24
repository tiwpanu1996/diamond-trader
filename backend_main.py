"""
DIAMOND TRADER — backend_main.py v3.1.1
FastAPI + War Room HUD Dashboard (3-Zone Structure)
SSOT: PA_SPEC_MASTER_v2.1 + SNIPER_HUD_BIBLE_v1.1

Change Log v3.1 → v3.1.1:
  - Fix: Verdict NO-TRADE fires when VIP OFF (OVL > 300 pts) per SSOT §3.6 filter order
  - Fix: last_signal tracker populates Zone A pattern row (▲/▼ PatX [TF])
  - Fix: JS vbox.className now handles 'no-trade' class correctly
  - Fix: CF M5 default display '🔴 — 0/3' when no signal received
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import sqlite3, json, os, httpx, asyncio, math, logging

# ── Logging setup ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
log = logging.getLogger("diamond")

DB_PATH      = os.getenv("DB_PATH", "diamond_trader.db")
FINNHUB_KEY  = os.getenv("FINNHUB_KEY", "")

# ── In-memory state ──────────────────────────────────────────────
last_price: dict  = {"price": 0.0, "updated_at": None}
usdthb_rate: dict = {"rate": 36.5, "updated_at": None}

# CF State v3.1: Enhanced with color_state
cf_state: dict = {
    "cf_count": 0, "cf_pass": False, "cf_dir": "neutral",
    "cf_status": "WAIT", "color_state": "RED",  # GREEN / YELLOW / RED
    "grid_level": 0.0, "close": 0.0,
    "ticker": "", "updated_at": None,
}

structure_state: dict = {}
zones: list = []
news_guard: dict = {"blocked": False, "reason": "", "unblock_at": None}
news_cache: list = []

# Last PA signal for Zone A pattern display
last_signal: dict = {
    "pattern": "", "direction": "", "interval": "", "price": 0.0, "updated_at": None
}

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
    try:
        conn.execute("ALTER TABLE alerts ADD COLUMN pattern TEXT")
        log.info("Migration: added column 'pattern' to alerts")
    except Exception:
        pass
    conn.commit()
    conn.close()

# ── Helpers ──────────────────────────────────────────────────────

def _compute_cf_color_state(count, passed):
    """Compute color_state for CF M5 per SSOT §3.1"""
    if passed and count >= 3:
        return "GREEN"      # ✓ 3/3 READY
    elif count >= 1 and count < 3:
        return "YELLOW"     # ⏳ 1-2/3 WAIT
    else:
        return "RED"        # ❌ 0/3 NO-TRADE

def _cf_display_v31(count, passed, direction):
    """Enhanced CF display with direction + color emoji"""
    d = "BUY" if direction == "buy" else "SELL" if direction == "sell" else "—"
    color = _compute_cf_color_state(count, passed)
    emoji = "🟢" if color == "GREEN" else "🟡" if color == "YELLOW" else "🔴"
    
    if count == 0:
        return {"display": f"{emoji} — 0/3", "color": color}
    if passed:
        return {"display": f"{emoji} ✓ {d} 3/3 READY", "color": color}
    return {"display": f"{emoji} ⏳ {d} {count}/3", "color": color}

def _nearest_grid(price):
    return round(price / 5.0) * 5.0

def _ovl_points(price):
    grid = _nearest_grid(price)
    return round(abs(price - grid) * 100)

def _vip_station_check(price):
    """Check if price is ON STATION (VIP) — within 300 pts of grid"""
    if price <= 0:
        return False, "—"
    ovl = _ovl_points(price)
    if ovl <= 300:
        return True, f"ON STATION ✓ ({ovl} pts)"
    return False, f"OFF ✗ ({ovl} pts)"

def _bias_vote(intervals, tf_state):
    bull = sum(1 for i in intervals if tf_state.get(i, {}).get("direction") == "BUY")
    bear = sum(1 for i in intervals if tf_state.get(i, {}).get("direction") == "SELL")
    total = bull + bear
    if total == 0: return "NEUTRAL"
    if bull > bear: return "BUY"
    if bear > bull: return "SELL"
    return "CONFLICT"

def _compute_bias(tf_state):
    higher_bias       = _bias_vote(["MN", "W", "D"], tf_state)
    h4_dir = tf_state.get("H4", {}).get("direction", "")
    h1_dir = tf_state.get("H1", {}).get("direction", "")
    if h4_dir == h1_dir and h4_dir: inter_bias = h4_dir
    elif h4_dir: inter_bias = h4_dir
    else: inter_bias = "NEUTRAL"
    lower_intervals = ["M30", "M15", "M5", "M1"]
    bull = sum(1 for i in lower_intervals if tf_state.get(i, {}).get("direction") == "BUY")
    bear = sum(1 for i in lower_intervals if tf_state.get(i, {}).get("direction") == "SELL")
    if bull > bear:   lower_bias = "BUY"
    elif bear > bull: lower_bias = "SELL"
    else:             lower_bias = tf_state.get("M30", {}).get("direction", "CONFLICT") or "CONFLICT"
    if inter_bias == higher_bias and inter_bias not in ("NEUTRAL", "CONFLICT"):
        bias_now = inter_bias
    elif inter_bias not in ("NEUTRAL", "CONFLICT"):
        bias_now = inter_bias + "?"
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

def _zone_tag(width):
    if width <= 500: return "TIGHT_SL"
    return "WIDE_REFINE"

# ── Background Tasks ─────────────────────────────────────────────
async def fetch_usdthb():
    while True:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://api.exchangerate-api.com/v4/latest/USD")
                rate = r.json()["rates"].get("THB", 36.5)
                usdthb_rate["rate"]       = float(rate)
                usdthb_rate["updated_at"] = datetime.utcnow().isoformat()
        except Exception as e:
            log.warning("fetch_usdthb: %s", e)
        await asyncio.sleep(300)

async def fetch_economic_news():
    while True:
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            fetched = []
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
        except Exception as e:
            log.warning("fetch_news: %s", e)
        await asyncio.sleep(3600)

async def cleanup_breakout():
    while True:
        now = datetime.utcnow()
        for iv, st in list(structure_state.items()):
            if st.get("structure") == "BREAKOUT":
                ts = st.get("updated_at", "")
                try:
                    dt = datetime.fromisoformat(ts)
                    if (now - dt).total_seconds() > 900:
                        structure_state[iv]["structure"] = "SIDEWAY"
                except Exception:
                    pass
        await asyncio.sleep(60)

async def cleanup_old_alerts():
    while True:
        await asyncio.sleep(1800)
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
            count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            if count > 500:
                conn.execute("""
                    DELETE FROM alerts WHERE id NOT IN (
                        SELECT id FROM alerts ORDER BY id DESC LIMIT 500
                    )
                """)
                deleted = count - 500
                conn.commit()
                log.info("cleanup_alerts: deleted %d rows, kept 500", deleted)
            else:
                log.info("cleanup_alerts: %d rows OK, no cleanup needed", count)
            conn.close()
        except Exception as e:
            log.error("cleanup_alerts failed: %s", e)

@asynccontextmanager
async def lifespan(app):
    init_db()
    asyncio.create_task(fetch_usdthb())
    asyncio.create_task(fetch_economic_news())
    asyncio.create_task(cleanup_breakout())
    asyncio.create_task(cleanup_old_alerts())
    yield

app = FastAPI(title="DIAMOND TRADER v3.1.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── API Endpoints ─────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "DIAMOND TRADER", "version": "3.1.1"}

@app.get("/price")
async def get_price():
    if last_price["price"] > 0:
        return {"price": last_price["price"], "symbol": "XAUUSD", "updated_at": last_price["updated_at"]}
    return {"price": 0, "symbol": "XAUUSD", "status": "waiting_signal", "updated_at": None}

@app.get("/cf-status")
async def get_cf_status():
    cf_display = _cf_display_v31(cf_state["cf_count"], cf_state["cf_pass"], cf_state["cf_dir"])
    return {
        **cf_state,
        "display": cf_display["display"],
        "color_state": cf_display["color"],
    }

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
    """v3.1: Enhanced response with Zone A/B/C data"""
    _check_news_guard()
    price = last_price["price"]
    ovl   = _ovl_points(price) if price > 0 else None
    bias  = _compute_bias({iv: s for iv, s in structure_state.items()})

    # VIP Station check
    vip_on, vip_msg = _vip_station_check(price)

    # CF Display with color
    cf_display = _cf_display_v31(cf_state["cf_count"], cf_state["cf_pass"], cf_state["cf_dir"])

    # Zone A verdict logic (v3.1) — per SSOT §3.6 filter order
    # OVL > 300 = NO-TRADE regardless of CF
    if news_guard.get("blocked"):
        verdict = "NEWS BLOCK"
    elif not vip_on and price > 0:
        verdict = "NO-TRADE"
    elif cf_state["cf_pass"]:
        verdict = f"READY {cf_state['cf_dir'].upper()}"
    elif cf_state["cf_count"] > 0:
        verdict = "WAIT"
    else:
        verdict = "STANDBY"

    # Active zone proximity
    zone_proximity = []
    for z in zones:
        mid    = (z["upper"] + z["lower"]) / 2
        dist   = round(abs(price - mid) * 100) if price > 0 else None
        alert  = dist is not None and dist < 100
        width  = round((z["upper"] - z["lower"]) * 100)
        zone_proximity.append({**z, "dist_pts": dist, "proximity_alert": alert,
                                "width_pts": width, "tag": _zone_tag(width)})

    # TF summary
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
        # ── ZONE A: SNIPER SIGNALS ──
        "zone_a": {
            "cf_count": cf_state["cf_count"],
            "cf_pass": cf_state["cf_pass"],
            "cf_dir": cf_state["cf_dir"],
            "cf_display": cf_display["display"],
            "cf_color": cf_display["color"],
            "vip_on": vip_on,
            "vip_msg": vip_msg,
            "verdict": verdict,
            "pattern": last_signal["pattern"],
            "interval": last_signal["interval"],
            "pa_dir": last_signal["direction"],
        },
        # ── ZONE B: MARKET FLOW ──
        "zone_b": {
            "bias": bias,
            "tf_rows": tf_rows,
            "bull_count": bull,
            "bear_count": bear,
            "structure": structure_state,
        },
        # ── ZONE C: EXECUTION METER ──
        "zone_c": {
            "zones": zone_proximity,
            "ovl_pts": ovl,
            "news_guard": news_guard,
        },
        # Legacy support (deprecated v3.0 fields)
        "cf": cf_state,
        "cf_display": cf_display["display"],
        "bias": bias,
        "tf_rows": tf_rows,
        "bull_count": bull,
        "bear_count": bear,
        "structure": structure_state,
        "zones": zone_proximity,
        "news_guard": news_guard,
        "news": news_cache[:5],
        "verdict": verdict,
    }

@app.post("/alerts")
async def post_alert(request: Request):
    try: body = await request.json()
    except: return JSONResponse({"status":"error","msg":"invalid JSON"}, status_code=400)

    msg_type = body.get("type", "PA_SIGNAL")

    # ── CF_UPDATE ──
    if msg_type == "CF_UPDATE":
        count = int(body.get("cf_count", 0))
        passed = bool(body.get("cf_pass", False))
        direction = str(body.get("cf_dir", "neutral")).lower()
        
        cf_state.update({
            "cf_count": count,
            "cf_pass": passed,
            "cf_dir": direction,
            "cf_status": str(body.get("cf_status", "WAIT")),
            "color_state": _compute_cf_color_state(count, passed),
            "grid_level": float(body.get("grid_level", 0.0)),
            "close": float(body.get("close", 0.0)),
            "ticker": str(body.get("ticker", "")),
            "updated_at": datetime.utcnow().isoformat(),
        })
        cf_display = _cf_display_v31(count, passed, direction)
        log.info("CF_UPDATE count=%d pass=%s dir=%s color=%s", count, passed, direction, cf_display["color"])
        return {"status":"ok","type":"CF_UPDATE", **cf_display}

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
        log.info("STRUCT_UPDATE [%s] struct=%s dir=%s", iv, body.get("structure",""), body.get("direction",""))
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
        zones[:] = [z for z in zones if not (z["zone_type"]==zone["zone_type"] and z["interval"]==zone["interval"])]
        zones.append(zone)
        log.info("ZONE_UPDATE %s [%s] %.2f—%.2f", zone["zone_type"], zone["interval"], zone["lower"], zone["upper"])
        return {"status":"ok","type":"ZONE_UPDATE","zone":zone}

    # ── PA_SIGNAL ──
    if msg_type == "PA_SIGNAL":
        price = float(body.get("close", body.get("price", 0)))
        last_price["price"] = price
        last_price["updated_at"] = datetime.utcnow().isoformat()
        
        direction = str(body.get("direction", "")).upper()
        pattern = str(body.get("pattern", "PA"))
        interval = str(body.get("interval", "M5"))
        ticker = str(body.get("ticker", "XAUUSD"))

        # Update Zone A pattern display
        if direction in ("BUY", "SELL"):
            last_signal.update({
                "pattern": pattern, "direction": direction,
                "interval": interval, "price": price,
                "updated_at": datetime.utcnow().isoformat(),
            })
        
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
            conn.execute(
                "INSERT INTO alerts (timestamp,ticker,interval,pattern,direction,price,verdict,raw) VALUES (?,?,?,?,?,?,?,?)",
                (datetime.utcnow().isoformat(), ticker, interval, pattern, direction, price, "logged", json.dumps(body))
            )
            conn.commit()
            conn.close()
            log.info("PA_SIGNAL [%s] %s %s @ %.2f", interval, direction, pattern, price)
        except Exception as e:
            log.error("PA_SIGNAL DB insert: %s", e)
        
        return {"status":"ok","type":"PA_SIGNAL","price":price,"interval":interval,"pattern":pattern}

    return JSONResponse({"status":"error","msg":"unknown type"}, status_code=400)

# ── DASHBOARD HTML (v3.1 — Zone A/B/C Structure) ────────────────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>💎 DIAMOND TRADER v3.1.1 — War Room</title>
<style>
:root{
  --bg: #0a0e27;
  --bg2: #121929;
  --bg3: #1a1f3a;
  --border: #2a3050;
  --border2: #3a4060;
  --white: #e0e6ff;
  --muted: #8090a8;
  --muted2: #606070;
  --green: #00e676;
  --red: #ff5252;
  --orange: #ffb74d;
  --cyan: #4fc3f7;
  --yellow: #ffd54f;
  --font: "Menlo", "Monaco", monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--white);font-family:var(--font);font-size:12px;overflow-x:hidden}
a{color:var(--cyan);text-decoration:none}

/* ── Topbar ──────────────────────────────────────────────────────────────────────── */
#topbar{display:flex;align-items:center;height:36px;padding:0 12px;background:var(--bg2);
  border-bottom:1px solid var(--border);gap:16px}
.brand{font-weight:800;font-size:14px;color:var(--green);flex-grow:0}
.topbar-item{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted)}
.dot{width:6px;height:6px;border-radius:50%;background:var(--muted2);animation:pulse 1.5s infinite}
.dot.live{background:var(--green);animation:none}
@keyframes pulse{0%{opacity:0.3}50%{opacity:1}100%{opacity:0.3}}
.sp{flex-grow:1}
#price-hud{padding:2px 6px;border-radius:3px;background:var(--bg3);border:1px solid var(--border)}
#price-hud.up{color:var(--green)}
#price-hud.down{color:var(--red)}

/* ── News Banner ─────────────────────────────────────────────────────────────────── */
#news-banner{display:none;height:24px;background:rgba(255,82,82,.15);border-bottom:1px solid var(--red);
  padding:0 12px;align-items:center;color:var(--red);font-weight:700;font-size:10px;gap:6px}

/* ── War Room Grid (3-Zone Layout) ──────────────────────────────────────────────── */
#war-room{display:grid;grid-template-columns:1fr 1fr 1fr;grid-gap:12px;padding:12px;
  max-width:1600px;margin:0 auto;min-height:calc(100vh - 72px)}

/* ── Cards (Generic) ────────────────────────────────────────────────────────────── */
.card{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:12px;
  display:flex;flex-direction:column;gap:8px;overflow:hidden}
.card-title{font-weight:700;font-size:12px;color:var(--white);text-transform:uppercase;
  letter-spacing:0.5px;border-bottom:1px solid var(--border);padding-bottom:6px}

/* ── Zone A: SNIPER SIGNALS ──────────────────────────────────────────────────────── */
#zone-a{display:flex;flex-direction:column;gap:8px}
.zone-row{padding:6px;background:rgba(255,255,255,.02);border-radius:4px;border-left:2px solid var(--border)}
.zone-row-label{font-size:10px;color:var(--muted);text-transform:uppercase}
.zone-row-value{font-weight:700;font-size:13px;color:var(--white);margin-top:2px}
.zone-row-value.on{color:var(--green)}
.zone-row-value.off{color:var(--red)}

#verdict-box{padding:12px;border-radius:4px;text-align:center;font-size:16px;font-weight:800;
  background:rgba(0,0,0,.3);border:2px solid var(--border);color:var(--muted)}
#verdict-box.ready{background:rgba(0,230,118,.15);border-color:var(--green);color:var(--green)}
#verdict-box.wait{background:rgba(255,213,79,.15);border-color:var(--orange);color:var(--orange)}
#verdict-box.no-trade{background:rgba(255,82,82,.15);border-color:var(--red);color:var(--red)}
#verdict-box.news-block{background:rgba(244,67,54,.15);border-color:var(--red);color:var(--red)}

/* ── Zone B: MARKET FLOW ─────────────────────────────────────────────────────────── */
#zone-b{display:flex;flex-direction:column;gap:8px}
.tf-group-label{font-size:10px;color:var(--muted);text-transform:uppercase;font-weight:700;
  margin-top:6px;border-bottom:1px solid rgba(255,255,255,.05);padding-bottom:4px}
.tf-row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.03);
  font-size:11px}
.tf-dir{font-weight:700}
.tf-dir.buy{color:var(--green)}
.tf-dir.sell{color:var(--red)}
.tf-pat{color:var(--muted);font-size:10px}
.tf-footer{display:flex;gap:12px;padding:6px 0;border-top:1px solid var(--border);margin-top:6px;font-size:11px}
.tf-bull{color:var(--green);font-weight:700}
.tf-bear{color:var(--red);font-weight:700}

.bias-group{display:flex;flex-direction:column;gap:4px}
.bias-row{display:flex;justify-content:space-between;padding:4px;background:rgba(255,255,255,.02);
  border-radius:3px;font-size:11px}
.bias-tf-label{color:var(--muted);font-weight:700}
.bias-val{font-weight:800}
.bias-val.bull{color:var(--green)}
.bias-val.bear{color:var(--red)}
.bias-val.neutral{color:var(--muted)}
.bias-val.conflict{color:var(--orange)}
#bias-now-box{padding:6px;background:rgba(0,230,118,.1);border-radius:4px;border-left:2px solid var(--green)}
#bias-now-val{font-size:14px;font-weight:800;color:var(--green)}

.struct-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}
.struct-cell{padding:4px;background:rgba(255,255,255,.02);border-radius:3px;font-size:10px;text-align:center;
  border:1px solid var(--border)}
.struct-cell.buy{color:var(--green);border-color:var(--green)}
.struct-cell.sell{color:var(--red);border-color:var(--red)}

#news-list{max-height:120px;overflow-y:auto}
.news-item{padding:4px;margin-bottom:2px;background:rgba(255,255,255,.02);border-left:2px solid var(--orange);
  border-radius:2px;font-size:10px;color:var(--muted)}
.news-item .title{color:var(--white);font-weight:700}
.news-item .time{color:var(--muted2);font-size:9px}
#no-news{padding:8px;text-align:center;color:var(--muted2);font-size:11px}

#alert-list{max-height:180px;overflow-y:auto}
.alert-row{padding:4px 6px;margin-bottom:3px;background:rgba(255,255,255,.02);
  border-left:2px solid var(--border);border-radius:2px;display:flex;justify-content:space-between;
  align-items:center;font-size:10px}
.alert-dir.buy{color:var(--green);font-weight:700}
.alert-dir.sell{color:var(--red);font-weight:700}
.alert-price{color:var(--yellow);font-weight:700}

/* ── Zone C: EXECUTION METER ────────────────────────────────────────────────────── */
#zone-c{display:flex;flex-direction:column;gap:8px}
.param-row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.03);
  font-size:11px}
.p-label{color:var(--muted);font-weight:700}
.p-val{font-weight:800}
.p-val.pat{color:var(--cyan)}
.p-val.entry{color:var(--yellow)}
.p-val.sl{color:var(--red)}
.p-val.tp{color:var(--green)}

#rr-card input{background:var(--bg3);border:1px solid var(--border);border-radius:4px;
  color:var(--white);font-family:var(--font);font-size:12px;padding:4px 8px;width:100px}
#rr-card select{background:var(--bg3);border:1px solid var(--border);border-radius:4px;
  color:var(--white);font-family:var(--font);font-size:12px;padding:4px 6px}
.rr-row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.03)}
.rr-label{font-size:10px;color:var(--muted)}
.rr-val{font-weight:800;font-size:12px}
.rr-risk{color:var(--red)}.rr-reward{color:var(--green)}.rr-lot{color:var(--cyan)}

#zone-list{max-height:140px;overflow-y:auto}
.zone-row{padding:6px;background:rgba(255,255,255,.02);border-radius:4px;margin-bottom:4px;font-size:10px}
.zone-header{display:flex;justify-content:space-between;margin-bottom:2px}
.zone-type{font-weight:700}
.zone-type.dz{color:var(--green)}
.zone-type.sz{color:var(--red)}
.zone-tag{font-weight:700;font-size:9px;padding:1px 4px;border-radius:2px;background:var(--bg)}
.zone-range{color:var(--yellow);font-weight:700;font-size:11px}
.zone-dist{color:var(--muted);font-size:9px;margin-top:2px}
.zone-dist.alert{color:var(--orange);font-weight:700}

#ovl-bar-wrap{height:8px;border-radius:4px;background:var(--bg3);border:1px solid var(--border);
  overflow:hidden;margin-top:3px}
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
  <div class="brand">💎 DIAMOND TRADER v3.1.1</div>
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

  <!-- ══ ZONE A: SNIPER SIGNALS ══════════════════════════════════════════════════════ -->
  <div id="zone-a">
    <div class="card">
      <div class="card-title">🎯 Zone A — Sniper Signals</div>
      
      <div class="zone-row">
        <div class="zone-row-label">PA Pattern</div>
        <div class="zone-row-value" id="za-pattern">—</div>
      </div>
      
      <div class="zone-row">
        <div class="zone-row-label">Grid Level</div>
        <div class="zone-row-value" id="za-grid">—</div>
      </div>
      
      <div class="zone-row">
        <div class="zone-row-label">VIP Station</div>
        <div class="zone-row-value" id="za-vip">—</div>
      </div>
      
      <div class="zone-row">
        <div class="zone-row-label">CF M5 Counter</div>
        <div class="zone-row-value" id="za-cf">— 0/3</div>
      </div>
      
      <div style="border-top:1px solid var(--border);padding-top:8px;margin-top:4px">
        <div id="verdict-box" class="standby">STANDBY</div>
      </div>
    </div>
  </div>

  <!-- ══ ZONE B: MARKET FLOW ═════════════════════════════════════════════════════════ -->
  <div id="zone-b">
    <div class="card">
      <div class="card-title">🏗️ Zone B — Market Flow</div>
      
      <div class="tf-group-label">◆ MTF BIAS VOTE</div>
      <div id="zb-bias"></div>
      
      <div class="tf-group-label">◆ TF PATTERN STATUS</div>
      <div id="zb-tfrows" style="max-height:120px;overflow-y:auto"></div>
      <div class="tf-footer">
        <span class="tf-bull">▲ BULL: <span id="zb-bull">0</span></span>
        <span class="tf-bear">▼ BEAR: <span id="zb-bear">0</span></span>
      </div>
    </div>
    
    <div class="card">
      <div class="card-title">📰 Economic News (USD)</div>
      <div id="zb-news" style="max-height:100px;overflow-y:auto"><div id="no-news">Fetching news...</div></div>
    </div>
    
    <div class="card">
      <div class="card-title">📜 Live Signal Feed</div>
      <div id="zb-alerts" style="max-height:140px;overflow-y:auto"></div>
    </div>
  </div>

  <!-- ══ ZONE C: EXECUTION METER ═════════════════════════════════════════════════════ -->
  <div id="zone-c">
    <div class="card">
      <div class="card-title">🎯 Target Parameters</div>
      <div class="param-row"><span class="p-label">PATTERN</span><span class="p-val pat" id="zc-pat">—</span></div>
      <div class="param-row"><span class="p-label">ENTRY</span><span class="p-val entry" id="zc-entry">—</span></div>
      <div class="param-row"><span class="p-label">STOP LOSS</span><span class="p-val sl" id="zc-sl">—</span></div>
      <div class="param-row"><span class="p-label">TAKE PROFIT</span><span class="p-val tp" id="zc-tp">—</span></div>
      <div class="param-row"><span class="p-label">SL (pts)</span><span class="p-val" id="zc-slpts" style="color:var(--muted)">—</span></div>
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
      <div id="zc-zones"><div style="color:var(--muted);font-size:11px;text-align:center;padding:10px">No zones yet</div></div>
    </div>
    
    <div class="card">
      <div class="card-title">📡 Grid OVL Meter</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span style="color:var(--muted);font-size:10px">Distance to grid</span>
        <span id="zc-ovl" style="font-weight:800;font-size:13px;color:var(--green)">— pts</span>
      </div>
      <div id="ovl-bar-wrap"><div id="ovl-bar"></div></div>
      <div style="display:flex;justify-content:space-between;margin-top:2px;font-size:9px;color:var(--muted2)">
        <span>0</span><span>150</span><span>300+</span>
      </div>
    </div>
  </div>

</div>

<script>
const TF_HIGHER = ["MN","W","D"];
const TF_INTER = ["H4","H1"];
const TF_LOWER = ["M30","M15","M5","M1"];
let state = {}, entryPrice=0, direction='', slPts=300, usdthb=36.5;
let lastPrice=0, lastAlertId=0, lastZoneCheck={}, TTS=window.speechSynthesis;

// ── Utility functions ──────────────────────────────────────────────────────────────
function speak(txt){
  if(!TTS) return;
  const u=new SpeechSynthesisUtterance(txt);u.lang='en-US';u.rate=1.1;
  TTS.cancel(); TTS.speak(u);
}

// ── Zone A Renderers ───────────────────────────────────────────────────────────────
function updateZoneA(d){
  const za=d.zone_a||{};
  document.getElementById('za-grid').textContent = (d.grid||0).toFixed(2);
  document.getElementById('za-vip').textContent = za.vip_msg || '—';
  if(za.vip_on) document.getElementById('za-vip').className='zone-row-value on';
  else document.getElementById('za-vip').className='zone-row-value off';

  // PA Pattern: ▲/▼ PatX.X [TF]
  const patEl=document.getElementById('za-pattern');
  if(za.pattern){
    const arrow=za.pa_dir==='BUY'?'▲':'▼';
    patEl.textContent=`${arrow} ${za.pattern} [${za.interval||'?'}]`;
    patEl.style.color=za.pa_dir==='BUY'?'var(--green)':'var(--red)';
  }

  document.getElementById('za-cf').textContent = za.cf_display || '🔴 — 0/3';
  const cf_col = document.getElementById('za-cf');
  cf_col.style.color = za.cf_color==='GREEN'?'var(--green)':za.cf_color==='YELLOW'?'var(--orange)':'var(--red)';
  
  const vbox = document.getElementById('verdict-box');
  vbox.textContent = za.verdict || 'STANDBY';
  vbox.className = za.verdict&&za.verdict.includes('READY')?'ready':
                    za.verdict==='WAIT'?'wait':
                    za.verdict==='NO-TRADE'?'no-trade':
                    za.verdict&&za.verdict.includes('NEWS')?'news-block':'';
}

// ── Zone B Renderers ───────────────────────────────────────────────────────────────
function renderBias(bias){
  const el=document.getElementById('zb-bias');
  if(!bias) return;
  el.innerHTML=`
    <div class="bias-row">
      <span class="bias-tf-label">Higher (MN/W/D)</span>
      <span class="bias-val ${(bias.higher||'').toLowerCase()}">${bias.higher||'—'}</span>
    </div>
    <div class="bias-row">
      <span class="bias-tf-label">Inter (H4/H1)</span>
      <span class="bias-val ${(bias.intermediate||'').toLowerCase().replace('?','')}">${bias.intermediate||'—'}</span>
    </div>
    <div class="bias-row">
      <span class="bias-tf-label">Lower (M30–M1)</span>
      <span class="bias-val ${(bias.lower||'').toLowerCase()}">${bias.lower||'—'}</span>
    </div>
  `;
}

function renderTfRows(rows){
  const el=document.getElementById('zb-tfrows');
  if(!rows||!rows.length) {el.innerHTML='—'; return;}
  el.innerHTML='';
  rows.forEach(r=>{
    const dirCls = r.direction==='BUY'?'buy':r.direction==='SELL'?'sell':'';
    el.innerHTML+=`<div class="tf-row">
      <span class="tf-interval">${r.interval}</span>
      <span class="tf-dir ${dirCls}">${r.direction||'—'}</span>
      <span class="tf-pat">${r.pattern||'—'}</span>
    </div>`;
  });
}

function renderNews(news){
  const el=document.getElementById('zb-news');
  if(!news||!news.length) {el.innerHTML='<div id="no-news" style="padding:8px;text-align:center;color:var(--muted2);font-size:11px">No news</div>';return;}
  el.innerHTML='';
  news.forEach(n=>{
    el.innerHTML+=`<div class="news-item">
      <div class="title">${n.title||'—'}</div>
      <div class="time">${n.event_time||'—'}</div>
    </div>`;
  });
}

function addAlert(d, prepend){
  const list=document.getElementById('zb-alerts');
  const el=document.createElement('div');
  el.className='alert-row';
  const buy=d.direction==='BUY';
  el.innerHTML=`<span class="alert-dir ${buy?'buy':'sell'}">${buy?'▲':'▼'} [${d.interval||'?'}] ${d.pattern||'PA'}</span>
    <span class="alert-price">${d.price?parseFloat(d.price).toFixed(2):''}</span>`;
  if(prepend&&list.firstChild) list.insertBefore(el,list.firstChild);
  else list.appendChild(el);
  while(list.children.length>12) list.removeChild(list.lastChild);
}

// ── Zone C Renderers ───────────────────────────────────────────────────────────────
function updateExec(alert){
  const p=parseFloat(alert.close||alert.price||0);
  if(!p) return;
  entryPrice=p; direction=alert.direction||'';
  const isBuy=direction==='BUY';
  const sl=isBuy?p-3.0:p+3.0;
  const tp=isBuy?p+9.0:p-9.0;
  slPts=300;
  document.getElementById('zc-pat').textContent=alert.pattern||'—';
  document.getElementById('zc-entry').textContent=p.toFixed(2);
  document.getElementById('zc-sl').textContent=sl.toFixed(2);
  document.getElementById('zc-tp').textContent=tp.toFixed(2);
  document.getElementById('zc-slpts').textContent=slPts+' pts';
  calcRR();
}

function calcRR(){
  const curr=document.getElementById('currency-sel').value;
  const bal=parseFloat(document.getElementById('balance-input').value)||1000;
  if(bal<=0 || entryPrice<=0) return;
  const riskPts=slPts;
  const rewardPts=riskPts*3;
  if(curr==='THB'){
    const riskUSD = riskPts/100;
    const rewardUSD = rewardPts/100;
    const riskTHB = riskUSD*usdthb;
    const rewardTHB = rewardUSD*usdthb;
    const riskPct = riskTHB/bal;
    const sugLot = riskPct<=0.02 ? 1 : riskPct<=0.05 ? 0.5 : 0.25;
    document.getElementById('rr-thb-rate').textContent=usdthb.toFixed(2);
    document.getElementById('rr-risk').textContent=riskTHB>0?`-${riskTHB.toFixed(0)} ฿`:'—';
    document.getElementById('rr-reward').textContent=rewardTHB>0?`+${rewardTHB.toFixed(0)} ฿`:'—';
    document.getElementById('rr-lot').textContent=sugLot>0?sugLot.toFixed(2):'—';
  } else {
    const riskUSD = riskPts/100;
    const rewardUSD = rewardPts/100;
    const riskPct = riskUSD/bal;
    const sugLot = riskPct<=0.02 ? 1 : riskPct<=0.05 ? 0.5 : 0.25;
    document.getElementById('rr-risk').textContent=riskUSD>0?`-${riskUSD.toFixed(2)} $`:'—';
    document.getElementById('rr-reward').textContent=rewardUSD>0?`+${rewardUSD.toFixed(2)} $`:'—';
    document.getElementById('rr-lot').textContent=sugLot>0?sugLot.toFixed(2):'—';
  }
}

function renderZones(zones){
  const list=document.getElementById('zc-zones');
  if(!zones||!zones.length){list.innerHTML='<div style="color:var(--muted);font-size:11px;text-align:center;padding:10px">No zones</div>';return;}
  list.innerHTML='';
  zones.forEach(z=>{
    const distCls=z.proximity_alert?'zone-dist alert':'zone-dist';
    const distTxt=z.dist_pts!=null?`${z.dist_pts} pts away`:'—';
    const key=z.zone_type+'_'+z.interval;
    if(z.proximity_alert && !lastZoneCheck[key]){
      speak(z.zone_type==='DZ'?'H4 Demand Check':'H4 Supply Check');
    }
    lastZoneCheck[key]=z.proximity_alert;
    list.innerHTML+=`<div class="zone-row">
      <div class="zone-header">
        <span class="zone-type ${z.zone_type==='DZ'?'dz':'sz'}">${z.zone_type==='DZ'?'🟢 DEMAND':'🔴 SUPPLY'} [${z.interval}]</span>
      </div>
      <div class="zone-range">${parseFloat(z.lower).toFixed(2)} — ${parseFloat(z.upper).toFixed(2)}</div>
      <div class="${distCls}">${distTxt}</div>
    </div>`;
  });
}

function updateOvl(pts){
  const el=document.getElementById('zc-ovl');
  const bar=document.getElementById('ovl-bar');
  if(pts==null){el.textContent='— pts';return;}
  el.textContent=pts+' pts';
  const pct=Math.min(pts/300*100,100);
  bar.style.width=pct+'%';
  if(pts<=150){el.style.color='var(--green)';bar.style.background='var(--green)'}
  else if(pts<=300){el.style.color='var(--orange)';bar.style.background='var(--orange)'}
  else{el.style.color='var(--red)';bar.style.background='var(--red)'}
}

// ── Clock ──────────────────────────────────────────────────────────────────────────
setInterval(()=>{
  document.getElementById('top-time').textContent=new Date().toUTCString().slice(17,25)+' UTC';
},1000);

// ── Main poll ──────────────────────────────────────────────────────────────────────
async function pollState(){
  const dot=document.getElementById('ws-dot');
  const lbl=document.getElementById('ws-status');
  try{
    const d=await (await fetch('/dashboard-state')).json();
    state=d;
    dot.className='dot live';lbl.textContent='LIVE';
    
    if(d.price){
      const p=parseFloat(d.price);
      const el=document.getElementById('paxg-price');
      const hud=document.getElementById('price-hud');
      el.textContent=p.toLocaleString(undefined,{minimumFractionDigits:2});
      hud.className=p>lastPrice?'up':p<lastPrice?'down':'';
      lastPrice=p;
      document.getElementById('top-grid').textContent=(d.grid||0).toFixed(2);
      document.getElementById('top-ovl').textContent=(d.ovl_pts||0)+' pts';
    }
    
    if(d.usdthb){usdthb=d.usdthb;document.getElementById('top-thb').textContent=usdthb.toFixed(2);}
    
    // Zone A
    updateZoneA(d);
    
    // Zone B
    renderBias(d.bias);
    renderTfRows(d.tf_rows||[]);
    document.getElementById('zb-bull').textContent=d.bull_count||0;
    document.getElementById('zb-bear').textContent=d.bear_count||0;
    renderNews(d.news);
    
    // Zone C
    updateOvl(d.ovl_pts);
    renderZones(d.zones||[]);
    
    // News guard
    const b=document.getElementById('news-banner');
    const t=document.getElementById('news-banner-txt');
    if(d.news_guard&&d.news_guard.blocked){
      b.style.display='block';
      t.textContent=d.news_guard.reason||'High Impact Event';
    } else {
      b.style.display='none';
    }
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
      const last=news[news.length-1];
      if(last.direction) speak(last.direction==='BUY'?'Buy signal':'Sell signal');
    }
  }catch(e){}
}

// ── Events ────────────────────────────────────────────────────────────────────────
document.getElementById('balance-input').addEventListener('input',calcRR);
document.getElementById('currency-sel').addEventListener('change',calcRR);

// ── Init ──────────────────────────────────────────────────────────────────────────
setInterval(pollState,2000);
setInterval(pollAlerts,1500);
pollState();
pollAlerts();
calcRR();
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard(): return DASHBOARD_HTML
