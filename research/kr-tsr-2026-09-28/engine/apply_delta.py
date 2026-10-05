"""Rebase the 2026-09-28 snapshot to the latest close found by the delta-update workflow.

- universe.json : P0/P0_date -> latest verified close; previous values kept in P0_0928/P0_0928_date
- dossiers_lite : adds a "delta" block (price change, news since 9/28, thesis impact)
- macro_brief   : adds a "delta" block; index scenario TSRs are rebased with the scenario
                  end levels held fixed, i.e. (1 + TSR_0928) * L_0928 / L_new - 1;
                  risk-free rates switch to the latest KTB yields where available
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(work: Path, delta_path: Path) -> None:
    delta = json.loads(delta_path.read_text())
    mk, stocks = delta["market"], {s["name"]: s for s in delta["stocks"]}
    uni = json.loads((work / "universe.json").read_text())
    log = []
    for u in uni:
        d = stocks.get(u["name"])
        u.setdefault("P0_0928", u["P0"])
        u.setdefault("P0_0928_date", u["P0_date"])
        if d and d.get("also_found_0928_close") and u["P0_0928_date"] != "2026-09-28":
            u["P0_0928"], u["P0_0928_date"] = d["also_found_0928_close"], "2026-09-28"
        if d and d.get("close_krw") and d.get("close_date") and d["close_date"][:10] >= u["P0_date"]:
            u["P0"], u["P0_date"] = d["close_krw"], d["close_date"][:10]
            u["P0_cross_checked"] = d.get("cross_checked", False)
        else:
            log.append(f"{u['name']}: no newer close found; keeping {u['P0']} ({u['P0_date']})")
        u["recheck"] = False
        lite = work / "dossiers_lite" / f"{u['name']}.json"
        if lite.exists() and d:
            dos = json.loads(lite.read_text())
            dos["delta"] = {
                "snapshot_price": [u["P0_0928"], u["P0_0928_date"]],
                "latest_price": [u["P0"], u["P0_date"]],
                "change_pct": round((u["P0"] / u["P0_0928"] - 1) * 100, 2) if u["P0_0928"] else None,
                "news_since_0928": d.get("news", []),
                "thesis_impact": d.get("thesis_impact"),
            }
            lite.write_text(json.dumps(dos, ensure_ascii=False, indent=0))
    (work / "universe.json").write_text(json.dumps(uni, ensure_ascii=False, indent=1))

    brief = json.loads((work / "macro_brief.json").read_text())
    k0, q0 = brief["key_facts_0928"]["kospi"]["close"], brief["key_facts_0928"]["kosdaq"]["close"]
    k1, q1 = mk["kospi"]["close"] or k0, mk["kosdaq"]["close"] or q0
    rk, rq = k0 / k1, q0 / q1

    def rebase(x, r):
        return round(((1 + x / 100) * r - 1) * 100, 1)

    for sc in brief["scenarios"]:
        it = sc["index_tsr"]
        sc["index_tsr_from_latest"] = {k: rebase(v, rk if k.startswith("kospi") else rq) for k, v in it.items()}
    e = brief["expected_index_tsr_from_0928"]
    brief["expected_index_tsr"] = {k: rebase(v, rk if k.startswith("kospi") else rq) for k, v in e.items()}
    rf = dict(brief["risk_free"])
    kt = mk.get("ktb", {})
    if kt.get("y3"):
        rf["h3_pct"] = kt["y3"]
    if kt.get("y5"):
        rf["h5_pct"] = kt["y5"]
    if kt.get("y1"):
        rf["h1_pct"] = kt["y1"]
    else:
        # keep the 9/28 interpolation logic: shift the 1y estimate by the 3y move
        if kt.get("y3"):
            rf["h1_pct"] = round(brief["risk_free"]["h1_pct"] + (kt["y3"] - brief["risk_free"]["h3_pct"]), 3)
    rf["basis"] = (f"{kt.get('date')} 국고채 금리(3년 {kt.get('y3')}%, 5년 {kt.get('y5')}%, 1년 {kt.get('y1')}). "
                   "1년물이 확인되지 않으면 9/28 보간 추정치에 3년물 변동폭을 더해 추정. 9/28 기준: " + brief["risk_free"]["basis"][:300])
    brief["risk_free_0928"] = brief["risk_free"]
    brief["risk_free"] = rf
    brief["delta"] = {
        "latest_trading_day": mk["latest_trading_day"], "calendar": mk["calendar"],
        "kospi": mk["kospi"], "kosdaq": mk["kosdaq"], "usdkrw": mk["usdkrw"], "ktb": kt, "ust10y": mk["ust10y"],
        "kospi_change_since_0928_pct": round((k1 / k0 - 1) * 100, 2),
        "kosdaq_change_since_0928_pct": round((q1 / q0 - 1) * 100, 2),
        "events": mk["events"], "material_change_vs_0928": mk["material_change_vs_0928"],
        "rebasing_rule": "지수 시나리오의 기말 수준은 9/28 분석값으로 고정하고 새 기준 수준 대비 TSR로 환산했다.",
    }
    (work / "macro_brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=1))
    print("\n".join(log) or "all prices refreshed")
    print("KOSPI", k0, "->", k1, "KOSDAQ", q0, "->", q1, "expected index TSR", brief["expected_index_tsr"], "rf", {k: rf[k] for k in ("h1_pct", "h3_pct", "h5_pct")})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("delta", type=Path)
    a = ap.parse_args()
    main(a.work, a.delta)
