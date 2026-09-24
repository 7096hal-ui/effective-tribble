"""본문에 인용한 반사실 계산(기준 모수 1조합)을 다시 만드는 스크립트.

- 첫 번째 질문 S1~S3의 3개월 시점 첫 시간 A를 수면 경로(kappa_s, kappa_c)와
  다일 누적 부하(beta)를 하나씩 끄고 다시 계산해, 첫 시간 결손을 나눠 본다.
- 수면을 8시간으로 지킨 14시간 가상안(2부 4-3절)의 첫 시간 A.
- 두 번째 질문 A(11h)·B90(9.5h)에서 휴식·여가 회복 경로를 모두 끈 B/A 비율.
- 10시간 계획에서 여가 회복(r_l)을 끈 연간 총량.

실행: python3 model/counterfactuals.py  →  model/outputs/counterfactuals.json, counterfactuals.md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import study_model as m

OUT = Path(__file__).resolve().parent / "outputs"


def run(plan, **override):
    P = m.base_params(1)
    for k, v in override.items():
        P[k] = np.full(1, float(v))
    return m.simulate(plan, P)


def first_hour_A(plan, tp="3개월", **override):
    sim = run(plan, **override)
    _, A = m.cycle_average(sim, m.TIMEPOINTS[tp], 14)
    return float(A[0, 0])


def total(plan, **override):
    return float(run(plan, **override)["total_rhe"][0])


def main():
    res = {"decomposition_3m": {}}
    for s in ("S1", "S2", "S3"):
        pl = m.prompt1_plan(s)
        base = first_hour_A(pl)
        no_load = first_hour_A(pl, beta=0)
        no_sleep = first_hour_A(pl, kappa_s=0, kappa_c=0)
        res["decomposition_3m"][s] = {"A1": base, "A1_beta0": no_load, "A1_no_sleep_path": no_sleep,
                                      "load_points": no_load - base, "sleep_points": no_sleep - base}

    se, _ = m.life2_cfg("base")
    hyp = m.Plan("14h-8h수면(가상)", 14, tib=8.6, sleep_eff=se, wake=6.5,
                 morning=0.2, lunch=0.4, dinner=0.4, evening=0.4)
    res["hyp14_8h_first_hour_A"] = {tp: first_hour_A(hyp, tp) for tp in ("1-2주", "3개월", "6개월", "12개월")}

    A = m.prompt2_plan(11, "base", 1, 0)
    B = m.prompt2_plan(9.5, "base", 2, 0)
    off = dict(r_l=0, r_rest=0, rest_sleep_extra=0)
    a, b = total(A), total(B)
    a0, b0 = total(A, **off), total(B, **off)
    res["B90_over_A11"] = {"base": b / a, "recovery_off": b0 / a0,
                           "nominal_ratio": m.annual_nominal(B) / m.annual_nominal(A)}

    P10 = m.prompt2_plan(10, "base", 1, 0)
    t10, t10_0 = total(P10), total(P10, r_l=0)
    res["plan10_leisure_recovery_off"] = {"base": t10, "r_l0": t10_0, "ratio": t10_0 / t10}

    OUT.mkdir(exist_ok=True)
    (OUT / "counterfactuals.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))

    d = res["decomposition_3m"]
    lines = ["# 반사실 계산(기준 모수 1조합)", "",
             "## 첫 번째 질문: 3개월 시점 첫 시간 A의 분해", "",
             "| 시나리오 | 첫 시간 A | 다일 부하(β=0) 끄면 | 수면 경로(κ_s=κ_c=0) 끄면 | 부하 몫(점) | 수면 몫(점) |",
             "|---|---|---|---|---|---|"]
    for s, v in d.items():
        lines.append(f"| {s} | {v['A1']:.1f} | {v['A1_beta0']:.1f} | {v['A1_no_sleep_path']:.1f} | "
                     f"{v['load_points']:.1f} | {v['sleep_points']:.1f} |")
    lines += ["", "## 수면을 지킨 14시간 가상안의 첫 시간 A", "",
              "| 시점 | 첫 시간 A |", "|---|---|"]
    lines += [f"| {tp} | {v:.1f} |" for tp, v in res["hyp14_8h_first_hour_A"].items()]
    r = res["B90_over_A11"]
    p = res["plan10_leisure_recovery_off"]
    lines += ["", "## 두 번째 질문", "",
              f"- B90(9.5h) / A(11h) 연간 총량: 기준 {r['base']:.3f}, 휴식·여가 회복 경로를 모두 끄면 {r['recovery_off']:.3f}, "
              f"연간 명목 공부시간 비율 {r['nominal_ratio']:.3f}",
              f"- 10시간 계획의 연간 총량: 기준 {p['base']:.0f}, 여가 회복(r_l)을 끄면 {p['r_l0']:.0f} (비율 {p['ratio']:.4f})", ""]
    (OUT / "counterfactuals.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
