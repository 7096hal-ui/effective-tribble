#!/usr/bin/env python3
"""26개 종목 1·3·5년 TSR 분포 몬테카를로 및 순위 엔진.

입력
  data/final/params.json : 종목별 최종 시나리오(확률·기말 주당가치·누적 주당배당), 변동성 가정,
                           전문가/일반 분석가 기대 TSR, 베이스레이트 사전분포, 표준 충격 민감도
  (params.json 최상위에 rf·index 포함)
출력
  output/metrics.json, output/rank_{1,3,5}.csv, output/sensitivity.json, output/robustness.json

방법 요약(보고서 부록과 동일)
  1) 시나리오 TSR_s = (기말 주당가치_s + 누적 주당배당_s) / 기준주가 − 1
  2) 베이스레이트 축소: 연환산 기대수익률 A를 사전평균 μ 쪽으로 w = τ²/(τ²+d²+q²) 만큼만 남김.
     d = |A_전문가 − A_일반|/2 (분석가 간 이견), q = 데이터 품질 잡음, τ = 사전분포 폭.
     목표 기대값은 시나리오 값(가치평가)을 바꾸지 않고 확률만 최소 상대엔트로피(지수 틸팅)로 재조정해 맞춘다.
  3) 몬테카를로: 시나리오 추출 → 로그수익률 = ln(1+TSR_s) − σw²/2 + σw·Z (시나리오 내 평균 = TSR_s).
     σw는 연도별 변동성 경로(σ1 → σLR, 3년차부터 장기값)의 누적분산에서 시나리오 간 분산을 뺀 값(하한 있음).
  4) 연환산 하방편차: 기말 로그수익률을 조건으로 한 연간 경로(브라운 브리지)에서 연간 단순수익률이
     무위험수익률에 못 미친 부분의 제곱평균제곱근. Forward Sortino = (기대 연환산 − rf) / 연환산 하방편차.
  5) 백분위 정규화 후 균형형 60/25/15, 공격형 75/15/10, 방어형 40/35/25.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

HORIZONS = (1, 3, 5)
N_PATHS = 200_000
SEED = 20260928
TAU = {1: 0.15, 3: 0.10, 5: 0.08}          # 사전분포 폭(연환산 기대수익률, 소수)
Q1 = {"높음": 0.04, "보통": 0.08, "낮음": 0.12}  # 1년 기준 데이터 품질 잡음; 다른 기간은 τ_h/τ_1 배
WITHIN_FLOOR = 0.35                         # 시나리오 내 표준편차 하한 = 0.35 × 변동성 기반 총 표준편차
MIN_GROSS = 0.01                            # 주당가치 하한: 기준가의 1%(TSR −99%)
WEIGHTS = {
    "balanced": (0.60, 0.25, 0.15),
    "aggressive": (0.75, 0.15, 0.10),
    "defensive": (0.40, 0.35, 0.25),
}
SHOCK_IDS = [
    "FX_KRW_STRONG", "FX_KRW_WEAK", "RATES_UP", "RATES_DOWN", "MULTIPLE_DOWN",
    "SEMI_DOWN", "SEMI_UP", "AUTO_DOWN", "BIO_POS_DOWN", "DILUTION_UP", "KEY_CUSTOMER_DOWN",
]
RF_SHIFT = {"RATES_UP": 0.01, "RATES_DOWN": -0.01}
UNSTABLE_RANK_MOVE = 4                      # 단일 표준 충격에 균형형 순위가 이만큼 이상 움직이면 '순위 불안정'


def ann(e: float, h: int) -> float:
    return (1.0 + e) ** (1.0 / h) - 1.0


def cum(a: float, h: int) -> float:
    return (1.0 + a) ** h - 1.0


def sigma_path(s1: float, slr: float, h: int) -> np.ndarray:
    """연도별 변동성: 1년차 σ1, 2년차 중간값, 3년차 이후 σLR."""
    return np.array([s1 + (slr - s1) * min(t - 1, 2) / 2.0 for t in range(1, h + 1)])


def scen_arrays(scen: list[dict], p0: float) -> tuple[np.ndarray, np.ndarray]:
    p = np.array([float(s["p"]) for s in scen])
    if abs(p.sum() - 1.0) > 1e-6:
        raise ValueError(f"scenario probabilities sum to {p.sum():.6f}")
    tsr = np.array([(float(s["value"]) + float(s.get("div", 0.0))) / p0 - 1.0 for s in scen])
    return p, np.maximum(tsr, MIN_GROSS - 1.0)


def tilt(p: np.ndarray, tsr: np.ndarray, target: float) -> tuple[np.ndarray, float, str | None]:
    """p'_s ∝ p_s·(1+TSR_s)^λ 로 Σp'·TSR = target 을 맞춘다(최소 상대엔트로피)."""
    g = np.log1p(tsr)
    lo, hi = float(tsr.min()), float(tsr.max())
    flag = None
    eps = 0.005 * (hi - lo) if hi > lo else 0.0
    if target <= lo + eps:
        target, flag = lo + eps, "clipped_low"
    elif target >= hi - eps:
        target, flag = hi - eps, "clipped_high"

    def at(lam: float) -> tuple[float, np.ndarray]:
        z = lam * g
        w = p * np.exp(z - z.max())
        w = w / w.sum()
        return float((w * tsr).sum()), w

    a, b = -200.0, 200.0
    for _ in range(300):
        m = 0.5 * (a + b)
        if at(m)[0] < target:
            a = m
        else:
            b = m
    lam = 0.5 * (a + b)
    return at(lam)[1], lam, flag


def shrink(p, tsr, h, conf, spec_e, gen_e, prior_ann, tau_scale=1.0, q_scale=1.0, enabled=True):
    e_raw = float((p * tsr).sum())
    a_raw = ann(e_raw, h)
    tau = TAU[h] * tau_scale
    q = Q1[conf] * (TAU[h] / TAU[1]) * q_scale
    d = abs(ann(spec_e, h) - ann(gen_e, h)) / 2.0 if spec_e is not None and gen_e is not None else 0.0
    w = tau * tau / (tau * tau + d * d + q * q) if enabled else 1.0
    a_t = prior_ann + w * (a_raw - prior_ann)
    e_t = cum(a_t, h)
    p2, lam, flag = tilt(p, tsr, e_t) if enabled else (p.copy(), 0.0, None)
    return p2, {
        "E_raw": e_raw, "A_raw": a_raw, "w": w, "d": d, "q": q, "tau": tau,
        "prior_ann": prior_ann, "A_target": a_t, "E_target": e_t, "lambda": lam, "flag": flag,
        "E_post": float((p2 * tsr).sum()),
    }


def simulate(p, tsr, sig, rf, seed, n=N_PATHS, floor=WITHIN_FLOOR):
    rng = np.random.default_rng(seed)
    h = len(sig)
    s_tot = float((sig ** 2).sum())
    g = np.log1p(tsr)
    gbar = float((p * g).sum())
    vb = float((p * (g - gbar) ** 2).sum())
    sw2 = max(s_tot - vb, floor * floor * s_tot)
    sw = math.sqrt(sw2)
    idx = rng.choice(len(p), size=n, p=p / p.sum())
    z = rng.standard_normal(n)
    logret = g[idx] - 0.5 * sw2 + sw * z
    r = np.expm1(logret)
    if h == 1:
        yearly = r[:, None]
    else:
        e = rng.standard_normal((n, h)) * sig[None, :]
        x = e + (sig ** 2 / s_tot)[None, :] * (logret - e.sum(axis=1))[:, None]
        yearly = np.expm1(x)
    down = np.minimum(yearly - rf, 0.0)
    dd = math.sqrt(float((down ** 2).mean()))
    return r, dd, {"S": s_tot, "Vb": vb, "sw": sw}


def metrics(r, dd, e, h, rf, idx_ann):
    a = ann(e, h)
    p10, p50, p90 = np.percentile(r, [10, 50, 90])
    return {
        "E": e, "A": a, "median": float(p50), "p10": float(p10), "p50": float(p50), "p90": float(p90),
        "p_loss": float((r < 0).mean()), "p_loss30": float((r <= -0.30).mean()),
        "p_loss50": float((r <= -0.50).mean()), "cvar10": float(r[r <= p10].mean()),
        "dd": dd, "sortino": (a - rf) / dd if dd > 0 else float("nan"),
        "excess": a - idx_ann, "mc_mean": float(r.mean()),
    }


def pct_rank(x, higher_better=True):
    x = np.asarray(x, float)
    r = rankdata(x if higher_better else -x, method="average")
    return 100.0 * (r - 1.0) / (len(x) - 1.0)


def rank_horizon(rows: list[dict], perm_loss: dict[str, float]) -> None:
    """rows: 같은 기간의 투자가능 종목 지표(dict). 순위·백분위·종합점수를 제자리에 기록한다."""
    a = [r["A"] for r in rows]
    s = [r["sortino"] for r in rows]
    c = [r["cvar10"] for r in rows]
    pa, ps, pc = pct_rank(a), pct_rank(s), pct_rank(c)
    for i, r in enumerate(rows):
        r["pct_A"], r["pct_S"], r["pct_C"] = float(pa[i]), float(ps[i]), float(pc[i])
        for k, (wa, ws, wc) in WEIGHTS.items():
            r[f"score_{k}"] = wa * pa[i] + ws * ps[i] + wc * pc[i]
    order = sorted(range(len(rows)), key=lambda i: (-rows[i]["A"], -rows[i]["sortino"]))
    for k, i in enumerate(order):
        rows[i]["rank_E"] = k + 1
    order = sorted(range(len(rows)), key=lambda i: (
        -round(rows[i]["sortino"], 2), -rows[i]["cvar10"], rows[i]["p_loss"], perm_loss[rows[i]["code"]]))
    for k, i in enumerate(order):
        rows[i]["rank_R"] = k + 1
    for key in WEIGHTS:
        order = sorted(range(len(rows)), key=lambda i: (-round(rows[i][f"score_{key}"], 6), -rows[i]["A"]))
        for k, i in enumerate(order):
            rows[i][f"rank_{key}"] = k + 1


def validate(params: dict) -> list[str]:
    issues = []
    for st in params["stocks"]:
        if not st.get("investable", True):
            continue
        tag = f'{st["name"]}({st["code"]})'
        if not (0.05 <= st["sigma1"] <= 1.5 and 0.05 <= st["sigma_lr"] <= 1.5):
            issues.append(f"{tag}: sigma out of range {st['sigma1']}/{st['sigma_lr']}")
        for h in HORIZONS:
            hs = st["h"][str(h)]
            p = sum(s["p"] for s in hs["scen"])
            if abs(p - 1) > 1e-6:
                issues.append(f"{tag} {h}y: prob sum {p:.4f}")
            vals = [(s["value"] + s.get("div", 0)) for s in hs["scen"]]
            if any(v <= 0 for v in vals):
                issues.append(f"{tag} {h}y: non-positive scenario value")
            if hs["conf"] not in Q1:
                issues.append(f"{tag} {h}y: bad confidence {hs['conf']}")
            if hs.get("prior_ann") is None:
                issues.append(f"{tag} {h}y: missing prior")
    return issues


def run(params: dict, *, tau_scale=1.0, q_scale=1.0, floor=WITHIN_FLOOR, sig_scale=1.0,
        shrink_on=True, shocks: dict | None = None, rf_shift=0.0, n=N_PATHS) -> dict:
    """전체 파이프라인 1회 실행. shocks={code: {h: Δ누적TSR}} 이면 기대값을 곱셈 이동한다."""
    rf = {h: params["rf"][str(h)] + rf_shift for h in HORIZONS}
    out = {h: [] for h in HORIZONS}
    detail = {}
    for st in params["stocks"]:
        if not st.get("investable", True):
            continue
        code = st["code"]
        idx_cum = params["index"][st["market"]]
        detail[code] = {}
        for h in HORIZONS:
            hs = st["h"][str(h)]
            p, tsr = scen_arrays(hs["scen"], st["p0"])
            p2, info = shrink(p, tsr, h, hs["conf"], hs.get("spec_E"), hs.get("gen_E"), hs["prior_ann"],
                              tau_scale, q_scale, shrink_on)
            e = info["E_post"]
            if shocks is not None:
                delta = shocks.get(code, {}).get(h, 0.0)
                e_new = max(e + delta, -0.95)
                tsr = np.maximum((1 + tsr) * (1 + e_new) / (1 + e) - 1, MIN_GROSS - 1)
                e = float((p2 * tsr).sum())
            sig = sigma_path(st["sigma1"], st["sigma_lr"], h) * sig_scale
            seed = SEED + st["no"] * 10 + h
            r, dd, sim = simulate(p2, tsr, sig, rf[h], seed, n=n, floor=floor)
            m = metrics(r, dd, e, h, rf[h], ann(idx_cum[str(h)], h))
            m.update({"no": st["no"], "name": st["name"], "code": code, "market": st["market"],
                      "group": st.get("group", ""), "conf": hs["conf"], "p0": st["p0"]})
            out[h].append(m)
            detail[code][h] = {"shrink": info, "sim": sim, "p_post": p2.tolist(), "tsr": tsr.tolist(),
                               "p_raw": p.tolist(), "labels": [s["label"] for s in hs["scen"]]}
    perm = {r["code"]: r["p_loss50"] for r in out[5]}
    for h in HORIZONS:
        rank_horizon(out[h], perm)
    return {"rows": out, "detail": detail, "rf": rf}


def rank_map(res: dict, key="rank_balanced") -> dict:
    return {h: {r["code"]: r[key] for r in res["rows"][h]} for h in HORIZONS}


def sensitivity(params: dict, base: dict, n: int) -> dict:
    base_rank = rank_map(base)
    table = {}
    for sid in SHOCK_IDS:
        shocks = {st["code"]: {h: float(st["sens"].get(sid, [0, 0, 0])[i]) for i, h in enumerate(HORIZONS)}
                  for st in params["stocks"] if st.get("investable", True)}
        res = run(params, shocks=shocks, rf_shift=RF_SHIFT.get(sid, 0.0), n=n)
        rm = rank_map(res)
        table[sid] = {h: {c: rm[h][c] - base_rank[h][c] for c in rm[h]} for h in HORIZONS}
    return table


def robustness(params: dict, base: dict, n: int) -> dict:
    variants = {
        "축소 약하게(τ×1.5)": dict(tau_scale=1.5), "축소 강하게(τ×0.67)": dict(tau_scale=2 / 3),
        "축소 없음": dict(shrink_on=False), "품질잡음 q×0.5": dict(q_scale=0.5), "품질잡음 q×1.5": dict(q_scale=1.5),
        "변동성 ×0.8": dict(sig_scale=0.8), "변동성 ×1.2": dict(sig_scale=1.2),
        "시나리오 내 분산 하한 0.2": dict(floor=0.2), "시나리오 내 분산 하한 0.5": dict(floor=0.5),
    }
    base_rank = rank_map(base)
    out = {}
    for name, kw in variants.items():
        res = run(params, n=n, **kw)
        rm = rank_map(res)
        out[name] = {h: {c: rm[h][c] - base_rank[h][c] for c in rm[h]} for h in HORIZONS}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=str(Path(__file__).resolve().parents[1] / "data/final/params.json"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "output"))
    ap.add_argument("--n", type=int, default=N_PATHS)
    ap.add_argument("--sens-n", type=int, default=100_000)
    ap.add_argument("--skip-sens", action="store_true")
    args = ap.parse_args()

    params = json.loads(Path(args.params).read_text())
    issues = validate(params)
    for msg in issues:
        print("VALIDATION:", msg)
    if any("prob sum" in m or "non-positive" in m for m in issues):
        raise SystemExit("fix params first")

    base = run(params, n=args.n)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "metrics.json").write_text(json.dumps(
        {"rf": base["rf"], "rows": {str(h): base["rows"][h] for h in HORIZONS},
         "detail": {c: {str(h): v for h, v in d.items()} for c, d in base["detail"].items()}},
        ensure_ascii=False, indent=1, default=float))
    for h in HORIZONS:
        rows = sorted(base["rows"][h], key=lambda r: r["rank_balanced"])
        cols = ["rank_balanced", "rank_E", "rank_R", "rank_aggressive", "rank_defensive", "name", "code", "p0",
                "E", "A", "median", "p10", "p50", "p90", "p_loss", "p_loss30", "p_loss50", "sortino", "dd",
                "cvar10", "excess", "conf", "score_balanced", "mc_mean"]
        lines = [",".join(cols)] + [",".join(str(r[c]) for c in cols) for r in rows]
        (outdir / f"rank_{h}.csv").write_text("\n".join(lines) + "\n")
    if not args.skip_sens:
        (outdir / "sensitivity.json").write_text(json.dumps(
            {sid: {str(h): v for h, v in d.items()} for sid, d in sensitivity(params, base, args.sens_n).items()},
            ensure_ascii=False, indent=1))
        (outdir / "robustness.json").write_text(json.dumps(
            {k: {str(h): v for h, v in d.items()} for k, d in robustness(params, base, args.sens_n).items()},
            ensure_ascii=False, indent=1))
    for h in HORIZONS:
        print(f"\n== {h}y (balanced order)")
        for r in sorted(base["rows"][h], key=lambda r: r["rank_balanced"]):
            print(f'{r["rank_balanced"]:>2} E{r["rank_E"]:>2} R{r["rank_R"]:>2} {r["name"]:<10} '
                  f'E={r["E"]*100:6.1f}% A={r["A"]*100:5.1f}% med={r["median"]*100:6.1f}% '
                  f'P(L)={r["p_loss"]*100:4.1f}% S={r["sortino"]:.2f} CVaR={r["cvar10"]*100:6.1f}% '
                  f'mc={r["mc_mean"]*100:6.1f}%')


if __name__ == "__main__":
    main()
