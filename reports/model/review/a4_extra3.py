# -*- coding: utf-8 -*-
"""a4_extra3.py - 4번 보조 계산 3: 반영 기준을 등급합 대신 '가중 백분위'로 계산.
W = 0.4 x (국 백분위, 수 백분위, 영 환산 중 1위) + 0.4 x (2위) + 0.2 x max(통합사회, 통합과학 백분위)
 - 2025 나사렛대·백석대 산출식 구조 [1번 S2/S3]를 2028에 그대로 가정(미확인)
 - 상대평가 등급 -> 백분위: 등급 구간 중앙값(98, 92.5, 83, 68.5, 50, 31.5, 17, 7.5, 2) [4번 판단, 근사]
 - 영어 환산: 중간형(100,95,88,79,68,56,44,32,20) [4번 판단: 1번 3.6절 표들의 중간], 박한형(중부대형 95,85,75,65,55,45,35,25,15) [1번 D]
 - 합격선 근사: W>=80(2025 공식자료 사례 76~79에 소폭 여유), W>=83(여유 큼) [4번 판단]
"""
import itertools, math, os, sys, time
import numpy as np
sys.path.insert(0, ".")
import a2mod as M
from a4_stress import hours, HRS_DEF, SEED_A, SEED_K
from a4_extra import oracle_reflect
N = int(os.environ.get("A4N", "5000"))
PCT = np.array([0, 98, 92.5, 83, 68.5, 50, 31.5, 17, 7.5, 2], dtype=float)
ENG = {"중간형": np.array([0, 100, 95, 88, 79, 68, 56, 44, 32, 20], dtype=float),
       "박한형": np.array([0, 95, 85, 75, 65, 55, 45, 35, 25, 15], dtype=float)}

def w_table(cands, eng, thr, n_noise=4000, seed=7):
    rng = np.random.default_rng(seed)
    z0 = rng.standard_normal(n_noise); za = rng.standard_normal((n_noise, 5))
    sd = np.array([M.NOISE_SD[a] for a in M.AREAS]); rho = M.RHO_NOISE
    e = sd[None, :] * (math.sqrt(rho) * z0[:, None] + math.sqrt(1 - rho) * za)
    out = np.empty(len(cands)); wexp = np.empty(len(cands))
    for st in range(0, len(cands), 400):
        c = cands[st:st + 400].astype(float)
        obs = np.clip(np.rint(c[:, None, :] + e[None, :, :]), 1, 9).astype(int)
        k_ = PCT[obs[:, :, 0]]; s_ = PCT[obs[:, :, 1]]; y_ = eng[obs[:, :, 2]]
        top = np.sort(np.stack([k_, s_, y_], axis=2), axis=2)[:, :, ::-1]
        tam = np.maximum(PCT[obs[:, :, 3]], PCT[obs[:, :, 4]])
        W = 0.4 * top[:, :, 0] + 0.4 * top[:, :, 1] + 0.2 * tam
        out[st:st + 400] = np.mean(W >= thr, axis=1)
        ci = cands[st:st + 400]
        t2 = np.sort(np.stack([PCT[ci[:, 0]], PCT[ci[:, 1]], eng[ci[:, 2]]], axis=1), axis=1)[:, ::-1]
        wexp[st:st + 400] = 0.4 * t2[:, 0] + 0.4 * t2[:, 1] + 0.2 * np.maximum(PCT[ci[:, 3]], PCT[ci[:, 4]])
    return out, wexp

t0 = time.time()
sig = M.SIGMA["Q3"]
pick = ["H0 2번 현실(7h, 80% 5.5-9)", "H2 5.5h, 80% 3.5-8.5 + 중단위험 20%", "H4 4h, 80% 2.5-6.5 + 중단위험 25%"]
Avec = {k: hours(N, SEED_A, **HRS_DEF[k]) for k in pick}
cands = np.array([c for c in itertools.product(range(1, 7), (9, 8, 7, 6, 5, 4, 3), (1, 2, 3, 4, 5), range(1, 9), range(1, 9))], dtype=np.int64)
print("# a4_extra3.py 출력 (N=%d)\n" % N)
print("| Q3 가정 | 영어 환산 | 합격선 | 점추정 최소비용 조합(기대 W) | P_W(그 조합) | 오라클 H0 | H2 | H4 |")
print("|---|---|---|---|---|---|---|---|")
for nm, over in (("기준(국어 5, 영어 2.5)", {}), ("국어 6 + 영어 4.0", dict(q3_kor_start=6, q3_eng_start=4.0))):
    tab, hist = M.tables("Q3", **over)
    B = np.zeros(len(cands))
    for j, a in enumerate(M.AREAS):
        lut = np.array([0.0] + [tab[a][g] for g in M.GRADES]); B += lut[cands[:, j]]
    B += hist
    for en, eng in ENG.items():
        for thr in (80, 83):
            pw, wexp = w_table(cands, eng, thr)
            m = wexp >= thr
            i = np.where(m)[0][np.argmin(B[m])]
            ps = [oracle_reflect(tab, hist, sig, Avec[k], cands, pw) for k in pick]
            print(f"| {nm} | {en} | W>={thr} | {tuple(int(x) for x in cands[i])} {B[i]:,.0f}h (W {wexp[i]:.1f}) | {pw[i]:.2f} | " + " | ".join(f"{x:.2f}" for x in ps) + " |")
    print(f"  ({time.time()-t0:.0f}s)")
