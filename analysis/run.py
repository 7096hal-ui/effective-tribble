# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0,'/tmp/claude-0/-home-user-effective-tribble/7742eeb0-1748-5d25-b889-a3f3ed6c53be/scratchpad/krx')
import numpy as np
from engine import simulate, metrics, composite, WEIGHTS
from model import UNIVERSE, S_LIQ as S

# 2026-09-18 국고채 수익률 (기간대응 무위험수익률)
RF = {"1Y":0.03976, "3Y":0.04034, "5Y":0.04221}
YRS = {"1Y":1.0, "3Y":3.0, "5Y":5.0}
# 벤치마크 기대 연환산수익률 (거시 시나리오 정합)
BENCH = {"KOSPI":{"1Y":0.040,"3Y":0.010,"5Y":0.030},
         "KOSDAQ":{"1Y":0.070,"3Y":0.060,"5Y":0.060}}

META = {u[0]:dict(code=u[1],mkt=u[2],px=u[3],asof=u[4],sec=u[5],conf=u[6]) for u in UNIVERSE}

OUT={}
for h in ["1Y","3Y","5Y"]:
    rows=[]
    for i,(name,meta) in enumerate(META.items()):
        sce,sig,pw = S[name][h]
        scen=[{"p":p,"px":px,"div":dv} for (p,px,dv) in sce]
        R = simulate(meta["px"], scen, sig, p_wipe=pw, years=YRS[h], seed=20260921+i*7919+hash(h)%1000)
        m = metrics(R, YRS[h], RF[h], BENCH[meta["mkt"]][h])
        rows.append({"name":name,"m":m,**meta})
    composite(rows,h)
    OUT[h]=rows

# 순위 부여
for h,rows in OUT.items():
    key='e_cum' if h=='1Y' else 'e_ann'
    for k,field in [("rank_ret",lambda r:-r["m"][key]),("rank_risk",lambda r:(-r["m"]["sortino"],-r["m"]["cvar10"],r["m"]["p_loss"])),
                    ("rank_bal",lambda r:-r["score_균형형"]),("rank_agg",lambda r:-r["score_공격형"]),("rank_def",lambda r:-r["score_방어형"])]:
        for i,r in enumerate(sorted(rows,key=field)): r[k]=i+1

json.dump({h:[{kk:(vv if not isinstance(vv,dict) else vv) for kk,vv in r.items()} for r in rows] for h,rows in OUT.items()},
          open('/tmp/claude-0/-home-user-effective-tribble/7742eeb0-1748-5d25-b889-a3f3ed6c53be/scratchpad/krx/results.json','w'), ensure_ascii=False)

def pc(x,d=1): return f"{100*x:.{d}f}"
for h in ["1Y","3Y","5Y"]:
    rows=sorted(OUT[h],key=lambda r:r["rank_bal"])
    print(f"\n{'='*150}\n■ {h} — 균형형 종합순위\n{'='*150}")
    print(f"{'균형':>3}{'기대':>4}{'위험':>4}  {'종목':<12}{'현재가':>10}{'기대누적':>9}{'기대연환산':>10}{'중앙값':>9}{'P10':>8}{'P90':>8}{'손실%':>7}{'30%↓':>7}{'Sortino':>8}{'CVaR10':>8}{'초과':>7}  신뢰")
    for r in rows:
        m=r["m"]
        print(f"{r['rank_bal']:>3}{r['rank_ret']:>4}{r['rank_risk']:>4}  {r['name']:<12}{r['px']:>10,}{pc(m['e_cum']):>9}{pc(m['e_ann']):>10}{pc(m['med_cum']):>9}{pc(m['p10']):>8}{pc(m['p90']):>8}{pc(m['p_loss']):>7}{pc(m['p_loss30']):>7}{m['sortino']:>8.2f}{pc(m['cvar10']):>8}{pc(m['excess']):>7}  {r['conf']}")
