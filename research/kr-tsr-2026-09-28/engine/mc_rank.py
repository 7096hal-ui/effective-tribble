"""Monte Carlo TSR distribution, risk metrics and composite rankings.

Input  : model.json (per-stock scenario sets for 1/3/5-year horizons, forward vol,
         sensitivities, analyst disagreement) produced by the multi-agent pipeline.
Output : results.json plus CSV tables in the output directory.

Model
-----
Each horizon's scenarios (probability p_i, cumulative TSR x_i) form a mixture of
lognormals.  Scenario i contributes ln R ~ N(ln G_i - s^2/2, s^2) with G_i = 1 + x_i,
so E[R | i] = G_i and the mixture mean equals the probability-weighted scenario
TSR exactly.  The common within-scenario sigma s is chosen so the mixture's total
log-return standard deviation matches a forward-looking target

    target = max(fwd_vol, vol_floor) * sqrt(T * VR(T))

where VR is a variance-ratio haircut for long horizons.  Because the between-
scenario variance does not depend on s, s^2 = max(target^2 - between^2,
(MIN_WITHIN * target)^2).

Risk-adjusted metric (forward Sortino):
    (E_ann - rf_T) / DD_ann
    DD_ann = sqrt(mean(min(ln R - T*ln(1+rf_T), 0)^2) / T)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

HORIZONS = (1, 3, 5)
VR = {1: 1.00, 3: 0.85, 5: 0.80}
MIN_WITHIN = 0.35
N_SAMPLES = 200_000
SEED = 20260928

# Forward-vol floors (annual, %) so thin price history cannot manufacture a high Sortino.
VOL_FLOORS = [  # (min market cap in 억원, floor %)
    (500_000, 28.0),   # >= 50조
    (50_000, 32.0),    # >= 5조
    (10_000, 40.0),    # >= 1조
    (0, 48.0),
]
RECENT_IPO_FLOOR_ADD = 5.0

WEIGHTS = {
    "balanced": (0.60, 0.25, 0.15),
    "aggressive": (0.75, 0.15, 0.10),
    "defensive": (0.40, 0.35, 0.25),
}

FACTORS = [
    "fx_usdkrw_up10", "rates_up100bp", "terminal_multiple_down20", "semi_ai_down",
    "auto_tariff_demand", "bio_pos_down25", "dilution_up10", "key_customer_down20",
]


def vol_floor(mcap_eok: float | None, recent_ipo: bool) -> float:
    floor = VOL_FLOORS[-1][1]
    if mcap_eok is not None:
        for cut, f in VOL_FLOORS:
            if mcap_eok >= cut:
                floor = f
                break
    return floor + (RECENT_IPO_FLOOR_ADD if recent_ipo else 0.0)


def normalise(scen: list[dict]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    p = np.array([float(s["p"]) for s in scen])
    x = np.array([float(s["tsr"]) for s in scen]) / 100.0
    notes = []
    if abs(p.sum() - 1.0) > 1e-6:
        notes.append(f"prob sum {p.sum():.4f} renormalised")
        p = p / p.sum()
    if (x <= -1.0).any():
        notes.append("TSR <= -100% clipped to -99%")
        x = np.maximum(x, -0.99)
    return p, x, notes


def within_sigma(p: np.ndarray, g: np.ndarray, target: float) -> float:
    lg = np.log(g)
    between = float(np.sqrt(np.sum(p * (lg - np.sum(p * lg)) ** 2)))
    s2 = max(target ** 2 - between ** 2, (MIN_WITHIN * target) ** 2)
    return math.sqrt(s2)


def sample(p: np.ndarray, g: np.ndarray, s: float, rng: np.random.Generator) -> np.ndarray:
    idx = rng.choice(len(p), size=N_SAMPLES, p=p)
    z = rng.standard_normal(N_SAMPLES)
    return np.exp(np.log(g[idx]) - 0.5 * s * s + s * z)


def dd_ann(logr: np.ndarray, T: int, rf: float, lnk: float = 0.0) -> float:
    d = logr + lnk - T * math.log1p(rf)
    return math.sqrt(float(np.mean(np.minimum(d, 0.0) ** 2)) / T)


def metrics(R: np.ndarray, e_cum: float, T: int, rf: float) -> dict:
    x = R - 1.0
    q10, q50, q90 = np.quantile(x, [0.10, 0.50, 0.90])
    worst = np.sort(x)[: int(0.10 * len(x))]
    e_ann = (1.0 + e_cum) ** (1.0 / T) - 1.0
    dd = dd_ann(np.log(R), T, rf)
    return {
        "e_cum": e_cum,
        "e_ann": e_ann,
        "median": float(q50),
        "p10": float(q10), "p50": float(q50), "p90": float(q90),
        "p_loss": float(np.mean(R < 1.0)),
        "p_loss30": float(np.mean(R < 0.7)),
        "cvar10": float(worst.mean()),
        "dd_ann": dd,
        "sortino": (e_ann - rf) / dd if dd > 0 else float("nan"),
    }


def pct_rank(values: np.ndarray, higher_better: bool = True) -> np.ndarray:
    """0-100 percentile, best = 100, ties averaged."""
    v = np.nan_to_num(values if higher_better else -values, nan=-1e9)
    order = v.argsort().argsort().astype(float)  # 0 = worst
    # average ties
    out = order.copy()
    for val in np.unique(v):
        m = v == val
        out[m] = order[m].mean()
    n = len(v)
    return out / (n - 1) * 100.0 if n > 1 else np.full(n, 100.0)


def rank_desc(score: np.ndarray, tiebreak: np.ndarray | None = None) -> np.ndarray:
    keys = (-score,) if tiebreak is None else (-tiebreak, -score)
    order = np.lexsort(keys)
    r = np.empty(len(score), dtype=int)
    r[order] = np.arange(1, len(score) + 1)
    return r


def composite(e: np.ndarray, so: np.ndarray, cv: np.ndarray, w: tuple) -> np.ndarray:
    return w[0] * pct_rank(e) + w[1] * pct_rank(so) + w[2] * pct_rank(cv)


def risk_rank(so, cv, pl, perm) -> np.ndarray:
    # Sortino (2dp) desc, CVaR desc (less negative), loss prob asc, permanent-loss asc
    so = np.nan_to_num(so, nan=-1e9)
    order = np.lexsort((perm, pl, -cv, -np.round(so, 2)))
    r = np.empty(len(so), dtype=int)
    r[order] = np.arange(1, len(so) + 1)
    return r


def run(model_path: Path, out_dir: Path) -> dict:
    model = json.loads(model_path.read_text())
    rng = np.random.default_rng(SEED)
    rf = {int(k): v / 100.0 for k, v in model["rf"].items()}
    idx_exp = model.get("index_expected", {})
    stocks = [s for s in model["stocks"] if s.get("rankable", True)]
    res = {"meta": {"n_samples": N_SAMPLES, "seed": SEED, "vr": VR, "min_within": MIN_WITHIN,
                    "vol_floors": VOL_FLOORS, "recent_ipo_floor_add": RECENT_IPO_FLOOR_ADD,
                    "weights": WEIGHTS, "rf": model["rf"]},
           "horizons": {}}

    for T in HORIZONS:
        rows, cache = [], []
        for s in stocks:
            h = s["horizons"][str(T)]
            p, x, notes = normalise(h["scenarios"])
            g = 1.0 + x
            fv = max(float(s["fwd_vol"]), vol_floor(s.get("mcap_eok"), s.get("recent_ipo", False)))
            target = fv / 100.0 * math.sqrt(T * VR[T])
            sig = within_sigma(p, g, target)
            R = sample(p, g, sig, rng)
            e_cum = float(np.sum(p * g) - 1.0)
            m = metrics(R, e_cum, T, rf[T])
            bench = idx_exp.get(s.get("market", "KOSPI"), {}).get(str(T))
            if bench is not None:
                b_ann = (1 + bench / 100.0) ** (1.0 / T) - 1.0
                m["excess_cum"] = e_cum - bench / 100.0
                m["excess_ann"] = m["e_ann"] - b_ann
            m.update({"id": s["id"], "name": s["name"], "code": s.get("code"),
                      "within_sigma": sig, "fwd_vol_used": fv, "notes": notes,
                      "perm_loss": float(s.get("perm_loss", 0.0)),
                      "confidence": s.get("confidence", {}).get(str(T), "N/A")})
            rows.append(m)
            logr = np.log(R)
            cache.append({"logr": np.sort(logr)[:: max(1, N_SAMPLES // 20_000)],
                          "e_cum": e_cum, "cvar": m["cvar10"], "sens": s.get("sens", {}),
                          "gap": s.get("disagreement", {}).get(str(T)),
                          "conf": m["confidence"]})

        e = np.array([r["e_cum"] for r in rows])
        so = np.array([r["sortino"] for r in rows])
        cv = np.array([r["cvar10"] for r in rows])
        pl = np.array([r["p_loss"] for r in rows])
        perm = np.array([r["perm_loss"] for r in rows])
        ranks = {"exp": rank_desc(e), "risk": risk_rank(so, cv, pl, perm)}
        for k, w in WEIGHTS.items():
            sc = composite(e, so, cv, w)
            ranks[k] = rank_desc(sc, e)
            for r, v in zip(rows, sc):
                r[f"score_{k}"] = float(v)
        for r, i in zip(rows, range(len(rows))):
            for k, v in ranks.items():
                r[f"rank_{k}"] = int(v[i])

        # --- single-factor sensitivity: shift each stock's expected TSR by its own delta
        sens_out = {}
        for f in FACTORS:
            e2, so2, cv2 = [], [], []
            for c in cache:
                d = (c["sens"].get(f, {}) or {}).get(str(T), 0.0) or 0.0
                k = max((1 + c["e_cum"] + d / 100.0) / (1 + c["e_cum"]), 0.05)
                e2.append(k * (1 + c["e_cum"]) - 1)
                cv2.append(k * (1 + c["cvar"]) - 1)
                ea = (1 + e2[-1]) ** (1.0 / T) - 1
                dd = dd_ann(c["logr"], T, rf[T], math.log(k))
                so2.append((ea - rf[T]) / dd if dd > 0 else float("nan"))
            e2 = np.array(e2)
            r2 = rank_desc(composite(e2, np.array(so2), np.array(cv2), WEIGHTS["balanced"]), e2)
            sens_out[f] = {rows[i]["id"]: int(r2[i]) for i in range(len(rows))}
        # --- model-uncertainty rank stability
        conf_sd = {"높음": 0.06, "보통": 0.12, "낮음": 0.22, "high": 0.06, "medium": 0.12, "low": 0.22}
        draws = 600
        rk = np.zeros((draws, len(rows)), dtype=int)
        srng = np.random.default_rng(SEED + T)
        base_sd = np.array([conf_sd.get(c["conf"], 0.12) * math.sqrt(T) for c in cache])
        gap = np.array([abs(c["gap"]) / 100.0 / 2 if c["gap"] is not None else 0.0 for c in cache])
        sd = np.sqrt(base_sd ** 2 + gap ** 2)
        for dI in range(draws):
            z = srng.standard_normal(len(rows))
            e2, so2, cv2 = [], [], []
            for j, c in enumerate(cache):
                lnk = z[j] * sd[j] / max(1 + c["e_cum"], 0.05)
                lnk = float(np.clip(lnk, -2.0, 2.0))
                k = math.exp(lnk)
                e2.append(k * (1 + c["e_cum"]) - 1)
                cv2.append(k * (1 + c["cvar"]) - 1)
                ea = (1 + e2[-1]) ** (1.0 / T) - 1
                dd = dd_ann(c["logr"], T, rf[T], lnk)
                so2.append((ea - rf[T]) / dd if dd > 0 else float("nan"))
            e2 = np.array(e2)
            rk[dI] = rank_desc(composite(e2, np.array(so2), np.array(cv2), WEIGHTS["balanced"]), e2)
        for j, r in enumerate(rows):
            lo, hi = np.quantile(rk[:, j], [0.10, 0.90])
            r["rank_band80"] = [int(lo), int(hi)]
            moves = [abs(sens_out[f][r["id"]] - r["rank_balanced"]) for f in FACTORS]
            r["max_factor_move"] = int(max(moves))
            r["worst_factor"] = FACTORS[int(np.argmax(moves))]
            r["model_sd_cum"] = float(sd[j])
        res["horizons"][str(T)] = {"rows": rows, "sensitivity_ranks": sens_out}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    for T in HORIZONS:
        rows = sorted(res["horizons"][str(T)]["rows"], key=lambda r: r["rank_balanced"])
        cols = ["rank_balanced", "rank_exp", "rank_risk", "rank_aggressive", "rank_defensive", "id", "name",
                "code", "e_cum", "e_ann", "median", "p10", "p50", "p90", "p_loss", "p_loss30", "sortino",
                "cvar10", "excess_cum", "excess_ann", "fwd_vol_used", "within_sigma", "confidence",
                "rank_band80", "max_factor_move", "worst_factor"]
        with open(out_dir / f"ranking_{T}y.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c) for c in cols])
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out"))
    a = ap.parse_args()
    run(a.model, a.out)
