# -*- coding: utf-8 -*-
"""a4_extra4.py - 인지 프로필 배수(Q3ADJ) 민감도. 2번 8절에 없는 항목. 오라클, 2번 잡음, H0/H2."""
import os, sys, time
import numpy as np
sys.path.insert(0, ".")
import a2mod as M
from a4_stress import hours, HRS_DEF, SEED_A
from a4_extra import oracle_p
N = int(os.environ.get("A4N", "5000"))
sig = M.SIGMA["Q3"]
pick = ["H0 2번 현실(7h, 80% 5.5-9)", "H2 5.5h, 80% 3.5-8.5 + 중단위험 20%"]
Avec = {k: hours(N, SEED_A, **HRS_DEF[k]) for k in pick}
base = dict(M.Q3ADJ)
cases = [
    ("2번 Q3ADJ 그대로", {}),
    ("Q3ADJ 전부 1.0(프로필 미반영)", {k: 1.0 for k in base}),
    ("국어 실전 ×0.8 제거(국어_P=1.0)", {"국어_P": 1.0}),
    ("단기기억 벌점 강화(통합사회_F 1.35, 통합과학_F 1.45, 한국사 1.35)", {"통합사회_F": 1.35, "통합과학_F": 1.45, "한국사": 1.35}),
    ("강점 할인 제거 + 벌점 유지(국어_P 1.0, 영어_inc 1.0, 통합사회_P 1.0)", {"국어_P": 1.0, "영어_inc": 1.0, "통합사회_P": 1.0}),
]
print("# a4_extra4.py 출력 (N=%d)\n" % N)
print("| Q3ADJ 변경 | 필요시간 P50 | P H0 | P H2 |")
print("|---|---|---|---|")
for nm, ch in cases:
    M.Q3ADJ.clear(); M.Q3ADJ.update(base); M.Q3ADJ.update(ch)
    tab, hist = M.tables("Q3")
    r0 = oracle_p(tab, hist, sig, Avec[pick[0]])
    r2 = oracle_p(tab, hist, sig, Avec[pick[1]])
    print(f"| {nm} | {r0[1]:,.0f} | {r0[0]:.2f} | {r2[0]:.2f} |")
M.Q3ADJ.clear(); M.Q3ADJ.update(base)
