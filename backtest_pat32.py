"""
backtest_pat32.py — Pat3.2 Backtest (v1.0 vs v2.1)
SSOT: PA_SPEC_MASTER_v2.1

เปรียบเทียบ 2 logic:
  v1.0: กำแพง = midBody ของ k3 เดียว
  v2.1: กำแพง = midCombined (k3+k2 รวมกัน) ← SSOT ปัจจุบัน

Simulation:
  Entry  = close[1] (Sig candle)
  SL     = 300 จุด (fixed fallback ตาม spec)
  TP     = RR 1:3 = 900 จุด
  Exit   = เช็ค high/low แท่งถัดไปทีละแท่ง (max 48 แท่ง = 2 วัน H1)
  Data   = Synthetic XAU H1 realistic random walk (seed ตายตัว = reproducible)
  Spread = 160 จุด (หักออกจาก entry)
"""

import random
import math
from dataclasses import dataclass
from typing import Optional, List, Tuple

# ── กำหนด seed ตายตัว (reproducible) ──────────────────────────
SEED = 42
random.seed(SEED)

# ── ค่าคงที่ระบบ ───────────────────────────────────────────────
SL_PTS     = 300     # จุด = 3.00 USD
TP_PTS     = 900     # RR 1:3
SPREAD_PTS = 160     # หักจาก entry (buy ซื้อแพงกว่า)
MAX_BARS   = 48      # ถือสูงสุด 48 แท่ง
IS_SMALL_RATIO = 0.15


# ─────────────────────────────────────────────────────────────────
#  CANDLE DATA
# ─────────────────────────────────────────────────────────────────
@dataclass
class Candle:
    o: float
    h: float
    l: float
    c: float


# ─────────────────────────────────────────────────────────────────
#  SYNTHETIC XAU OHLC GENERATOR
#  ลักษณะ: GBM + wick ratio realistic ของ XAU H1
# ─────────────────────────────────────────────────────────────────
def generate_xau_candles(n: int = 3000, start_price: float = 3200.0) -> List[Candle]:
    """
    สร้าง XAU H1 synthetic OHLC ที่ realistic:
    - drift = 0 (neutral market)
    - vol   = 0.0015 per bar (≈ 5 USD / bar บน 3200)
    - wick  = 0.3–0.7 × range (realistic)
    """
    candles = []
    price = start_price

    for _ in range(n):
        # Return สุ่ม (GBM)
        ret = random.gauss(0, 0.0015)
        close_price = price * (1 + ret)

        # Range = volatility × base
        bar_range = abs(price * random.gauss(0.002, 0.0008))
        bar_range = max(bar_range, 0.5)  # min 50 จุด

        open_p = price
        close_p = close_price

        # จัด high/low ให้ครอบ body + wick
        body_lo = min(open_p, close_p)
        body_hi = max(open_p, close_p)
        body_sz = body_hi - body_lo

        # wick ratio: lower 20–60% ของ range, upper ที่เหลือ
        wick_lo = random.uniform(0.15, 0.55) * bar_range
        wick_hi = bar_range - body_sz - wick_lo
        wick_hi = max(wick_hi, 0.02)

        low_p  = body_lo - wick_lo
        high_p = body_hi + wick_hi

        candles.append(Candle(o=round(open_p, 2),
                              h=round(high_p, 2),
                              l=round(low_p, 2),
                              c=round(close_p, 2)))
        price = close_price

    return candles


# ─────────────────────────────────────────────────────────────────
#  PA HELPERS
# ─────────────────────────────────────────────────────────────────
def body(k: Candle) -> float:
    return abs(k.c - k.o)

def mid(k: Candle) -> float:
    return (k.o + k.c) / 2.0

def mid_combined_buy(k3: Candle, k2: Candle) -> float:
    """v2.1 — กำแพงรวม open[3] ลงมาครึ่งก้อน"""
    return k3.o - (body(k3) + body(k2)) / 2.0

def mid_combined_sell(k3: Candle, k2: Candle) -> float:
    """v2.1 — กำแพงรวม open[3] ขึ้นมาครึ่งก้อน"""
    return k3.o + (body(k3) + body(k2)) / 2.0


# ─────────────────────────────────────────────────────────────────
#  PAT3.2 DETECTION — 2 version
# ─────────────────────────────────────────────────────────────────
def is_pat32_buy_v21(k3: Candle, k2: Candle, sig: Candle) -> bool:
    """v2.1: midCombined (k3+k2) — SSOT ปัจจุบัน"""
    if not (sig.c > sig.o):           return False   # Sig ต้องเขียว
    if not (k3.c < k3.o):             return False   # k3 ต้องแดง
    if k3.c == k3.o or k2.c == k2.o: return False   # ห้าม doji
    is_small = body(k2) < IS_SMALL_RATIO * body(k3)
    if is_small:                       return False   # Pat3.1 ไม่ใช่ 3.2
    if not (k2.c < k2.o):             return False   # k2 ต้องแดง (เล็กลง)
    wall = mid_combined_buy(k3, k2)
    return sig.c > wall                              # strict >

def is_pat32_sell_v21(k3: Candle, k2: Candle, sig: Candle) -> bool:
    """v2.1: midCombined (k3+k2) — SSOT ปัจจุบัน"""
    if not (sig.c < sig.o):           return False
    if not (k3.c > k3.o):             return False   # k3 ต้องเขียว
    if k3.c == k3.o or k2.c == k2.o: return False
    is_small = body(k2) < IS_SMALL_RATIO * body(k3)
    if is_small:                       return False
    if not (k2.c > k2.o):             return False   # k2 ต้องเขียว (เล็กลง)
    wall = mid_combined_sell(k3, k2)
    return sig.c < wall

def is_pat32_buy_v10(k3: Candle, k2: Candle, sig: Candle) -> bool:
    """v1.0: midBody ของ k3 เดียว (logic เก่า ก่อน v2.0)"""
    if not (sig.c > sig.o):           return False
    if not (k3.c < k3.o):             return False
    if k3.c == k3.o or k2.c == k2.o: return False
    is_small = body(k2) < IS_SMALL_RATIO * body(k3)
    if is_small:                       return False
    if not (k2.c < k2.o):             return False
    wall = mid(k3)                                   # กำแพงเดิม = mid k3 เดียว
    return sig.c > wall

def is_pat32_sell_v10(k3: Candle, k2: Candle, sig: Candle) -> bool:
    """v1.0: midBody ของ k3 เดียว"""
    if not (sig.c < sig.o):           return False
    if not (k3.c > k3.o):             return False
    if k3.c == k3.o or k2.c == k2.o: return False
    is_small = body(k2) < IS_SMALL_RATIO * body(k3)
    if is_small:                       return False
    if not (k2.c > k2.o):             return False
    wall = mid(k3)
    return sig.c < wall


# ─────────────────────────────────────────────────────────────────
#  TRADE SIMULATOR — RR 1:3, fixed SL 300 pts
# ─────────────────────────────────────────────────────────────────
def simulate_trade(candles: List[Candle], entry_idx: int,
                   direction: str) -> Optional[str]:
    """
    ส่งออก 'TP' / 'SL' / 'TIMEOUT'
    direction: 'buy' หรือ 'sell'
    entry_idx: index ของ Sig[1] (แท่งที่เพิ่งปิด)
    """
    sig = candles[entry_idx]

    if direction == 'buy':
        entry = sig.c + SPREAD_PTS * 0.01   # หัก spread (จุด → USD)
        sl    = entry - SL_PTS * 0.01
        tp    = entry + TP_PTS * 0.01
    else:
        entry = sig.c - SPREAD_PTS * 0.01
        sl    = entry + SL_PTS * 0.01
        tp    = entry - TP_PTS * 0.01

    # สแกนแท่งถัดไป
    for i in range(entry_idx + 1, min(entry_idx + 1 + MAX_BARS, len(candles))):
        bar = candles[i]
        if direction == 'buy':
            if bar.l <= sl: return 'SL'
            if bar.h >= tp: return 'TP'
        else:
            if bar.h >= sl: return 'SL'
            if bar.l <= tp: return 'TP'

    return 'TIMEOUT'


# ─────────────────────────────────────────────────────────────────
#  BACKTEST ENGINE
# ─────────────────────────────────────────────────────────────────
def run_backtest(candles: List[Candle],
                 detector_buy, detector_sell,
                 label: str) -> dict:
    results = {'TP': 0, 'SL': 0, 'TIMEOUT': 0, 'signals': 0,
               'buy_signals': 0, 'sell_signals': 0}

    # ต้องมี k3[3], k2[2], sig[1] → เริ่มจาก index 2
    for i in range(2, len(candles) - MAX_BARS - 1):
        k3  = candles[i - 2]
        k2  = candles[i - 1]
        sig = candles[i]

        fired = False
        if detector_buy(k3, k2, sig):
            outcome = simulate_trade(candles, i, 'buy')
            results[outcome] += 1
            results['signals'] += 1
            results['buy_signals'] += 1
            fired = True

        if not fired and detector_sell(k3, k2, sig):
            outcome = simulate_trade(candles, i, 'sell')
            results[outcome] += 1
            results['signals'] += 1
            results['sell_signals'] += 1

    tp = results['TP']
    sl = results['SL']
    total = tp + sl
    wr = (tp / total * 100) if total > 0 else 0.0

    results['label']    = label
    results['win_rate'] = round(wr, 1)
    results['total_decided'] = total
    return results


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def print_report(r: dict):
    print(f"\n{'='*55}")
    print(f"  {r['label']}")
    print(f"{'='*55}")
    print(f"  Signals detected : {r['signals']:>6}  "
          f"(Buy {r['buy_signals']} / Sell {r['sell_signals']})")
    print(f"  TP               : {r['TP']:>6}")
    print(f"  SL               : {r['SL']:>6}")
    print(f"  Timeout (48bar)  : {r['TIMEOUT']:>6}")
    print(f"  Decided (TP+SL)  : {r['total_decided']:>6}")
    print(f"  WIN RATE         : {r['win_rate']:>5}%  "
          f"(breakeven RR 1:3 = 25.0%)")
    edge = r['win_rate'] - 25.0
    marker = "✅ ABOVE breakeven" if edge >= 0 else "❌ BELOW breakeven"
    print(f"  vs Breakeven     : {edge:>+5.1f}%  {marker}")


if __name__ == '__main__':
    print("Generating 3,000 synthetic XAU H1 candles (seed=42)...")
    candles = generate_xau_candles(n=3000, start_price=3200.0)
    print(f"Price range: {min(c.l for c in candles):.2f} – "
          f"{max(c.h for c in candles):.2f} USD")

    print("\nRunning backtests...")

    r_v10 = run_backtest(candles,
                         is_pat32_buy_v10, is_pat32_sell_v10,
                         "Pat3.2 — v1.0 (midBody k3 เดียว)")

    r_v21 = run_backtest(candles,
                         is_pat32_buy_v21, is_pat32_sell_v21,
                         "Pat3.2 — v2.1 (midCombined k3+k2) ← SSOT")

    print_report(r_v10)
    print_report(r_v21)

    # สรุปเปรียบเทียบ
    delta_wr      = r_v21['win_rate'] - r_v10['win_rate']
    delta_signals = r_v21['signals'] - r_v10['signals']

    print(f"\n{'='*55}")
    print("  COMPARISON SUMMARY")
    print(f"{'='*55}")
    print(f"  Win Rate change  : {delta_wr:>+5.1f}%  "
          f"({'ดีขึ้น ✅' if delta_wr >= 0 else 'แย่ลง ❌'})")
    print(f"  Signal change    : {delta_signals:>+5d}  "
          f"(wall หนาขึ้น = signals น้อยลง = คุณภาพขึ้น)")
    print(f"\n  ⚠️  NOTE: Synthetic data — validate ด้วย real XAU CSV")
    print(f"       Export OHLC จาก TradingView แล้วรัน: ")
    print(f"       python backtest_pat32.py --csv <file.csv>")
    print(f"{'='*55}")


# ─────────────────────────────────────────────────────────────────
#  CSV IMPORT (สำหรับ real TradingView data)
#  Format: Date,Open,High,Low,Close (TradingView export standard)
# ─────────────────────────────────────────────────────────────────
def load_csv(path: str) -> List[Candle]:
    import csv
    candles = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                o = float(row.get('Open') or row.get('open', 0))
                h = float(row.get('High') or row.get('high', 0))
                l = float(row.get('Low')  or row.get('low', 0))
                c = float(row.get('Close') or row.get('close', 0))
                if o and h and l and c:
                    candles.append(Candle(o=o, h=h, l=l, c=c))
            except (ValueError, KeyError):
                continue
    return candles


if __name__ == '__main__' and '--csv' in __import__('sys').argv:
    import sys
    csv_path = sys.argv[sys.argv.index('--csv') + 1]
    print(f"Loading real data: {csv_path}")
    candles = load_csv(csv_path)
    print(f"Loaded {len(candles)} candles")
    if len(candles) < 10:
        print("ERROR: ข้อมูลน้อยเกินไป")
        sys.exit(1)

    r_v10 = run_backtest(candles, is_pat32_buy_v10, is_pat32_sell_v10,
                         "Pat3.2 — v1.0 (midBody k3 เดียว) [REAL DATA]")
    r_v21 = run_backtest(candles, is_pat32_buy_v21, is_pat32_sell_v21,
                         "Pat3.2 — v2.1 (midCombined k3+k2) [REAL DATA]")
    print_report(r_v10)
    print_report(r_v21)
