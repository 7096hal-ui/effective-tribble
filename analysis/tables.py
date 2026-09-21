# -*- coding: utf-8 -*-
import sys, copy, json
sys.path.insert(0,'/tmp/claude-0/-home-user-effective-tribble/7742eeb0-1748-5d25-b889-a3f3ed6c53be/scratchpad/krx')
import numpy as np
from engine import simulate, metrics, composite
from model import UNIVERSE, S_LIQ as S

RF={"1Y":0.03976,"3Y":0.04034,"5Y":0.04221}; YRS={"1Y":1.0,"3Y":3.0,"5Y":5.0}
BENCH={"KOSPI":{"1Y":0.040,"3Y":0.010,"5Y":0.030},"KOSDAQ":{"1Y":0.070,"3Y":0.060,"5Y":0.060}}
META={u[0]:dict(code=u[1],mkt=u[2],px=u[3],asof=u[4],sec=u[5],conf=u[6]) for u in UNIVERSE}

def build(Smod=None, rf=None, bench=None):
    Su = Smod or S; rfu = rf or RF; bu = bench or BENCH
    OUT={}
    for h in ["1Y","3Y","5Y"]:
        rows=[]
        for i,(name,meta) in enumerate(META.items()):
            sce,sig,pw = Su[name][h]
            scen=[{"p":p,"px":px,"div":dv} for (p,px,dv) in sce]
            R=simulate(meta["px"],scen,sig,p_wipe=pw,years=YRS[h],seed=20260921+i*7919+{"1Y":11,"3Y":33,"5Y":55}[h])
            rows.append({"name":name,"m":metrics(R,YRS[h],rfu[h],bu[meta["mkt"]][h]),**meta})
        composite(rows,h)
        for k,f in [("rank_ret",lambda r:-r["m"]["e_cum"]),
                    ("rank_risk",lambda r:(-r["m"]["sortino"],-r["m"]["cvar10"],r["m"]["p_loss"])),
                    ("rank_bal",lambda r:-r["score_균형형"]),("rank_agg",lambda r:-r["score_공격형"]),
                    ("rank_def",lambda r:-r["score_방어형"])]:
            for i,r in enumerate(sorted(rows,key=f)): r[k]=i+1
        OUT[h]=rows
    return OUT

BASE=build()
def p(x,d=1): return f"{100*x:.{d}f}%"

L=[]
# ---- 3부 기간별 전체 순위표
for h in ["1Y","3Y","5Y"]:
    L.append(f"\n### {h} 전체 순위표\n")
    L.append("| 균형 | 기대 | 위험 | 종목(코드) | 기준가(원) | 기대누적TSR | 기대연환산 | 중앙값누적 | P10 | P50 | P90 | 손실확률 | 30%↓확률 | Sortino | CVaR10 | 초과수익 | 신뢰 |")
    L.append("|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--:|")
    for r in sorted(BASE[h],key=lambda r:r["rank_bal"]):
        m=r["m"]
        L.append(f"| {r['rank_bal']} | {r['rank_ret']} | {r['rank_risk']} | {r['name']}({r['code']}) | {r['px']:,} | {p(m['e_cum'])} | {p(m['e_ann'])} | {p(m['med_cum'])} | {p(m['p10'])} | {p(m['p50'])} | {p(m['p90'])} | {p(m['p_loss'],0)} | {p(m['p_loss30'],0)} | {m['sortino']:.2f} | {p(m['cvar10'])} | {p(m['excess'])} | {r['conf']} |")

# ---- 4부 순위 변화표
L.append("\n### 기간별 순위 변화\n")
L.append("| 종목 | 1년 종합 | 3년 종합 | 5년 종합 | 1Y공격 | 1Y방어 | 3Y공격 | 3Y방어 | 5Y공격 | 5Y방어 |")
L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
idx={h:{r["name"]:r for r in BASE[h]} for h in BASE}
for name in sorted(META, key=lambda n: idx["5Y"][n]["rank_bal"]):
    a,b,c=idx["1Y"][name],idx["3Y"][name],idx["5Y"][name]
    L.append(f"| {name} | {a['rank_bal']} | {b['rank_bal']} | {c['rank_bal']} | {a['rank_agg']} | {a['rank_def']} | {b['rank_agg']} | {b['rank_def']} | {c['rank_agg']} | {c['rank_def']} |")

# ---- 1부 핵심 결론용 Top5
L.append("\n### Top5 요약\n")
for h in ["1Y","3Y","5Y"]:
    tr=sorted(BASE[h],key=lambda r:r["rank_ret"])[:5]
    rr=sorted(BASE[h],key=lambda r:r["rank_risk"])[:5]
    bl=sorted(BASE[h],key=lambda r:r["rank_bal"])[:5]
    L.append(f"- **{h} 기대수익률 Top5**: "+", ".join(f"{r['name']}({p(r['m']['e_cum'])} 누적 / {p(r['m']['e_ann'])} 연환산)" for r in tr))
    L.append(f"- **{h} 위험조정 Top5**: "+", ".join(f"{r['name']}(Sortino {r['m']['sortino']:.2f}, CVaR {p(r['m']['cvar10'])})" for r in rr))
    L.append(f"- **{h} 균형형 Top5**: "+", ".join(f"{r['name']}" for r in bl))

# 일관성: 3기간 균형형 순위 평균
cons=sorted(META,key=lambda n:(idx["1Y"][n]["rank_bal"]+idx["3Y"][n]["rank_bal"]+idx["5Y"][n]["rank_bal"])/3)
L.append("\n- **3기간 일관 상위 5**: "+", ".join(f"{n}(평균 {(idx['1Y'][n]['rank_bal']+idx['3Y'][n]['rank_bal']+idx['5Y'][n]['rank_bal'])/3:.1f}위)" for n in cons[:5]))
# 기대값-중앙값 괴리
gap=sorted(META,key=lambda n: idx["5Y"][n]["m"]["e_cum"]-idx["5Y"][n]["m"]["med_cum"], reverse=True)
L.append("- **5년 기대값−중앙값 괴리 최대(투기성)**: "+", ".join(f"{n}({p(idx['5Y'][n]['m']['e_cum'])} vs 중앙값 {p(idx['5Y'][n]['m']['med_cum'])})" for n in gap[:5]))

# ---- 8부 민감도
def shock_px(sectors=None, names=None, mult=1.0, hs=("1Y","3Y","5Y")):
    Sm=copy.deepcopy(S)
    for n in Sm:
        if sectors and META[n]["sec"] not in sectors: continue
        if names and n not in names: continue
        for h in hs:
            sce,sig,pw=Sm[n][h]
            Sm[n][h]=([(pp,px*mult,dv) for (pp,px,dv) in sce],sig,pw)
    return Sm

SCEN={
 "반도체·AI 가격 쇼크 (메모리·장비·PCB 기말가치 −25%)": build(shock_px(sectors={"대형반도체","반도체장비"},mult=0.75)),
 "자동차 수요·관세 악화 (자동차 기말가치 −20%)": build(shock_px(sectors={"자동차"},mult=0.80)),
 "바이오 임상·허가 실패율 상승 (바이오 기말가치 −20%)": build(shock_px(sectors={"바이오"},mult=0.80)),
 "추가 자금조달·희석 (저신뢰 소형주 기말가치 −12%)": build(shock_px(names={n for n in META if META[n]["conf"]=="낮음"},mult=0.88)),
 "무위험금리 +100bp": build(rf={k:v+0.01 for k,v in RF.items()}),
 "원화 강세 (수출 대형주 −10%, 내수·방산 +3%)": build(shock_px(sectors={"대형반도체","자동차"},mult=0.90)),
}
L.append("\n### 민감도: 균형형 종합순위 변동 (기준 대비)\n")
L.append("| 종목 | "+" | ".join(f"{k.split('(')[0].strip()}" for k in SCEN)+" | 최대변동 |")
L.append("|---|"+ "---:|"*(len(SCEN)+1))
insta=[]
for name in sorted(META,key=lambda n:idx["3Y"][n]["rank_bal"]):
    deltas=[]
    for k,B in SCEN.items():
        j={r["name"]:r for r in B["3Y"]}
        deltas.append(j[name]["rank_bal"]-idx["3Y"][name]["rank_bal"])
    mx=max(abs(d) for d in deltas)
    insta.append((name,mx))
    L.append(f"| {name} | "+" | ".join(f"{d:+d}" if d else "0" for d in deltas)+f" | {mx} |")
L.append("\n- **순위 불안정 종목(3년 기준, 최대 순위변동 ≥4)**: "+", ".join(f"{n}({m}계단)" for n,m in sorted(insta,key=lambda x:-x[1]) if m>=4))

open('/tmp/claude-0/-home-user-effective-tribble/7742eeb0-1748-5d25-b889-a3f3ed6c53be/scratchpad/krx/tables.md','w').write("\n".join(L))
print("\n".join(L[-40:]))
print("\n[생성완료] tables.md", len("\n".join(L)), "chars")
