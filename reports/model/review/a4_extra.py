#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a4_extra.py - 4번(검토) 보조 계산. 2번 v2 기계(a2mod.py)를 그대로 쓰고 다음 셋만 계산.
 X1 종합 사전모형(synth_prior_model.py) Q3 표를 2번 기계(오라클·잡음·배수 불확실성)에 넣었을 때 P(관측합계<=15)
 X2 '진도가 느리면 공부시간도 준다' 되먹임: 가용시간 A x max(영역 배수 기하평균, 1)^(-0.5)  [4번 판단, 비대칭:
    느린 쪽만 시간 감소, 빠른 쪽은 시간 증가 없음]
 X3 반영 기준 R: (국·수·영 중 좋은 2개 등급합) + (통합사회·통합과학 중 좋은 1개 등급) <= 9 또는 <= 8
    (2025~2026 충청권 3개교 구조를 2028에 그대로 가정 [1번 S2/S3], 등급합-컷 대응은 4번 판단)
가용시간 분포 H0~H4는 a4_stress.py와 같음. 모두 판단값이며 실증 보정이 없음.
"""
import itertools
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")
import a2mod as M  # noqa: E402
from a4_stress import hours, HRS_DEF, SEED_A, SEED_K  # noqa: E402

N = int(os.environ.get("A4N", "5000"))


def oracle_p(tab, hist, sig, A, p15sub=None):
    keep = M.P15_SUB
    if p15sub is not None:
        M.P15_SUB = p15sub
    try:
        r = M.mc(tab, hist, sig, n=N, seed=SEED_K, budgets={"x": A})
    finally:
        M.P15_SUB = keep
    return float(np.mean(r["succ"]["x"])), float(np.median(r["hreq"]))


def synth_q3():
    pers = {
        "국어": {9: 0, 8: 0, 7: 0, 6: 0, 5: 30, 4: 100, 3: 220, 2: 450, 1: 850},
        "수학": {9: 0, 8: 120, 7: 260, 6: 400, 5: 730, 4: 1100, 3: 1580, 2: 2200, 1: 3100},
        "영어": {9: 0, 8: 0, 7: 0, 6: 0, 5: 0, 4: 0, 3: 40, 2: 180, 1: 480},
        "통합사회": {9: 0, 8: 10, 7: 25, 6: 50, 5: 100, 4: 175, 3: 280, 2: 420, 1: 640},
        "통합과학": {9: 0, 8: 40, 7: 90, 6: 150, 5: 250, 4: 370, 3: 530, 2: 740, 1: 1050},
    }
    tab = {a: {g: v * 1.10 for g, v in d.items()} for a, d in pers.items()}
    return tab, 55 * 1.10


# ---------------------------------------------------------------- X3 반영 기준
def reflect_p_table(cands, thr, n_noise=4000, seed=7):
    rng = np.random.default_rng(seed)
    z0 = rng.standard_normal(n_noise)
    za = rng.standard_normal((n_noise, 5))
    sd = np.array([M.NOISE_SD[a] for a in M.AREAS])
    rho = M.RHO_NOISE
    e = sd[None, :] * (math.sqrt(rho) * z0[:, None] + math.sqrt(1 - rho) * za)  # (n_noise,5)
    out = np.empty(len(cands))
    for st in range(0, len(cands), 400):
        c = cands[st:st + 400].astype(float)
        obs = np.clip(np.rint(c[:, None, :] + e[None, :, :]), 1, 9)  # (m, n_noise, 5)
        kme = np.sort(obs[:, :, :3], axis=2)[:, :, :2].sum(axis=2)
        tam = np.minimum(obs[:, :, 3], obs[:, :, 4])
        out[st:st + 400] = np.mean(kme + tam <= thr, axis=1)
    return out


def oracle_reflect(tab, hist, sig, A, cands, pr):
    rng = np.random.default_rng(SEED_K)
    k = M.draw_k(sig, N, rng)
    K = np.vstack([k[a] for a in M.AREAS])
    B = np.zeros((len(cands), 5))
    for j, a in enumerate(M.AREAS):
        lut = np.array([0.0] + [tab[a][g] for g in M.GRADES])
        B[:, j] = lut[cands[:, j]]
    succ = np.empty(N)
    cost_best = np.empty(N)
    for st in range(0, N, 250):
        en = min(N, st + 250)
        C = B @ K[:, st:en] + hist * k[M.HIST][st:en]
        ok = C <= A[st:en][None, :]
        pv = np.where(ok, pr[:, None], -1.0)
        best = pv.max(axis=0)
        best[best < 0] = 0.0
        succ[st:en] = best
    return float(np.mean(succ))


def main():
    t0 = time.time()
    sig = M.SIGMA["Q3"]
    Avec = {k: hours(N, SEED_A, **v) for k, v in HRS_DEF.items()}
    names = list(Avec)
    print(f"# a4_extra.py 출력 (N={N})\n")

    print("## X1. 종합 사전모형 Q3 표를 2번 기계에 넣은 경우(오라클, 2번 잡음)\n")
    tabS, histS = synth_q3()
    tabV, histV = M.tables("Q3")
    print("| 표 | " + " | ".join(names) + " | 필요시간 P50 |")
    print("|---|" + "---|" * len(names) + "---|")
    for nm, (tab, hist) in (("2번 v2 Q3", (tabV, histV)), ("종합 사전모형 Q3(x1.1, 한국사 61h)", (tabS, histS))):
        row, h50 = [], None
        for hn in names:
            p, h50 = oracle_p(tab, hist, sig, Avec[hn])
            row.append(f"{p:.2f}")
        print(f"| {nm} | " + " | ".join(row) + f" | {h50:,.0f} |")
    pb = M.point_best(tabS, histS, 15, 3)
    print("\n종합 사전모형 표의 점추정 최소비용(기대합계<=15) 상위 3: " +
          "; ".join(f"{c} {h:,.0f}h P={p:.2f}" for h, c, p in pb))
    print(f"({time.time() - t0:.0f}s)")

    print("\n## X2. 진도-시간 되먹임(가용 A x max(배수 기하평균,1)^-0.5, 비대칭), 2번 v2 Q3 표, 오라클\n")
    rng = np.random.default_rng(SEED_K)
    k = M.draw_k(sig, N, rng)
    gm = np.exp(np.mean([np.log(k[a]) for a in M.AREAS], axis=0))
    print("| 가용 | 되먹임 없음 | 되먹임 있음 |")
    print("|---|---|---|")
    for hn in names:
        p0, _ = oracle_p(tabV, histV, sig, Avec[hn])
        p1, _ = oracle_p(tabV, histV, sig, Avec[hn] * np.maximum(gm, 1.0) ** -0.5)
        print(f"| {hn} | {p0:.2f} | {p1:.2f} |")
    print(f"({time.time() - t0:.0f}s)")

    print("\n## X3. 반영 기준 R(국·수·영 상위2 등급합 + 탐구 상위1 등급), 2번 v2 Q3 표, 오라클\n")
    cands = np.array([c for c in itertools.product(range(1, 6), (9, 8, 7, 6, 5, 4, 3), (1, 2, 3, 4), range(1, 9), range(1, 9))],
                     dtype=np.int64)
    print(f"- 후보 조합 {len(cands):,}개(국1~5, 수9~3, 영1~4, 사1~8, 과1~8)")
    for thr in (9, 8):
        pr = reflect_p_table(cands, thr)
        # 점추정 최소비용(기대 기준 R<=thr)과 그 P
        B = np.zeros(len(cands))
        for j, a in enumerate(M.AREAS):
            lut = np.array([0.0] + [tabV[a][g] for g in M.GRADES])
            B += lut[cands[:, j]]
        B += histV
        exp_r = np.sort(cands[:, :3], axis=1)[:, :2].sum(axis=1) + np.minimum(cands[:, 3], cands[:, 4])
        m = exp_r <= thr
        idx = np.where(m)[0][np.argsort(B[m])][:3]
        print(f"\n- 기준 R<={thr}: 점추정 최소비용 상위 3 = " +
              "; ".join(f"{tuple(int(x) for x in cands[i])} {B[i]:,.0f}h P_R={pr[i]:.2f}" for i in idx))
        for bud in (800, 1000, 1200, 1500):
            ok = B <= bud
            i = np.where(ok)[0][np.argmax(pr[ok])]
            print(f"  - 예산 {bud:,}h에서 P_R 최대: {tuple(int(x) for x in cands[i])} {B[i]:,.0f}h P_R={pr[i]:.2f}")
        row = []
        for hn in names:
            row.append(f"{oracle_reflect(tabV, histV, sig, Avec[hn], cands, pr):.2f}")
        print(f"\n| 기준 R<={thr} | " + " | ".join(row) + " |")
        print("|---|" + "---|" * len(names))
        print("| (열) | " + " | ".join(names) + " |")
    print(f"\n총 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
