# 📋 TradingView CF M5 Addon — Setup Guide
## DIAMOND TRADER v2.1 | SSOT: SNIPER_HUD_BIBLE_v1.1 §3.1

---

## ขั้นตอนที่ 1 — เปิด PA Scanner v12 ใน Pine Editor

1. เปิด TradingView → Chart **XAUUSDm** (Exness)
2. ล่างสุดของจอ → คลิก **Pine Script Editor**
3. คลิก dropdown ชื่อ indicator → เลือก **DIAMOND TRADER PA Scanner v12**
4. โค้ดจะโหลดขึ้นมาใน Editor

---

## ขั้นตอนที่ 2 — เพิ่ม CF M5 Addon

**เลื่อนไปบรรทัดสุดท้ายของโค้ด** (หลัง plotshape / plot สุดท้าย)

วาง code block ด้านล่างนี้ต่อท้ายทันที:

```pine
// ═══════════════════════════════════════════════════════════════
// CF M5 ADDON — DIAMOND TRADER v2.1
// SSOT: SNIPER_HUD_BIBLE_v1.1 §3.1
// ═══════════════════════════════════════════════════════════════

float nearestGrid = math.round(close / 5.0) * 5.0

float m5Close = request.security(
     syminfo.tickerid,
     "5",
     close[1],
     lookahead = barmerge.lookahead_off
     )

float m5Grid = request.security(
     syminfo.tickerid,
     "5",
     math.round(close[1] / 5.0) * 5.0,
     lookahead = barmerge.lookahead_off
     )

var int cfCount     = 0
var int cfDir       = 0
var int cfCountPrev = 0

if barstate.isconfirmed
    bool m5BuySide  = m5Close > m5Grid
    bool m5SellSide = m5Close < m5Grid

    if m5BuySide
        if cfDir == 1
            cfCount := cfCount + 1
        else
            cfCount := 1
            cfDir   := 1
    else if m5SellSide
        if cfDir == -1
            cfCount := cfCount + 1
        else
            cfCount := 1
            cfDir   := -1
    else
        cfCount := 0
        cfDir   := 0

bool cfPass    = cfCount >= 3
bool cfChanged = cfCount != cfCountPrev

if barstate.isconfirmed and cfChanged
    string cfDirStr = cfDir == 1 ? "buy" : cfDir == -1 ? "sell" : "neutral"
    string cfStatus = cfPass ? "READY" : "WAIT"
    alert(
         '{"type":"CF_UPDATE",'
         + '"ticker":"'     + syminfo.ticker              + '",'
         + '"interval":"'   + timeframe.period            + '",'
         + '"cf_count":'    + str.tostring(cfCount)       + ','
         + '"cf_pass":'     + (cfPass ? "true" : "false") + ','
         + '"cf_dir":"'     + cfDirStr                    + '",'
         + '"cf_status":"'  + cfStatus                    + '",'
         + '"grid_level":'  + str.tostring(m5Grid, "#.##") + ','
         + '"close":'       + str.tostring(m5Close, "#.##")
         + '}',
         alert.freq_once_per_bar_close
         )
    cfCountPrev := cfCount
```

3. คลิก **Save** (Ctrl+S)
4. คลิก **Add to Chart** (หรือ Update ถ้า indicator อยู่บน chart แล้ว)

⚠️ **ถ้า Error "too many security calls":** แสดงว่า PA Scanner ใช้ request.security() เกิน 38 calls อยู่แล้ว → ต้องลด MTF calls ก่อน (แจ้งได้)

---

## ขั้นตอนที่ 3 — ตั้ง Alert สำหรับ CF_UPDATE

1. คลิกไอคอน **นาฬิกา (Alerts)** ด้านบนขวาของ TradingView
2. คลิก **+ Create Alert**
3. ตั้งค่าดังนี้:

| ฟิลด์ | ค่าที่ตั้ง |
|---|---|
| **Condition** | `DIAMOND TRADER PA Scanner v12` → `alert() function calls` |
| **Trigger** | `Once Per Bar Close` |
| **Alert Name** | `DIAMOND CF M5 Update` |
| **Message** | ⚠️ **ลบทุกอย่างออกให้ว่างเปล่า** (Pine จัดการ JSON ให้เอง) |
| **Webhook URL** | `https://web-production-f6b1.up.railway.app/alerts` |

4. คลิก **Create**

---

## ขั้นตอนที่ 4 — ทดสอบ

### 4.1 เช็คว่า Alert ยิงได้
รอแท่ง M5 ปิดแท่งแรก → ดู Alert log ใน TradingView ว่ามี "DIAMOND CF M5 Update" ขึ้น

### 4.2 เช็คว่า Backend รับได้
เปิด browser ไปที่:
```
https://web-production-f6b1.up.railway.app/cf-status
```

ควรเห็น JSON เช่น:
```json
{
  "cf_count": 1,
  "cf_pass": false,
  "cf_dir": "buy",
  "cf_status": "WAIT",
  "grid_level": 3200.0,
  "display": "⏳ BUY 1/3"
}
```

### 4.3 เช็ค Dashboard
เปิด `https://web-production-f6b1.up.railway.app/`
→ กล่อง **CF M5 Counter** ควรแสดง `⏳ BUY 1/3` (หรือ count ปัจจุบัน)

---

## Checklist ก่อน Go-Live

- [ ] Pine Script save + add to chart ไม่มี error
- [ ] Alert "DIAMOND CF M5 Update" สร้างแล้ว
- [ ] Webhook URL ถูกต้อง (ลงท้าย /alerts)
- [ ] Message field ว่างเปล่า (ไม่มี custom text)
- [ ] /cf-status คืนค่าได้ (ไม่ใช่ cf_count: 0 ตลอด)
- [ ] Dashboard CF counter อัปเดตตาม M5 bar

---

## ⚠️ จุดเสี่ยงที่ต้องระวัง

| ปัญหา | สาเหตุ | แก้ |
|---|---|---|
| CF count ไม่เปลี่ยน | Alert ไม่ได้ตั้ง `Once Per Bar Close` | เปลี่ยน Trigger |
| JSON ผิดรูปแบบ | Message field มีข้อความ | ลบออกให้ว่าง |
| count reset บ่อยผิดปกติ | กราฟเปลี่ยน TF (ไม่ใช่ M5 base) | ดู TF ที่ indicator วิ่งอยู่ |
| Security calls error | PA Scanner ใช้ security() ≥ 38 | แจ้งเพื่อ optimize |
