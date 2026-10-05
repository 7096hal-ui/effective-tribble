"""Render the Korean-language research report (Markdown) from pipeline outputs.

Inputs (work dir): universe.json, macro.json, dossiers/, analysis/, final/, bear/, coord.json,
                   editorial.json (hand-written summaries and short labels)
Engine outputs   : out_final/results.json, out_prelim/results.json, model_final.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

H = ("1", "3", "5")
HK = {"1": "y1", "3": "y3", "5": "y5"}
END = {"1": "2027-09-28(화)", "3": "2029-09-28(금)", "5": "2031-09-28(일) → 직전 거래일 2031-09-26(금) 종가"}
FACTOR_KO = {
    "fx_usdkrw_up10": "원/달러 +10%",
    "rates_up100bp": "할인율 +100bp",
    "terminal_multiple_down20": "최종 멀티플 -20%",
    "semi_ai_down": "반도체 가격·AI 설비투자 하향",
    "auto_tariff_demand": "자동차 수요 -5%·관세 +10%p",
    "bio_pos_down25": "바이오 성공확률 -25%(상대)",
    "dilution_up10": "추가 희석 +10%",
    "key_customer_down20": "핵심고객 매출 -20%",
}
GROUP_KO = {
    "SEMI_AI_DISPLAY": "반도체·AI HW·디스플레이",
    "AUTO_SDV": "자동차·전장·SDV",
    "BIO_MEDTECH": "바이오·의료기기·진단",
    "SPACE_TELECOM": "우주·위성통신·5G/6G·방산",
    "ESS_INDUSTRIAL_MATERIALS": "ESS·산업재·특수소재",
}


def J(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def pc(x, sign=True):
    if x is None:
        return "N/A"
    return f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%"


def won(v):
    return "N/A" if v is None else f"{v:,.0f}"


def cell(s: str | None, n: int = 400) -> str:
    if not s:
        return ""
    s = " ".join(str(s).split()).replace("|", "/")
    return s if len(s) <= n else s[: n - 1] + "…"


class Ctx:
    def __init__(self, work: Path, final_dir: Path, prelim_dir: Path):
        self.w = work
        self.uni = J(work / "universe.json")
        self.U = {u["name"]: u for u in self.uni}
        self.macro = J(work / "macro.json")
        self.res = J(final_dir / "results.json")
        self.pre = J(prelim_dir / "results.json")
        self.coord = J(work / "coord.json") or {}
        self.ed = J(work / "editorial.json") or {}
        self.dos = {n: J(work / "dossiers" / f"{n}.json") for n in self.U}
        self.ana = {n: J(work / "analysis" / f"{n}.json") for n in self.U}
        self.fin = {n: J(work / "final" / f"{n}.json") for n in self.U}
        self.bear = {n: J(work / "bear" / f"{n}.json") for n in self.U}
        self.rows = {T: {r["name"]: r for r in self.res["horizons"][T]["rows"]} for T in H}
        self.prows = {T: {r["name"]: r for r in self.pre["horizons"][T]["rows"]} for T in H} if self.pre else None

    def ranked(self, T, key="rank_balanced"):
        return sorted(self.rows[T].values(), key=lambda r: r[key])

    def hz(self, n, T):
        f = self.fin.get(n)
        if f:
            return f["horizons"][HK[T]]
        return self.ana[n]["fin"]["horizons"][HK[T]]

    def label(self, n):
        return f"{n}({self.U[n]['code']})"


def part1(c: Ctx) -> list[str]:
    L = ["## 1부. 핵심 결론", ""]
    ed = c.ed.get("part1_intro")
    if ed:
        L += [ed, ""]
    for T in H:
        e = c.ranked(T, "rank_exp")[:5]
        r = c.ranked(T, "rank_risk")[:5]
        metric = "기대 누적 TSR" if T == "1" else "기대 연환산"
        L.append(f"**{T}년 기대수익률 상위 5** ({metric} 기준): " + ", ".join(
            f"{x['rank_exp']}. {x['name']} ({pc(x['e_cum'])}" + ("" if T == "1" else f", 연 {pc(x['e_ann'])}") + ")" for x in e))
        L.append("")
        L.append(f"**{T}년 위험조정 상위 5** (Forward Sortino 기준): " + ", ".join(
            f"{x['rank_risk']}. {x['name']} (Sortino {x['sortino']:.2f}, CVaR10 {pc(x['cvar10'])})" for x in r))
        L.append("")
    avg = sorted(c.U, key=lambda n: -sum(c.rows[T][n]["score_balanced"] for T in H if n in c.rows[T]) / 3 if all(n in c.rows[T] for T in H) else 0)
    top = [n for n in avg if all(n in c.rows[T] for T in H)][:5]
    L.append("**세 기간 전체에서 가장 일관되게 높은 종목 5** (균형형 점수 3기간 평균): " + ", ".join(
        f"{n} (균형 순위 {'/'.join(str(c.rows[T][n]['rank_balanced']) for T in H)})" for n in top))
    L.append("")
    for key in ("high_e_high_risk", "mid_e_good_risk", "optimism_priced"):
        if c.ed.get(key):
            L += [c.ed[key], ""]
    return L


def part2(c: Ctx) -> list[str]:
    L = ["## 2부. 종목 식별 및 데이터 검증표", "",
         "기준 주가는 2026-09-28 정규장 종가를 원칙으로 하되, 확인하지 못한 종목은 확인 가능한 가장 최근 종가와 날짜를 적었다. 시가총액은 기준 주가×보통주 발행주식수(에이전트 계산 또는 보도치)이며 기준일을 병기한다.", "",
         "| 회사명 | 종목코드 | 시장 | 거래 가능 | 기준 주가(원, 기준일) | 시가총액(억원, 기준일) | 최근 결산·보고 기준 | 핵심 사업 | 데이터상 특이사항 |",
         "|---|---|---|---|---|---|---|---|---|"]
    short = c.ed.get("business_short", {})
    notes = c.ed.get("data_notes", {})
    for u in c.uni:
        n = u["name"]
        d = (c.dos.get(n) or {}).get("data", {})
        mcap = d.get("market_cap_krw_eok")
        mdate = cell(d.get("market_cap_asof"), 40)
        L.append(f"| {n} | {u['code']} | {u['market']} | {'가능' if u.get('tradable', True) else '불가'} | "
                 f"{won(u['P0'])} ({u['P0_date']}) | {won(mcap)} ({mdate}) | {cell(d.get('fiscal', {}).get('latest_reported_period'), 40)} | "
                 f"{cell(short.get(n) or d.get('business'), 90)} | {cell(notes.get(n), 220)} |")
    L.append("")
    return L


def part3(c: Ctx) -> list[str]:
    rf = c.res["meta"]["rf"]
    L = ["## 3부. 기간별 전체 순위표", "",
         "지표 정의: 기대 누적 TSR = 시나리오 확률가중 평균. 기대 연환산 = (1+기대 누적)^(1/T)−1. 중앙값·P10/P50/P90·손실확률·CVaR10은 시나리오 혼합 로그정규 몬테카를로(종목·기간당 20만 경로)에서 계산했다. "
         f"Forward Sortino = (기대 연환산 − 무위험) ÷ 연환산 하방편차. 무위험수익률은 1년 {rf['1']:.2f}%(추정), 3년 {rf['3']:.3f}%, 5년 {rf['5']:.3f}%(국고채, 2026-09-28)다. "
         "초과수익은 해당 시장지수(KOSPI/KOSDAQ) 기대 TSR 대비 연환산 차이다.", ""]
    for T in H:
        L += [f"### {T}년 (종료일 {END[T]})", "",
              "| 균형 | 기대 | 위험조정 | 종목(코드) | 현재가(원) | 기대 누적 TSR | 기대 연환산 | 중앙값 누적 | P10 / P50 / P90 | 손실확률 | −30% 이하 확률 | Fwd Sortino | CVaR10 | 지수 대비 초과(연) | 신뢰도 | 순위를 결정한 핵심 요인 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in c.ranked(T):
            n = r["name"]
            L.append(f"| {r['rank_balanced']} | {r['rank_exp']} | {r['rank_risk']} | {c.label(n)} | {won(c.U[n]['P0'])} | {pc(r['e_cum'])} | {pc(r['e_ann'])} | "
                     f"{pc(r['median'])} | {pc(r['p10'])} / {pc(r['p50'])} / {pc(r['p90'])} | {pc(r['p_loss'], False)} | {pc(r['p_loss30'], False)} | "
                     f"{r['sortino']:.2f} | {pc(r['cvar10'])} | {pc(r.get('excess_ann'))} | {r['confidence']} | {cell(c.hz(n, T).get('key_driver'), 160)} |")
        L.append("")
    excl = [u for u in c.uni if not u.get("rankable", True)]
    L.append("투자가능 종목 순위 제외: " + (", ".join(f"{u['name']}({u.get('exclude_reason', '')})" for u in excl) if excl else "없음. 26개 종목 모두 2026-09-28 기준 상장·거래 중으로 확인되어 순위에 포함했다."))
    L.append("")
    return L


def part4(c: Ctx) -> list[str]:
    L = ["## 4부. 기간별 순위 변화표", "",
         "| 종목 | 1년 균형 | 3년 균형 | 5년 균형 | 공격형 1/3/5년 | 방어형 1/3/5년 | 장기로 갈수록 순위가 오르거나 내리는 이유 |",
         "|---|---|---|---|---|---|---|"]
    reasons = c.ed.get("rank_change_reason", {})
    order = sorted(c.U, key=lambda n: c.rows["5"][n]["rank_balanced"] if n in c.rows["5"] else 99)
    for n in order:
        if not all(n in c.rows[T] for T in H):
            continue
        b = [c.rows[T][n]["rank_balanced"] for T in H]
        a = [c.rows[T][n]["rank_aggressive"] for T in H]
        d = [c.rows[T][n]["rank_defensive"] for T in H]
        flag = " ⚑" if max(abs(x - y) for x, y in zip(a, d)) >= 6 else ""
        L.append(f"| {n}{flag} | {b[0]} | {b[1]} | {b[2]} | {'/'.join(map(str, a))} | {'/'.join(map(str, d))} | {cell(reasons.get(n), 260)} |")
    L += ["", "⚑ = 어느 한 기간에서라도 공격형과 방어형 순위 차이가 6계단 이상인 '위험선호 민감' 종목.", ""]
    return L


def scen_table(c: Ctx, n: str) -> list[str]:
    L = ["| 기간 | 시나리오 | 확률 | 기말 주가(원) | 누적 배당(원) | 누적 TSR |", "|---|---|---|---|---|---|"]
    for T in H:
        for s in c.hz(n, T)["scenarios"]:
            L.append(f"| {T}년 | {cell(s['name'], 30)} | {s['prob'] * 100:.0f}% | {won(s['end_price_krw'])} | {won(s['cum_dividends_krw'])} | {s['tsr_cum_pct']:+.1f}% |")
    return L


def part5(c: Ctx) -> list[str]:
    L = ["## 5부. 상위 종목 상세 분석", ""]
    names = []
    for T in H:
        for r in c.ranked(T)[:5]:
            if r["name"] not in names:
                names.append(r["name"])
    L.append("각 기간 균형형 종합순위 상위 5개의 합집합: " + ", ".join(
        f"{n}(균형 {'/'.join(str(c.rows[T][n]['rank_balanced']) for T in H)})" for n in names))
    L.append("")
    for n in names:
        a = c.ana[n]
        f = a["fin"]
        sp, ge = a["sp"], a["ge"]
        fj = c.fin.get(n)
        L += [f"### {c.label(n)} — {GROUP_KO.get(c.U[n]['group'], c.U[n]['group'])}", ""]
        L.append(f"- 기준 주가 {won(c.U[n]['P0'])}원({c.U[n]['P0_date']}). 균형 순위 1/3/5년 = {'/'.join(str(c.rows[T][n]['rank_balanced']) for T in H)}, "
                 f"기대 누적 TSR = {' / '.join(pc(c.rows[T][n]['e_cum']) for T in H)}, 중앙값 = {' / '.join(pc(c.rows[T][n]['median']) for T in H)}.")
        L.append(f"- **핵심 투자논지**: {cell(c.ed.get('thesis', {}).get(n) or sp.get('thesis'), 700)}")
        L.append(f"- **현재 주가가 암시하는 기대**: {cell(f.get('implied_expectations'), 600)}")
        L.append(f"- **시장 전망과 자체 전망의 차이**: {cell(f.get('market_vs_own'), 500)}")
        L.append(f"- **매출·이익·현금흐름 전망**: {cell(f.get('forecast_summary'), 600)}")
        fv = f["fair_value_krw"]
        L.append(f"- **가치평가 방법과 적정가치 범위**: {cell(f.get('valuation_summary'), 600)} (종합 적정가치 {won(fv['low'])}~{won(fv['high'])}원, 중심 {won(fv['mid'])}원)")
        L.append(f"- **가장 중요한 촉매**: {cell('; '.join(f.get('catalysts', [])[:3]), 400)}")
        L.append(f"- **가장 중요한 하방위험**: {cell('; '.join(f.get('risks', [])[:3]), 400)}")
        L.append(f"- **투자논지 무효화 조건**: {cell('; '.join(f.get('invalidation', [])[:3]), 400)}")
        L.append(f"- **다음 실적·공시 확인 지표**: {cell('; '.join(f.get('kpis', [])[:4]), 400)}")
        if fj:
            L.append(f"- **반대심문 반영**: {cell(fj.get('change_summary'), 500)}")
        L += ["", "비관·기준·낙관 시나리오(반대심문 반영 후, 잎이 3개를 넘으면 사건트리의 잎):", ""] + scen_table(c, n) + [""]
    return L


def part6(c: Ctx) -> list[str]:
    L = ["## 6부. 하위 종목 및 고위험 종목", ""]
    names = []
    for T in H:
        for r in c.ranked(T)[-5:]:
            if r["name"] not in names:
                names.append(r["name"])
    for r in c.rows["1"].values():
        if r["p_loss"] >= 0.45 and r["name"] not in names:
            names.append(r["name"])
    L.append("각 기간 균형형 하위 5개와 1년 손실확률 45% 이상 종목: " + ", ".join(names))
    L.append("")
    for n in names:
        f = c.ana[n]["fin"]
        d = c.dos.get(n) or {}
        fo = d.get("forensic", {})
        L += [f"### {c.label(n)}", ""]
        L.append(f"- 균형 순위 1/3/5년 = {'/'.join(str(c.rows[T][n]['rank_balanced']) for T in H)}; 1년 손실확률 {pc(c.rows['1'][n]['p_loss'], False)}, "
                 f"5년 손실확률 {pc(c.rows['5'][n]['p_loss'], False)}, 5년 CVaR10 {pc(c.rows['5'][n]['cvar10'])}.")
        L.append(f"- **낮은 순위의 핵심 원인**: {cell(c.ed.get('low_reason', {}).get(n) or c.hz(n, '3').get('key_driver'), 500)}")
        L.append(f"- **현재 주가에 반영된 기대**: 낙관 반영도 {f.get('optimism_priced_in')}/5 — {cell(f.get('optimism_rationale'), 400)}")
        L.append(f"- **재무·희석·기술·고객·규제 위험**: 포렌식 {fo.get('forensic_score', 'N/A')}; " + cell('; '.join(f.get('risks', [])[:3]), 450))
        L.append(f"- **순위를 크게 끌어올릴 변화**: {cell(f.get('upside_triggers'), 450)}")
        L.append("")
    return L


def part7(c: Ctx) -> list[str]:
    L = ["## 7부. 에이전트 의견 차이와 반대심문 결과", ""]
    gaps = []
    for n in c.U:
        a = c.ana.get(n)
        if not a:
            continue
        dis = a["fin"]["disagreement"]
        g5 = abs(dis["specialist_expected"]["y5"] - dis["generalist_expected"]["y5"])
        g1 = abs(dis["specialist_expected"]["y1"] - dis["generalist_expected"]["y1"])
        gaps.append((g5 + g1, n, dis))
    gaps.sort(reverse=True)
    L += ["### 분석가 간 전망 차이가 가장 컸던 종목", "",
          "| 종목 | 산업전문가 기대 누적 TSR 1/3/5년 | 일반분석가 1/3/5년 | 핵심 가정 차이 | 최종 가중 |", "|---|---|---|---|---|"]
    for _, n, dis in gaps[:8]:
        s, g = dis["specialist_expected"], dis["generalist_expected"]
        L.append(f"| {n} | {s['y1']:+.1f}% / {s['y3']:+.1f}% / {s['y5']:+.1f}% | {g['y1']:+.1f}% / {g['y3']:+.1f}% / {g['y5']:+.1f}% | "
                 f"{cell(dis.get('key_assumption_diff'), 300)} | {cell(dis.get('weighting'), 250)} |")
    L.append("")
    if c.ed.get("disagreement_summary"):
        L += [c.ed["disagreement_summary"], ""]
    if c.coord:
        L += ["### 총괄 조정·베이스레이트 횡단면 점검", ""]
        for x in c.coord.get("industry_bias_findings", []):
            L.append(f"- [{x['industry']}] {cell(x['finding'], 400)} (해당: {', '.join(x['affected'])})")
        for x in c.coord.get("consistency_issues", []):
            L.append(f"- [일관성] {cell(x, 350)}")
        L.append("")
    L += ["### 약세론 에이전트의 가장 강한 반론과 최종 심사", "",
          "| 종목 | 가장 강한 반론 | 반대심문 전→후 기대 누적 TSR(1/3/5년) | 최종 심사 판단 |", "|---|---|---|---|"]
    for n in c.U:
        b, fj = c.bear.get(n), c.fin.get(n)
        if not (b and fj):
            continue
        pre = c.ana[n]["fin"]["horizons"]
        before = " / ".join(f"{pre[HK[T]]['expected_tsr_cum_pct']:+.1f}%" for T in H)
        after = " / ".join(f"{fj['horizons'][HK[T]]['expected_tsr_cum_pct']:+.1f}%" for T in H)
        L.append(f"| {n} | {cell(b.get('strongest_counterargument'), 350)} | {before} → {after} | {cell(fj.get('weighting_rationale'), 300)} |")
    L.append("")
    if c.prows:
        L += ["### 반대심문 후 순위가 크게 바뀐 종목(균형형, 3계단 이상)", ""]
        moved = []
        for T in H:
            for n, r in c.rows[T].items():
                p = c.prows[T].get(n)
                if p and abs(p["rank_balanced"] - r["rank_balanced"]) >= 3:
                    moved.append(f"- {T}년 {n}: {p['rank_balanced']}위 → {r['rank_balanced']}위")
        L += (moved or ["- 없음"]) + [""]
    return L


def part8(c: Ctx) -> list[str]:
    L = ["## 8부. 순위 민감도", "",
         "각 표준 충격을 26개 종목에 동시에 적용했다(종목별 민감도는 보정 에이전트와 최종 심사 에이전트가 추정한 기대 누적 TSR 변화 %p). 충격 후 시나리오 분포를 비례 이동해 균형형 순위를 다시 계산했다. "
         "별도로 종목별 모형 불확실성(신뢰도별 기본 표준편차 높음 6%p·보통 12%p·낮음 22%p×√T와 분석가 간 차이의 절반을 합성)으로 600회 섭동해 균형 순위의 80% 구간을 구했다.", ""]
    for T in H:
        sens = c.res["horizons"][T]["sensitivity_ranks"]
        L += [f"### {T}년", "", "| 충격 | 순위가 가장 크게 오른 종목 | 가장 크게 내린 종목 |", "|---|---|---|"]
        for f, ko in FACTOR_KO.items():
            mv = [(sens[f][c.rows[T][n]["id"]] - c.rows[T][n]["rank_balanced"], n) for n in c.rows[T]]
            up = sorted(mv)[:3]
            dn = sorted(mv, reverse=True)[:3]
            fmt = lambda xs: ", ".join(f"{n}({-d:+d})" for d, n in xs if d != 0) or "변화 없음"
            L.append(f"| {ko} | {fmt(up)} | {fmt([(d, n) for d, n in dn])} |")
        L.append("")
        L += ["| 종목 | 균형 순위 | 80% 순위 구간 | 단일 충격 최대 이동 | 가장 민감한 충격 | 판정 |", "|---|---|---|---|---|---|"]
        for r in c.ranked(T):
            lo, hi = r["rank_band80"]
            unstable = r["max_factor_move"] >= 5 or (hi - lo) >= 12
            L.append(f"| {r['name']} | {r['rank_balanced']} | {lo}~{hi} | {r['max_factor_move']} | {FACTOR_KO.get(r['worst_factor'], r['worst_factor'])} | {'순위 불안정' if unstable else ''} |")
        L.append("")
    L.append("판정 기준: 단일 표준 충격에 균형 순위가 5계단 이상 움직이거나, 모형 불확실성 섭동의 80% 순위 구간 폭이 12계단 이상이면 '순위 불안정'.")
    L.append("")
    return L


def part9(c: Ctx) -> list[str]:
    L = ["## 9부. 최종 판단", ""]
    if c.ed.get("final"):
        L += c.ed["final"] + [""]
    L.append("개인의 위험선호와 재무상황이 주어지지 않았으므로 투자비중이나 매매지시는 제시하지 않는다. 모든 확률과 수익률은 문서화된 가정에 따른 추정치이며 확정된 사실이 아니다.")
    L.append("")
    return L


def header(c: Ctx) -> list[str]:
    f = c.macro["facts"]
    s = c.macro["scen"]
    rf = s["risk_free"]
    dates = sorted({u["P0_date"] for u in c.uni})
    n928 = sum(1 for u in c.uni if u["P0_date"] == "2026-09-28")
    L = ["# 한국 26개 종목 1·3·5년 총주주수익률(TSR) 전망과 순위", "",
         "| 항목 | 내용 |", "|---|---|",
         "| 분석 기준일시 | 2026-09-28(월) 19:40 KST (한국거래소 정규장 마감 후) |",
         f"| 사용 주가 기준일 | 2026-09-28 정규장 종가 {n928}개 종목, 나머지는 확인 가능한 최근 종가({', '.join(d for d in dates if d != '2026-09-28')}) — 2부 표에 종목별 명시 |",
         f"| 전망 종료일 | 1년 {END['1']}, 3년 {END['3']}, 5년 {END['5']} |",
         "| 기준 통화 | 원화(KRW). 세전·수수료 차감 전 총주주수익률(주가+배당+희석·소각 반영) |",
         f"| 시장 기준값 | KOSPI {f['kospi']['close']:,.2f}(2026-09-28, 전일 대비 −2.70%), KOSDAQ {f['kosdaq']['close']:,.2f}(2026-09-28), 원/달러 {f['usdkrw']['value']:,.1f}원(2026-09-28 주간 종가) |",
         f"| 무위험수익률 | 1년 {rf['h1_pct']:.2f}%(1년물 금리 확인 불가로 보간 추정), 3년 {rf['h3_pct']:.3f}%, 5년 {rf['h5_pct']:.3f}%(국고채 최종호가, 2026-09-28) |",
         "| 자료 접근 한계 | 실행 환경의 네트워크 정책으로 KRX·DART·네이버 금융·FnGuide 등 원자료 사이트에 직접 접속할 수 없었다. 모든 수치는 웹 검색 결과(언론 보도·금융 포털 요약)를 서로 다른 검색어로 교차확인한 값이며, 일별 가격 시계열이 없어 변동성·베타·최대낙폭은 추정치다. 유료 데이터베이스에는 접근하지 않았다. |",
         ""]
    if c.ed.get("process_note"):
        L += [c.ed["process_note"], ""]
    return L


def macro_appendix(c: Ctx) -> list[str]:
    s = c.macro["scen"]
    L = ["## 부록 A. 공통 거시 시나리오(C 에이전트)", "",
         "| 시나리오 | 확률 | 요지 | KOSPI TSR 1/3/5년 | KOSDAQ TSR 1/3/5년 | 원/달러 경로 |", "|---|---|---|---|---|---|"]
    for x in s["scenarios"]:
        i = x["index_tsr"]
        L.append(f"| {x['name']} | {x['prob'] * 100:.0f}% | {cell(x['narrative'], 300)} | {i['kospi_1y']:+.0f}% / {i['kospi_3y_cum']:+.0f}% / {i['kospi_5y_cum']:+.0f}% | "
                 f"{i['kosdaq_1y']:+.0f}% / {i['kosdaq_3y_cum']:+.0f}% / {i['kosdaq_5y_cum']:+.0f}% | {cell(x['usdkrw_path'], 160)} |")
    e = s["expected_index_tsr"]
    L += ["", f"확률가중 기대 TSR: KOSPI 1년 {e['kospi_1y']:+.1f}%, 3년 누적 {e['kospi_3y_cum']:+.1f}%, 5년 누적 {e['kospi_5y_cum']:+.1f}%; "
          f"KOSDAQ 1년 {e['kosdaq_1y']:+.1f}%, 3년 누적 {e['kosdaq_3y_cum']:+.1f}%, 5년 누적 {e['kosdaq_5y_cum']:+.1f}%.", ""]
    L += ["산업별 공통 가정:", ""]
    for k, v in s["industry_common_assumptions"].items():
        L.append(f"- **{k}**: {cell(v, 700)}")
    L.append("")
    return L


def method_appendix(c: Ctx) -> list[str]:
    m = c.res["meta"]
    return ["## 부록 B. 방법론과 산식", "",
            "1. **에이전트 구성**: 거시(C: 사실검증→반도체·AI 사이클/기타 산업 사이클→시나리오) → 종목별 식별·데이터(B) → 회계·지배구조 포렌식(E)과 정량·위험(G) → 가격 재확인(B2) → 산업 전문가(D)와 산업 비소속 일반 분석가가 서로의 결과를 보지 않고 각각 가치평가·시나리오 작성 → 베이스레이트·보정(H)이 가중 통합·축소 → 잠정 순위 → 총괄 조정(A)의 횡단면 편향 점검 → 약세론(I) 반대심문 → 최종 심사(J) → 최종 순위.",
            f"2. **분포 모형**: 시나리오 i(확률 p_i, 누적 TSR x_i)마다 ln R ~ N(ln(1+x_i) − s²/2, s²). 혼합분포의 평균은 확률가중 시나리오 TSR과 정확히 같다. 시나리오 내 σ(s)는 혼합분포 전체의 로그수익률 표준편차가 max(forward 연변동성, 하한)×√(T×VR(T))가 되도록 정했다. VR = {m['vr']}, 시나리오 내 σ의 최소 비율 {m['min_within']}. 변동성 하한은 시가총액 50조 이상 28%, 5조 이상 32%, 1조 이상 40%, 그 미만 48%이며 상장 2년 미만은 +5%p다(짧은 주가이력이 높은 Sortino를 만들지 않도록).",
            f"3. **몬테카를로**: 종목·기간당 {m['n_samples']:,}개 경로, 시드 {m['seed']}.",
            "4. **Forward Sortino** = (기대 연환산 − 무위험) ÷ √(E[min(ln R − T·ln(1+rf), 0)²]/T). 위험조정 순위는 Sortino(소수 둘째 자리) → CVaR10이 덜 부정적인 순 → 손실확률이 낮은 순 → 영구자본손실 확률(5년 뒤 −50% 이하)이 낮은 순.",
            "5. **균형형 종합점수** = 기대수익률 백분위×60% + Sortino 백분위×25% + CVaR10 백분위×15% (CVaR는 덜 부정적일수록 높은 백분위). 공격형 75/15/10, 방어형 40/35/25. 기대수익률 지표는 1년은 기대 누적 TSR, 3·5년은 기대 연환산(같은 기간 안에서는 순위가 동일).",
            "6. **축소(shrinkage)**: 데이터 품질이 낮거나 두 분석가의 차이가 큰 종목은 보정 에이전트가 시장·산업 베이스레이트 쪽으로 기대값을 축소했다(종목별 축소 전·후 값은 부록 C). 신뢰도 점수를 곱하는 이중 벌점은 쓰지 않았다. 신뢰도는 순위 안정성 섭동의 폭에만 반영했다.",
            "7. **TSR 검산**: 모든 시나리오의 TSR을 (기말 주가 + 누적 배당)/기준 주가 − 1로 재계산해 1%p 넘게 어긋나면 재계산값을 썼고, 확률합이 1이 아니면 정규화했다(부록 C에 건수와 내역).",
            ""]


def main(work: Path, final_dir: Path, prelim_dir: Path, out: Path) -> None:
    c = Ctx(work, final_dir, prelim_dir)
    L = header(c)
    for p in (part1, part2, part3, part4, part5, part6, part7, part8, part9, macro_appendix, method_appendix):
        L += p(c)
    extra = c.ed.get("appendix_c")
    if extra:
        L += extra
    out.write_text("\n".join(L))
    print(f"wrote {out} ({len(L)} lines)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("--final", type=Path, required=True)
    ap.add_argument("--prelim", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    main(a.work, a.final, a.prelim, a.out)
