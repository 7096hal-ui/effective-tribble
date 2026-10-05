# -*- coding: utf-8 -*-
"""a4_extra5.py - (1) 수학 반영 대학 제약(수학 기대등급 <=5 또는 <=4만 허용) (2) 비관 요인 결합. 오라클, 5과목 기준."""
import os, sys
import numpy as np
sys.path.insert(0, ".")
import a2mod as M
from a4_stress import hours, HRS_DEF, SEED_A, SEED_K, p15_gd, sd_matrix
from a4_extra import oracle_p
N = int(os.environ.get("A4N", "5000"))
sig = M.SIGMA["Q3"]
pick = ["H0 2번 현실(7h, 80% 5.5-9)", "H2 5.5h, 80% 3.5-8.5 + 중단위험 20%", "H4 4h, 80% 2.5-6.5 + 중단위험 25%"]
Avec = {k: hours(N, SEED_A, **HRS_DEF[k]) for k in pick}
print("# a4_extra5.py 출력 (N=%d)\n" % N)
print("## 1. 수학 하한 제약(수학 기대등급 상한) - 2번 v2 Q3 표, 2번 잡음\n")
print("| 제약 | 필요시간 P50 | P H0 | P H2 | P H4 |")
print("|---|---|---|---|---|")
for nm, gmax in (("제약 없음", 9), ("수학 5등급 이내", 5), ("수학 4등급 이내", 4), ("수학 3등급 이내", 3)):
    tab, hist = M.tables("Q3")
    for g in range(gmax + 1, 10):
        tab["수학"][g] = 1e7
    ps, h50 = [], None
    for k in pick:
        p, h50 = oracle_p(tab, hist, sig, Avec[k])
        ps.append(p)
    print(f"| {nm} | {h50:,.0f} | " + " | ".join(f"{x:.2f}" for x in ps) + " |")

print("\n## 2. 비관 요인 결합(5과목 기준)\n")
keep = {a: dict(M.PRAC[a]) for a in ("통합사회", "통합과학")}
base_sd = dict(M.NOISE_SD)
SD1 = sd_matrix({**base_sd, "영어": 0.80}, {"통합사회": {1: 1.0, 2: 1.0}, "통합과학": {1: 1.0, 2: 1.0}, "수학": {6: 0.9, 7: 1.0, 8: 1.0, 9: 1.0}})
P1 = p15_gd(M.SUB.astype(float), SD1)
rng = np.random.default_rng(SEED_K); k = M.draw_k(sig, N, rng)
gm = np.exp(np.mean([np.log(k[a]) for a in M.AREAS], axis=0))
fb = np.maximum(gm, 1.0) ** -0.5
print("| 결합 | P H0 | P H2 | P H4 |")
print("|---|---|---|---|")
for nm, over in (("T1+N1+되먹임", {}), ("T1+N1+되먹임+국어6·영어4.0", dict(q3_kor_start=6, q3_eng_start=4.0)),
                 ("T1+N1+되먹임+국어6·영어3.5+망각1.25", dict(q3_kor_start=6, q3_eng_start=3.5, r_over=1.25))):
    M.PRAC["통합사회"].update({3: 110, 2: 270, 1: 700}); M.PRAC["통합과학"].update({3: 160, 2: 375, 1: 800})
    tab, hist = M.tables("Q3", **over)
    M.PRAC["통합사회"].update(keep["통합사회"]); M.PRAC["통합과학"].update(keep["통합과학"])
    ps = [oracle_p(tab, hist, sig, Avec[kk] * fb, P1)[0] for kk in pick]
    print(f"| {nm} | " + " | ".join(f"{x:.2f}" for x in ps) + " |")
