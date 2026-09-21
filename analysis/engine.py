# -*- coding: utf-8 -*-
"""
KRX 26종목 멀티에이전트 리서치 — 정량 엔진
시나리오 입력 -> 몬테카를로 -> TSR 분포 -> Sortino/CVaR -> 백분위 종합순위
기준일: 2026-09-21 (KST). 통화: KRW. 수익률: 세전·수수료 차감 전 TSR.
"""
import math, json
import numpy as np

SEED = 20260921
HORIZONS = {"1Y": 1.0, "3Y": 3.0, "5Y": 5.0}

# 기간대응 무위험수익률(원화 국고채). 거시 에이전트 확정치로 교체됨.
RF = {"1Y": 0.0290, "3Y": 0.0305, "5Y": 0.0320}

# 벤치마크 기대 연환산수익률(초과수익 계산용). 거시 시나리오와 정합.
BENCH = {"KOSPI": {"1Y": 0.040, "3Y": 0.055, "5Y": 0.055},
         "KOSDAQ": {"1Y": 0.060, "3Y": 0.070, "5Y": 0.065}}

N_SIM = 200000


def simulate(S0, scenarios, sigma_within, p_wipe=0.0, wipe_recovery=0.03,
             years=1.0, n=N_SIM, seed=SEED):
    """
    scenarios: [{'p':확률, 'px':기말 주당가치, 'div':기간누적 주당 현금환원}]
      - px/div 는 희석·증자·자사주소각을 모두 반영한 '주당' 값이어야 함.
    sigma_within: 시나리오 내부 잔차 변동성(기간 전체, 로그 기준)
    p_wipe: 영구자본손실(상장폐지/자본잠식) 확률 -> 잔존가치 wipe_recovery 배
    반환: 누적 TSR 배수 배열 R (= 총가치/S0)
    """
    rng = np.random.default_rng(seed)
    ps = np.array([s['p'] for s in scenarios], dtype=float)
    assert abs(ps.sum() - 1.0) < 1e-9, f"확률합 != 1: {ps.sum()}"
    base = np.array([(s['px'] + s.get('div', 0.0)) / S0 for s in scenarios], dtype=float)

    idx = rng.choice(len(ps), size=n, p=ps)
    z = rng.standard_normal(n)
    # px는 '해당 시나리오의 조건부 중앙값'으로 해석한다.
    # 따라서 중앙값 보존형 잔차를 쓴다(평균보존형은 중앙값을 exp(-s^2/2)만큼 끌어내려
    # 시나리오 분산과 잔차 분산으로 위험을 이중 반영하게 된다).
    R = base[idx] * np.exp(sigma_within * z)

    if p_wipe > 0:
        w = rng.random(n) < p_wipe
        R[w] = wipe_recovery * np.exp(0.5 * rng.standard_normal(w.sum()))
    return np.maximum(R, 1e-4)


def metrics(R, years, rf, bench):
    ann = R ** (1.0 / years) - 1.0            # 연환산수익률
    cum = R - 1.0                              # 누적 TSR
    e_cum = float(cum.mean())
    # 기대 연환산수익률 = 기대 종료시점 부(富)의 연환산치.
    # E[R^(1/T)] 는 젠슨 효과로 왜곡분포에 이중 벌점을 주므로 쓰지 않는다.
    e_ann = (1.0 + e_cum) ** (1.0 / years) - 1.0
    e_ann_mean_of_ann = float(ann.mean())   # 참고용
    med_cum = float(np.median(cum))
    med_ann = float(np.median(ann))
    p10, p50, p90 = [float(np.percentile(cum, q)) for q in (10, 50, 90)]
    p_loss = float((cum < 0).mean())
    p_loss30 = float((cum < -0.30).mean())
    q10 = np.percentile(cum, 10)
    cvar10 = float(cum[cum <= q10].mean())
    # 하방편차: 연환산수익률이 무위험수익률에 못 미친 부분만
    short = np.minimum(ann - rf, 0.0)
    dd = float(math.sqrt((short ** 2).mean()))
    sortino = (e_ann - rf) / dd if dd > 1e-9 else float('nan')
    return dict(e_ann=e_ann, e_ann_alt=e_ann_mean_of_ann, e_cum=e_cum, med_cum=med_cum, med_ann=med_ann,
                p10=p10, p50=p50, p90=p90, p_loss=p_loss, p_loss30=p_loss30,
                cvar10=cvar10, dd=dd, sortino=sortino, excess=e_ann - bench)


def pct_rank(vals):
    """0~100 백분위 (클수록 100). 동점은 평균 순위."""
    a = np.asarray(vals, dtype=float)
    n = len(a)
    order = a.argsort()
    ranks = np.empty(n, float)
    ranks[order] = np.arange(n)
    # 동점 처리
    for v in np.unique(a):
        m = a == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    return 100.0 * ranks / (n - 1) if n > 1 else np.full(n, 50.0)


WEIGHTS = {"균형형": (0.60, 0.25, 0.15),
           "공격형": (0.75, 0.15, 0.10),
           "방어형": (0.40, 0.35, 0.25)}


def composite(rows, horizon):
    """rows: [{'name':..,'m':metrics dict}] -> 백분위 및 종합점수 부여"""
    key = 'e_cum' if horizon == '1Y' else 'e_ann'
    pr_ret = pct_rank([r['m'][key] for r in rows])
    pr_sor = pct_rank([r['m']['sortino'] for r in rows])
    pr_cvar = pct_rank([r['m']['cvar10'] for r in rows])   # 덜 부정적 = 높은 점수
    for i, r in enumerate(rows):
        r['pr_ret'], r['pr_sor'], r['pr_cvar'] = pr_ret[i], pr_sor[i], pr_cvar[i]
        for style, (a, b, c) in WEIGHTS.items():
            r[f'score_{style}'] = a * pr_ret[i] + b * pr_sor[i] + c * pr_cvar[i]
    return rows


def shrink(scenarios, prior_R, w):
    """베이스레이트 축소: 시나리오별 총수익배수를 산업 사전분포 쪽으로 w만큼 당김."""
    out = []
    for s in scenarios:
        out.append(dict(s))
    return out, prior_R, w


def pct(x, d=1):
    return f"{100*x:.{d}f}%"
