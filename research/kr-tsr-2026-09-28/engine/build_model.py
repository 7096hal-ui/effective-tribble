"""Assemble engine input (model.json) from agent outputs.

Reads   : work/macro.json, work/dossiers/<name>.json, work/analysis/<name>.json,
          optional work/final/<name>.json (post cross-examination overrides),
          work/universe.json (id, name, code, market, P0, P0_date, rankable, ...).
Writes  : model.json and a list of consistency corrections.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

ASOF = date(2026, 9, 28)
FACTORS = [
    "fx_usdkrw_up10", "rates_up100bp", "terminal_multiple_down20", "semi_ai_down",
    "auto_tariff_demand", "bio_pos_down25", "dilution_up10", "key_customer_down20",
]


def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def recent_ipo(listing_date: str | None) -> bool:
    if not listing_date:
        return False
    try:
        y, m, d = (int(x) for x in listing_date[:10].split("-"))
        return (ASOF - date(y, m, d)).days < 730
    except Exception:
        return False


def check_scenarios(name: str, T: str, scen: list[dict], P0: float, log: list[str]) -> list[dict]:
    out = []
    for sc in scen:
        tsr = float(sc["tsr_cum_pct"])
        end, div = sc.get("end_price_krw"), sc.get("cum_dividends_krw", 0) or 0
        if end is not None and P0:
            implied = ((float(end) + float(div)) / P0 - 1) * 100
            if abs(implied - tsr) > 1.0:
                log.append(f"{name} {T}y {sc['name']}: tsr {tsr:.1f}% -> {implied:.1f}% (from end price/dividends)")
                tsr = implied
        out.append({"name": sc["name"], "p": float(sc["prob"]), "tsr": tsr})
    s = sum(x["p"] for x in out)
    if abs(s - 1) > 1e-6:
        log.append(f"{name} {T}y: prob sum {s:.4f} renormalised")
        for x in out:
            x["p"] /= s
    return out


def main(work: Path, out: Path) -> None:
    macro = load(work / "macro.json")
    uni = load(work / "universe.json")
    scen = macro["scen"]
    rf = {"1": scen["risk_free"]["h1_pct"], "3": scen["risk_free"]["h3_pct"], "5": scen["risk_free"]["h5_pct"]}
    ei = scen["expected_index_tsr"]
    index_expected = {
        "KOSPI": {"1": ei["kospi_1y"], "3": ei["kospi_3y_cum"], "5": ei["kospi_5y_cum"]},
        "KOSDAQ": {"1": ei["kosdaq_1y"], "3": ei["kosdaq_3y_cum"], "5": ei["kosdaq_5y_cum"]},
    }
    log: list[str] = []
    stocks = []
    for u in uni:
        if not u.get("rankable", True):
            continue
        name = u["name"]
        dos = load(work / "dossiers" / f"{name}.json") or {}
        ana = load(work / "analysis" / f"{name}.json")
        fin_override = load(work / "final" / f"{name}.json")
        if ana is None or "fin" not in ana:
            log.append(f"{name}: no analysis output — excluded")
            continue
        fin = ana["fin"]
        hz_src = fin_override["horizons"] if fin_override else fin["horizons"]
        horizons = {}
        for T, key in (("1", "y1"), ("3", "y3"), ("5", "y5")):
            horizons[T] = {"scenarios": check_scenarios(name, T, hz_src[key]["scenarios"], u["P0"], log)}
        sens = {f: {"1": fin["sensitivities"][f]["y1"], "3": fin["sensitivities"][f]["y3"],
                    "5": fin["sensitivities"][f]["y5"]} for f in FACTORS}
        if fin_override and fin_override.get("sensitivities"):
            for f, v in fin_override["sensitivities"].items():
                sens[f] = {"1": v["y1"], "3": v["y3"], "5": v["y5"]}
        dis = fin["disagreement"]
        gap = {T: abs(dis["specialist_expected"][k] - dis["generalist_expected"][k])
               for T, k in (("1", "y1"), ("3", "y3"), ("5", "y5"))}
        conf_src = fin_override["horizons"] if fin_override else fin["horizons"]
        stocks.append({
            "id": u["id"], "name": name, "code": u["code"], "market": u["market"],
            "price": u["P0"], "price_date": u["P0_date"], "group": u.get("group"),
            "mcap_eok": u.get("mcap_eok"), "recent_ipo": recent_ipo((dos.get("data") or {}).get("listing_date")),
            "fwd_vol": (fin_override or {}).get("forward_vol_annual_pct", fin["forward_vol_annual_pct"]),
            "horizons": horizons, "sens": sens, "disagreement": gap,
            "confidence": {T: conf_src[k].get("confidence", "보통") for T, k in (("1", "y1"), ("3", "y3"), ("5", "y5"))},
            "perm_loss": (fin_override or fin)["tail"]["prob_permanent_loss_50pct_5y"],
        })
    model = {"asof": "2026-09-28 19:40 KST", "rf": rf, "index_expected": index_expected, "stocks": stocks}
    out.write_text(json.dumps(model, ensure_ascii=False, indent=1))
    (out.parent / (out.stem + "_corrections.txt")).write_text("\n".join(log))
    print(f"{len(stocks)} stocks, {len(log)} corrections")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("--out", type=Path, default=Path("model.json"))
    a = ap.parse_args()
    main(a.work, a.out)
