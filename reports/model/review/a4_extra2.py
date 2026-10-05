# -*- coding: utf-8 -*-
"""a4_extra2.py - 4번 보조 계산 2: (1) 반영 기준 R과 5과목 기준의 '국어·영어 출발점' 민감도,
(2) 4번 권고 중앙 조합(T1 비용 + N1 잡음 + 비대칭 되먹임) 확률. 모두 판단값, 실증 보정 없음."""
import itertools, os, sys, time
import numpy as np
sys.path.insert(0, ".")
import a2mod as M
from a4_stress import hours, HRS_DEF, SEED_A, SEED_K, p15_gd, sd_matrix
from a4_extra import reflect_p_table, oracle_reflect, oracle_p
N = int(os.environ.get("A4N", "5000"))
t0 = time.time()
sig = M.SIGMA["Q3"]
pick = ["H0 2번 현실(7h, 80% 5.5-9)", "H2 5.5h, 80% 3.5-8.5 + 중단위험 20%", "H4 4h, 80% 2.5-6.5 + 중단위험 25%"]
Avec = {k: hours(N, SEED_A, **HRS_DEF[k]) for k in pick}
cands = np.array([c for c in itertools.product(range(1, 7), (9, 8, 7, 6, 5, 4, 3), (1, 2, 3, 4, 5), range(1, 9), range(1, 9))], dtype=np.int64)
pr9 = reflect_p_table(cands, 9)
print("# a4_extra2.py 출력 (N=%d)\n" % N)
print("## 1. 출발점 민감도: 5과목 기준(P관측합계<=15)과 반영 기준 R<=9, 오라클, 2번 잡음\n")
print("| Q3 가정 | 5과목 H0 | 5과목 H2 | 5과목 H4 | R<=9 H0 | R<=9 H2 | R<=9 H4 | R<=9 점추정 최소비용 조합 |")
print("|---|---|---|---|---|---|---|---|")
cases = [("기준(국어 5, 영어 2.5)", {}), ("영어 실제 3.5", dict(q3_eng_start=3.5)), ("영어 실제 4.0", dict(q3_eng_start=4.0)),
         ("국어 출발 6", dict(q3_kor_start=6)), ("국어 6 + 영어 4.0", dict(q3_kor_start=6, q3_eng_start=4.0))]
for nm, over in cases:
    tab, hist = M.tables("Q3", **over)
    five = [oracle_p(tab, hist, sig, Avec[k])[0] for k in pick]
    refl = [oracle_reflect(tab, hist, sig, Avec[k], cands, pr9) for k in pick]
    B = np.zeros(len(cands))
    for j, a in enumerate(M.AREAS):
        lut = np.array([0.0] + [tab[a][g] for g in M.GRADES]); B += lut[cands[:, j]]
    B += hist
    exp_r = np.sort(cands[:, :3], axis=1)[:, :2].sum(axis=1) + np.minimum(cands[:, 3], cands[:, 4])
    m = exp_r <= 9
    i = np.where(m)[0][np.argmin(B[m])]
    print(f"| {nm} | " + " | ".join(f"{x:.2f}" for x in five + refl) + f" | {tuple(int(x) for x in cands[i])} {B[i]:,.0f}h |")
print(f"({time.time()-t0:.0f}s)")

print("\n## 2. 4번 권고 '중앙 근처' 조합: T1(탐구 1~2등급 비용 상향) + N1(등급의존 잡음) + 비대칭 되먹임, 5과목 기준\n")
keep = {a: dict(M.PRAC[a]) for a in ("통합사회", "통합과학")}
M.PRAC["통합사회"].update({3: 110, 2: 270, 1: 700}); M.PRAC["통합과학"].update({3: 160, 2: 375, 1: 800})
tabT, histT = M.tables("Q3")
M.PRAC["통합사회"].update(keep["통합사회"]); M.PRAC["통합과학"].update(keep["통합과학"])
base_sd = dict(M.NOISE_SD)
SD1 = sd_matrix({**base_sd, "영어": 0.80}, {"통합사회": {1: 1.0, 2: 1.0}, "통합과학": {1: 1.0, 2: 1.0}, "수학": {6: 0.9, 7: 1.0, 8: 1.0, 9: 1.0}})
P1 = p15_gd(M.SUB.astype(float), SD1)
rng = np.random.default_rng(SEED_K); k = M.draw_k(sig, N, rng)
gm = np.exp(np.mean([np.log(k[a]) for a in M.AREAS], axis=0))
print("| 가용 | T1+N1 | T1+N1+되먹임 |")
print("|---|---|---|")
for kk in pick:
    pa = oracle_p(tabT, histT, sig, Avec[kk], P1)[0]
    pb = oracle_p(tabT, histT, sig, Avec[kk] * np.maximum(gm, 1.0) ** -0.5, P1)[0]
    print(f"| {kk} | {pa:.2f} | {pb:.2f} |")
print(f"\n총 {time.time()-t0:.0f}s")
