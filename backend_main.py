"""
DIAMOND TRADER — Backend API v2
FastAPI + SQLite + Filter fields
"""

import sqlite3
import json
import os
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = "alerts.db"
PORT    = int(os.environ.get("PORT", 8000))

app = FastAPI(title="DIAMOND TRADER API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
            cf_count    INTEGER DEFAULT 0,
            ovl_pts     REAL DEFAULT 0,
            sideway     TEXT DEFAULT '',
            mtf_score   TEXT DEFAULT '',
            timestamp   TEXT,
            raw_message TEXT
        )
    """)
    # เพิ่ม column ใหม่ถ้ายังไม่มี (migration)
    for col, typ in [("cf_count","INTEGER DEFAULT 0"),("ovl_pts","REAL DEFAULT 0"),
                     ("sideway","TEXT DEFAULT ''"),("mtf_score","TEXT DEFAULT ''")]:
        try:
            conn.execute(f"ALTER TABLE alerts ADD COLUMN {col} {typ}")
        except Exception:
            pass
    conn.commit()
    conn.close()

init_db()

# ═══════════════════════════════════════════════════
# PARSE ALERT
# ═══════════════════════════════════════════════════
def parse_alert(raw: str) -> dict:
    raw = raw.strip()
    base = {
        "pattern":"—","direction":"—","entry_price":0.0,"grid":0.0,
        "sl":0.0,"tp":0.0,"symbol":"XAUUSDm","tf":"M5","verdict":"WAIT",
        "cf_count":0,"ovl_pts":0.0,"sideway":"","mtf_score":"",
        "timestamp":datetime.utcnow().isoformat(),"raw_message":raw,
    }

    # JSON
    try:
        data = json.loads(raw)
        for k in base:
            if k in data:
                base[k] = data[k]
        base["raw_message"] = raw
        base["timestamp"] = data.get("timestamp", base["timestamp"])
        return base
    except Exception:
        pass

    # plain text: "Pat3.2 BUY @ 3200.50 | Grid:3200.00 | SL:.. | TP:.. | READY"
    try:
        parts = [p.strip() for p in raw.split("|")]
        first = parts[0].split()
        base["pattern"]   = first[0] if len(first)>0 else "—"
        base["direction"] = first[1] if len(first)>1 else "—"
        base["entry_price"] = float(first[3]) if len(first)>3 else 0.0
        if len(parts)>1: base["grid"]    = float(parts[1].split(":")[1])
        if len(parts)>2: base["sl"]      = float(parts[2].split(":")[1])
        if len(parts)>3: base["tp"]      = float(parts[3].split(":")[1])
        if len(parts)>4: base["verdict"] = parts[4].strip()
    except Exception:
        base["pattern"] = "UNKNOWN"
        base["verdict"] = "ERR"
    return base

def save_alert(d: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        INSERT INTO alerts (pattern,direction,entry_price,grid,sl,tp,symbol,tf,
                           verdict,cf_count,ovl_pts,sideway,mtf_score,timestamp,raw_message)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (d["pattern"],d["direction"],d["entry_price"],d["grid"],d["sl"],d["tp"],
          d["symbol"],d["tf"],d["verdict"],d["cf_count"],d["ovl_pts"],
          d["sideway"],d["mtf_score"],d["timestamp"],d["raw_message"]))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

# ═══════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    p = "diamond_trader_dashboard.html"
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>DIAMOND TRADER</h1><p>dashboard not found</p>")

@app.post("/alerts")
async def receive_alert(request: Request):
    raw  = (await request.body()).decode("utf-8", errors="ignore")
    print(f"[ALERT] {raw[:200]}")
    data = parse_alert(raw)
    rid  = save_alert(data)
    data["id"] = rid
    return {"status":"ok","id":rid,"pattern":data["pattern"]}

@app.get("/alerts")
async def get_alerts(limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/health")
async def health():
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    conn.close()
    return {"status":"ok","total_alerts":count,"port":PORT}

# WebSocket (เก็บไว้เผื่อ platform อื่นรองรับ)
class CM:
    def __init__(self): self.active=[]
    async def connect(self,ws): await ws.accept(); self.active.append(ws)
    def disconnect(self,ws):
        if ws in self.active: self.active.remove(ws)
manager = CM()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend_main:app", host="0.0.0.0", port=PORT, reload=True)
