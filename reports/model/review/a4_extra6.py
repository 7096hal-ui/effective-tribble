# -*- coding: utf-8 -*-
"""a4_extra6.py - 2029학년도 수능(2028-11-16 가정)까지, 4번 가용시간 시나리오. 2번 (iii)절과 같은 방식:
오버헤드 1.15, 2년차 효율 0.9 [2번 판단]. 중단위험은 기간 전체 총량에 한 번 적용(25개월이므로 보수성 낮음)."""
import math, os, sys
import numpy as np
sys.path.insert(0, ".")
import a2mod as M
from a4_stress import HRS_DEF, SEED_A
from a4_extra import oracle_p
N = int(os.environ.get("A4N", "5000"))
w1 = M.weeks("S2", "E28b"); wt = M.weeks("S2", "E29b")
eff_w = w1 + (wt - w1) * 0.90
print("# a4_extra6.py 출력: 10/5 -> 2028-11-16, 유효 주수 %.1f\n" % eff_w)
tab, hist = M.tables("Q3", r_over=1.15)
print("| 가용 시나리오 | 가용 P10/P50/P90 | P(관측합계<=15) |")
print("|---|---|---|")
for nm, v in HRS_DEF.items():
    rng = np.random.default_rng(SEED_A)
    sig = (math.log(v["hi"]) - math.log(v["lo"])) / (2 * M.Z80)
    A = np.exp(math.log(v["med"]) + sig * rng.standard_normal(N)) * 6.5 * eff_w
    if v.get("disrupt_p", 0) > 0:
        r2 = np.random.default_rng(SEED_A + 999)
        hit = r2.random(N) < v["disrupt_p"]; loss = r2.uniform(0.25, 0.5, N)
        A = np.where(hit, A * (1 - loss), A)
    p, h50 = oracle_p(tab, hist, M.SIGMA["Q3"], A)
    print(f"| {nm} | {np.quantile(A,.1):,.0f}/{np.quantile(A,.5):,.0f}/{np.quantile(A,.9):,.0f} | {p:.2f} |")
