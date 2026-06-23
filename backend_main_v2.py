from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sqlite3
import json
import os

app = FastAPI(title="DIAMOND TRADER Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.getenv("DB_PATH", "diamond_trader.db")

# ── CF M5 State (in-memory) ──────────────────────────────────────
cf_state: dict = {
    "cf_count":   0,
    "cf_pass":    False,
    "cf_dir":     "neutral",
    "cf_status":  "WAIT",
    "grid_level": 0.0,
    "close":      0.0,
    "ticker":     "",
    "updated_at": None
}


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
    dir_label = "BUY" if direction == "buy" else "SELL" if direction == "sell" else "—"
    if count == 0:
        return "— 0/3"
    if passed:
        return f"✓ {dir_label} 3/3 READY"
    return f"⏳ {dir_label} {count}/3"


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "DIAMOND TRADER"}


@app.get("/cf-status")
async def get_cf_status():
    """Dashboard polls ทุก 3 วิ — Live CF M5 counter"""
    return {
        "cf_count":   cf_state["cf_count"],
        "cf_pass":    cf_state["cf_pass"],
        "cf_dir":     cf_state["cf_dir"],
        "cf_status":  cf_state["cf_status"],
        "grid_level": cf_state["grid_level"],
        "close":      cf_state["close"],
        "ticker":     cf_state["ticker"],
        "updated_at": cf_state["updated_at"],
        "display":    _cf_display(
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
    cols = ["id", "timestamp", "ticker", "interval",
            "pattern", "direction", "price", "verdict", "raw"]
    return [dict(zip(cols, r)) for r in rows]


@app.post("/alerts")
async def post_alert(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"status": "error", "msg": "invalid JSON"}

    # ── CF_UPDATE — อัป state, ไม่บันทึก DB ─────────────────────
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
            "status":   "ok",
            "type":     "CF_UPDATE",
            "cf_count": cf_state["cf_count"],
            "display":  _cf_display(
                            cf_state["cf_count"],
                            cf_state["cf_pass"],
                            cf_state["cf_dir"]
                        )
        }

    # ── PA Signal — บันทึก DB ────────────────────────────────────
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
           (timestamp, ticker, interval, pattern, direction, price, verdict, raw)
           VALUES (?,?,?,?,?,?,?,?)""",
        (now, ticker, interval, pattern, direction, price, verdict, json.dumps(body))
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "type": "PA_SIGNAL", "pattern": pattern}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)