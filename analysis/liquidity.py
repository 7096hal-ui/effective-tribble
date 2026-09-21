# -*- coding: utf-8 -*-
"""
유동성 처리 — 기대수익률이 아니라 위험(왼쪽 꼬리)에 반영한다.

근거: 본 리서치의 TSR 정의는 '세전·수수료 차감 전'이다. 따라서 호가 스프레드와
시장충격 같은 거래비용을 기대 TSR에서 차감하면 정의를 위반한다.
낮은 유동성이 실제로 바꾸는 것은 '하락 국면에서 빠져나올 수 있는가'이며,
이는 하방편차·CVaR·영구자본손실 확률에 나타나야 한다.

등급은 일평균 거래대금(ADTV) 기준.
"""

TIERS = [
    # (등급, 하한 ADTV(원), 라벨, sigma 배수, p_wipe 가산)
    (1, 1_000_00000000, "매우높음(1,000억+)", 1.00, 0.000),
    (2,   100_00000000, "높음(100~1,000억)",  1.02, 0.000),
    (3,    20_00000000, "보통(20~100억)",     1.06, 0.002),
    (4,     5_00000000, "낮음(5~20억)",       1.12, 0.006),
    (5,             0,  "매우낮음(5억 미만)",  1.20, 0.012),
]


def tier_of(adtv_won):
    """일평균 거래대금(원) -> (등급, 라벨, sigma배수, p_wipe가산). None이면 보수적으로 3등급."""
    if adtv_won is None:
        return (3, "확인불가(보통 가정)", 1.06, 0.002)
    for t, lo, label, smul, pw in TIERS:
        if adtv_won >= lo:
            return (t, label, smul, pw)
    return TIERS[-1][0], TIERS[-1][2], TIERS[-1][3], TIERS[-1][4]


def apply(S, adtv_map, cap_sigma={"1Y": 0.40, "3Y": 0.50, "5Y": 0.58}):
    """시나리오 딕셔너리 S에 유동성 위험을 반영한다. 기말 주당가치는 건드리지 않는다."""
    out = {}
    for name, per_h in S.items():
        _, _, smul, pw_add = tier_of(adtv_map.get(name))
        out[name] = {}
        for h, (sce, sig, pw) in per_h.items():
            out[name][h] = (sce, min(round(sig * smul, 3), cap_sigma[h]), round(pw + pw_add, 4))
    return out
