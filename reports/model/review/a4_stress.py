#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a4_stress.py - 4번(검토) 에이전트의 2번 모형 스트레스 시험.
2번 v2 스크립트 사본(a2mod.py = agent2_model_fixed.py 복사본)의 표·함수를 그대로 쓰고,
아래 판단값만 바꿔 P(관측합계<=15)를 다시 계산한다. 바꾼 값은 모두 [4번 판단]이며 실증 계수가 아님.

바꾸는 축
  H  가용 실질시간 분포(중앙값·폭·중단 위험)
  T  통합사회·통합과학 1~2등급 실전연습 비용(천장효과)
  N  등급 의존 시험 당일 변동(탐구 1~2등급, 수학 6~9등급 찍기 분산, 영어 연도 난이도)
  O  배분 정책: 2번의 '오라클 재최적화'(실현된 영역 배수를 알고 조합을 고름) vs '고정 계획'
     (사전 중앙값 표로 계획을 세우고 실현 시간을 같은 비율로 배분, 재최적화 없음)
실행: python3 a4_stress.py  (seed 고정)
"""
import math
import sys
import time

import numpy as np

sys.path.insert(0, ".")
import a2mod as M  # noqa: E402  (import 시 2번 기본 P15_SUB 계산, 약 20초)

import os
N = int(os.environ.get("A4N", "5000"))
SEED_K = M.SEED + 41          # 2번 8~9절과 같은 배수 난수
SEED_A = M.SEED + 31          # 2번 8절과 같은 가용시간 난수
WK = M.weeks("S2", "E28b")     # 10/5 -> 2027-11-18, 58.43주
# 가용 실질시간 시나리오 [4번 판단]. 중단위험 = 해당 확률로 총 가용시간의 25~50%를 잃음(질병·생활사건·소진)
HRS_DEF = {
    "H0 2번 현실(7h, 80% 5.5-9)": dict(med=7.0, lo=5.5, hi=9.0),
    "H1 6h, 80% 4-9": dict(med=6.0, lo=4.0, hi=9.0),
    "H2 5.5h, 80% 3.5-8.5 + 중단위험 20%": dict(med=5.5, lo=3.5, hi=8.5, disrupt_p=0.2),
    "H3 5h, 80% 3-8 + 중단위험 20%": dict(med=5.0, lo=3.0, hi=8.0, disrupt_p=0.2),
    "H4 4h, 80% 2.5-6.5 + 중단위험 25%": dict(med=4.0, lo=2.5, hi=6.5, disrupt_p=0.25),
}


# ---------------------------------------------------------------- 벡터 정규 CDF (A&S 7.1.26)
def ncdf(z):
    z = np.asarray(z, dtype=float)
    x = np.abs(z) / math.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    erf = np.sign(z) * y
    return 0.5 * (1.0 + erf)


# ---------------------------------------------------------------- 등급 의존 잡음의 P(관측합계<=15)
def sd_matrix(base, overrides):
    """base: 영역별 기본 SD, overrides: {영역: {등급: SD}} -> 영역별 길이 10 배열(인덱스=등급)."""
    out = {}
    for a in M.AREAS:
        arr = np.full(10, base[a], dtype=float)
        for g, v in overrides.get(a, {}).items():
            arr[g] = v
        out[a] = arr
    return out


def sd_at(arr, g):
    """비정수 기대등급 g에서 SD 선형보간."""
    g = np.clip(g, 1, 9)
    lo = np.floor(g).astype(int)
    hi = np.minimum(lo + 1, 9)
    w = g - lo
    return arr[lo] * (1 - w) + arr[hi] * w


def p15_gd(means, sdm, rho=M.RHO_NOISE, target=15, nodes=41, chunk=4000):
    """means: (n,5) 기대등급(정수 또는 실수). sdm: 영역별 등급 의존 SD 배열."""
    x, w = np.polynomial.hermite_e.hermegauss(nodes)
    w = w / w.sum()
    out = np.zeros(len(means))
    edges = np.arange(1, 9) + 0.5
    for st in range(0, len(means), chunk):
        mm = means[st:st + chunk]
        n = len(mm)
        S = [sd_at(sdm[a], mm[:, j]) for j, a in enumerate(M.AREAS)]
        acc = np.zeros(n)
        for z0, wt in zip(x, w):
            dist = np.zeros((n, 46))
            dist[:, 0] = 1.0
            for j in range(5):
                s = S[j]
                mu = mm[:, j] + s * math.sqrt(rho) * z0
                sc = s * math.sqrt(1 - rho)
                cdf = ncdf((edges[None, :] - mu[:, None]) / sc[:, None])
                pm = np.empty((n, 9))
                pm[:, 0] = cdf[:, 0]
                pm[:, 1:8] = cdf[:, 1:] - cdf[:, :-1]
                pm[:, 8] = 1 - cdf[:, 7]
                new = np.zeros_like(dist)
                for o in range(1, 10):
                    new[:, o:] += dist[:, :46 - o] * pm[:, o - 1][:, None]
                dist = new
            acc += wt * dist[:, :target + 1].sum(axis=1)
        out[st:st + chunk] = acc
    return out


# ---------------------------------------------------------------- 가용시간 분포
def hours(n, seed, med, lo, hi, d=6.5, wk=WK, disrupt_p=0.0, disrupt_lo=0.25, disrupt_hi=0.5):
    """하루 실질시간 로그정규(중앙 med, 80% lo~hi) x 주당일수 x 주수, 선택적으로 '장기 중단' 혼합."""
    rng = np.random.default_rng(seed)
    sig = (math.log(hi) - math.log(lo)) / (2 * M.Z80)
    A = np.exp(math.log(med) + sig * rng.standard_normal(n)) * d * wk
    if disrupt_p > 0:
        r2 = np.random.default_rng(seed + 999)
        hit = r2.random(n) < disrupt_p
        loss = r2.uniform(disrupt_lo, disrupt_hi, n)
        A = np.where(hit, A * (1 - loss), A)
    return A


# ---------------------------------------------------------------- 오라클(2번 방식)
def oracle(tab, hist, sig, A, p15sub, n=N, seed=SEED_K):
    keep = M.P15_SUB
    M.P15_SUB = p15sub
    try:
        r = M.mc(tab, hist, sig, n=n, seed=seed, budgets={"x": A})
    finally:
        M.P15_SUB = keep
    return r


# ---------------------------------------------------------------- 고정 계획(재최적화 없음)
def frac_grade(Hrow, e):
    """Hrow: 등급 1..9의 누적 필요시간(인덱스 0=1등급), e: 실효 투입시간 배열 -> 비정수 기대등급."""
    H = np.asarray(Hrow, dtype=float)
    g = np.full(e.shape, 9.0)
    # 등급 1부터 9까지 '도달 가능한 가장 좋은 정수 등급' 탐색
    gi = np.full(e.shape, 9, dtype=int)
    for gg in range(9, 0, -1):
        gi = np.where(H[gg - 1] <= e, gg, gi)
    g = gi.astype(float)
    # gi-1 등급 쪽으로 선형 보간(부분 진척)
    m = gi > 1
    Hhi = H[np.clip(gi - 2, 0, 8)]   # (gi-1)등급 시간
    Hlo = H[gi - 1]                   # gi등급 시간
    span = np.maximum(Hhi - Hlo, 1e-9)
    frac = np.clip((e - Hlo) / span, 0, 1)
    g = np.where(m, gi - frac, 1.0)
    return g


def fixed_plan(tab, hist, plan, A, k, sdm):
    """plan: 정수 기대등급 튜플. 계획 비용 비율대로 실현 가용시간 A를 배분, 실현 배수 k로 도달 등급 계산."""
    costs = np.array([tab[a][g] for a, g in zip(M.AREAS, plan)])
    C = costs.sum() + hist
    scale = A / C
    means = np.empty((len(A), 5))
    for j, a in enumerate(M.AREAS):
        e = costs[j] * scale / k[a]
        Hrow = [tab[a][g] for g in M.GRADES]
        means[:, j] = frac_grade(Hrow, e)
    return p15_gd(means, sdm), means


def plan_pick(tab, hist, budget, p15sub, max_sum=22):
    c = M.cost_matrix(tab, M.SUB).sum(axis=1) + hist
    ok = (c <= budget) & (M.SUMS_S[:M.END22] <= max_sum)
    i = np.where(ok)[0][np.argmax(p15sub[ok])]
    return tuple(int(x) for x in M.SUB[i]), float(c[i]), float(p15sub[i])


def main():
    t0 = time.time()
    print(f"# a4_stress.py 출력 (N={N}, 배수 seed={SEED_K}, 가용 seed={SEED_A}, 기간 10/5->2027-11-18 {WK:.2f}주)")

    base_sd = dict(M.NOISE_SD)
    SD0 = sd_matrix(base_sd, {})
    # N1: 등급 의존 잡음 [4번 판단]
    SD1 = sd_matrix({**base_sd, "영어": 0.80},
                    {"통합사회": {1: 1.0, 2: 1.0}, "통합과학": {1: 1.0, 2: 1.0},
                     "수학": {6: 0.9, 7: 1.0, 8: 1.0, 9: 1.0}})
    # 2번 기본 잡음 재계산(근사 CDF) - 2번 P15_SUB와 비교
    P0 = p15_gd(M.SUB.astype(float), SD0)
    print(f"- 근사 CDF 검증: 2번 P15_SUB와 최대 절대차 {np.max(np.abs(P0 - M.P15_SUB)):.4f}")
    P1 = p15_gd(M.SUB.astype(float), SD1)
    print(f"- P15 표 계산 {time.time() - t0:.0f}s")

    # 표: 2번 v2(Q3), v1 복원, 1~2등급 비용 상향(T1)
    tabs = {}
    tabs["v2"] = M.tables("Q3")
    keep = {a: dict(M.PRAC[a]) for a in ("통합사회", "통합과학")}
    M.PRAC["통합사회"].update({2: 170, 1: 320}); M.PRAC["통합과학"].update({2: 230, 1: 400})
    tabs["v1"] = M.tables("Q3")
    M.PRAC["통합사회"].update(keep["통합사회"]); M.PRAC["통합과학"].update(keep["통합과학"])
    M.PRAC["통합사회"].update({3: 110, 2: 270, 1: 700}); M.PRAC["통합과학"].update({3: 160, 2: 375, 1: 800})
    tabs["T1"] = M.tables("Q3")
    M.PRAC["통합사회"].update(keep["통합사회"]); M.PRAC["통합과학"].update(keep["통합과학"])
    for nm in ("v1", "v2", "T1"):
        tab, hist = tabs[nm]
        print(f"- 표 {nm}: 통합사회 3/2/1등급 {tab['통합사회'][3]:.0f}/{tab['통합사회'][2]:.0f}/{tab['통합사회'][1]:.0f}h, "
              f"통합과학 {tab['통합과학'][3]:.0f}/{tab['통합과학'][2]:.0f}/{tab['통합과학'][1]:.0f}h")

    sig = M.SIGMA["Q3"]
    HRS = HRS_DEF
    Avec = {k: hours(N, SEED_A, **v) for k, v in HRS.items()}
    for k, A in Avec.items():
        print(f"- {k}: 가용 P10/P50/P90 {np.quantile(A, .1):,.0f}/{np.quantile(A, .5):,.0f}/{np.quantile(A, .9):,.0f}h")

    # k 난수(오라클과 같은 seed) - 고정 계획에서 재사용
    rng = np.random.default_rng(SEED_K)
    kd = M.draw_k(sig, N, rng)

    print("\n## A. 오라클(2번 방식) P(관측합계<=15) - 표 x 잡음 x 가용시간\n")
    print("| 표 | 잡음 | " + " | ".join(HRS) + " | 필요시간 P50 |")
    print("|---|---|" + "---|" * len(HRS) + "---|")
    res = {}
    for tn in ("v1", "v2", "T1"):
        tab, hist = tabs[tn]
        for sn, P in (("N0 2번", P0), ("N1 등급의존", P1)):
            row = []
            hreq = None
            for hn, A in Avec.items():
                r = oracle(tab, hist, sig, A, P)
                p = float(np.mean(r["succ"]["x"]))
                res[(tn, sn, hn)] = p
                row.append(f"{p:.2f}")
                hreq = float(np.median(r["hreq"]))
            print(f"| {tn} | {sn} | " + " | ".join(row) + f" | {hreq:,.0f} |")
        print(f"  ({time.time() - t0:.0f}s)")

    print("\n## B. 고정 계획(재최적화 없음) vs 오라클 - 표 v2·T1, 잡음 N0·N1\n")
    for tn in ("v2", "T1"):
        tab, hist = tabs[tn]
        for sn, P, SD in (("N0 2번", P0, SD0), ("N1 등급의존", P1, SD1)):
            # 계획 3종: 2번 최소비용(기대합계<=15), 계획예산(2,658h=7h 중앙)에서 P15 최대, 2,000h에서 P15 최대
            pmin = M.point_best(tab, hist, 15, 1)[0]
            plans = [("최소비용 기대합계≤15", pmin[1])]
            for bud in (2658, 2000):
                pc = plan_pick(tab, hist, bud, P)
                plans.append((f"예산 {bud:,}h에서 P15 최대", pc[0]))
            for pn, plan in plans:
                cost = sum(tab[a][g] for a, g in zip(M.AREAS, plan)) + hist
                row = []
                for hn, A in Avec.items():
                    p, means = fixed_plan(tab, hist, plan, A, kd, SD)
                    row.append(f"{np.mean(p):.2f}")
                print(f"| {tn} | {sn} | {pn} {plan} {cost:,.0f}h | " + " | ".join(row) + " |")
        print(f"  ({time.time() - t0:.0f}s)")

    print("\n## C. 가용시간이 계획 비용에 못 미칠 확률(2번 Q3 v2 최소비용 조합의 실현 비용 기준)")
    tab, hist = tabs["v2"]
    plan = M.point_best(tab, hist, 15, 1)[0][1]
    real_cost = sum(tab[a][g] * kd[a] for a, g in zip(M.AREAS, plan)) + hist * kd[M.HIST]
    for hn, A in Avec.items():
        print(f"- {hn}: P(가용 < 실현 비용) = {np.mean(A < real_cost):.2f}")
    print(f"\n총 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
