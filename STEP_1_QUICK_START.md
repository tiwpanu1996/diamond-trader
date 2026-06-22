# 🚀 DIAMOND TRADER — Step 1 Quick Start (Pine Script ↔ Backend)

## 📋 ต้องทำอะไรบ้าง

```
┌─────────────────────────────────────────────────┐
│  1. Copy Pine Script ไปที่ TradingView          │
│  2. Setup Webhook Alert ใน TradingView         │
│  3. Test webhook ด้วย curl command             │
│  4. ตรวจสอบ Alert มาถึง Dashboard             │
└─────────────────────────────────────────────────┘
```

---

## 1️⃣ Copy Pine Script ไปที่ TradingView

### ไฟล์: `diamond_trader_alerts.pine`
- ตำแหน่ง: `/home/claude/diamond_trader_alerts.pine` (ที่นี่)

### ขั้นตอน:
1. ไปที่ **TradingView.com** → เข้าระบบ
2. เปิด Chart **XAUUSDm** (Exness)
3. ขวาล่าง → **Pine Script Editor**
4. **New** → ตั้งชื่อ `DIAMOND TRADER PA Alerts`
5. Paste โค้ด Diamond Trader ทั้งหมด
6. **Save**
7. **Add to Chart**

---

## 2️⃣ Setup Webhook Alert

### Settings ที่สำคัญ:

```
Grid Spacing (USD)          : 5.0
OVL Tolerance (points)      : 300
Spread ปัจจุบัน (points)    : 160   ← ดูจาก Exness ตอนนี้
Spread Max (points)         : 350
CF M5 Threshold (candles)   : 3
Webhook URL                 : http://localhost:8000/alerts  ← สำคัญ!
Enable Webhook Alerts       : ✓ ON
```

### Alert Frequency:
- **Once Per Bar Close** (ต้องเป็นอย่างนี้)

---

## 3️⃣ Test Webhook

### 3.1 ตรวจ Backend กำลังรันอยู่

CMD หนึ่ง (ตัวแรก):
```bash
cd C:\Users\piyawan\DIAMOND_TRADER
uvicorn backend_main:app --host 0.0.0.0 --port 8000 --reload
```

ต้องเห็น:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

✅ **ทิ้งไว้ค้างไว้**

### 3.2 Test ด้วย Script

CMD ใหม่ (ตัวที่สอง):
```bash
cd C:\Users\piyawan\DIAMOND_TRADER
test_webhook.bat
```

ต้องเห็น:
```
✓ Backend พร้อม
✓ Dashboard เปิด
📤 Test 1: Pat3.2 BUY...
📤 Test 2: Pat3.3 SELL...
📤 Test 3: Pat2 BUY...
📤 Test 4: Pat1 SELL [LOW-EDGE]...
```

---

## 4️⃣ ตรวจสอบ Dashboard

### เปิด Browser
```
http://localhost:8000
```

### ดูส่วน ALERTS (ขวาล่าง)
ต้องเห็น alerts 4 รายการ:
- ✓ Pat3.2 BUY
- ✓ Pat3.3 SELL
- ✓ Pat2 BUY
- ✓ Pat1 SELL (LOW-EDGE)

**ถ้าเห็น 4 รายการ = ✅ SUCCESS**

---

## ⚡ ถ้ามีปัญหา

### Alert ไม่ขึ้นใน Dashboard?
```
1. F5 refresh browser
2. ตรวจ WebSocket เชื่อมต่อ (ควรเห็น "connection open" ใน CMD)
3. ตรวจ curl response ว่า HTTP 200 หรือไม่
```

### Backend error?
```
1. ปิด CMD backend ที่รันอยู่
2. รัน uvicorn ใหม่
3. ลบไฟล์ alerts.db ถ้าอยากเริ่มใหม่
   del C:\Users\piyawan\DIAMOND_TRADER\alerts.db
```

### TradingView alert ไม่ยิง?
```
1. ตรวจ URL ถูกต้องหรือ (http://localhost:8000/alerts)
2. ตรวจ Frequency = "Once Per Bar Close"
3. รอ Signal ขึ้นจริง (อ่านกราฟ M5)
```

---

## 📌 ความสำคัญ

- **Backend + test_webhook.bat ต้องรันใน CMD แยกกัน** (2 tabs)
- **ห้าม close/minimize CMD backend** ขณะเทรด
- **Spread ต้องกรอกเอง** (ดูจาก Exness Terminal)
- **Alert เป็นการช่วยตัดสิน เท่านั้น** — ตัดสินเอง!

---

## ✅ Checklist

- [ ] Pine Script upload TradingView ✓
- [ ] Settings Webhook URL ถูก ✓
- [ ] Backend รันอยู่ (uvicorn) ✓
- [ ] Test webhook 4 patterns ผ่าน ✓
- [ ] Dashboard alert ขึ้น 4 รายการ ✓
- [ ] Ready ไปขั้นที่ 2!

---

**พอ Alert ขึ้นได้แล้ว →** ขั้นที่ 2: **Deploy Railway** (เดี๋ยวทำต่อ)
