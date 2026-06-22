# 🎯 DIAMOND TRADER — Alert Message Template

## วิธีใช้: Copy JSON ไปวางในช่อง "ข้อความ" ของ Alert ใน TradingView

TradingView รองรับ placeholder `{{...}}` ที่จะแทนค่าจริงตอน alert ยิง

---

## ⭐ Template หลัก (แนะนำ) — ส่ง field ครบ

```json
{"pattern":"{{plot_0}}","direction":"{{strategy.order.action}}","entry_price":{{close}},"grid":0,"tf":"{{interval}}","verdict":"READY","cf_count":3,"symbol":"{{ticker}}"}
```

⚠️ แต่ Pine indicator แบบ `alertcondition` ใช้ `{{plot}}` ไม่ได้ตรงๆ

---

## ✅ Template ที่ใช้ได้จริงกับ v12 (แยกตาม pattern)

เวลาตั้ง Alert แต่ละ condition ให้วาง JSON ตามนี้:

### BUY Patterns
**PA BUY P.3.2:**
```json
{"pattern":"Pat3.2","direction":"BUY","entry_price":{{close}},"tf":"{{interval}}","verdict":"READY","symbol":"{{ticker}}"}
```

**PA BUY P.3.3:**
```json
{"pattern":"Pat3.3","direction":"BUY","entry_price":{{close}},"tf":"{{interval}}","verdict":"READY","symbol":"{{ticker}}"}
```

**PA BUY P.3.1:**
```json
{"pattern":"Pat3.1","direction":"BUY","entry_price":{{close}},"tf":"{{interval}}","verdict":"WAIT","symbol":"{{ticker}}"}
```

**PA BUY P.2:**
```json
{"pattern":"Pat2","direction":"BUY","entry_price":{{close}},"tf":"{{interval}}","verdict":"WAIT","symbol":"{{ticker}}"}
```

### SELL Patterns
**PA SELL P.3.2:**
```json
{"pattern":"Pat3.2","direction":"SELL","entry_price":{{close}},"tf":"{{interval}}","verdict":"READY","symbol":"{{ticker}}"}
```

**PA SELL P.3.3:**
```json
{"pattern":"Pat3.3","direction":"SELL","entry_price":{{close}},"tf":"{{interval}}","verdict":"READY","symbol":"{{ticker}}"}
```

**PA SELL P.3.1:**
```json
{"pattern":"Pat3.1","direction":"SELL","entry_price":{{close}},"tf":"{{interval}}","verdict":"WAIT","symbol":"{{ticker}}"}
```

**PA SELL P.2:**
```json
{"pattern":"Pat2","direction":"SELL","entry_price":{{close}},"tf":"{{interval}}","verdict":"WAIT","symbol":"{{ticker}}"}
```

---

## TradingView Placeholders ที่ใช้ได้

| Placeholder | ความหมาย |
|-------------|----------|
| `{{close}}` | ราคาปิดแท่งปัจจุบัน |
| `{{ticker}}` | สัญลักษณ์ (XAUUSD) |
| `{{interval}}` | timeframe (5, 15, 60...) |
| `{{time}}` | เวลาแท่ง |
| `{{volume}}` | volume |

---

## วิธีตั้ง (ทบทวน)

1. Right-click indicator → เพิ่มการแจ้งเตือน
2. Condition: DIAMOND TRADER v12 → เลือก pattern (เช่น PA BUY P.3.2)
3. **ช่อง "ข้อความ"** → ลบของเดิม → วาง JSON ตาม pattern นั้น
4. การแจ้งเตือน → Webhook URL: `https://web-production-f6b1.up.railway.app/alerts`
5. สร้าง

> 💡 ต้องตั้ง Alert แยกแต่ละ pattern (8 อัน) ถ้าอยากได้ครบ
> หรือตั้งแค่ P.3.2 + P.3.3 ก็พอ (edge สูงสุด)
