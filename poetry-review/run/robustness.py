"""강건성 시험: S = Σ w_i·d_i (A/B 환산 비교값, 양수=작품 A「건축」 쪽).

사용: python3 run/robustness.py '{"A":"-1","B":"U",...}'
- U 축은 [-2,+2] 구간으로 두어 S의 가능한 범위를 계산한다.
  하한 = 확정 항의 합 − 2×(U 축 가중치 합), 상한 = 확정 항의 합 + 2×(U 축 가중치 합).
- 14개 설정: 기본 1, 균등 1, 한 축 제거·재정규화 6, 한 축 40%·나머지 기본 비율로 60% 6.
분수 연산(fractions)으로 계산해 반올림 오차 없이 동률(0)을 판정한다.
"""
import json
import sys
from fractions import Fraction as Fr

AXES = ["A", "B", "C", "D", "E", "F"]
BASE = {"A": Fr(20, 100), "B": Fr(20, 100), "C": Fr(20, 100), "D": Fr(20, 100),
        "E": Fr(10, 100), "F": Fr(10, 100)}


def settings():
    out = [("기본 가중치", dict(BASE))]
    out.append(("균등 가중치", {a: Fr(1, 6) for a in AXES}))
    for x in AXES:
        rest = sum(BASE[a] for a in AXES if a != x)
        out.append((f"축 {x} 제거", {a: (Fr(0) if a == x else BASE[a] / rest) for a in AXES}))
    for x in AXES:
        rest = sum(BASE[a] for a in AXES if a != x)
        out.append((f"축 {x} 40%", {a: (Fr(40, 100) if a == x else BASE[a] / rest * Fr(60, 100)) for a in AXES}))
    return out


def evaluate(d, w):
    fixed = sum(w[a] * int(d[a]) for a in AXES if d[a] != "U")
    uw = sum(w[a] for a in AXES if d[a] == "U")
    return fixed, fixed - 2 * uw, fixed + 2 * uw, uw


def label(lo, hi):
    if uw_zero(lo, hi):
        v = lo
        return "A 쪽" if v > 0 else ("B 쪽" if v < 0 else "동률")
    if lo > 0:
        return "A 쪽(U와 무관)"
    if hi < 0:
        return "B 쪽(U와 무관)"
    return "미결정(범위가 0 포함)"


def uw_zero(lo, hi):
    return lo == hi


def fmt(x):
    return f"{float(x):+.3f}"


def run(d):
    rows = []
    for name, w in settings():
        assert sum(w.values()) == 1, name
        fixed, lo, hi, uw = evaluate(d, w)
        rows.append((name, w, fixed, lo, hi, uw, label(lo, hi)))
    return rows


def show(d, title=""):
    if title:
        print(f"### {title}")
    print("d (A/B 환산):", " ".join(f"{a}={d[a]}" for a in AXES))
    print("| 설정 | 가중치 A/B/C/D/E/F | 확정 항 합 | S 범위 | 결과 |")
    print("|---|---|---|---|---|")
    for name, w, fixed, lo, hi, uw, lab in run(d):
        ws = "/".join(f"{float(w[a]):.3f}" for a in AXES)
        rng = fmt(lo) if lo == hi else f"[{fmt(lo)}, {fmt(hi)}]"
        print(f"| {name} | {ws} | {fmt(fixed)} | {rng} | {lab} |")
    print()


if __name__ == "__main__":
    for i, arg in enumerate(sys.argv[1:]):
        d = json.loads(arg)
        show(d, f"입력 {i + 1}")
