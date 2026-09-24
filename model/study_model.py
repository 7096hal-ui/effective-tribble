"""수능 전업 수험생의 시간별·연간 학습성과 조건부 모형 (연구책임자 통합 모형).

무엇을 계산하나
  Q(t,h): t일의 h번째 '명목' 공부시간이 기여하는 기대 학습량
          (7일 지연 평가 기준의 유지·적용 가능한 학습, 복습에 의한 망각 방지 포함; 표준화된 가상 단위)
  R(t,h) = 100 * Q(t,h) / Q(t,1)          같은 날 첫 시간 대비
  A(t,h) = 100 * Q(t,h) / Q_ref           충분히 회복된 '기준 쌍둥이'의 첫 시간 대비
  RHE    = sum A/100                      충분히 회복된 첫 시간 몇 개에 해당하는가(rested-hour equivalents)

Q_ref: 같은 사람, 같은 지식수준·과제 구성, 같은 기상 시각·시간표에서
       수면 필요량을 채운 상태(수면부채 0), 다일 누적 부하 0, 일정에 적응 완료된 상태의 첫 1시간.
       -> A는 지식수준에 따른 학습곡선 체감(연중 공통)을 제외하고 '상태'(피로·수면·적응)만 반영한다.

모형 구조 (한 시간 = 5분 단위 12스텝의 평균)
  Q_step = e * k
    e  = e0(t) * warm * (1 - eps * (1 - F*G))          # 명목시간 중 실제 과제 관여 비율
    k  = C * F * G                                     # 관여 1분당 학습효율
    C  = 1 - morning(clock) - dip(clock) - late(tau, B)  # 일주기·각성시간(수면부채가 늦은 저하를 앞당김)
    F  = 1 - f_tot * u                                  # 블록 내 과제지속 피로 u(0..1), 식사·긴 휴식에서 일부 회복
    G  = 1 - g(t,L) * W^p / (W^p + W50^p)               # 그날 누적 관여시간 W에 따른 일중 누적 피로(수면으로만 해소)
  Q(t,h) = mean_steps(Q_step) * D_sleep(t) * D_load(t) * K(t)
    D_sleep = 1 - kappa_s * B            # 아침 수면부채 B(시간 환산)
    D_load  = 1 - beta * L/(L+L_h)       # 수면과 별개인 다일 누적 부하 L(동기·소진 포함)
    K       = 1 - kappa_c * max(0, N - s)/N   # 그날 밤 수면이 당일 학습의 공고화(7일 유지)에 미치는 영향
  수면부채   B <- max(0, B*(1-lam) + (N - s))          # 중등도 제한에서는 평형으로 수렴(발산하지 않음)
  누적 부하  L <- L*phi + alpha*max(0, W_day - W_s);  여가 L *= (1 - r_l*min(여가,3));  휴일 L *= (1 - r_rest)

모든 모수는 PARAMS에 값, 민감도 범위, 근거 등급(문헌 제약 / 간접 추정 / 가정)을 적었다.
이 모형은 관측 자료로 보정된 예측모형이 아니라, 문헌이 지지하는 방향과 크기 범위를 투명한 가정으로
연결한 조건부 모형이다. 출력의 범위는 통계적 신뢰구간이 아니라 가정 범위(scenario range)다.
"""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
STEP_H = 5.0 / 60.0
STEPS_PER_H = 12
DAYS = 365
CYCLE = 14

# ---------------------------------------------------------------------------
# 모수: (기준값, 민감도 하한, 상한, 등급, 근거)
# 등급: L = 문헌 제약(literature_constrained), I = 간접 추정(indirect_estimate), A = 가정(assumption)
# ---------------------------------------------------------------------------
PARAMS = {
    # 관여(engagement)
    "e0":        (0.80, 0.70, 0.90, "A", "명목 1시간 중 과제 관여 비율(짧은 휴식·전환·이탈 포함). 온라인 강의 중 마음 방황이 흔하고 중간 퀴즈로 줄어든다는 방향만 차용(Szpunar 2013)"),
    "warm0":     (0.25, 0.00, 0.45, "A", "하루 첫 20분 준비·몰입 지연에 따른 관여 감소 비율"),
    "eps":       (0.50, 0.25, 1.00, "A", "피로 지수가 관여 비율(마음 방황·저노력 전략 이동)에 전달되는 정도. 하루 6시간 이상 고난도 인지작업 뒤 저노력 선택 증가(Blain 2016; Wiehler 2022)에서 방향만 차용"),
    # 일주기·각성시간
    "d_morn":    (0.04, 0.00, 0.08, "I", "기상 직후 수면관성·저녁형(20세 전후 가장 늦음, Roenneberg 2004) 오전 저하; 동조효과 비일관(Chauhan 2025)"),
    "d_dip":     (0.03, 0.00, 0.06, "I", "오후 저하(post-lunch dip, Monk 2005), 개인차 큼"),
    "tau_c0":    (16.0, 15.1, 16.6, "L", "깨어 있은 지 약 16시간 이후 저하(Van Dongen 2003 임계 15.84±0.73h; Dijk & Czeisler 1994)"),
    "xi":        (0.15, 0.05, 0.30, "A", "수면부채 1시간당 늦은 저하 시작이 앞당겨지는 정도(h/h)"),
    "c_late":    (0.03, 0.015, 0.06, "A", "임계 이후 각성시간 제곱에 비례하는 저하 계수(/h^2)"),
    # 블록 내 과제지속 피로
    "f_tot":     (0.06, 0.02, 0.12, "I", "블록 내 최대 과제지속 저하. 학교 하루 동안 시간당 -0.9% SD, 20~30분 휴식 +1.7% SD(Sievertsen 2016); 3.5~5.5h 시험에서 수행 저하 없음(Ackerman & Kanfer 2009)"),
    "tau_tot":   (1.5, 1.0, 3.0, "A", "블록 내 피로 누적 시간상수(h)"),
    "rho":       (0.75, 0.50, 1.00, "I", "30분 이상 식사·휴식에서 블록 피로가 회복되는 비율(Sievertsen 2016: 휴식 효과가 1시간 저하보다 큼)"),
    # 일중 누적 피로(수면으로만 해소)
    "g_max":     (0.45, 0.25, 0.65, "A", "그날 누적 관여시간에 따른 최대 저하. 5h 안팎까지 뚜렷한 수행 저하 없음(Ackerman), 6h 이후 선택 변화(Wiehler 2022) 외에 직접 근거 없음"),
    "W50":       (10.0, 8.0, 13.0, "A", "누적 저하가 최대치의 절반이 되는 누적 관여시간(h)"),
    "p":         (3.0, 1.0, 4.0, "A", "누적 저하 곡선의 모양(1=초반부터 떨어지는 오목형, 3~4=후반 가속)"),
    # 적응
    "a_e":       (0.08, 0.00, 0.15, "A", "시작 직후 일정 미적응에 따른 관여 감소(초기 몇 주)"),
    "T_a":       (21.0, 10.0, 45.0, "A", "일정 적응 시간상수(일)"),
    "end_max":   (0.20, 0.00, 0.35, "I", "인지 지구력 훈련으로 일중 저하가 줄어드는 최대 비율(Brown et al. 2025: 시험 내 저하 22% 감소)"),
    "T_end":     (45.0, 20.0, 90.0, "A", "지구력 적응 시간상수(일)"),
    # 수면
    "N":         (8.3, 7.8, 8.8, "L", "실수면 필요량(Van Dongen 2003 약 8.16h; Kitamura 2016 8.4h, 개인 7.3~9.3h; Klerman & Dijk 2008 약 8.9h)"),
    "lam":       (0.20, 0.10, 0.35, "I", "만성 중등도 수면제한에서 수행이 새 평형으로 수렴하는 속도(Belenky 2003; McCauley 2009)"),
    "kappa_s":   (0.015, 0.007, 0.028, "I", "수면부채(시간 환산)당 학습효율 저하. 수면제한 메타분석 장기기억 g=-0.19, 실행기능 -0.32(Lowe 2017), 부분제한 후 부호화 저하(Cousins 2018)에서 크기 범위만 차용"),
    "kappa_c":   (0.25, 0.10, 0.40, "I", "완전 수면박탈 시 당일 학습 공고화 손실 비율(학습 후 박탈 g=0.28, Newbury 2021; 수면 대 각성 g=0.44, Berres & Erdfelder 2021)에서 선형 환산"),
    "rest_sleep_extra": (1.0, 0.5, 2.0, "A", "휴일 밤 추가 실수면(h)"),
    # 다일 누적 부하(수면 외)
    "T_L":       (10.0, 5.0, 20.0, "I", "누적 부하 자연 감쇠 시간상수(일). 휴가 효과 1~4주 내 소멸(de Bloom 2009; Speth 2024)"),
    "W_s":       (6.0, 4.0, 8.0, "A", "하루 누적 관여시간 중 다음 날로 부하를 남기지 않는 수준(h)"),
    "alpha":     (0.25, 0.10, 0.50, "A", "초과 관여 1시간당 누적 부하 입력"),
    "beta":      (0.25, 0.10, 0.40, "A", "누적 부하가 첫 시간 성과를 낮추는 최대 비율. 학생 소진-성취 r=-0.24(Madigan & Curran 2021)는 사람 간 상관이라 방향만 차용"),
    "L_h":       (10.0, 10.0, 10.0, "A", "부하 효과가 절반이 되는 부하량(척도 고정용)"),
    "eta":       (0.50, 0.00, 1.00, "A", "누적 부하가 일중 저하를 키우는 정도"),
    "r_l":       (0.03, 0.01, 0.06, "A", "자유 여가 1시간당 누적 부하 회복률(최대 3시간까지)"),
    "r_rest":    (0.35, 0.15, 0.60, "A", "완전 휴일 하루의 누적 부하 회복률(주말 회복→다음 주 수행, Binnewies 2010, 자기보고)"),
    # 운동·명상의 직접 효과(기준 0)
    "ex_gain":   (0.00, 0.00, 0.03, "I", "규칙적 운동의 인지 직접 효과(젊은 성인 소효과, 편향 보정 시 0에 가까움: Ludyga 2020; Ciria 2023)"),
}

SWEEP_KEYS = [k for k in PARAMS if PARAMS[k][1] != PARAMS[k][2]]


def base_params(n: int = 1) -> dict:
    return {k: np.full(n, float(v[0])) for k, v in PARAMS.items()}


def sample_params(n: int, seed: int = 20260924, keys=None) -> dict:
    """가정 범위 안에서 라틴 하이퍼큐브 추출(균등). 결과는 확률분포가 아니라 가정의 스윕이다."""
    rng = np.random.default_rng(seed)
    keys = SWEEP_KEYS if keys is None else keys
    p = base_params(n)
    for k in keys:
        _, lo, hi, _, _ = PARAMS[k]
        u = (rng.permutation(n) + rng.random(n)) / n
        p[k] = lo + (hi - lo) * u
    return p


# ---------------------------------------------------------------------------
# 하루 시간표
# ---------------------------------------------------------------------------
@dataclass
class Plan:
    name: str
    H: float                       # 공부일 명목 공부시간
    tib: float                     # 침대 시간
    sleep_eff: float               # 수면효율
    wake: float = 7.0              # 기상 시각(시)
    morning: float = 0.25          # 기상 후 공부 시작 전(세면·옷·이동 일부)
    lunch: float = 0.5
    dinner: float = 0.5
    pre_dinner: float = 0.0        # 오후 블록과 저녁 식사 사이(운동+샤워 등)
    evening: float = 0.5           # 마지막 블록 후 취침 전(샤워·정리·명상 등, 여가 제외)
    leisure: float = 0.0           # 자유 여가(공부일)
    rest_per_14: int = 1           # 14일 중 완전 휴일
    partial_per_14: int = 0        # 14일 중 반일 휴식일(공부 절반)
    exercise: bool = False
    irregular: float = 0.0         # 수면 시각 불규칙성으로 인한 실수면 추가 손실(h)
    note: str = ""

    def life(self) -> float:
        return self.morning + self.lunch + self.dinner + self.pre_dinner + self.evening

    def check(self) -> float:
        return self.H + self.tib + self.life() + self.leisure

    def actual_sleep(self) -> float:
        return self.tib * self.sleep_eff - self.irregular


def day_types(plan: Plan) -> list[str]:
    """14일 주기의 날 종류. 휴일은 주기 안에 고르게 배치(1개면 14일째)."""
    types = ["study"] * CYCLE
    r, pday = plan.rest_per_14, plan.partial_per_14
    if r > 0:
        idx = [int(round((i + 1) * CYCLE / r)) - 1 for i in range(r)]
        for i in idx:
            types[i] = "rest"
    if pday > 0:
        free = [i for i in range(CYCLE) if types[i] == "study"]
        # 반일 휴식일은 휴일 사이 중간쯤
        for j in range(pday):
            pos = free[int((j + 0.5) * len(free) / pday)]
            types[pos] = "partial"
    return types


def study_steps(plan: Plan, H: float):
    """공부 스텝별 (시계 시각, 기상 후 경과, 블록 번호, 직전 휴식 길이)."""
    fr = (0.34, 0.38, 0.28)
    blocks = [H * f for f in fr]
    breaks_before = [plan.morning, plan.lunch, plan.pre_dinner + plan.dinner]
    steps = []
    t = 0.0
    for b, (dur, brk) in enumerate(zip(blocks, breaks_before)):
        t += brk
        n = int(round(dur / STEP_H))
        for i in range(n):
            steps.append((plan.wake + t + (i + 0.5) * STEP_H, t + (i + 0.5) * STEP_H, b, brk if i == 0 else 0.0))
        t += n * STEP_H
    return steps


# ---------------------------------------------------------------------------
# 시뮬레이션
# ---------------------------------------------------------------------------
def simulate(plan: Plan, P: dict, days: int = DAYS, record_hours: int = 14, store=True):
    n = len(next(iter(P.values())))
    types = day_types(plan)
    B = np.zeros(n)
    L = np.zeros(n)
    s_night = plan.actual_sleep()
    total_rhe = np.zeros(n)
    rec = {}  # day -> (Q per hour array n x H, M_day)
    stepsH = study_steps(plan, plan.H)
    stepsHalf = study_steps(plan, plan.H / 2)
    qref = rested_first_hour(plan, P)
    daily = []
    engaged = []
    for d in range(days):
        typ = types[d % CYCLE]
        if typ == "rest":
            steps, Wd = [], 0.0
        else:
            steps = stepsH if typ == "study" else stepsHalf
        D_sleep = np.clip(1 - P["kappa_s"] * B, 0.4, 1.0)
        D_load = 1 - P["beta"] * L / (L + P["L_h"])
        adapt_e = 1 - P["a_e"] * np.exp(-d / P["T_a"])
        gmax = P["g_max"] * (1 - P["end_max"] * (1 - np.exp(-d / P["T_end"]))) * (1 + P["eta"] * L / (L + P["L_h"]))
        # 그날 밤 수면
        if typ == "rest":
            s = s_night + P["rest_sleep_extra"]
            leisure = 24 - plan.tib - plan.life() * 0.6  # 휴일: 생활 일부만, 나머지 여가
        elif typ == "partial":
            s = s_night + 0.5 * P["rest_sleep_extra"]
            leisure = plan.leisure + plan.H / 2
        else:
            s = np.full(n, s_night)
            leisure = plan.leisure
        K = 1 - P["kappa_c"] * np.maximum(0, P["N"] - s) / P["N"]
        M = D_sleep * D_load * K * (1 + P["ex_gain"] * (1.0 if plan.exercise else 0.0))
        if steps:
            Qh, Wd = run_day(steps, P, B, gmax, adapt_e)
            Qh = Qh * M[:, None]
            A = Qh / qref[:, None]
            total_rhe += A.sum(axis=1)
            if store:
                rec[d] = (Qh, A, D_sleep, D_load, K)
            daily.append(A.sum(axis=1))
            engaged.append(Wd)
        else:
            daily.append(np.zeros(n))
            Wd = np.zeros(n)
        # 상태 갱신
        B = np.maximum(0, B * (1 - P["lam"]) + (P["N"] - s))
        phi = np.exp(-1 / P["T_L"])
        L = L * phi + P["alpha"] * np.maximum(0, Wd - P["W_s"])
        L = L * (1 - P["r_l"] * min(leisure if np.isscalar(leisure) else 3, 3))
        if typ == "rest":
            L = L * (1 - P["r_rest"])
        elif typ == "partial":
            L = L * (1 - 0.5 * P["r_rest"])
    return {"total_rhe": total_rhe, "rec": rec, "qref": qref, "daily": np.array(daily), "types": types,
            "engaged_mean": np.mean(engaged, axis=0) if engaged else np.zeros(n)}


def run_day(steps, P, B, gmax, adapt_e):
    n = len(B)
    u = np.zeros(n)
    W = np.zeros(n)
    tau_c = P["tau_c0"] - P["xi"] * B
    q = []
    first_t = None
    for clock, tau, blk, brk in steps:
        if brk > 0 and first_t is not None:
            # 휴식에 따른 블록 피로 회복: 30분 이상이면 rho, 짧으면 비례
            u = u * (1 - P["rho"] * min(1.0, brk / 0.5))
        if first_t is None:
            first_t = tau
        since = tau - first_t
        warm = 1 - P["warm0"] * max(0.0, 1 - since / 0.333)
        morning = P["d_morn"] * min(1.0, max(0.0, (9.0 - clock) / 2.0))
        dip = P["d_dip"] * math.exp(-0.5 * ((clock - 14.5) / 1.0) ** 2)
        late = P["c_late"] * np.maximum(0, tau - tau_c) ** 2
        C = 1 - morning - dip - late
        F = 1 - P["f_tot"] * u
        G = 1 - gmax * W ** P["p"] / (W ** P["p"] + P["W50"] ** P["p"])
        e = P["e0"] * adapt_e * warm * (1 - P["eps"] * (1 - F * G))
        k = C * F * G
        q.append(e * k)
        # 상태 진행
        u = u + (1 - u) * (STEP_H / P["tau_tot"])
        W = W + e * STEP_H
    q = np.array(q).T  # n x steps
    nh = int(math.ceil(q.shape[1] / STEPS_PER_H))
    Qh = np.zeros((n, nh))
    for h in range(nh):
        seg = q[:, h * STEPS_PER_H:(h + 1) * STEPS_PER_H]
        Qh[:, h] = seg.sum(axis=1) / STEPS_PER_H  # 부분 시간은 그만큼만 기여
    return Qh, W


def rested_first_hour(plan: Plan, P: dict):
    n = len(P["e0"])
    steps = study_steps(plan, max(1.0, plan.H))[:STEPS_PER_H]
    gmax = P["g_max"] * (1 - P["end_max"])
    Qh, _ = run_day(steps, P, np.zeros(n), gmax, np.ones(n))
    return Qh[:, 0]


# ---------------------------------------------------------------------------
# 시나리오 정의
# ---------------------------------------------------------------------------
def prompt1_plan(label: str, H: float = 14.0) -> Plan:
    """첫 번째 질문(생활조건 미지정). 14h 기준 S1/S2/S3. 운동·명상은 포함하지 않음."""
    if label == "S1":
        return Plan("S1 회복 유리", H, tib=8.25, sleep_eff=0.93, morning=0.25, lunch=0.5, dinner=0.5, evening=0.5,
                    note="최소 생활 1.75h, 침대 8.25h, 실수면 약 7.7h")
    if label == "S2":
        return Plan("S2 기준", H, tib=7.5, sleep_eff=0.93, morning=0.5, lunch=0.67, dinner=0.67, evening=0.66,
                    note="생활 2.5h, 침대 7.5h, 실수면 약 7.0h")
    if label == "S3":
        return Plan("S3 회복 불리", H, tib=7.0, sleep_eff=0.90, morning=0.75, lunch=0.75, dinner=0.75, evening=0.75,
                    irregular=0.2, note="생활 3.0h, 침대 7.0h, 실수면 약 6.1h(불규칙)")
    raise ValueError(label)


def prompt1_reallocated(H: float, route: str = "sleep_first") -> Plan:
    """공부시간을 줄여 생긴 시간을 수면(필요량까지) -> 여가 순으로 재배분. 생활 2.5h(S2와 동일)."""
    life = dict(morning=0.5, lunch=0.67, dinner=0.67, evening=0.66)
    free = 24 - H - 2.5
    need_tib = 8.3 / 0.93
    if route == "sleep_first":
        tib = min(free, need_tib)
    else:  # 수면은 S2(7.5h)로 고정, 남는 시간 전부 여가
        tib = min(free, 7.5)
    leisure = free - tib
    return Plan(f"{H:g}h ({'수면 우선' if route=='sleep_first' else '수면 고정'})", H, tib=tib, sleep_eff=0.93,
                leisure=leisure, **life)


LIFE2 = {
    "tight": dict(sleep_eff=0.95, morning=0.25, lunch=0.45, dinner=0.45, pre_dinner=0.6, evening=0.97),
    "base": dict(sleep_eff=0.93, morning=0.45, lunch=0.6, dinner=0.6, pre_dinner=0.88, evening=1.77),
    "generous": dict(sleep_eff=0.90, morning=0.7, lunch=0.85, dinner=0.85, pre_dinner=1.18, evening=2.53),
}
LIFE2_TOTAL = {"tight": 176 / 60, "base": 258 / 60, "generous": 366 / 60}


def life2_cfg(life: str):
    """생활 항목(시간표 배치용)을 LIFE2_TOTAL 합계에 맞춰 반환. (수면효율, 항목 dict)"""
    cfg = dict(LIFE2[life])
    se = cfg.pop("sleep_eff")
    scale = LIFE2_TOTAL[life] / sum(cfg.values())
    return se, {k: v * scale for k, v in cfg.items()}


def prompt2_plan(H: float, life: str = "base", rest_per_14: int = 1, partial_per_14: int = 0,
                 leisure_floor: float = 0.0) -> Plan | None:
    """두 번째 질문 조건(실수면 8h, 운동·명상·식사·위생 포함). 여가 = 24 - TIB - 생활 - H."""
    se, cfg = life2_cfg(life)
    tib = 8.0 / se
    leisure = 24 - tib - LIFE2_TOTAL[life] - H
    if leisure < leisure_floor - 1e-9:
        return None
    return Plan(f"{H:g}h/{life}/휴일{rest_per_14}/반일{partial_per_14}", H, tib=tib, sleep_eff=se, wake=6.5,
                leisure=leisure, rest_per_14=rest_per_14, partial_per_14=partial_per_14, exercise=True, **cfg)


TIMEPOINTS = {"1-2주": 0, "1개월": 2, "3개월": 6, "6개월": 12, "12개월": 25}  # 14일 주기 번호


def cycle_average(sim, cycle: int, nh: int = 14):
    days = [d for d in range(cycle * CYCLE, (cycle + 1) * CYCLE) if d in sim["rec"]]
    Q = np.mean([sim["rec"][d][0][:, :nh] for d in days], axis=0)
    A = np.mean([sim["rec"][d][1][:, :nh] for d in days], axis=0)
    R = 100 * Q / Q[:, :1]
    return R, 100 * A


def first_below(R_row, thr):
    for h, v in enumerate(R_row):
        if v <= thr + 1e-9:
            return h + 1
    return None


# ---------------------------------------------------------------------------
# 출력 도우미
# ---------------------------------------------------------------------------
def r5(x):
    return int(5 * round(float(x) / 5))


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main(n_sweep: int = 300):
    os.makedirs(OUT, exist_ok=True)
    results = {"meta": {"n_sweep": n_sweep, "note": "범위는 가정 스윕의 10~90 백분위이며 신뢰구간이 아님"}}
    Pb = base_params(1)
    Ps = sample_params(n_sweep)

    # 0) 24시간 검증
    budget_rows = []
    for lab in ("S1", "S2", "S3"):
        pl = prompt1_plan(lab)
        budget_rows.append([pl.name, pl.H, round(pl.tib, 2), round(pl.life(), 2), round(pl.leisure, 2),
                            round(pl.check(), 2), round(pl.actual_sleep(), 2), round(24 - pl.actual_sleep(), 2)])
        assert abs(pl.check() - 24) < 0.02, pl
    write_csv(os.path.join(OUT, "budget_prompt1.csv"),
              ["시나리오", "명목공부h", "침대h", "생활h", "여가h", "합계h", "실수면h", "각성h"], budget_rows)

    # 1) 14h 시간별 표 (S1/S2/S3 x 시점)
    hourly = {}
    thresholds = []
    yearly = {}
    for lab in ("S1", "S2", "S3"):
        pl = prompt1_plan(lab)
        sb = simulate(pl, Pb)
        ss = simulate(pl, Ps)
        hourly[lab] = {}
        for tp, cyc in TIMEPOINTS.items():
            Rb, Ab = cycle_average(sb, cyc)
            Rs, As = cycle_average(ss, cyc)
            hourly[lab][tp] = {
                "R": Rb[0].tolist(), "A": Ab[0].tolist(),
                "R_lo": np.percentile(Rs, 10, axis=0).tolist(), "R_hi": np.percentile(Rs, 90, axis=0).tolist(),
                "A_lo": np.percentile(As, 10, axis=0).tolist(), "A_hi": np.percentile(As, 90, axis=0).tolist(),
            }
            t80 = first_below(Rb[0], 80)
            t50 = first_below(Rb[0], 50)
            t80s = [first_below(r, 80) for r in Rs]
            t50s = [first_below(r, 50) for r in Rs]
            thresholds.append({
                "scenario": lab, "timepoint": tp, "le80_base": t80, "le50_base": t50,
                "le80_range": pct_hours(t80s), "le50_range": pct_hours(t50s),
                "share_never80": float(np.mean([t is None for t in t80s])),
                "share_never50": float(np.mean([t is None for t in t50s])),
            })
        # 연중 변화: 주기별 첫 시간 A, 하루 RHE, 9~14시간째 비중
        cyc_rows = []
        for cyc in range(26):
            days = [d for d in range(cyc * CYCLE, (cyc + 1) * CYCLE) if d in sb["rec"]]
            A = np.mean([sb["rec"][d][1][0] for d in days], axis=0) * 100
            Asw = np.mean([ss["rec"][d][1] for d in days], axis=0) * 100  # n x 14
            daily_rhe = A.sum() / 100
            daily_sw = Asw.sum(axis=1) / 100
            late_share = A[8:].sum() / A.sum()
            cyc_rows.append([cyc + 1, round(A[0], 1), round(daily_rhe, 2), round(late_share, 3),
                             round(np.percentile(Asw[:, 0], 10), 1), round(np.percentile(Asw[:, 0], 90), 1),
                             round(np.percentile(daily_sw, 10), 2), round(np.percentile(daily_sw, 90), 2)])
        yearly[lab] = cyc_rows
        write_csv(os.path.join(OUT, f"yearly_{lab}.csv"),
                  ["주기", "첫시간A", "하루RHE", "9~14시간째비중", "첫시간A_p10", "첫시간A_p90", "하루RHE_p10", "하루RHE_p90"], cyc_rows)
        # 휴일 직후(주기 1일째)와 직전(13일째)
        pre_post = []
        for cyc in (6, 25):
            d1, d13 = cyc * CYCLE, cyc * CYCLE + 12
            for tag, d in (("휴일 직후", d1), ("휴일 직전", d13)):
                Q, A = sb["rec"][d][0][0], sb["rec"][d][1][0] * 100
                R = 100 * Q / Q[0]
                pre_post.append([f"{cyc+1}주기 {tag}", round(A[0], 1)] + [round(x) for x in R[[7, 9, 11, 13]]] + [round(A.sum() / 100, 2)])
        write_csv(os.path.join(OUT, f"prepost_{lab}.csv"), ["날", "첫시간A", "R8", "R10", "R12", "R14", "하루RHE"], pre_post)
        results.setdefault("prepost", {})[lab] = pre_post
    results["hourly"] = hourly
    results["thresholds"] = thresholds
    results["yearly"] = yearly

    # 2) 일정 비교 (첫 번째 질문 틀): 8/10/12/14, 재배분 경로 두 가지
    comp = []
    for route in ("sleep_first", "sleep_fixed"):
        prev = None
        for H in (8, 10, 12, 14):
            pl = prompt1_plan("S2") if H == 14 else prompt1_reallocated(H, route)
            sb = simulate(pl, Pb, store=False)
            ss = simulate(pl, Ps, store=False)
            row = {"route": route, "H": H, "tib": round(pl.tib, 2), "sleep": round(pl.actual_sleep(), 2),
                   "leisure": round(pl.leisure, 2), "rhe": float(sb["total_rhe"][0]),
                   "rhe_p10": float(np.percentile(ss["total_rhe"], 10)), "rhe_p90": float(np.percentile(ss["total_rhe"], 90)),
                   "nominal": H * 13 * 26 + H * 1}
            row["_sw"] = ss["total_rhe"]
            comp.append(row)
    # 증가분과 분해(블록 기여 vs 파급)
    incs = []
    for route in ("sleep_first", "sleep_fixed"):
        rows = [r for r in comp if r["route"] == route]
        for a, b in zip(rows[:-1], rows[1:]):
            net = b["rhe"] - a["rhe"]
            netsw = b["_sw"] - a["_sw"]
            blk, spill = decompose(a["H"], b["H"], route, Pb)
            incs.append({"route": route, "step": f"{a['H']}→{b['H']}", "net": net, "block": blk, "spill": spill,
                         "net_p10": float(np.percentile(netsw, 10)), "net_p90": float(np.percentile(netsw, 90)),
                         "share_negative": float(np.mean(netsw < 0))})
    for r in comp:
        r.pop("_sw")
    results["schedule_prompt1"] = comp
    results["increments_prompt1"] = incs

    # 3) 두 번째 질문 틀: 조건 고정 시 가능 범위와 최적화
    opt = optimize_prompt2(Pb, Ps)
    results.update(opt)

    results.update(extra_analysis(Pb, Ps))
    results["representative"] = representative_plans(Pb, Ps)

    # 4) 민감도(일대일): 핵심 결론 3개
    results["sensitivity"] = one_at_a_time()

    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1, default=float)
    return results


def pct_hours(ts):
    """임계 도달 시간의 10~90 백분위. 14시간 안에 도달하지 않으면 15로 두고 '없음'으로 표기."""
    vals = [t if t is not None else 15 for t in ts]
    lo, hi = np.percentile(vals, 10), np.percentile(vals, 90)
    lo, hi = int(round(lo)), int(round(hi))
    f = lambda v: "없음" if v >= 15 else f"{v}"
    if lo >= 15:
        return "14h 안에 없음"
    return f"{f(lo)}~{f(hi)}"


def decompose(H0, H1, route, P):
    """H0→H1 연장의 순효과를 (추가 블록의 기여)와 (나머지 시간·날에 대한 파급)으로 분해."""
    pl0 = prompt1_reallocated(H0, route) if H0 < 14 else prompt1_plan("S2")
    pl1 = prompt1_reallocated(H1, route) if H1 < 14 else prompt1_plan("S2")
    s0 = simulate(pl0, P)
    s1 = simulate(pl1, P)
    nh0 = int(math.ceil(H0))
    blk = sum(s1["rec"][d][1][0, nh0:].sum() for d in s1["rec"])
    first = sum(s1["rec"][d][1][0, :nh0].sum() for d in s1["rec"])
    base = float(s0["total_rhe"][0])
    return float(blk), float(first - base)


def optimize_prompt2(Pb, Ps):
    out = {}
    # 가능 최대치
    feas = []
    for life in ("tight", "base", "generous"):
        tib = 8.0 / LIFE2[life]["sleep_eff"]
        feas.append({"life": life, "tib": round(tib, 2), "life_h": round(LIFE2_TOTAL[life], 2),
                     "max_H": round(24 - tib - LIFE2_TOTAL[life], 2)})
    out["feasibility_prompt2"] = feas
    # 격자
    grid = []
    Hs = [x / 2 for x in range(14, 26)]  # 7.0 ~ 12.5
    for rest in (1, 2, 3, 4):
        for part in (0, 1, 2):
            if rest + part > 6:
                continue
            for H in Hs:
                pl = prompt2_plan(H, "base", rest, part)
                if pl is None:
                    continue
                sb = simulate(pl, Pb, store=False)
                grid.append({"H": H, "rest": rest, "partial": part, "leisure": round(pl.leisure, 2),
                             "rhe": float(sb["total_rhe"][0]), "nominal": annual_nominal(pl)})
    out["grid_prompt2_base"] = grid
    best = max(grid, key=lambda g: g["rhe"])
    band = [g for g in grid if g["rhe"] >= 0.98 * best["rhe"]]
    out["optA"] = {"best": best, "band": band}
    # 시나리오 B: 여가 하한 + 매주 1일 이상 완전 휴일(rest>=2)
    optB = {}
    for floor in (1.0, 1.5, 2.0):
        cand = [g for g in grid if g["rest"] >= 2 and g["leisure"] >= floor - 1e-9]
        if cand:
            b = max(cand, key=lambda g: g["rhe"])
            optB[f"{int(floor*60)}"] = {"best": b, "band": [g for g in cand if g["rhe"] >= 0.98 * b["rhe"]]}
    out["optB"] = optB
    # 가정 스윕에서 최적 H의 분포(휴일 1/14, 2/14). 두 곡선 모두 같은 가정 조합의 '휴일 1/14 최댓값'으로 정규화
    sweep = {}
    mats = {}
    for rest in (1, 2):
        vals = []
        for H in Hs:
            pl = prompt2_plan(H, "base", rest, 0)
            if pl is None:
                continue
            vals.append((H, simulate(pl, Ps, store=False)["total_rhe"]))
        mats[rest] = (np.array([v[0] for v in vals]), np.stack([v[1] for v in vals]))
    ref = mats[1][1].max(axis=0, keepdims=True)
    for rest in (1, 2):
        Hgrid, M = mats[rest]
        argbest = Hgrid[np.argmax(M, axis=0)]
        rel = M / ref
        sweep[str(rest)] = {"H": Hgrid.tolist(),
                            "opt_H_p10": float(np.percentile(argbest, 10)), "opt_H_p50": float(np.percentile(argbest, 50)),
                            "opt_H_p90": float(np.percentile(argbest, 90)),
                            "rel_p10": np.percentile(rel, 10, axis=1).tolist(), "rel_p50": np.percentile(rel, 50, axis=1).tolist(),
                            "rel_p90": np.percentile(rel, 90, axis=1).tolist(),
                            "share_opt_at_max": float(np.mean(argbest == Hgrid.max()))}
    out["opt_sweep"] = sweep
    # 휴일 빈도 비교(최적 H에서)
    # 14h 조건부 변형(조건을 깨는 경우)
    variants = []
    se, cfg = life2_cfg("base")
    for tag, pl in (
        ("수면을 줄여 맞춤(운동·명상 유지)", Plan("14h-수면삭감", 14, tib=24 - 14 - LIFE2_TOTAL["base"], sleep_eff=se,
                                             wake=6.5, exercise=True, **cfg)),
        ("운동·명상 생략, 실수면 8h 유지(생활 1.4h로 압축)", Plan("14h-생활압축", 14, tib=8.6, sleep_eff=se, wake=6.5,
                                                     morning=0.2, lunch=0.4, dinner=0.4, evening=0.4)),
    ):
        sb = simulate(pl, Pb, store=False)
        variants.append({"variant": tag, "tib": round(pl.tib, 2), "sleep": round(pl.actual_sleep(), 2),
                         "rhe": float(sb["total_rhe"][0]), "check24": round(pl.check(), 2)})
    out["variants_14h_prompt2"] = variants
    return out



def extra_analysis(Pb, Ps):
    """(1) 두 번째 질문 틀의 8/10/11/12/14h 비교(불가능 일정은 어떤 조건을 깨는지 명시)
    (2) 휴일 빈도와 여가의 손익분기(모형과 무관한 산술) 및 가정 스윕에서 휴일을 늘리는 쪽이 이기는 비율
    (3) 대표안의 순공부시간(관여 시간) 추정"""
    out = {}
    se, cfg = life2_cfg("base")
    rows = []
    def add(tag, pl, cond):
        sb = simulate(pl, Pb, store=False)
        ss = simulate(pl, Ps, store=False)
        rows.append({"plan": tag, "H": pl.H, "sleep": round(pl.actual_sleep(), 2), "leisure": round(pl.leisure, 2),
                     "check24": round(pl.check(), 2), "condition": cond, "rhe": float(sb["total_rhe"][0]),
                     "rhe_p10": float(np.percentile(ss["total_rhe"], 10)), "rhe_p90": float(np.percentile(ss["total_rhe"], 90)),
                     "engaged_h": float(sb["engaged_mean"][0]), "nominal": annual_nominal(pl)})
    for H in (8, 10, 11):
        add(f"{H}h", prompt2_plan(H, "base", 1, 0), "조건 모두 충족(기준 생활 4.3h)")
    add("12h-빠듯한 생활", prompt2_plan(12, "tight", 1, 0), "조건 충족하나 생활시간을 빠듯한 가정(2.9h)으로 줄여야 가능")
    add("12h-수면삭감", Plan("12h-수면삭감", 12, tib=24 - 12 - LIFE2_TOTAL["base"], sleep_eff=se, wake=6.5, exercise=True, **cfg),
        "실수면 8h 조건 위반(수면을 줄여 맞춤)")
    add("14h-수면삭감", Plan("14h-수면삭감", 14, tib=24 - 14 - LIFE2_TOTAL["base"], sleep_eff=se, wake=6.5, exercise=True, **cfg),
        "실수면 8h 조건 위반(수면을 줄여 맞춤)")
    add("14h-생활압축", Plan("14h-생활압축", 14, tib=8.6, sleep_eff=se, wake=6.5, morning=0.2, lunch=0.4, dinner=0.4, evening=0.4),
        "운동·명상 조건 위반, 식사·위생 1.4h로 압축(비현실적)")
    out["prompt2_compare"] = rows

    # 손익분기: 휴일 14일에 1일 -> 2일로 늘리면 공부일 13 -> 12일
    out["breakeven"] = {
        "rest_1_to_2_per14_required_gain_pct": 100 * (13 / 12 - 1),
        "rest_1_to_3_per14_required_gain_pct": 100 * (13 / 11 - 1),
        "note": "휴일을 하루 늘려도 연간 총량이 같으려면 남은 공부일의 하루 총학습량이 평균 이만큼 높아져야 한다(시간당 효율 곡선과 무관한 산술).",
    }
    # 여가 손익분기: 기준 모형에서 H=11 -> 10 (여가 +1h)일 때 잃는 11번째 시간의 비중
    s11 = simulate(prompt2_plan(11, "base", 1, 0), Pb)
    last = []
    for d in s11["rec"]:
        A = s11["rec"][d][1][0]
        last.append((A[10], A.sum()))
    share = float(np.sum([a for a, _ in last]) / np.sum([t for _, t in last]))
    out["breakeven"]["leisure_hour_required_gain_pct"] = 100 * share / (1 - share)
    out["breakeven"]["leisure_note"] = "11h -> 10h로 줄여 여가 1시간을 만들 때, 남는 10시간의 성과가 평균 이만큼 올라야 본전(기준 모형의 11번째 시간 비중으로 계산)."

    # 가정 스윕에서 휴일을 늘리는 쪽이 이기는 비율
    win = {}
    for H in (10.0, 11.0):
        base1 = simulate(prompt2_plan(H, "base", 1, 0), Ps, store=False)["total_rhe"]
        for rest in (2, 3):
            alt = simulate(prompt2_plan(H, "base", rest, 0), Ps, store=False)["total_rhe"]
            win[f"H{H:g}_rest{rest}_vs_rest1"] = {"share_alt_better": float(np.mean(alt > base1)),
                                                 "ratio_p10": float(np.percentile(alt / base1, 10)),
                                                 "ratio_p50": float(np.percentile(alt / base1, 50)),
                                                 "ratio_p90": float(np.percentile(alt / base1, 90))}
        part = simulate(prompt2_plan(H, "base", 1, 1), Ps, store=False)["total_rhe"]
        win[f"H{H:g}_partial1_vs_none"] = {"share_alt_better": float(np.mean(part > base1)),
                                          "ratio_p50": float(np.percentile(part / base1, 50))}
    # 여가 하한에 따른 비용(가정 스윕): 11h(여가 0.1) 대비 10h(1.1), 9.5h(1.6), 9h(2.1)
    b11 = simulate(prompt2_plan(11, "base", 1, 0), Ps, store=False)["total_rhe"]
    for H, rest in ((10, 2), (9.5, 2), (9, 2), (10, 1)):
        alt = simulate(prompt2_plan(H, "base", rest, 0), Ps, store=False)["total_rhe"]
        win[f"H{H:g}_rest{rest}_vs_H11_rest1"] = {"share_alt_better": float(np.mean(alt > b11)),
                                                 "ratio_p10": float(np.percentile(alt / b11, 10)),
                                                 "ratio_p50": float(np.percentile(alt / b11, 50)),
                                                 "ratio_p90": float(np.percentile(alt / b11, 90))}
    out["rest_leisure_sweep"] = win
    return out


def representative_plans(Pb, Ps):
    """두 번째 질문의 대표안(A, B60, B90, B120)과 14h 가상안(실수면 8h 유지, 운동·명상 생략)의 요약·시간별 표."""
    se, cfg = life2_cfg("base")
    plans = {
        "A_11h_휴일14일1": prompt2_plan(11, "base", 1, 0),
        "A_10.5h_휴일14일1": prompt2_plan(10.5, "base", 1, 0),
        "B60_10h_주1휴일": prompt2_plan(10, "base", 2, 0),
        "B90_9.5h_주1휴일": prompt2_plan(9.5, "base", 2, 0),
        "B120_9h_주1휴일": prompt2_plan(9, "base", 2, 0),
    }
    out = {}
    ref = None
    for k, pl in plans.items():
        sb = simulate(pl, Pb, store=False)
        ss = simulate(pl, Ps, store=False)
        if ref is None:
            ref = ss["total_rhe"]
        out[k] = {"H": pl.H, "rest_per_14": pl.rest_per_14, "leisure": round(pl.leisure, 2), "sleep": round(pl.actual_sleep(), 2),
                  "engaged_h": float(sb["engaged_mean"][0]), "annual_nominal": annual_nominal(pl),
                  "weekly_nominal": annual_nominal(pl) / DAYS * 7,
                  "rhe": float(sb["total_rhe"][0]), "rhe_p10": float(np.percentile(ss["total_rhe"], 10)),
                  "rhe_p90": float(np.percentile(ss["total_rhe"], 90)),
                  "rel_to_A11_p10": float(np.percentile(ss["total_rhe"] / ref, 10)),
                  "rel_to_A11_p50": float(np.percentile(ss["total_rhe"] / ref, 50)),
                  "rel_to_A11_p90": float(np.percentile(ss["total_rhe"] / ref, 90))}
    # 14h 가상안: 실수면 8h 유지, 생활 1.4h(운동·명상 생략)
    hyp = Plan("14h-8h수면(가상)", 14, tib=8.6, sleep_eff=se, wake=6.5, morning=0.2, lunch=0.4, dinner=0.4, evening=0.4)
    sb, ss = simulate(hyp, Pb), simulate(hyp, Ps)
    tabs = {}
    for tp in ("1-2주", "6개월", "12개월"):
        cyc = TIMEPOINTS[tp]
        Rb, Ab = cycle_average(sb, cyc)
        Rs, As = cycle_average(ss, cyc)
        tabs[tp] = {"R": Rb[0].tolist(), "A": Ab[0].tolist(),
                    "R_lo": np.percentile(Rs, 10, axis=0).tolist(), "R_hi": np.percentile(Rs, 90, axis=0).tolist(),
                    "A_lo": np.percentile(As, 10, axis=0).tolist(), "A_hi": np.percentile(As, 90, axis=0).tolist(),
                    "le80": first_below(Rb[0], 80), "le80_range": pct_hours([first_below(r, 80) for r in Rs])}
    out["hyp14_8h"] = tabs
    return out


def annual_nominal(pl: Plan) -> float:
    types = day_types(pl)
    per = {"study": pl.H, "partial": pl.H / 2, "rest": 0.0}
    return sum(per[types[d % CYCLE]] for d in range(DAYS))


def oat_params():
    """열 0 = 기준, 이후 각 모수를 하한/상한으로 바꾼 열. 한 번의 벡터 시뮬레이션으로 계산."""
    cols = [("기준", None, None)]
    for k in SWEEP_KEYS:
        _, lo, hi, _, _ = PARAMS[k]
        cols += [(k, "하한", lo), (k, "상한", hi)]
    P = base_params(len(cols))
    for j, (k, _, v) in enumerate(cols):
        if v is not None:
            P[k][j] = v
    return cols, P


def one_at_a_time():
    """핵심 결론별 일대일 민감도: (a) S2 3개월 R<=80% 시간, (b) 12→14 순효과, (c) 두 번째 질문 틀 최적 H."""
    cols, P = oat_params()
    R, _ = cycle_average(simulate(prompt1_plan("S2"), P), 6)
    le80 = [first_below(r, 80) for r in R]
    a = simulate(prompt1_reallocated(12, "sleep_first"), P, store=False)["total_rhe"]
    b = simulate(prompt1_plan("S2"), P, store=False)["total_rhe"]
    net = b - a
    Hs = [x / 2 for x in range(14, 23)]
    vals = []
    for H in Hs:
        pl = prompt2_plan(H, "base", 1, 0)
        if pl is not None:
            vals.append((H, simulate(pl, P, store=False)["total_rhe"]))
    Hg = np.array([v[0] for v in vals])
    M = np.stack([v[1] for v in vals])
    optH = Hg[np.argmax(M, axis=0)]
    rows = []
    for j, (k, tag, v) in enumerate(cols):
        rows.append({"param": k, "grade": PARAMS[k][3] if k in PARAMS else "", "set": tag, "value": v,
                     "le80_S2_3m": le80[j], "net_12_14": float(net[j]), "opt_H_A": float(optH[j])})
    return {"base": rows[0], "rows": rows[1:]}


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    res = main(n)
    print(json.dumps(res["thresholds"], ensure_ascii=False, indent=1))
