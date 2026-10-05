#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
synth_final_model.py - 5번(종합) 재계산 스크립트.
2번 에이전트 모듈(agent2_model.py: 영역별 필요시간표·조합 탐색·시험 당일 변동·몬테카를로)을 그대로 쓰고,
종합 단계 보정 세 가지만 덧씌운다. 보정값은 모두 [판단]이며 상단 상수로 바꿀 수 있다.
  (1) BIAS: 필요시간 과소추정 보정 배수(계획 오류 성격). 1.0 = 2번 원값.
  (2) 실행 혼합분포: 확률 Q_BREAK로 '실행 붕괴'(하루 실질 중앙 3.5h), 나머지는 '정상 실행'(중앙 6.5h).
  (3) 반영 구조 대안: '국·수·영 중 상위 2 + 탐구 1과목' 구조에서 필요한 시간.
실행: python3 synth_final_model.py  (numpy 필요, seed 고정)
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent2_model as m   # 모듈 임포트 시 P15_SUB(시험 당일 변동 정확계산)만 수행

N = 10000
D_WEEK = 6.5
NORMAL = dict(med=6.5, lo=4.8, hi=8.5)      # [판단] 정상 실행 시 하루 실질시간 중앙/80% 구간
BROKEN = dict(med=3.5, lo=2.0, hi=5.0)      # [판단] 실행 붕괴 시
GRID_BIAS = (1.0, 1.2, 1.35)
GRID_Q = (0.0, 0.2, 0.3)
CENTRAL = dict(bias=1.2, q=0.2)

def lnsig(lo, hi):
    return (math.log(hi) - math.log(lo)) / (2 * m.Z80)

def daily_hours(n, q, seed):
    rng = np.random.default_rng(seed)
    nh = np.exp(math.log(NORMAL["med"]) + lnsig(NORMAL["lo"], NORMAL["hi"]) * rng.standard_normal(n))
    bh = np.exp(math.log(BROKEN["med"]) + lnsig(BROKEN["lo"], BROKEN["hi"]) * rng.standard_normal(n))
    return np.where(rng.random(n) < q, bh, nh)

def run(key, weeks, bias, q, seed=101, r_over=None, y2=None):
    tab, hist = m.tables(key) if r_over is None else m.tables(key, r_over=r_over)
    h = daily_hours(N, q, seed)
    if y2 is None:
        A = h * D_WEEK * weeks
    else:  # y2 = (1년차 주수, 2년차 주수, 2년차 효율)
        A = h * D_WEEK * (y2[0] + y2[1] * y2[2])
    r = m.mc(tab, hist, m.SIGMA[key], n=N, seed=m.SEED + 7, budgets={"A": A / bias})
    sb = r["sbest"]["A"]
    return float(np.mean(r["succ"]["A"])), sb, A

def q_(x, p):
    return float(np.quantile(x, p))

def main():
    wk = {k: m.weeks(*k) for k in (("S1", "E28b"), ("S2", "E28b"), ("S2", "E29b"))}
    print("# synth_final_model.py 출력 (N=%d, 정상 실행 %s, 붕괴 %s, 주 %.1f일)" % (N, NORMAL, BROKEN, D_WEEK))

    print("\n## A. Q3 개인화: 2027-11-18 수능에서 P(관측 5영역 합계≤15) — 보정 격자")
    for per in (("S2", "E28b"), ("S1", "E28b")):
        print(f"\n시작 {m.DATES[per[0]]} → {m.DATES[per[1]]} ({wk[per]:.1f}주)\n")
        print("| 편향 배수 \\ 붕괴확률 | " + " | ".join(f"q={q:.1f}" for q in GRID_Q) + " |")
        print("|---|" + "---|" * len(GRID_Q))
        for b in GRID_BIAS:
            row = []
            for q in GRID_Q:
                p, sb, A = run("Q3", wk[per], b, q)
                row.append(f"{p:.2f}")
            print(f"| ×{b:.2f} | " + " | ".join(row) + " |")

    print("\n## B. 같은 계산을 Q1 기준 모델에 (10/5 시작)")
    print("\n| 편향 배수 \\ 붕괴확률 | " + " | ".join(f"q={q:.1f}" for q in GRID_Q) + " |")
    print("|---|" + "---|" * len(GRID_Q))
    for b in GRID_BIAS:
        print(f"| ×{b:.2f} | " + " | ".join(f"{run('Q1', wk[('S2','E28b')], b, q)[0]:.2f}" for q in GRID_Q) + " |")

    print("\n## C. 중심 보정(편향 ×%.2f, 붕괴 %.1f)에서 실패 시 도달 수준 (Q3, 10/5 시작)" % (CENTRAL["bias"], CENTRAL["q"]))
    p, sb, A = run("Q3", wk[("S2", "E28b")], CENTRAL["bias"], CENTRAL["q"])
    print(f"- P(관측합계≤15) = {p:.2f}; 가용 실질시간 A P10/P50/P90 = {q_(A,.1):,.0f}/{q_(A,.5):,.0f}/{q_(A,.9):,.0f}h (편향 배수 적용 전)")
    print(f"- 예산 내 최선 기대합계(=실력 수준) P10/P50/P90 = {q_(sb,.1):.0f}/{q_(sb,.5):.0f}/{q_(sb,.9):.0f}  (평균등급 = 합계/5)")
    fail = sb[sb > 15]
    print(f"- 기대합계>15(실력이 목표 미달)인 경우 비율 {np.mean(sb > 15):.2f}; 그때 기대합계 P25/P50/P75/P90 = "
          f"{q_(fail,.25):.0f}/{q_(fail,.5):.0f}/{q_(fail,.75):.0f}/{q_(fail,.9):.0f}")
    hist_ = {s: float(np.mean(sb == s)) for s in range(5, 24)}
    print("- 기대합계 분포: " + ", ".join(f"{s}:{v:.0%}" for s, v in hist_.items() if v >= 0.01))

    print("\n## D. 1년 더(2029학년도 수능 2028-11-16 가정), 망각 오버헤드 1.15·2년차 효율 0.9 (2번 가정 승계)")
    y1, y2w = wk[("S2", "E28b")], wk[("S2", "E29b")] - wk[("S2", "E28b")]
    print("\n| 편향 배수 \\ 붕괴확률 | q=0.2 | q=0.3 | q=0.4 |")
    print("|---|---|---|---|")
    for b in GRID_BIAS:
        print(f"| ×{b:.2f} | " + " | ".join(f"{run('Q3', 0, b, q, r_over=1.15, y2=(y1, y2w, 0.9))[0]:.2f}" for q in (0.2, 0.3, 0.4)) + " |")

    print("\n## E. 하루 실질시간 고정 시나리오(붕괴 없음)에서 Q3 P — 편향 ×1.0 / ×1.2")
    for hd in (4, 5, 6, 7, 8, 12):
        tab, hist = m.tables("Q3")
        A = np.full(N, hd * D_WEEK * wk[("S2", "E28b")])
        r1 = m.mc(tab, hist, m.SIGMA["Q3"], n=N, seed=m.SEED + 7, budgets={"a": A, "b": A / 1.2})
        print(f"- {hd}h/일 × {D_WEEK}일 × {wk[('S2','E28b')]:.1f}주 = {A[0]:,.0f}h: P = {np.mean(r1['succ']['a']):.2f} / {np.mean(r1['succ']['b']):.2f}")

    print("\n## F. 반영 구조 대안: '국·수·영 중 상위 2 + 탐구 1과목' (Q3 시간표 점추정, 한국사 포함)")
    tab, hist = m.tables("Q3")
    for label, parts in [
        ("국3·영2·통합사회3", [("국어", 3), ("영어", 2), ("통합사회", 3)]),
        ("국3·영2·통합과학3", [("국어", 3), ("영어", 2), ("통합과학", 3)]),
        ("국2·영2·통합사회2", [("국어", 2), ("영어", 2), ("통합사회", 2)]),
        ("국2·영2·통합과학2", [("국어", 2), ("영어", 2), ("통합과학", 2)]),
        ("(참고) 위 + 수학 5등급", [("국어", 2), ("영어", 2), ("통합과학", 2), ("수학", 5)]),
    ]:
        h = sum(tab[a][g] for a, g in parts) + hist
        print(f"- {label}: {h:,.0f}h (중앙값 합; 영역별 80% 구간은 1절 표)")

if __name__ == "__main__":
    main()
