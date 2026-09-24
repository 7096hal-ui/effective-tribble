"""outputs/results.json -> outputs/tables.md (보고서에 붙이는 마크다운 표).

시간별 백분율은 근거 수준에 맞춰 5% 단위로 반올림한다. 범위는 가정 스윕의 10~90 백분위(신뢰구간 아님).
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def r5(x):
    return int(5 * round(float(x) / 5))


def rng(lo, hi):
    a, b = r5(lo), r5(hi)
    return f"{a}" if a == b else f"{a}~{b}"


def cell(v, lo, hi):
    return f"{r5(v)} ({rng(lo, hi)})"


def hourly_main(res, lab="S2"):
    H = res["hourly"][lab]
    rows = ["| 몇 번째 시간 | 초기 1~2주 R | 1개월 R | 3개월 R | 6개월 R | 12개월 R | 12개월 A |",
            "|---|---|---|---|---|---|---|"]
    for h in range(14):
        cells = []
        for tp in ("1-2주", "1개월", "3개월", "6개월", "12개월"):
            d = H[tp]
            cells.append("100" if h == 0 else cell(d["R"][h], d["R_lo"][h], d["R_hi"][h]))
        d = H["12개월"]
        cells.append(cell(d["A"][h], d["A_lo"][h], d["A_hi"][h]))
        rows.append(f"| {h+1} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def hourly_scen(res):
    rows = ["| 몇 번째 시간 | S1 3개월 R | S2 3개월 R | S3 3개월 R | S1 12개월 A | S2 12개월 A | S3 12개월 A |",
            "|---|---|---|---|---|---|---|"]
    for h in range(14):
        cells = []
        for lab in ("S1", "S2", "S3"):
            d = res["hourly"][lab]["3개월"]
            cells.append("100" if h == 0 else cell(d["R"][h], d["R_lo"][h], d["R_hi"][h]))
        for lab in ("S1", "S2", "S3"):
            d = res["hourly"][lab]["12개월"]
            cells.append(cell(d["A"][h], d["A_lo"][h], d["A_hi"][h]))
        rows.append(f"| {h+1} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def thresholds(res):
    rows = ["| 시나리오 | 시점 | R이 처음 80% 이하가 되는 시간: 기준 (가정 범위) | 14h 안에 80% 미도달 비율 | R이 처음 50% 이하가 되는 시간: 기준 (가정 범위) | 14h 안에 50% 미도달 비율 |",
            "|---|---|---|---|---|---|"]
    for t in res["thresholds"]:
        f = lambda v: "14h 안에 없음" if v is None else f"{v}번째"
        rows.append(f"| {t['scenario']} | {t['timepoint']} | {f(t['le80_base'])} ({t['le80_range']}) | {100*t['share_never80']:.0f}% | "
                    f"{f(t['le50_base'])} ({t['le50_range']}) | {100*t['share_never50']:.0f}% |")
    return "\n".join(rows)


def yearly(res):
    rows = ["| 시나리오 | 시점 | 첫 1시간 A | 공부일 하루 총량(RHE) | 9~14번째 시간의 기여(RHE) | 13~14번째 시간의 기여(RHE) | 9~14번째 시간의 비중 |",
            "|---|---|---|---|---|---|---|"]
    pick = {"초기(1~2주)": ("1-2주", 1), "1개월": ("1개월", 3), "3개월": ("3개월", 7), "6개월": ("6개월", 13), "12개월": ("12개월", 26)}
    for lab in ("S1", "S2", "S3"):
        yr = res["yearly"][lab]
        for name, (tp, cyc) in pick.items():
            r = yr[cyc - 1]
            h = res["hourly"][lab][tp]
            rows.append(f"| {lab} | {name} | {r5(r[1])} ({rng(r[4], r[5])}) | {r[2]:.1f} ({r[6]:.1f}~{r[7]:.1f}) | "
                        f"{h['late9_14']:.1f} ({h['late9_14_p10']:.1f}~{h['late9_14_p90']:.1f}) | {h['late13_14']:.1f} ({h['late13_14_p10']:.1f}~{h['late13_14_p90']:.1f}) | "
                        f"{100*r[3]:.0f}% ({100*h['share9_14_p10']:.0f}~{100*h['share9_14_p90']:.0f}%) |")
    return "\n".join(rows)


def plan_hourly(res, key):
    T = res["representative"][key]
    H = T["12개월"]["H"]
    nh = len(T["12개월"]["R"])
    frac = H - int(H) if H != int(H) else 1.0
    rows = ["| 몇 번째 시간 | 초기 1~2주 R | 6개월 R | 12개월 R | 초기 1~2주 A | 6개월 A | 12개월 A |",
            "|---|---|---|---|---|---|---|"]
    for h in range(nh):
        scale = 1.0 / frac if (h == nh - 1 and frac < 1.0) else 1.0
        label = f"{h+1}" if scale == 1.0 else f"{h+1} (마지막 {int(frac*60)}분, 1시간당 환산)"
        cells = []
        for tp in ("1-2주", "6개월", "12개월"):
            d = T[tp]
            cells.append("100" if h == 0 else cell(d["R"][h] * scale, d["R_lo"][h] * scale, d["R_hi"][h] * scale))
        for tp in ("1-2주", "6개월", "12개월"):
            d = T[tp]
            cells.append(cell(d["A"][h] * scale, d["A_lo"][h] * scale, d["A_hi"][h] * scale))
        rows.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def prepost(res):
    rows = ["| 시나리오 | 날 | 첫 1시간 A | R 8번째 | R 10번째 | R 12번째 | R 14번째 | 하루 RHE |", "|---|---|---|---|---|---|---|---|"]
    for lab in ("S1", "S2", "S3"):
        for r in res["prepost"][lab]:
            if r[0].startswith("26"):
                rows.append(f"| {lab} | {r[0].replace('26주기 ', '12개월, ')} | {r[1]:.0f} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]:.1f} |")
    return "\n".join(rows)


def schedule_p1(res):
    name = {"sleep_first": "수면 우선(필요량까지 수면, 남으면 여가)", "sleep_fixed": "수면 고정(실수면 7.0h, 남는 시간은 여가)"}
    rows = ["| 재배분 경로 | 공부일 명목 공부시간 h | 실수면 h | 공부일 자유 여가 h | 연간 명목 공부시간 h | 연간 RHE: 기준 (가정 범위) | 공부일 하루 평균 RHE |",
            "|---|---|---|---|---|---|---|"]
    for c in res["schedule_prompt1"]:
        per_day = c["rhe"] / 339
        rows.append(f"| {name[c['route']]} | {c['H']} | {c['sleep']:.1f} | {c['leisure']:.1f} | {c['nominal']:.0f} | "
                    f"{c['rhe']:.0f} ({c['rhe_p10']:.0f}~{c['rhe_p90']:.0f}) | {per_day:.1f} |")
    return "\n".join(rows)


def increments(res):
    name = {"sleep_first": "수면 우선", "sleep_fixed": "수면 고정"}
    rows = ["| 경로 | 연장 | 추가된 시간 블록의 기여(RHE/년) | 나머지 시간·날에 대한 파급(RHE/년) | 순효과: 기준 (가정 범위) | 순효과가 음수인 가정 조합 |",
            "|---|---|---|---|---|---|"]
    for c in res["increments_prompt1"]:
        rows.append(f"| {name[c['route']]} | {c['step']} | +{c['block']:.0f} | {c['spill']:+.0f} | {c['net']:+.0f} ({c['net_p10']:+.0f}~{c['net_p90']:+.0f}) | {100*c['share_negative']:.0f}% |")
    return "\n".join(rows)


def prompt2_compare(res):
    rows = ["| 일정 | 실수면 h | 공부일 자유 여가 h | 조건 | 공부일 순공부시간 h | 연간 명목 공부시간 h | 연간 RHE: 기준 (가정 범위) |", "|---|---|---|---|---|---|---|"]
    for c in res["prompt2_compare"]:
        rows.append(f"| {c['plan']} | {c['sleep']:.1f} | {c['leisure']:.1f} | {c['condition']} | {c['engaged_h']:.1f} | {c['nominal']:.0f} | "
                    f"{c['rhe']:.0f} ({c['rhe_p10']:.0f}~{c['rhe_p90']:.0f}) |")
    return "\n".join(rows)


def sensitivity(res):
    s = res["sensitivity"]
    b = s["base"]
    rows = [f"기준: S2 3개월 R≤80% 첫 시간 = {b['le80_S2_3m']}번째, 12→14h 순효과(수면 우선 경로) = {b['net_12_14']:+.0f} RHE/년, 두 번째 질문 틀 최적 H = {b['opt_H_A']:g}h", "",
            "| 모수 | 등급 | 설정 | 값 | R≤80% 첫 시간 | 12→14 순효과 | 최적 H |", "|---|---|---|---|---|---|---|"]
    for r in s["rows"]:
        changed = (r["le80_S2_3m"] != b["le80_S2_3m"]) or abs(r["net_12_14"] - b["net_12_14"]) >= 40 or r["opt_H_A"] != b["opt_H_A"]
        if not changed:
            continue
        le = "14h 안에 없음" if r["le80_S2_3m"] is None else f"{r['le80_S2_3m']}번째"
        rows.append(f"| {r['param']} | {r['grade']} | {r['set']} | {r['value']:g} | {le} | {r['net_12_14']:+.0f} | {r['opt_H_A']:g} |")
    return "\n".join(rows)


def hyp14(res):
    H = res["representative"]["hyp14_8h"]
    rows = ["| 몇 번째 시간 | 초기 1~2주 R | 6개월 R | 12개월 R | 초기 1~2주 A | 6개월 A | 12개월 A |",
            "|---|---|---|---|---|---|---|"]
    for h in range(14):
        cells = []
        for tp in ("1-2주", "6개월", "12개월"):
            d = H[tp]
            cells.append("100" if h == 0 else cell(d["R"][h], d["R_lo"][h], d["R_hi"][h]))
        for tp in ("1-2주", "6개월", "12개월"):
            d = H[tp]
            cells.append(cell(d["A"][h], d["A_lo"][h], d["A_hi"][h]))
        rows.append(f"| {h+1} | " + " | ".join(cells) + " |")
    le = ", ".join(f"{tp}: {H[tp]['le80']}번째({H[tp]['le80_range']})" for tp in ("1-2주", "6개월", "12개월"))
    rows.append("")
    rows.append(f"R≤80% 첫 시간(기준, 가정 범위) — {le}")
    return "\n".join(rows)


def representative(res):
    R = res["representative"]
    rows = ["| 안 | 공부일 명목 공부시간 | 완전 휴일(14일당) | 공부일 여가 | 순공부시간 | 주간 명목 공부시간 | 연간 명목 공부시간 | 연간 RHE: 기준 (가정 범위) | A11 대비: 중앙값 (가정 범위) |",
            "|---|---|---|---|---|---|---|---|---|"]
    for k, v in R.items():
        if k in ("hyp14_8h", "A11_hourly", "B90_hourly", "rest0_vs_rest1_11h"):
            continue
        rows.append(f"| {k} | {v['H']:g}h | {v['rest_per_14']} | {v['leisure']:.1f}h | {v['engaged_h']:.1f}h | {v['weekly_nominal']:.1f}h | {v['annual_nominal']:.0f}h | "
                    f"{v['rhe']:.0f} ({v['rhe_p10']:.0f}~{v['rhe_p90']:.0f}) | {v['rel_to_A11_p50']:.2f} ({v['rel_to_A11_p10']:.2f}~{v['rel_to_A11_p90']:.2f}) |")
    return "\n".join(rows)


def main():
    with open(os.path.join(HERE, "outputs", "results.json"), encoding="utf-8") as f:
        res = json.load(f)
    parts = [
        ("표 C-1. 시간별 R과 A (S2 기준)", hourly_main(res, "S2")),
        ("표 C-2. 시나리오별 비교", hourly_scen(res)),
        ("표 C-3. 80%·50% 보조 기준", thresholds(res)),
        ("표 D-1. 연중 변화", yearly(res)),
        ("표 D-2. 휴일 직후와 직전", prepost(res)),
        ("표 E-1. 첫 번째 질문 틀 일정 비교", schedule_p1(res)),
        ("표 E-2. 연장의 분해", increments(res)),
        ("표 P2. 두 번째 질문 틀 일정 비교", prompt2_compare(res)),
        ("표 S. 일대일 민감도", sensitivity(res)),
        ("표 P2-H. 실수면 8h를 지킨 14h 가상 일정", hyp14(res)),
        ("표 P2-R. 두 번째 질문 대표안", representative(res)),
        ("표 P2-A. 시나리오 A(11h) 시간별", plan_hourly(res, "A11_hourly")),
        ("표 P2-B. 시나리오 B(9.5h) 시간별", plan_hourly(res, "B90_hourly")),
    ]
    out = "\n\n".join(f"### {t}\n\n{b}" for t, b in parts)
    with open(os.path.join(HERE, "outputs", "tables.md"), "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(out)


if __name__ == "__main__":
    main()
