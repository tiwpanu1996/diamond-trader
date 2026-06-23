"""
test_pa_full.py — PA Engine Test Suite
SSOT: PA_SPEC_MASTER_v2.1 (Section 9 Pseudocode)
Version: v2.1 | มิ.ย. 2026

กฎที่ทดสอบ:
  - Candle index: [1]=Sig, [2]=Setup, [3]=Anchor
  - ">" strict เสมอ (ค่าพอดี = ไม่นับ)
  - Pat3 ตรวจก่อน Pat2 เสมอ
  - open==close = reject (ทั้ง Sig และ anchor)
  - is_small = body[2] < 0.15 × body[3]
  - midCombined Buy  = open[3] - (body[3]+body[2]) / 2
  - midCombined Sell = open[3] + (body[3]+body[2]) / 2
"""

import unittest
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────
#  CANDLE DATA CLASS
# ─────────────────────────────────────────────
@dataclass
class Candle:
    o: float   # open
    h: float   # high
    l: float   # low
    c: float   # close


# ─────────────────────────────────────────────
#  PA ENGINE — ตรง §9 Pseudocode v2.1
# ─────────────────────────────────────────────
def mid(k: Candle) -> float:
    return (k.o + k.c) / 2.0

def body(k: Candle) -> float:
    return abs(k.c - k.o)

def mid_combined_buy(k3: Candle, k2: Candle) -> float:
    """กำแพงรวม 2 แท่งแดง — open[3] ลงมาครึ่งก้อน"""
    return k3.o - (body(k3) + body(k2)) / 2.0

def mid_combined_sell(k3: Candle, k2: Candle) -> float:
    """กำแพงรวม 2 แท่งเขียว — open[3] ขึ้นมาครึ่งก้อน"""
    return k3.o + (body(k3) + body(k2)) / 2.0

def detect_pat1_buy(k: Candle) -> Optional[str]:
    b = body(k)
    r = k.h - k.l
    lo = min(k.o, k.c) - k.l
    up = k.h - max(k.o, k.c)
    if r <= 0 or b <= 0:
        return None
    if b > 0.40 * r:
        return None
    if lo < 2.0 * b:
        return None
    if lo < 0.50 * r:
        return None
    if lo < 2.0 * up:
        return None
    return "Pat1"

def detect_pat1_sell(k: Candle) -> Optional[str]:
    b = body(k)
    r = k.h - k.l
    lo = min(k.o, k.c) - k.l
    up = k.h - max(k.o, k.c)
    if r <= 0 or b <= 0:
        return None
    if b > 0.40 * r:
        return None
    if up < 2.0 * b:
        return None
    if up < 0.50 * r:
        return None
    if up < 2.0 * lo:
        return None
    return "Pat1"

def detect_buy(cs: list) -> Optional[str]:
    """
    cs = [oldest, ..., k3, k2, sig]
    cs[-1]=Sig[1], cs[-2]=k2[2], cs[-3]=k3[3]
    """
    sig = cs[-1]
    # Sig ต้องเขียว (ตัดโดจิ)
    if not (sig.c > sig.o):
        return None

    # ── Pat3 (ตรวจก่อน) ──
    if len(cs) >= 3:
        k2 = cs[-2]
        k3 = cs[-3]
        # anchor [3] ต้องแดง + มีทิศ
        if k3.c < k3.o:
            is_small = body(k2) < 0.15 * body(k3)
            # สาย A: Pat3.1 (is_small) หรือ Pat3.2 (k2 แดง + ไม่เล็ก)
            if is_small or k2.c < k2.o:
                if sig.c > mid_combined_buy(k3, k2):
                    return "Pat3.1" if is_small else "Pat3.2"
            # สาย B: Pat3.3 — k2 เขียว + ไม่เล็ก
            elif k2.c > k2.o and not is_small:
                if sig.c > mid(k3):
                    return "Pat3.3"

    # ── Pat2 ──
    if len(cs) >= 2:
        k2 = cs[-2]
        if k2.c < k2.o and sig.c > mid(k2):
            return "Pat2"

    return None

def detect_sell(cs: list) -> Optional[str]:
    """mirror ของ detect_buy"""
    sig = cs[-1]
    # Sig ต้องแดง
    if not (sig.c < sig.o):
        return None

    # ── Pat3 ──
    if len(cs) >= 3:
        k2 = cs[-2]
        k3 = cs[-3]
        # anchor [3] ต้องเขียว + มีทิศ
        if k3.c > k3.o:
            is_small = body(k2) < 0.15 * body(k3)
            # สาย A: Pat3.1 / Pat3.2
            if is_small or k2.c > k2.o:
                if sig.c < mid_combined_sell(k3, k2):
                    return "Pat3.1" if is_small else "Pat3.2"
            # สาย B: Pat3.3 — k2 แดง + ไม่เล็ก
            elif k2.c < k2.o and not is_small:
                if sig.c < mid(k3):
                    return "Pat3.3"

    # ── Pat2 ──
    if len(cs) >= 2:
        k2 = cs[-2]
        if k2.c > k2.o and sig.c < mid(k2):
            return "Pat2"

    return None


# ─────────────────────────────────────────────
#  TEST SUITE
# ─────────────────────────────────────────────
class TestPat1Buy(unittest.TestCase):
    """Pat1 Buy — ขาหยั่ง (4 shape rules ครบ)"""

    def _pin_bar_buy(self):
        # o=3200,c=3202,h=3208,l=3188
        # body=2, range=20, lower=min(3200,3202)-3188=12, upper=3208-3202=6
        # (1)body(2)≤0.4*20=8 ✓ (2)lower(12)≥2*body(2)=4 ✓
        # (3)lower(12)≥0.5*20=10 ✓ (4)lower(12)≥2*upper(6)=12 ✓
        return Candle(o=3200, h=3208, l=3188, c=3202)

    def test_pat1_buy_pass(self):
        self.assertEqual(detect_pat1_buy(self._pin_bar_buy()), "Pat1")

    def test_pat1_buy_fail_body_too_large(self):
        # body=10 > 0.4*20=8
        k = Candle(o=3195, h=3210, l=3190, c=3205)
        self.assertIsNone(detect_pat1_buy(k))

    def test_pat1_buy_fail_lower_too_short(self):
        # lower=2 < 2*body — ขาหยั่งสั้นเกิน
        k = Candle(o=3198, h=3210, l=3196, c=3200)
        self.assertIsNone(detect_pat1_buy(k))

    def test_pat1_buy_fail_doji_body_zero(self):
        # body=0 → reject
        k = Candle(o=3200, h=3210, l=3190, c=3200)
        self.assertIsNone(detect_pat1_buy(k))


class TestPat1Sell(unittest.TestCase):
    """Pat1 Sell — หัวห้อย (mirror)"""

    def _shooting_star(self):
        # o=3200,c=3202,h=3214,l=3196
        # body=2, range=18, upper=3214-3202=12, lower=3200-3196=4
        # (1)body(2)<=0.4*18=7.2 ✓ (2)upper(12)>=2*body(2)=4 ✓
        # (3)upper(12)>=0.5*18=9 ✓ (4)upper(12)>=2*lower(4)=8 ✓
        return Candle(o=3200, h=3214, l=3196, c=3202)

    def test_pat1_sell_pass(self):
        self.assertEqual(detect_pat1_sell(self._shooting_star()), "Pat1")

    def test_pat1_sell_fail_upper_too_short(self):
        # upper=2 < 2*body
        k = Candle(o=3200, h=3202, l=3190, c=3198)
        self.assertIsNone(detect_pat1_sell(k))

    def test_pat1_sell_fail_doji(self):
        k = Candle(o=3200, h=3215, l=3190, c=3200)
        self.assertIsNone(detect_pat1_sell(k))


class TestPat2Buy(unittest.TestCase):
    """Pat2 Buy: anchor แดง[2] → Sig เขียว[1], close[1] > mid(k2)"""

    def _build(self, sig_close):
        # k2 แดง: o=3200, c=3190 → mid=3195
        k2 = Candle(o=3200, h=3205, l=3185, c=3190)
        sig = Candle(o=3188, h=3200, l=3186, c=sig_close)
        return [k2, sig]

    def test_pat2_buy_pass(self):
        # close=3196 > mid=3195
        self.assertEqual(detect_buy(self._build(3196)), "Pat2")

    def test_pat2_buy_fail_exact_mid(self):
        # close=3195 = mid → strict >, ไม่นับ
        self.assertIsNone(detect_buy(self._build(3195)))

    def test_pat2_buy_fail_below_mid(self):
        self.assertIsNone(detect_buy(self._build(3194)))

    def test_pat2_buy_fail_sig_red(self):
        # Sig ต้องเขียว
        k2 = Candle(o=3200, h=3205, l=3185, c=3190)
        sig = Candle(o=3198, h=3200, l=3186, c=3192)  # แดง
        self.assertIsNone(detect_buy([k2, sig]))

    def test_pat2_buy_fail_anchor_green(self):
        # anchor ต้องแดง
        k2 = Candle(o=3185, h=3205, l=3182, c=3195)   # เขียว
        sig = Candle(o=3192, h=3205, l=3190, c=3200)
        self.assertIsNone(detect_buy([k2, sig]))

    def test_pat2_buy_fail_anchor_doji(self):
        k2 = Candle(o=3195, h=3205, l=3185, c=3195)   # doji
        sig = Candle(o=3190, h=3205, l=3188, c=3200)
        self.assertIsNone(detect_buy([k2, sig]))


class TestPat2Sell(unittest.TestCase):
    """Pat2 Sell: anchor เขียว[2] → Sig แดง[1], close[1] < mid(k2)"""

    def _build(self, sig_close):
        # k2 เขียว: o=3190, c=3200 → mid=3195
        k2 = Candle(o=3190, h=3205, l=3185, c=3200)
        sig = Candle(o=3198, h=3200, l=3188, c=sig_close)
        return [k2, sig]

    def test_pat2_sell_pass(self):
        self.assertEqual(detect_sell(self._build(3194)), "Pat2")

    def test_pat2_sell_fail_exact_mid(self):
        self.assertIsNone(detect_sell(self._build(3195)))

    def test_pat2_sell_fail_above_mid(self):
        self.assertIsNone(detect_sell(self._build(3196)))

    def test_pat2_sell_fail_sig_green(self):
        k2 = Candle(o=3190, h=3205, l=3185, c=3200)
        sig = Candle(o=3192, h=3200, l=3190, c=3198)  # เขียว
        self.assertIsNone(detect_sell([k2, sig]))


class TestPat31Buy(unittest.TestCase):
    """Pat3.1 Buy: k3 แดง, k2 โดจิ/เล็ก (is_small), close[1] > midCombined"""

    def _build(self, sig_close, k2_body=0.5):
        # k3 แดง: o=3200, c=3180, body=20
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        # k2 โดจิ: body=0.5 < 0.15*20=3 → is_small=True
        k2 = Candle(o=3179, h=3182, l=3177, c=3179 + k2_body)  # เขียวเล็กมาก
        # midCombined = 3200 - (20 + body(k2)) / 2
        sig = Candle(o=3177, h=3205, l=3176, c=sig_close)
        return [k3, k2, sig]

    def test_pat31_buy_pass(self):
        # midCombined = 3200 - (20+0.5)/2 = 3200 - 10.25 = 3189.75
        self.assertEqual(detect_buy(self._build(3190.0)), "Pat3.1")

    def test_pat31_buy_fail_exact_wall(self):
        # close = 3189.75 → strict >, ไม่นับ
        self.assertIsNone(detect_buy(self._build(3189.75)))

    def test_pat31_buy_fail_not_small(self):
        # body k2 = 5 >= 0.15*20=3 → is_small=False
        # k2 เขียว → ไม่เข้า สาย A และ k2 เขียว not is_small → สาย B Pat3.3
        # แต่ Sig ต้องผ่าน mid(k3)=3190 ด้วย — ทดสอบว่าไม่ได้เป็น Pat3.1
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3179, h=3185, l=3177, c=3184)   # body=5, เขียว
        sig = Candle(o=3182, h=3205, l=3180, c=3191)   # > mid(k3)=3190
        result = detect_buy([k3, k2, sig])
        self.assertNotEqual(result, "Pat3.1")           # ไม่ใช่ 3.1
        self.assertEqual(result, "Pat3.3")              # ต้องเป็น 3.3


class TestPat31Sell(unittest.TestCase):
    """Pat3.1 Sell: k3 เขียว, k2 โดจิ, close[1] < midCombined"""

    def test_pat31_sell_pass(self):
        # k3 เขียว: o=3180, c=3200, body=20
        # k2 โดจิ: body=0.5
        # midCombined = 3180 + (20+0.5)/2 = 3180 + 10.25 = 3190.25
        k3 = Candle(o=3180, h=3205, l=3175, c=3200)
        k2 = Candle(o=3200, h=3202, l=3198, c=3200.5)  # body=0.5, เขียวเล็ก
        sig = Candle(o=3202, h=3204, l=3188, c=3190.0)  # < 3190.25
        self.assertEqual(detect_sell([k3, k2, sig]), "Pat3.1")

    def test_pat31_sell_fail_exact(self):
        k3 = Candle(o=3180, h=3205, l=3175, c=3200)
        k2 = Candle(o=3200, h=3202, l=3198, c=3200.5)
        sig = Candle(o=3202, h=3204, l=3188, c=3190.25)  # พอดี wall = ไม่นับ Pat3.1
        result = detect_sell([k3, k2, sig])
        self.assertNotEqual(result, "Pat3.1")   # strict > → Pat3.1 ต้องไม่ถูก return


class TestPat32Buy(unittest.TestCase):
    """Pat3.2 Buy: k3 แดง, k2 แดงเล็กลง (is_small=False, k2 แดง), close > midCombined"""

    def test_pat32_buy_pass(self):
        # k3 แดง: body=20
        # k2 แดง: body=5 >= 0.15*20=3 → is_small=False, k2 แดง → สาย A → Pat3.2
        # midCombined = 3200 - (20+5)/2 = 3200 - 12.5 = 3187.5
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3178, h=3180, l=3170, c=3173)  # แดง, body=5
        sig = Candle(o=3170, h=3200, l=3168, c=3188.0)  # > 3187.5
        self.assertEqual(detect_buy([k3, k2, sig]), "Pat3.2")

    def test_pat32_buy_fail_exact_wall(self):
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3178, h=3180, l=3170, c=3173)
        sig = Candle(o=3170, h=3200, l=3168, c=3187.5)  # = wall, strict > → Pat3.2 ต้องไม่ return
        result = detect_buy([k3, k2, sig])
        self.assertNotEqual(result, "Pat3.2")

    def test_pat32_buy_fail_k2_green(self):
        # k2 เขียว + ไม่เล็ก → สาย B (Pat3.3), ไม่ใช่ Pat3.2
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3173, h=3185, l=3170, c=3178)  # เขียว, body=5
        sig = Candle(o=3175, h=3200, l=3173, c=3191)
        result = detect_buy([k3, k2, sig])
        self.assertNotEqual(result, "Pat3.2")


class TestPat32Sell(unittest.TestCase):
    """Pat3.2 Sell: k3 เขียว, k2 เขียวเล็กลง, close < midCombined"""

    def test_pat32_sell_pass(self):
        # k3 เขียว: o=3180, c=3200, body=20
        # k2 เขียว: body=5 → is_small=False, k2 เขียว → สาย A → Pat3.2
        # midCombined = 3180 + (20+5)/2 = 3180 + 12.5 = 3192.5
        k3 = Candle(o=3180, h=3205, l=3175, c=3200)
        k2 = Candle(o=3200, h=3208, l=3200, c=3205)  # เขียว, body=5
        sig = Candle(o=3205, h=3207, l=3190, c=3192.0)  # < 3192.5
        self.assertEqual(detect_sell([k3, k2, sig]), "Pat3.2")

    def test_pat32_sell_fail_exact(self):
        k3 = Candle(o=3180, h=3205, l=3175, c=3200)
        k2 = Candle(o=3200, h=3208, l=3200, c=3205)
        sig = Candle(o=3205, h=3207, l=3190, c=3192.5)  # พอดี wall → Pat3.2 ต้องไม่ return
        result = detect_sell([k3, k2, sig])
        self.assertNotEqual(result, "Pat3.2")


class TestPat33Buy(unittest.TestCase):
    """Pat3.3 Buy: k3 แดง, k2 เขียวเล็ก (not is_small), close[1] > mid(k3)"""

    def test_pat33_buy_pass(self):
        # k3 แดง: o=3200, c=3180, body=20, mid=3190
        # k2 เขียว: body=6 >= 0.15*20=3 → not is_small, k2 เขียว → สาย B Pat3.3
        # Sig: close=3191 > mid(k3)=3190
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3178, h=3186, l=3177, c=3184)  # เขียว, body=6
        sig = Candle(o=3182, h=3205, l=3180, c=3191)
        self.assertEqual(detect_buy([k3, k2, sig]), "Pat3.3")

    def test_pat33_buy_fail_exact_mid(self):
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3178, h=3186, l=3177, c=3184)
        sig = Candle(o=3182, h=3205, l=3180, c=3190.0)  # = mid(k3), ไม่นับ
        self.assertIsNone(detect_buy([k3, k2, sig]))

    def test_pat33_buy_fail_k2_small(self):
        # k2 เขียวแต่เล็กมาก → is_small=True → สาย A (Pat3.1) ไม่ใช่ Pat3.3
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3178, h=3179, l=3177, c=3178.5)  # body=0.5 < 3
        sig = Candle(o=3177, h=3200, l=3176, c=3191)
        result = detect_buy([k3, k2, sig])
        self.assertNotEqual(result, "Pat3.3")
        self.assertEqual(result, "Pat3.1")

    def test_pat33_buy_fail_k2_red(self):
        # k2 แดง + not is_small → สาย A (Pat3.2) ไม่ใช่ Pat3.3
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)
        k2 = Candle(o=3182, h=3184, l=3174, c=3177)  # แดง, body=5
        sig = Candle(o=3175, h=3200, l=3173, c=3191)
        result = detect_buy([k3, k2, sig])
        self.assertNotEqual(result, "Pat3.3")
        self.assertEqual(result, "Pat3.2")


class TestPat33Sell(unittest.TestCase):
    """Pat3.3 Sell: k3 เขียว, k2 แดงเล็ก (not is_small), close[1] < mid(k3)"""

    def test_pat33_sell_pass(self):
        # k3 เขียว: o=3180, c=3200, mid=3190
        # k2 แดง: body=6, not is_small → สาย B Pat3.3
        # Sig: close=3189 < 3190
        k3 = Candle(o=3180, h=3205, l=3175, c=3200)
        k2 = Candle(o=3202, h=3204, l=3194, c=3196)  # แดง, body=6
        sig = Candle(o=3198, h=3200, l=3185, c=3189)
        self.assertEqual(detect_sell([k3, k2, sig]), "Pat3.3")

    def test_pat33_sell_fail_exact(self):
        k3 = Candle(o=3180, h=3205, l=3175, c=3200)
        k2 = Candle(o=3202, h=3204, l=3194, c=3196)
        sig = Candle(o=3198, h=3200, l=3185, c=3190.0)  # = mid(k3)
        self.assertIsNone(detect_sell([k3, k2, sig]))


class TestPriority(unittest.TestCase):
    """Pat3 ต้องตัด Pat2 ออกเมื่อเงื่อนไข Pat3 ครบ"""

    def test_pat3_wins_over_pat2_buy(self):
        # Setup ที่ Pat2 จะผ่าน แต่ Pat3.2 ก็ผ่านด้วย → ต้องได้ Pat3.2
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)   # แดง, body=20
        k2 = Candle(o=3178, h=3180, l=3170, c=3173)   # แดง, body=5
        # mid(k2) = (3178+3173)/2 = 3175.5
        # midCombined = 3200 - (20+5)/2 = 3187.5
        # close=3188 > 3187.5 (Pat3.2 pass) AND > 3175.5 (Pat2 pass)
        sig = Candle(o=3170, h=3200, l=3168, c=3188)
        self.assertEqual(detect_buy([k3, k2, sig]), "Pat3.2")

    def test_pat3_wins_over_pat2_sell(self):
        k3 = Candle(o=3180, h=3205, l=3175, c=3200)   # เขียว, body=20
        k2 = Candle(o=3202, h=3206, l=3200, c=3205)   # เขียว, body=3 → is_small=False
        # midCombined = 3180 + (20+3)/2 = 3180 + 11.5 = 3191.5
        # close=3191 < 3191.5 ✓ (Pat3.2) AND mid(k2)=(3202+3205)/2=3203.5 > 3191 (Pat2 ก็ผ่าน)
        sig = Candle(o=3205, h=3207, l=3188, c=3191.0)
        self.assertEqual(detect_sell([k3, k2, sig]), "Pat3.2")


class TestEdgeCases(unittest.TestCase):
    """Edge cases — กฎเด็ดขาดจาก §0"""

    def test_reject_sig_doji_buy(self):
        # Sig open==close → reject
        k2 = Candle(o=3200, h=3205, l=3185, c=3190)
        sig = Candle(o=3196, h=3202, l=3190, c=3196)  # doji
        self.assertIsNone(detect_buy([k2, sig]))

    def test_reject_sig_doji_sell(self):
        k2 = Candle(o=3190, h=3205, l=3185, c=3200)
        sig = Candle(o=3195, h=3202, l=3190, c=3195)  # doji
        self.assertIsNone(detect_sell([k2, sig]))

    def test_reject_k3_doji_anchor(self):
        # k3 doji (open==close) → k3.c < k3.o ไม่จริง → ไม่เข้า Pat3
        k3 = Candle(o=3190, h=3205, l=3175, c=3190)  # doji
        k2 = Candle(o=3188, h=3190, l=3186, c=3188.5)
        sig = Candle(o=3186, h=3205, l=3184, c=3195)
        # ถ้า Pat3 ถูก skip → ลง Pat2 (k2 เขียว → ไม่ผ่าน Pat2 Buy)
        self.assertIsNone(detect_buy([k3, k2, sig]))

    def test_pat2_strict_greater_than(self):
        # close พอดีกับ mid → ไม่นับ
        k2 = Candle(o=3200, h=3205, l=3185, c=3190)   # mid=3195
        sig = Candle(o=3193, h=3200, l=3191, c=3195)  # close=mid=3195
        self.assertIsNone(detect_buy([k2, sig]))

    def test_pat33_strict_greater_than(self):
        # close พอดี mid(k3) → ไม่นับ
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)   # mid=3190
        k2 = Candle(o=3178, h=3186, l=3177, c=3184)   # เขียว, body=6
        sig = Candle(o=3182, h=3200, l=3180, c=3190)  # =mid(k3)
        self.assertIsNone(detect_buy([k3, k2, sig]))

    def test_is_small_boundary(self):
        # body(k2) = exactly 0.15 × body(k3) → ไม่ is_small (< ไม่ผ่าน)
        # k3 body=20 → boundary = 3.0; k2 body=3.0 → is_small = False
        k3 = Candle(o=3200, h=3205, l=3175, c=3180)   # body=20
        k2 = Candle(o=3178, h=3180, l=3172, c=3175)   # body=3, แดง → Pat3.2
        # midCombined = 3200 - (20+3)/2 = 3188.5
        sig = Candle(o=3172, h=3200, l=3170, c=3189)
        result = detect_buy([k3, k2, sig])
        self.assertEqual(result, "Pat3.2")             # is_small=False → Pat3.2

    def test_no_signal_all_none(self):
        # ตลาดวิ่งตามเทรนด์ ไม่มี PA
        k2 = Candle(o=3195, h=3210, l=3192, c=3208)   # เขียว
        sig = Candle(o=3208, h=3220, l=3205, c=3218)  # เขียวต่อ (Sig เขียว, anchor เขียว → ไม่ผ่าน Pat2 Buy)
        self.assertIsNone(detect_buy([k2, sig]))


# ─────────────────────────────────────────────
#  RUNNER
# ─────────────────────────────────────────────
if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPat1Buy))
    suite.addTests(loader.loadTestsFromTestCase(TestPat1Sell))
    suite.addTests(loader.loadTestsFromTestCase(TestPat2Buy))
    suite.addTests(loader.loadTestsFromTestCase(TestPat2Sell))
    suite.addTests(loader.loadTestsFromTestCase(TestPat31Buy))
    suite.addTests(loader.loadTestsFromTestCase(TestPat31Sell))
    suite.addTests(loader.loadTestsFromTestCase(TestPat32Buy))
    suite.addTests(loader.loadTestsFromTestCase(TestPat32Sell))
    suite.addTests(loader.loadTestsFromTestCase(TestPat33Buy))
    suite.addTests(loader.loadTestsFromTestCase(TestPat33Sell))
    suite.addTests(loader.loadTestsFromTestCase(TestPriority))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"RESULT: {passed}/{total} passed")
    if result.wasSuccessful():
        print("✅ ALL PASS — PA Engine v2.1 validated")
    else:
        print("❌ FAILURES DETECTED — review above")
    print("=" * 60)
