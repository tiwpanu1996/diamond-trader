# 🎯 DIAMOND TRADER — TradingView Webhook Setup

## ขั้นที่ 1: Upload Pine Script ไปที่ TradingView

### 1.1 คัดลอก Code
- โค้ด Pine Script อยู่ที่: `diamond_trader_alerts.pine`
- Copy ทั้งหมด

### 1.2 เปิด TradingView → Pine Script Editor
```
TradingView → Chart → Pine Script Editor (ที่มุมขวาล่าง)
```

### 1.3 สร้าง Script ใหม่
- `New` → ตั้งชื่อ `DIAMOND TRADER PA Alerts`
- Paste โค้ด
- Save

### 1.4 Add to Chart
- `Add to Chart` (ปุ่มสีน้ำเงิน)
- ตั้ง Input ตามข้อ 2.1

---

## ขั้นที่ 2: ตั้ง Input Parameters

### 2.1 Settings Tab (ใน Indicator Panel)
| Parameter | ค่าแนะนำ | หมายเหตุ |
|-----------|---------|--------|
| **Grid Spacing (USD)** | 5.0 | ห่าง 500 จุด |
| **OVL Tolerance (points)** | 300 | ยอมรับห่างได้สูงสุด |
| **Spread ปัจจุบัน** | 160 | ดูจาก Exness Terminal ของจริง |
| **Spread Max** | 350 | ห้ามเทรดถ้าเกิน |
| **CF M5 Threshold** | 3 | 3 แท่ง ≥ ready, 5 = หนักแน่น |
| **Webhook URL** | `http://localhost:8000/alerts` | ที่ backend รับ |
| **Enable Webhook Alerts** | ✓ ON | เปิดยิง webhook |

### 2.2 Display Tab
- ☑ Show MTF Bias
- ☑ Show Pat1/2 (dimmed)

---

## ขั้นที่ 3: Setup Alert (ยิง Webhook)

### 3.1 บน Chart → Right-click Indicator
```
DIAMOND TRADER PA Alerts → Create Alert (หรือ + bell icon)
```

### 3.2 Alert Settings
| ฟิลด์ | ค่า |
|------|-----|
| **Condition** | `DIAMOND TRADER PA Alerts` → **Webhook fired** (หรือ Alert triggered) |
| **Frequency** | `Once Per Bar Close` |
| **Notification** | ☑ Webhook URL |
| **Webhook URL** | `http://localhost:8000/alerts` |

### 3.3 ยืนยัน
- กด `Create Alert`
- Alert ยังไม่เข้าระบบจน signal ปรากฏ

---

## ขั้นที่ 4: ทดสอบ Webhook (ท้องถิ่น)

### 4.1 ตรวจว่า Backend ยังรันอยู่
```cmd
C:\Users\piyawan\DIAMOND_TRADER> uvicorn backend_main:app --host 0.0.0.0 --port 8000 --reload
```
ต้องเห็น:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
Application startup complete.
```

### 4.2 ทดสอบ POST ด้วย curl (PowerShell)
```powershell
$body = @{
    pattern = "Pat3.2"
    direction = "BUY"
    entry_price = 3200.50
    grid = 3200.00
    sl = 3199.50
    tp = 3203.50
    symbol = "XAUUSDm"
    timestamp = "2026-06-22 10:30:00"
    tf = "M5"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/alerts" -Method POST -Body $body -ContentType "application/json"
```

### 4.3 ตรวจผล
- CMD (backend): ต้องเห็น `POST /alerts HTTP/1.1`
- Browser: ไปที่ `http://localhost:8000` → Dashboard → ALERTS section เพิ่ม 1 รายการ

---

## ขั้นที่ 5: ปรับแต่ง (ไม่บังคับตอนแรก)

### 5.1 Webhook URL ตามสถานการณ์
| สถานการณ์ | URL |
|----------|-----|
| ท้องถิ่น (ทดสอบ) | `http://localhost:8000/alerts` |
| Deploy Railway | `https://diamond-trader-<id>.railway.app/alerts` |
| Deploy Render | `https://diamond-trader-<id>.onrender.com/alerts` |

### 5.2 Spread Real-time
- ตรวจ Exness Terminal
- Input → **Spread ปัจจุบัน** → อัปเดตตามตลาด
- (ต่อหน้าผมจะทำให้อัตโนมัติ)

---

## 🔍 Troubleshooting

| ปัญหา | แก้ไข |
|------|------|
| Alert ไม่ยิง | ตรวจ Signal ขึ้นจริงหรือ (ดูกราฟ) |
| Webhook ไม่ถึง backend | ตรวจ URL ถูกต้องหรือ + backend รันอยู่ |
| Dashboard ไม่อัปเดต | F5 refresh + ตรวจ WebSocket เชื่อมต่อ |
| Spread ต่อ | ตรวจว่า Market open หรือ + spikes |

---

## 📌 ความสำคัญ

- **ห้ามลบหรือปิด indicator** ขณะเทรด (ยิง Webhook ขึ้นอยู่กับมัน)
- **ดูกราฟเสมอ** — indicator เป็นเครื่องช่วยเท่านั้น
- **RR & SL = projection เท่านั้น** — ตัดสินเอง
- **Spread ต้องกรอกเอง** (Pine อ่านสดไม่ได้)

---

**ถ้าพร้อมแล้ว** → ปั้ว 👍 เลยครับ
