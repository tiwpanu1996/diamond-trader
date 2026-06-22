"""
DIAMOND TRADER — Backend API
FastAPI + WebSocket + SQLite
Port: 8000
"""

import sqlite3
import json
import os
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ═══════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════
DB_PATH  = "alerts.db"
PORT     = int(os.environ.get("PORT", 8000))

app = FastAPI(title="DIAMOND TRADER API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern     TEXT,
            direction   TEXT,
            entry_price REAL,
            grid        REAL,
            sl          REAL,
            tp          REAL,
            symbol      TEXT DEFAULT 'XAUUSDm',
            tf          TEXT DEFAULT 'M5',
            verdict     TEXT DEFAULT 'WAIT',
            timestamp   TEXT,
            raw_message TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ═══════════════════════════════════════════════════
# WEBSOCKET MANAGER
# ═══════════════════════════════════════════════════
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] connection open — clients: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        print(f"[WS] disconnected — clients: {len(self.active)}")

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()

# ═══════════════════════════════════════════════════
# PARSE TRADINGVIEW ALERT MESSAGE
# ═══════════════════════════════════════════════════
def parse_alert(raw: str) -> dict:
    """
    รับ Alert message จาก TradingView ทั้ง JSON และ plain text
    ตัวอย่าง plain: "Pat3.2 BUY @ 3200.50 | Grid:3200.00 | SL:3199.50 | TP:3203.50 | READY"
    """
    raw = raw.strip()

    # --- ลอง JSON ก่อน ---
    try:
        data = json.loads(raw)
        return {
            "pattern":     data.get("pattern", "—"),
            "direction":   data.get("direction", "—"),
            "entry_price": float(data.get("entry_price", 0)),
            "grid":        float(data.get("grid", 0)),
            "sl":          float(data.get("sl", 0)),
            "tp":          float(data.get("tp", 0)),
            "symbol":      data.get("symbol", "XAUUSDm"),
            "tf":          data.get("tf", "M5"),
            "verdict":     data.get("verdict", "WAIT"),
            "timestamp":   data.get("timestamp", datetime.utcnow().isoformat()),
            "raw_message": raw,
        }
    except Exception:
        pass

    # --- plain text parse ---
    try:
        parts = [p.strip() for p in raw.split("|")]
        first = parts[0].split()          # ["Pat3.2", "BUY", "@", "3200.50"]
        pattern   = first[0] if len(first) > 0 else "—"
        direction = first[1] if len(first) > 1 else "—"
        entry     = float(first[3]) if len(first) > 3 else 0.0
        grid  = float(parts[1].split(":")[1]) if len(parts) > 1 else 0.0
        sl    = float(parts[2].split(":")[1]) if len(parts) > 2 else 0.0
        tp    = float(parts[3].split(":")[1]) if len(parts) > 3 else 0.0
        verdict = parts[4].strip() if len(parts) > 4 else "WAIT"
        return {
            "pattern": pattern, "direction": direction,
            "entry_price": entry, "grid": grid, "sl": sl, "tp": tp,
            "symbol": "XAUUSDm", "tf": "M5", "verdict": verdict,
            "timestamp": datetime.utcnow().isoformat(), "raw_message": raw,
        }
    except Exception:
        return {
            "pattern": "UNKNOWN", "direction": "—", "entry_price": 0,
            "grid": 0, "sl": 0, "tp": 0, "symbol": "XAUUSDm",
            "tf": "M5", "verdict": "ERR", "timestamp": datetime.utcnow().isoformat(),
            "raw_message": raw,
        }

def save_alert(data: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("""
        INSERT INTO alerts (pattern, direction, entry_price, grid, sl, tp,
                            symbol, tf, verdict, timestamp, raw_message)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data["pattern"], data["direction"], data["entry_price"],
        data["grid"], data["sl"], data["tp"],
        data["symbol"], data["tf"], data["verdict"],
        data["timestamp"], data["raw_message"],
    ))
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id

# ═══════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════

# ── Dashboard HTML ──────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = "diamond_trader_dashboard.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>DIAMOND TRADER</h1><p>dashboard file not found</p>")

# ── TradingView Webhook ─────────────────────────────
@app.post("/alerts")
async def receive_alert(request: Request):
    body = await request.body()
    raw  = body.decode("utf-8", errors="ignore")
    print(f"[ALERT] raw: {raw[:200]}")

    data   = parse_alert(raw)
    row_id = save_alert(data)
    data["id"] = row_id

    # broadcast ไป Dashboard
    await manager.broadcast({"type": "alert", "data": data})

    return {"status": "ok", "id": row_id, "pattern": data["pattern"]}

# ── WebSocket ───────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # ส่ง history ให้ client ใหม่
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 30")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        await ws.send_text(json.dumps({"type": "history", "data": rows}))

        while True:
            await ws.receive_text()   # keep-alive
    except WebSocketDisconnect:
        manager.disconnect(ws)

# ── REST: ดู Alerts ────────────────────────────────
@app.get("/alerts")
async def get_alerts(limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows

# ── Health Check ────────────────────────────────────
@app.get("/health")
async def health():
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    conn.close()
    return {"status": "ok", "total_alerts": count, "port": PORT}

# ── Entry Point ─────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend_main:app", host="0.0.0.0", port=PORT, reload=True)
