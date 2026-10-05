#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent2_model.py - 2번(학습과학) 에이전트 재현용 계산 스크립트 (v2)
실행: python3 agent2_model.py > agent2_model_out.txt   (numpy 필요, seed 고정 -> 같은 결과, 약 2~4분)

표기 규칙
  [확인] = 이번 세션에서 검색 결과나 원문 사본으로 존재와 내용을 확인한 값
  [판단] = 출처 없는 판단값(근거 약함). 상단 상수만 바꿔 다시 돌리면 전 결과가 갱신됨
단위: '실질 시간' = 정상 집중 상태의 학습 1시간(명목 책상 시간이 아님)
H[a][g] = 현재 상태에서 영역 a의 '기대 등급'(실력이 등급 구간 한가운데)을 g로 만드는 누적 실질 시간(중앙값).
시험 당일 변동은 별도 잡음 모형(6절)으로 처리.
"""
import itertools
import math
from collections import Counter
from datetime import date

import numpy as np

SEED = 20261005
N_MC = 20000          # 본 계산
N_SENS = 5000         # 민감도·진단 시나리오
Z80 = 1.2815515655446004  # 80% 구간 = 중앙값 x exp(+-Z80*sigma)

AREAS = ["국어", "수학", "영어", "통합사회", "통합과학"]
HIST = "한국사"
GRADES = list(range(1, 10))

# ================================================================ 0. 상수
# (가) 교육과정 분량 [확인: 2022 개정 초·중등학교 교육과정 총론(국가교육위원회 고시 제2026-1호) 텍스트 사본]
CREDIT_H = 16 * 50 / 60          # 1학점 = 50분 x 16회 = 13.33시간
MID_H = 45 / 60                  # 중학교 1시간 = 45분
CLASS_H = {
    "국어": 20 * CREDIT_H,       # 공통국어1·2(8학점) + 화법과 언어·독서와 작문·문학(선택과목 기본 4학점씩)
    "수학": 20 * CREDIT_H,       # 공통수학1·2(8) + 대수·미적분Ⅰ·확률과 통계(4씩)
    "영어": 16 * CREDIT_H,       # 공통영어1·2(8) + 영어Ⅰ·Ⅱ(4씩)
    "통합사회": 8 * CREDIT_H,    # 통합사회1·2
    "통합과학": 8 * CREDIT_H,    # 통합과학1·2 (과학탐구실험 2학점 제외)
    "한국사": 6 * CREDIT_H,      # 한국사1·2
}
MID_MATH_H = 374 * MID_H         # 중학교 수학 374시간(45분) = 280.5시간 [확인]
MID_SCI_H = 680 * MID_H * 0.57   # 중학 '과학/기술·가정/정보' 680시간 중 과학 몫 57% [판단] -> 약 290시간

DEFAULT = dict(
    r_over=1.10,         # [판단] 13~14개월 과정의 망각·복습 오버헤드 배수(80%: 1.05~1.25)
    # (나) 자습 배수 m = 기초 이수(개념+기본문제+1회 복습) 실질시간 / 수업시간 [판단]
    m_math=2.0, m_kor=0.6, m_soc=1.5, m_sci=1.8, m_hist=0.6,
    prac_math_mult=1.0, tong_mult=1.0,   # 민감도용 배수
    # 영어 [확인: Cambridge GLH 누적 A2 180-200, B1 350-400, B2 500-600, C1 700-800]
    k_l1=1.9,            # [판단] GLH -> 한국어 화자 자습 실질시간 배수(80%: 1.4~2.6)
    eng_maint=30.0,      # [판단] 2~3등급 보유자의 형식 적응·유지
    # Q3 개인화(라) [모두 판단]
    q3_math_pre=140.0,   # 중학 수학 재학습(망각 상당, 재학습 절약 반영) 80%: 80~240h
    q3_sci_pre=80.0,     # 중학 과학 기초 복구 80%: 40~150h
    q3_kor_start=5,      # 국어 무준비 출발 기대등급(미측정, 언어성 지수 근거) 80%: 3~6
    q3_eng_start=2.5,    # 영어 현재 기대등급(본인 추정 2~3, 미검증)
)
PHI = {  # (다-1) 등급별 필요한 기초 이수 비율 [판단]
    "수학":     {9: 0, 8: .15, 7: .35, 6: .60, 5: .85, 4: 1, 3: 1, 2: 1, 1: 1},
    "국어":     {9: 0, 8: 0, 7: 0, 6: 0, 5: .30, 4: .70, 3: 1, 2: 1, 1: 1},
    "통합사회": {9: 0, 8: 0, 7: .30, 6: .55, 5: .80, 4: 1, 3: 1, 2: 1, 1: 1},
    "통합과학": {9: 0, 8: 0, 7: .30, 6: .55, 5: .80, 4: 1, 3: 1, 2: 1, 1: 1},
}
PRAC = {  # (다-2) 기초 이수 뒤 목표 백분위까지의 실전 연습(기출·모의고사·오답) [판단]
    "수학":     {9: 0, 8: 0, 7: 0, 6: 30, 5: 80, 4: 200, 3: 500, 2: 850, 1: 1400},
    "국어":     {9: 0, 8: 0, 7: 0, 6: 0, 5: 20, 4: 60, 3: 150, 2: 330, 1: 650},
    # 25문항 단기 시험: 1등급은 사실상 무오답이 필요해 2->1 증분을 크게 둠(천장효과)
    "통합사회": {9: 0, 8: 0, 7: 0, 6: 0, 5: 15, 4: 40, 3: 90, 2: 180, 1: 430},
    "통합과학": {9: 0, 8: 0, 7: 0, 6: 0, 5: 20, 4: 60, 3: 130, 2: 250, 1: 500},
}
GLH = {"A2": 190, "A2+": 250, "B1-": 300, "B1": 375, "B1+": 460, "B2": 550, "B2+": 600}  # +,- 단계는 보간 [판단]
ENG_MAP = {6: "A2", 5: "A2+", 4: "B1-", 3: "B1", 2: "B1+", 1: "B2+"}  # 수능 영어 등급 <-> CEFR [판단, 미검증]
ENG_FMT = {6: 0, 5: 20, 4: 40, 3: 60, 2: 80, 1: 100}                   # 수능 형식 연습 [판단]
HIST_RAW = CLASS_H["한국사"] * 0.6 * 1.25   # = 60h: 기초 48h + 기출 12h 상당 [판단]

# Q3 프로파일 조정 배수(라) [모두 판단, 근거 약함 - 본문 1절 표 참조]
Q3ADJ = {
    "수학_F": 1.10 * 0.95 * 1.05 * 0.95,          # 시각처리 약점, 작업기억 강점, 연령, 메타인지
    "수학_P": 1.10 * 0.95 * 1.05 * 0.95 * 1.08,   # + 처리속도 평균(시간 압박)
    "국어_F": 1.00, "국어_P": 0.80,               # 문법·고전 암기(단기기억) vs 독해(언어성) 상쇄 / 실전 x0.8
    "통합사회_F": 1.15 * 1.03, "통합사회_P": 0.90, # 단기기억 약점·연령 / 자료·지문 해석(언어성)
    "통합과학_F": 1.10 * 1.10 * 1.03, "통합과학_P": 1.10 * 0.97,  # 단기기억·시각처리·연령 / 시각처리·작업기억
    "영어_inc": 0.95,                             # 청각·언어성 강점 vs 어휘 암기(단기기억)
    "한국사": 1.15 * 1.03,                        # 단기기억·연령
}

# 불확실성: 영역별 시간 배수 k ~ 로그정규(중앙값 1), 영역 간 상관 RHO_K [판단]
SIGMA = {
    "Q1": {"국어": .40, "수학": .35, "영어": .35, "통합사회": .40, "통합과학": .45, "한국사": .35},
    "Q2": {"국어": .40, "수학": .35, "영어": .60, "통합사회": .40, "통합과학": .45, "한국사": .35},
    "Q3": {"국어": .50, "수학": .40, "영어": .60, "통합사회": .45, "통합과학": .50, "한국사": .40},
}
RHO_K = 0.5

# 시험 당일 변동 [판단]: 관측등급 = clip(round(기대등급 + e), 1, 9),
# e = s_a*(sqrt(rho)*z0 + sqrt(1-rho)*z_a). 2~8등급 폭이 약 0.5 SD이므로 s=0.6은 약 0.3 SD 측정오차에 해당
NOISE_SD = {"국어": .60, "수학": .60, "영어": .60, "통합사회": .75, "통합과학": .75}
RHO_NOISE = 0.2

# 달력 제약 [판단]
C_MATH = 5.0      # 수학에 하루 투입 가능한 실질시간 상한(80%: 4~6)
T_MIN = 7.0       # 노베이스 전 범위 + 간격 복습 + 실전 회차에 필요한 최소 달력 기간(개월, 80%: 5~9)
WPM = 365.25 / 12 / 7  # 월당 주 수 4.348

SCEN = [  # (이름, 하루 실질시간, 주당 학습일)
    ("명목12h·주7일(계획 그대로)", 12.0, 7.0),
    ("명목12h·주6.5일(계획 그대로)", 12.0, 6.5),
    ("실질8h·주6.5일", 8.0, 6.5),
    ("실질7h·주6.5일", 7.0, 6.5),
    ("실질6h·주6.5일", 6.0, 6.5),
]
REAL_MED, REAL_LO, REAL_HI = 7.0, 5.5, 9.0   # 현실 분포: 하루 실질시간 중앙 7h, 80% 5.5~9.0h [판단]
REAL_SIG = (math.log(REAL_HI) - math.log(REAL_LO)) / (2 * Z80)

DATES = {"S1": date(2026, 9, 9), "S2": date(2026, 10, 5),
         "E28a": date(2027, 11, 11), "E28b": date(2027, 11, 18),
         "E29a": date(2028, 11, 9), "E29b": date(2028, 11, 16)}


def weeks(s, e):
    return (DATES[e] - DATES[s]).days / 7


def months(s, e):
    return (DATES[e] - DATES[s]).days / (365.25 / 12)


# ================================================================ 1. 영역별 시간표 생성
def eng_base_raw(p):
    h = {g: 0.0 for g in GRADES}
    for g, lev in ENG_MAP.items():
        h[g] = (GLH[lev] - GLH["A2"]) * p["k_l1"] + ENG_FMT[g]
    return h  # 출발 = 약 6등급(중학 상위 10% ~ A2 가정)


def interp_grade(h, gf):
    """비정수 등급 gf에서의 시간(선형보간)."""
    lo, hi = math.floor(gf), math.ceil(gf)
    if lo == hi:
        return h[int(gf)]
    w = gf - lo
    return h[lo] * (1 - w) + h[hi] * w


def eng_start_raw(p, start, mult=1.0):
    base = eng_base_raw(p)
    off = interp_grade(base, start)
    h = {g: 0.0 for g in GRADES}
    for g in GRADES:
        if g <= 6:
            inc = max(0.0, base[g] - off) * mult
            h[g] = inc + (p["eng_maint"] if g <= math.ceil(start) else 0.0)
    return h


def generic_raw(area, p, pre, f_mult=1.0, p_mult=1.0, start=None):
    m = {"수학": p["m_math"], "국어": p["m_kor"], "통합사회": p["m_soc"], "통합과학": p["m_sci"]}[area]
    F = CLASS_H[area] * m * f_mult
    pm = p_mult * (p["prac_math_mult"] if area == "수학" else 1.0)
    tm = p["tong_mult"] if area in ("통합사회", "통합과학") else 1.0
    h = {g: (PHI[area][g] * (pre + F) + PRAC[area][g] * pm) * tm for g in GRADES}
    if start is not None:
        off = interp_grade(h, start)
        h = {g: max(0.0, v - off) for g, v in h.items()}
    return h


def finalize(raw, p):
    out = {g: p["r_over"] * v for g, v in raw.items()}
    for g in range(8, 0, -1):
        out[g] = max(out[g], out[g + 1])
    return out


def tables(which, **over):
    p = dict(DEFAULT)
    p.update(over)
    if which in ("Q1", "Q2"):
        tab = {
            "국어": finalize(generic_raw("국어", p, 0.0), p),
            "수학": finalize(generic_raw("수학", p, 40.0), p),
            "영어": finalize(eng_base_raw(p), p),
            "통합사회": finalize(generic_raw("통합사회", p, 0.0), p),
            "통합과학": finalize(generic_raw("통합과학", p, 20.0), p),
        }
        if which == "Q2":
            tab["영어"] = finalize(eng_start_raw(p, 2.5), p)
        return tab, p["r_over"] * HIST_RAW
    a = Q3ADJ
    tab = {
        "국어": finalize(generic_raw("국어", p, 0.0, a["국어_F"], a["국어_P"], start=p["q3_kor_start"]), p),
        "수학": finalize(generic_raw("수학", p, p["q3_math_pre"], a["수학_F"], a["수학_P"]), p),
        "영어": finalize(eng_start_raw(p, p["q3_eng_start"], a["영어_inc"]), p),
        "통합사회": finalize(generic_raw("통합사회", p, 0.0, a["통합사회_F"], a["통합사회_P"]), p),
        "통합과학": finalize(generic_raw("통합과학", p, p["q3_sci_pre"], a["통합과학_F"], a["통합과학_P"]), p),
    }
    return tab, p["r_over"] * HIST_RAW * a["한국사"]


# ================================================================ 2. 조합·잡음
ALL = np.array(list(itertools.product(GRADES, repeat=5)), dtype=np.int64)
SUMS = ALL.sum(axis=1)
ORDER = np.argsort(SUMS, kind="stable")
ALL_S, SUMS_S = ALL[ORDER], SUMS[ORDER]
UNIQ, STARTS = np.unique(SUMS_S, return_index=True)
END15 = int(np.searchsorted(SUMS_S, 15, side="right"))
END22 = int(np.searchsorted(SUMS_S, 22, side="right"))   # P15 계산 대상(합계<=22)
SUB = ALL_S[:END22]


def p15_exact(combos, target=15, noise_sd=None, rho=RHO_NOISE, nodes=41):
    """가우스-에르미트 적분(공통성분) + 영역별 이산분포 합성으로 P(관측합계<=target) 정확 계산."""
    nsd = noise_sd or NOISE_SD
    x, w = np.polynomial.hermite_e.hermegauss(nodes)
    w = w / w.sum()
    n = len(combos)
    out = np.zeros(n)
    from math import erf, sqrt
    Phi = np.vectorize(lambda z: 0.5 * (1 + erf(z / sqrt(2))))
    for z0, wt in zip(x, w):
        dist = np.zeros((n, 46))
        dist[:, 0] = 1.0
        for j, a in enumerate(AREAS):
            s = nsd[a]
            mu = combos[:, j] + s * math.sqrt(rho) * z0
            sc = s * math.sqrt(1 - rho)
            edges = np.arange(1, 9) + 0.5  # 1.5..8.5
            cdf = Phi((edges[None, :] - mu[:, None]) / sc)  # n x 8
            pm = np.empty((n, 9))
            pm[:, 0] = cdf[:, 0]
            pm[:, 1:8] = cdf[:, 1:] - cdf[:, :-1]
            pm[:, 8] = 1 - cdf[:, 7]
            new = np.zeros_like(dist)
            for o in range(1, 10):
                new[:, o:] += dist[:, :46 - o] * pm[:, o - 1][:, None]
            dist = new
        out += wt * dist[:, :target + 1].sum(axis=1)
    return out


P15_SUB = p15_exact(SUB)  # 합계<=22 조합 전체의 P(관측합계<=15)


def cost_matrix(tab, rows):
    B = np.zeros((len(rows), 5))
    for j, a in enumerate(AREAS):
        lut = np.array([0.0] + [tab[a][g] for g in GRADES])
        B[:, j] = lut[rows[:, j]]
    return B


def point_best(tab, hist, max_sum=15, top=6, mask_fn=None):
    B = cost_matrix(tab, SUB)
    c = B.sum(axis=1) + hist
    mask = SUMS_S[:END22] <= max_sum
    if mask_fn is not None:
        mask &= mask_fn(SUB)
    idx = np.where(mask)[0]
    idx = idx[np.argsort(c[idx], kind="stable")][:top]
    return [(float(c[i]), tuple(int(x) for x in SUB[i]), float(P15_SUB[i])) for i in idx]


def point_cummin(tab, hist):
    B = cost_matrix(tab, ALL_S)
    c = B.sum(axis=1) + hist
    best_cost, best_combo = {}, {}
    run_c, run_i = float("inf"), None
    bounds = list(STARTS) + [len(c)]
    for k, s in enumerate(UNIQ):
        st, en = bounds[k], bounds[k + 1]
        i = st + int(np.argmin(c[st:en]))
        if c[i] < run_c:
            run_c, run_i = float(c[i]), i
        best_cost[int(s)] = run_c
        best_combo[int(s)] = tuple(int(x) for x in ALL_S[run_i])
    return best_cost, best_combo


def point_maxp15(tab, hist, budget):
    c = cost_matrix(tab, SUB).sum(axis=1) + hist
    ok = c <= budget
    if not ok.any():
        return None
    i = np.where(ok)[0][np.argmax(np.where(ok, P15_SUB, -1)[ok])]
    return float(c[i]), tuple(int(x) for x in SUB[i]), float(P15_SUB[i])


# ================================================================ 3. 몬테카를로
def draw_k(sig, n, rng, rho=RHO_K):
    z0 = rng.standard_normal(n)
    return {a: np.exp(sig[a] * (math.sqrt(rho) * z0 + math.sqrt(1 - rho) * rng.standard_normal(n)))
            for a in AREAS + [HIST]}


def mc(tab, hist, sig, n=N_MC, seed=SEED, budgets=None, full=False, chunk=250, rho=RHO_K):
    """budgets: dict 이름 -> (n,) 가용시간 배열. 반환: 필요시간·조합·수학시간, 예산별 P15-max 성공확률 등."""
    rng = np.random.default_rng(seed)
    k = draw_k(sig, n, rng, rho)
    K = np.vstack([k[a] for a in AREAS])
    Bsub = cost_matrix(tab, SUB)
    res = dict(hreq=np.empty(n), hmath=np.empty(n), combo=np.empty((n, 5), dtype=np.int64))
    succ = {b: np.empty(n) for b in (budgets or {})}
    sbest = {b: np.empty(n) for b in (budgets or {})}
    if full:
        Bfull = cost_matrix(tab, ALL_S)
        res["cummin"] = np.empty((len(UNIQ), n))
    for st in range(0, n, chunk):
        en = min(n, st + chunk)
        m = en - st
        C = Bsub @ K[:, st:en] + hist * k[HIST][st:en]
        sub15 = C[:END15]
        am = np.argmin(sub15, axis=0)
        res["hreq"][st:en] = sub15[am, np.arange(m)]
        res["combo"][st:en] = SUB[am]
        res["hmath"][st:en] = Bsub[am, 1] * K[1, st:en]
        for b, arr in (budgets or {}).items():
            ok = C <= arr[st:en][None, :]
            pv = np.where(ok, P15_SUB[:, None], -1.0)
            best = pv.max(axis=0)
            best[best < 0] = 0.0
            succ[b][st:en] = best
            # 최선 기대합계(합계<=22 범위 내; 범위 밖은 23으로 표기)
            sm = np.where(ok, SUMS_S[:END22][:, None], 99).min(axis=0)
            sbest[b][st:en] = np.where(sm == 99, 23, sm)
        if full:
            Cf = Bfull @ K[:, st:en] + hist * k[HIST][st:en]
            mins = np.minimum.reduceat(Cf, STARTS, axis=0)
            res["cummin"][:, st:en] = np.minimum.accumulate(mins, axis=0)
    res["succ"], res["sbest"] = succ, sbest
    return res


def q(x, p):
    return float(np.quantile(x, p))


def lnfit(x):
    lo, med, hi = q(x, .10), q(x, .50), q(x, .90)
    return med, (math.log(hi) - math.log(lo)) / (2 * Z80), lo, hi


def Phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def real_hours(n, seed, wk, med=REAL_MED, sig=REAL_SIG, d=6.5):
    rng = np.random.default_rng(seed)
    return np.exp(math.log(med) + sig * rng.standard_normal(n)) * d * wk


# ================================================================ 4. 출력 함수
def print_hours(name, tab, hist, sig):
    print(f"\n#### {name}: 영역별 누적 필요 실질시간 - 중앙값 (80% 구간)\n")
    print("| 영역 | 6등급 | 5등급 | 4등급 | 3등급 | 2등급 | 1등급 | σ |")
    print("|---|---|---|---|---|---|---|---|")
    for a in AREAS:
        cells = []
        for g in (6, 5, 4, 3, 2, 1):
            v = tab[a][g]
            cells.append("0" if v < .5 else
                         f"{v:,.0f} ({v * math.exp(-Z80 * sig[a]):,.0f}–{v * math.exp(Z80 * sig[a]):,.0f})")
        print(f"| {a} | " + " | ".join(cells) + f" | {sig[a]:.2f} |")
    print(f"| 한국사(고정: 4등급 이내 목표) | {hist:,.0f} ({hist * math.exp(-Z80 * sig[HIST]):,.0f}–"
          f"{hist * math.exp(Z80 * sig[HIST]):,.0f}) |  |  |  |  |  | {sig[HIST]:.2f} |")
    print("\n7/8/9등급 누적시간: " + "; ".join(f"{a} " + "/".join(f"{tab[a][g]:,.0f}" for g in (7, 8, 9)) for a in AREAS))


def print_combos(title, lst):
    print(f"\n{title}\n")
    print("| 순위 | 국 | 수 | 영 | 사 | 과 | 기대합계(평균) | 영어 제외 평균 | 필요 실질시간 | P(관측합계≤15) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, (c, gs, p) in enumerate(lst, 1):
        s = sum(gs)
        print(f"| {i} | " + " | ".join(map(str, gs)) + f" | {s} ({s / 5:.1f}) | {(s - gs[2]) / 4:.2f} | {c:,.0f} | {p:.2f} |")


def main():
    global P15_SUB
    print(f"# agent2_model.py v2 출력 (seed={SEED}, N_MC={N_MC}, N_SENS={N_SENS})")
    print("\n## 0. 기본 환산")
    for a, v in CLASS_H.items():
        print(f"- {a} 수업시간 환산 {v:.1f}h")
    print(f"- 중학 수학 {MID_MATH_H:.1f}h, 중학 과학(판단 비중) {MID_SCI_H:.0f}h")
    print("- 영어 GLH 스캐폴드 raw(오버헤드 전): " + ", ".join(
        f"{g}등급 {v:.0f}h" for g, v in sorted(eng_base_raw(DEFAULT).items()) if g <= 6))
    for s in ("S1", "S2"):
        for e in ("E28a", "E28b", "E29a", "E29b"):
            print(f"- {DATES[s]}→{DATES[e]}: {(DATES[e] - DATES[s]).days}일 = {months(s, e):.2f}개월 = {weeks(s, e):.2f}주")

    T = {k: tables(k) for k in ("Q1", "Q2", "Q3")}

    print("\n## 1. 영역별 누적 필요시간 표")
    for key, nm in (("Q1", "Q1 기준 모델"), ("Q2", "Q2 (Q1 + 영어만 2~3등급 출발)"), ("Q3", "Q3 개인화")):
        print_hours(nm, *T[key], SIGMA[key])

    print("\n## 2. 기대합계≤15 최소비용 조합(점추정) + 각 조합의 P(관측합계≤15)")
    PB = {}
    for key in ("Q1", "Q2", "Q3"):
        tab, hist = T[key]
        PB[key] = point_best(tab, hist, 15, 6)
        print_combos(f"**{key} 상위 6개(제약 없음)**", PB[key])
        cons = [
            ("수학 5등급 이내", lambda R: R[:, 1] <= 5),
            ("수학 4등급 이내", lambda R: R[:, 1] <= 4),
            ("통합사회·통합과학 1등급 의존 금지(둘 다 2등급 이하 목표)", lambda R: (R[:, 3] >= 2) & (R[:, 4] >= 2)),
        ]
        for cn, fn in cons:
            print_combos(f"{key} 제약: {cn} (상위 2)", point_best(tab, hist, 15, 2, fn))
        for ms in (14, 13):
            print_combos(f"{key} 안전여유: 기대합계≤{ms} (상위 1)", point_best(tab, hist, ms, 1))
        for bud in (2000, 2400, 2800):
            r = point_maxp15(tab, hist, bud)
            print(f"\n{key} 예산 {bud:,}h에서 P(관측합계≤15) 최대 조합: {r[1]} 비용 {r[0]:,.0f}h, P={r[2]:.2f}")

    print("\n## 3. 몬테카를로: 필요시간 분포(영역 배수 불확실성 + 조합 재최적화)")
    wk_main = weeks("S2", "E28b")
    budgets = {}
    for nm, h, d in SCEN:
        for per in (("S1", "E28b"), ("S2", "E28b"), ("S2", "E28a")):
            budgets[(nm, per)] = np.full(N_MC, h * d * weeks(*per))
    for i, per in enumerate((("S1", "E28b"), ("S2", "E28b"), ("S2", "E28a"))):
        budgets[("현실분포", per)] = real_hours(N_MC, SEED + 11 + i, weeks(*per))
    for b in (1200, 1600, 2000, 2400, 2800, 3200, 4000, 5000):
        budgets[("예산", b)] = np.full(N_MC, float(b))
    MC = {}
    for key in ("Q1", "Q2", "Q3"):
        tab, hist = T[key]
        MC[key] = mc(tab, hist, SIGMA[key], budgets=budgets, full=(key != "Q2"))
        h = MC[key]["hreq"]
        med, sg, lo, hi = lnfit(h)
        hm = MC[key]["hmath"]
        print(f"- {key}: 기대합계≤15 최소 필요시간 P10 {lo:,.0f} / P50 {med:,.0f} / P90 {hi:,.0f} h, "
              f"로그정규 근사 σ_H={sg:.3f}; 그 조합의 수학시간 P10/P50/P90 {q(hm, .1):,.0f}/{q(hm, .5):,.0f}/{q(hm, .9):,.0f}")
        cnt = Counter(tuple(int(x) for x in r) for r in MC[key]["combo"])
        print("  최빈 최적조합(국,수,영,사,과): " + "; ".join(f"{c} {v / N_MC:.0%}" for c, v in cnt.most_common(5)))
        mg = Counter(int(r[1]) for r in MC[key]["combo"])
        print("  최적조합의 수학 기대등급 분포: " + ", ".join(f"{g}:{mg[g] / N_MC:.0%}" for g in sorted(mg)))

    print("\n## 4. 필요 기간(개월) = max(필요시간/월 가용, 수학시간/(min(5h,일 가용)×주당일수×4.348), T_MIN)")
    for key in ("Q1", "Q2", "Q3"):
        h, hm = MC[key]["hreq"], MC[key]["hmath"]
        H = [q(h, p) for p in (.1, .5, .9)]
        HM = [q(hm, p) for p in (.1, .5, .9)]
        print(f"\n**{key}** (필요시간 P10/P50/P90 = {H[0]:,.0f}/{H[1]:,.0f}/{H[2]:,.0f}h)\n")
        print("| 가용 시나리오 | 월 가용 h | 시간만 P10/P50/P90 | 최종 P10/P50/P90 |")
        print("|---|---|---|---|")
        for nm, hd, d in SCEN:
            am = hd * d * WPM
            raw = [x / am for x in H]
            fin = [max(r, x / (min(C_MATH, hd) * d * WPM), T_MIN) for r, x in zip(raw, HM)]
            print(f"| {nm} | {am:,.0f} | {raw[0]:.1f}/{raw[1]:.1f}/{raw[2]:.1f} | {fin[0]:.1f}/{fin[1]:.1f}/{fin[2]:.1f} |")

        def fin1(Hx, HMx, hd, d=6.5):
            am = hd * d * WPM
            return max(Hx / am, HMx / (min(C_MATH, hd) * d * WPM), T_MIN), Hx / am
        A = [fin1(H[i], HM[i], 12.0) for i in range(3)]
        Bq = [fin1(H[0], HM[0], 8.0), fin1(H[1], HM[1], 7.0), fin1(H[2], HM[2], 6.0)]
        print(f"\n{key} 낙관/중앙/비관(괄호 = T_MIN 적용 전 시간만): "
              f"A 명목12h·주6.5일 그대로 {A[0][0]:.1f}({A[0][1]:.1f}) / {A[1][0]:.1f}({A[1][1]:.1f}) / {A[2][0]:.1f}({A[2][1]:.1f}); "
              f"B 실질 8h/7h/6h {Bq[0][0]:.1f}({Bq[0][1]:.1f}) / {Bq[1][0]:.1f}({Bq[1][1]:.1f}) / {Bq[2][0]:.1f}({Bq[2][1]:.1f})")
    # 제약 조합의 기간(Q3)
    tab3, hist3 = T["Q3"]
    print("\nQ3 제약 조합의 기간(점추정, 시간만/임계경로 포함):")
    for cn, fn in (("수학 5등급 이내", lambda R: R[:, 1] <= 5), ("수학 4등급 이내", lambda R: R[:, 1] <= 4),
                   ("수학 3등급", lambda R: R[:, 1] <= 3)):
        c, gs, p = point_best(tab3, hist3, 15, 1, fn)[0]
        hmath = tab3["수학"][gs[1]]
        for nm, hd, d in (("명목12h", 12, 6.5), ("실질7h", 7, 6.5)):
            am = hd * d * WPM
            crit = hmath / (min(C_MATH, hd) * d * WPM)
            print(f"- {cn} {gs} {c:,.0f}h (수학 {hmath:,.0f}h) @{nm}: 시간 {c / am:.1f}개월, 수학 임계경로 {crit:.1f}개월 → 최종 {max(c / am, crit, T_MIN):.1f}")

    print("\n## 5. Q2 절약 효과")
    t1, h1 = T["Q1"]
    t2, h2 = T["Q2"]
    c1, g1, _ = PB["Q1"][0]
    c2, g2, _ = PB["Q2"][0]
    naive = c1 - (t1["영어"][g1[2]] - t2["영어"][g1[2]])
    print(f"- Q1 최적 {g1} {c1:,.0f}h → (a) 같은 조합 영어만 교체 {naive:,.0f}h (절약 {c1 - naive:,.0f}h) → "
          f"(b) 재최적화 {g2} {c2:,.0f}h (절약 {c1 - c2:,.0f}h, 재배분 추가 {naive - c2:,.0f}h)")
    for nm, hd, d in SCEN:
        am = hd * d * WPM
        print(f"  - {nm}: (a) {(c1 - naive) / am:.1f}개월 (b) {(c1 - c2) / am:.1f}개월 단축(시간 기준)")
    dd = MC["Q1"]["hreq"] - MC["Q2"]["hreq"]
    print(f"- MC 절약시간(공통 난수) P10/P50/P90 {q(dd, .1):,.0f}/{q(dd, .5):,.0f}/{q(dd, .9):,.0f}h")
    # MC 기간 단축(중앙값 기준)
    for nm, hd, d in SCEN:
        am = hd * d * WPM
        print(f"  - {nm}: MC 중앙 필요시간 차이 기준 {(q(MC['Q1']['hreq'], .5) - q(MC['Q2']['hreq'], .5)) / am:.1f}개월")

    print("\n## 6. 시험 당일 변동: 기대합계 s의 대표 조합별 P(관측합계≤15)")
    # MC 교차검증(한 조합)
    rng = np.random.default_rng(SEED + 5)
    combo = np.array([3, 7, 2, 1, 2])
    nn = 400000
    z0 = rng.standard_normal(nn)
    tot = np.zeros(nn)
    for j, a in enumerate(AREAS):
        e = NOISE_SD[a] * (math.sqrt(RHO_NOISE) * z0 + math.sqrt(1 - RHO_NOISE) * rng.standard_normal(nn))
        tot += np.clip(np.rint(combo[j] + e), 1, 9)
    print(f"- 교차검증 (3,7,2,1,2): 정확계산 {p15_exact(combo[None, :])[0]:.3f} vs MC {np.mean(tot <= 15):.3f}")
    for key in ("Q1", "Q3"):
        tab, hist = T[key]
        bc, bcombo = point_cummin(tab, hist)
        print(f"\n{key}\n")
        print("| 기대합계 s | 최소비용 조합 | 필요시간 | P(관측≤15) | 같은 s에서 P 최대 조합 | 그 비용 | P |")
        print("|---|---|---|---|---|---|---|")
        for s in range(11, 19):
            cmb = np.array(bcombo[s])[None, :]
            p_min = p15_exact(cmb)[0]
            # 같은 기대합계 s 이하 조합 중 비용이 최소비용의 +5% 이내인 것들 중 P 최대
            B = cost_matrix(tab, SUB).sum(axis=1) + hist
            mask = (SUMS_S[:END22] == s) & (B <= bc[s] * 1.05)
            idx = np.where(mask)[0]
            if len(idx):
                j = idx[np.argmax(P15_SUB[idx])]
                alt = (tuple(int(x) for x in SUB[j]), B[j], P15_SUB[j])
            else:
                alt = (bcombo[s], bc[s], p_min)
            print(f"| {s} | {bcombo[s]} | {bc[s]:,.0f} | {p_min:.2f} | {alt[0]} | {alt[1]:,.0f} | {alt[2]:.2f} |")

    print("\n## 7. Q4 입력값")
    pers = (("S1", "E28b", "9/9→27-11-18"), ("S2", "E28b", "10/5→27-11-18"), ("S2", "E28a", "10/5→27-11-11"))
    for key in ("Q1", "Q3"):
        h = MC[key]["hreq"]
        medH, sgH, loH, hiH = lnfit(h)
        print(f"\n### {key}: 필요시간 H(기대합계≤15) 중앙 {medH:,.0f}h, 80% {loH:,.0f}–{hiH:,.0f}h, 로그정규 σ_H={sgH:.3f}\n")
        print("| 기간 | 가용 시나리오 | 가용 A(h) | P(A≥H) 분석식 | P(A≥H) MC | P(관측합계≤15) MC | 최선 기대합계 P10/P50/P90 |")
        print("|---|---|---|---|---|---|---|")
        for s, e, pn in pers:
            for nm, hd, d in SCEN:
                A = hd * d * weeks(s, e)
                pa = Phi((math.log(A) - math.log(medH)) / sgH)
                pm = float(np.mean(h <= A))
                ps = float(np.mean(MC[key]["succ"][(nm, (s, e))]))
                sb = MC[key]["sbest"][(nm, (s, e))]
                print(f"| {pn} | {nm} | {A:,.0f} | {pa:.2f} | {pm:.2f} | {ps:.2f} | "
                      f"{q(sb, .1):.0f}/{q(sb, .5):.0f}/{q(sb, .9):.0f} |")
            A = budgets[("현실분포", (s, e))]
            medA = REAL_MED * 6.5 * weeks(s, e)
            pa = Phi((math.log(medA) - math.log(medH)) / math.sqrt(sgH ** 2 + REAL_SIG ** 2))
            pm = float(np.mean(h <= A))
            ps = float(np.mean(MC[key]["succ"][("현실분포", (s, e))]))
            sb = MC[key]["sbest"][("현실분포", (s, e))]
            print(f"| {pn} | 현실분포 7h(80% 5.5–9h)·주6.5일 | {medA:,.0f} ({q(A, .1):,.0f}–{q(A, .9):,.0f}) | "
                  f"{pa:.2f} | {pm:.2f} | {ps:.2f} | {q(sb, .1):.0f}/{q(sb, .5):.0f}/{q(sb, .9):.0f} |")

    print("\n### (ii) 예산 → 최선 기대 평균등급")
    for key in ("Q1", "Q3"):
        tab, hist = T[key]
        bc, bcombo = point_cummin(tab, hist)
        print(f"\n{key}\n")
        print("| 예산 h | 점추정 최선 기대합계(평균) | 최소합계 조합 | 영어 제외 평균 | MC 최선합계 P10/P50/P90 | P(관측≤15) MC | 점추정 P최대 조합(P) |")
        print("|---|---|---|---|---|---|---|")
        for b in (1200, 1600, 2000, 2400, 2800, 3200, 4000, 5000):
            sb_ = min(s for s in bc if bc[s] <= b)
            cmb = bcombo[sb_]
            cm = MC[key]["cummin"]
            ok = cm <= b
            sdist = UNIQ[np.argmax(ok, axis=0)]
            ps = float(np.mean(MC[key]["succ"][("예산", b)]))
            r = point_maxp15(tab, hist, b)
            print(f"| {b:,} | {sb_} ({sb_ / 5:.1f}) | {cmb} | {(sb_ - cmb[2]) / 4:.2f} | "
                  f"{q(sdist, .1):.0f}/{q(sdist, .5):.0f}/{q(sdist, .9):.0f} | {ps:.2f} | " + (f"{r[1]} ({r[2]:.2f})" if r else "— (합계≤22 조합 없음)") + " |")

    print("\n### (iii) 2029학년도 수능(2028-11-16 가정)")
    Y2_EFF, R2 = 0.90, 1.15  # [판단] 2년차 가용 효율, 망각 오버헤드
    for key in ("Q1", "Q3"):
        tab, hist = tables(key, r_over=R2)
        b29 = {}
        for nm, hd, d in SCEN[1:]:
            for per in (("S1", "E29b"), ("S2", "E29b")):
                w1 = weeks(per[0], "E28b")
                b29[(nm, per)] = np.full(N_SENS, hd * d * (w1 + (weeks(*per) - w1) * Y2_EFF))
        for per in (("S1", "E29b"), ("S2", "E29b")):
            w1 = weeks(per[0], "E28b")
            rh = np.exp(math.log(REAL_MED) + REAL_SIG * np.random.default_rng(SEED + 21).standard_normal(N_SENS))
            b29[("현실분포", per)] = rh * 6.5 * (w1 + (weeks(*per) - w1) * Y2_EFF)
        r = mc(tab, hist, SIGMA[key], n=N_SENS, seed=SEED + 3, budgets=b29)
        medH, sgH, loH, hiH = lnfit(r["hreq"])
        print(f"\n{key} (오버헤드 {R2}, 2년차 효율 {Y2_EFF}): 필요시간 중앙 {medH:,.0f}h (80% {loH:,.0f}–{hiH:,.0f})\n")
        print("| 기간 | 가용 시나리오 | 가용 A(h) | P(A≥H) | P(관측합계≤15) | 최선 기대합계 P10/P50/P90 |")
        print("|---|---|---|---|---|---|")
        for (nm, per), A in b29.items():
            pn = "9/9→28-11-16" if per[0] == "S1" else "10/5→28-11-16"
            sb = r["sbest"][(nm, per)]
            print(f"| {pn} | {nm} | {q(A, .5):,.0f} | {np.mean(r['hreq'] <= A):.2f} | {np.mean(r['succ'][(nm, per)]):.2f} | "
                  f"{q(sb, .1):.0f}/{q(sb, .5):.0f}/{q(sb, .9):.0f} |")

    # ---------------------------------------------------------------- 8. 민감도·진단
    print("\n## 8. 민감도(Q3, 10/5→2027-11-18, 현실분포 7h) - 판단값 하나씩 바꾸기")
    wk = weeks("S2", "E28b")
    Areal = {("현실", 0): real_hours(N_SENS, SEED + 31, wk)}
    def run_case(label, which="Q3", sig=None, rho=RHO_K, noise=None, **over):
        tab, hist = tables(which, **over)
        r = mc(tab, hist, sig or SIGMA[which], n=N_SENS, seed=SEED + 41, budgets=Areal, rho=rho)
        return label, q(r["hreq"], .5), float(np.mean(r["succ"][("현실", 0)]))
    base = run_case("기준(Q3 기본값)")
    print("\n| 바꾼 판단값 | 필요시간 P50(h) | P(관측합계≤15) |")
    print("|---|---|---|")
    print(f"| {base[0]} | {base[1]:,.0f} | {base[2]:.2f} |")
    cases = [
        ("망각 오버헤드 1.05", dict(r_over=1.05)), ("망각 오버헤드 1.25", dict(r_over=1.25)),
        ("수학 자습배수 m 1.5", dict(m_math=1.5)), ("수학 자습배수 m 3.0", dict(m_math=3.0)),
        ("수학 실전연습 ×0.7", dict(prac_math_mult=0.7)), ("수학 실전연습 ×1.5", dict(prac_math_mult=1.5)),
        ("통합사회·과학 시간 ×0.7", dict(tong_mult=0.7)), ("통합사회·과학 시간 ×1.5", dict(tong_mult=1.5)),
        ("영어 GLH 배수 1.4", dict(k_l1=1.4)), ("영어 GLH 배수 2.6", dict(k_l1=2.6)),
    ]
    for label, over in cases:
        r = run_case(label, **over)
        print(f"| {r[0]} | {r[1]:,.0f} | {r[2]:.2f} |")
    # 상관·잡음 민감도
    tab, hist = tables("Q3")
    for label, rho in (("영역 간 배수 상관 0.2", 0.2), ("영역 간 배수 상관 0.8", 0.8)):
        r = mc(tab, hist, SIGMA["Q3"], n=N_SENS, seed=SEED + 41, budgets=Areal, rho=rho)
        print(f"| {label} | {q(r['hreq'], .5):,.0f} | {np.mean(r['succ'][('현실', 0)]):.2f} |")
    keep = P15_SUB.copy()
    for label, mult in (("시험 당일 변동 SD ×0.75", .75), ("시험 당일 변동 SD ×1.33", 1.33)):
        P15_SUB = p15_exact(SUB, noise_sd={a: v * mult for a, v in NOISE_SD.items()})
        r = mc(tab, hist, SIGMA["Q3"], n=N_SENS, seed=SEED + 41, budgets=Areal)
        print(f"| {label} | {q(r['hreq'], .5):,.0f} | {np.mean(r['succ'][('현실', 0)]):.2f} |")
    P15_SUB = keep
    for label, med in (("하루 실질 중앙 6h", 6.0), ("하루 실질 중앙 8h", 8.0), ("하루 실질 중앙 9h", 9.0)):
        Ax = {("현실", 0): real_hours(N_SENS, SEED + 31, wk, med=med)}
        r = mc(tab, hist, SIGMA["Q3"], n=N_SENS, seed=SEED + 41, budgets=Ax)
        print(f"| {label} | {q(r['hreq'], .5):,.0f} | {np.mean(r['succ'][('현실', 0)]):.2f} |")

    print("\n## 9. 진단 결과에 따른 갱신(Q3, 10/5→2027-11-18, 현실분포 7h)")
    print("\n| 진단 결과 가정 | 필요시간 P50(h) | P(관측합계≤15) | 최빈 최적조합 |")
    print("|---|---|---|---|")
    diag = [
        ("기준: 국어 출발 5등급, 영어 2.5, 중학수학 재학습 140h", {}),
        ("국어 무준비 진단 3등급", dict(q3_kor_start=3)),
        ("국어 무준비 진단 6등급", dict(q3_kor_start=6)),
        ("영어 진단 2등급(안정)", dict(q3_eng_start=2.0)),
        ("영어 진단 4등급(문법·어휘 약점 확인)", dict(q3_eng_start=4.0)),
        ("중학 수학 진단 양호(재학습 80h)", dict(q3_math_pre=80.0)),
        ("중학 수학 진단 매우 낮음(재학습 240h)", dict(q3_math_pre=240.0)),
        ("중학 과학 기초 양호(40h)", dict(q3_sci_pre=40.0)),
        ("첫 200시간 실측: 수학 진도 예상의 1.4배 소요(m=2.8)", dict(m_math=2.8, prac_math_mult=1.4)),
        ("첫 200시간 실측: 수학 진도 예상의 0.75배(m=1.5)", dict(m_math=1.5, prac_math_mult=0.75)),
    ]
    for label, over in diag:
        tab, hist = tables("Q3", **over)
        r = mc(tab, hist, SIGMA["Q3"], n=N_SENS, seed=SEED + 41, budgets=Areal)
        cnt = Counter(tuple(int(x) for x in rr) for rr in r["combo"]).most_common(1)[0]
        print(f"| {label} | {q(r['hreq'], .5):,.0f} | {np.mean(r['succ'][('현실', 0)]):.2f} | {cnt[0]} ({cnt[1] / N_SENS:.0%}) |")

    print("\n## 10. 12시간 계획의 시간 예산·효율 환산(판단)")
    sleep, life = 7.5, 3.0
    print(f"- 24h − 수면 {sleep}h − 식사·위생·이동·운동 {life}h = {24 - sleep - life:.1f}h → 12h 학습 시 여유 {24 - sleep - life - 12:.1f}h")
    curve = [1, 1, 1, 1, 1, 1, .8, .8, .6, .6, .4, .4]  # [판단] 시간대별 한계 효율
    print(f"- 시간대별 한계효율(1~6h 1.0, 7~8h 0.8, 9~10h 0.6, 11~12h 0.4) 합 = {sum(curve):.1f}h/일 (명목 12h 대비 {sum(curve) / 12:.2f})")
    print(f"- Pencavel 비유(주 70h 산출 ≈ 55h): 주 78h(12h×6.5) → 약 {55 / 70 * 78:.0f}h 상당 = 하루 {55 / 70 * 78 / 6.5:.1f}h")
    for adh in (0.75, 0.85, 0.95):
        print(f"- 한계효율 합 {sum(curve):.1f}h × 장기 실행률 {adh:.2f} = 실질 {sum(curve) * adh:.1f}h/일")


if __name__ == "__main__":
    main()
