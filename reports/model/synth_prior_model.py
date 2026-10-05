# 종합(5번)용 독립 사전 모형: 2번 에이전트 결과를 보기 전에 만든 '판단' 기반 숫자.
# 목적: 2번 결과와 교차검증. 숫자 자체는 문헌 계수가 아니라 판단임.
import itertools, math
from datetime import date

SUBJ = ["국어", "수학", "영어", "통합사회", "통합과학"]
# 누적 필요 실질시간(중앙값): 현재 상태 -> 해당 등급(시험 당일 50% 달성 기준)
base = {  # Q1 기준 모델(IQ120, 중학 상위10% 지식 유지, 고교 0)
 "국어":   {9:0, 8:0, 7:0, 6:20, 5:60, 4:150, 3:300, 2:560, 1:1000},
 "수학":   {9:0, 8:60, 7:150, 6:250, 5:520, 4:850, 3:1250, 2:1800, 1:2600},
 "영어":   {9:0, 8:30, 7:70, 6:120, 5:220, 4:360, 3:520, 2:780, 1:1200},
 "통합사회": {9:0, 8:10, 7:25, 6:50, 5:100, 4:170, 3:270, 2:400, 1:600},
 "통합과학": {9:0, 8:20, 7:45, 6:80, 5:150, 4:250, 3:380, 2:550, 1:800},
}
q2 = {k: dict(v) for k, v in base.items()}
q2["영어"] = {9:0, 8:0, 7:0, 6:0, 5:0, 4:0, 3:40, 2:180, 1:480}
pers = {  # Q3 개인화
 "국어":   {9:0, 8:0, 7:0, 6:0, 5:30, 4:100, 3:220, 2:450, 1:850},
 "수학":   {9:0, 8:120, 7:260, 6:400, 5:730, 4:1100, 3:1580, 2:2200, 1:3100},
 "영어":   {9:0, 8:0, 7:0, 6:0, 5:0, 4:0, 3:40, 2:180, 1:480},
 "통합사회": {9:0, 8:10, 7:25, 6:50, 5:100, 4:175, 3:280, 2:420, 1:640},
 "통합과학": {9:0, 8:40, 7:90, 6:150, 5:250, 4:370, 3:530, 2:740, 1:1050},
}
HIST = 55  # 한국사 고정
OVERHEAD = 1.10  # 14개월 동안의 망각·복습 오버헤드(판단)

def combos(tab, target_sum=15, top=6, floor=None):
    res = []
    for gs in itertools.product(range(1, 10), repeat=5):
        if sum(gs) > target_sum: continue
        if floor and any(g > floor.get(s, 9) for s, g in zip(SUBJ, gs)): continue
        h = sum(tab[s][g] for s, g in zip(SUBJ, gs))
        res.append((h, gs))
    res.sort()
    seen, out = set(), []
    for h, gs in res:
        if gs in seen: continue
        seen.add(gs); out.append((h, gs))
        if len(out) >= top: break
    return out

def best_avg(tab, budget):
    best = None
    for gs in itertools.product(range(1, 10), repeat=5):
        h = (sum(tab[s][g] for s, g in zip(SUBJ, gs)) + HIST) * OVERHEAD
        if h <= budget:
            a = sum(gs) / 5
            if best is None or a < best[0] or (a == best[0] and h < best[1]):
                best = (a, h, gs)
    return best

Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
def p_success(med_req, lo_req, hi_req, med_av, lo_av, hi_av, z=1.2816):
    s_r = (math.log(hi_req) - math.log(lo_req)) / (2 * z)
    s_a = (math.log(hi_av) - math.log(lo_av)) / (2 * z)
    d = math.log(med_av) - math.log(med_req)
    return Phi(d / math.sqrt(s_r**2 + s_a**2)), s_r, s_a

for name, tab in [("Q1 기준", base), ("Q2 영어2~3", q2), ("Q3 개인화", pers)]:
    print(f"== {name}: 합계<=15 최소비용 조합 (한국사 {HIST}h·오버헤드 {OVERHEAD} 반영 전/후)")
    for h, gs in combos(tab):
        tot = (h + HIST) * OVERHEAD
        print("  ", dict(zip(SUBJ, gs)), f"과목합 {h}h → 총 {tot:.0f}h", f"영어제외평균 {(sum(gs)-gs[2])/4:.2f}")
    print("   (수학 5등급 이내 제약)", [(round((h+HIST)*OVERHEAD), gs) for h, gs in combos(tab, floor={"수학":5}, top=2)])

d0, d1, exam = date(2026, 9, 9), date(2026, 10, 5), date(2027, 11, 18)
for start in (d0, d1):
    days = (exam - start).days
    print(f"\n시작 {start} → 수능 {exam}: {days}일 ({days/30.44:.1f}개월)")
    for label, h, dpw in [("명목12h·주7일", 12, 7), ("명목12h·주6.5일", 12, 6.5), ("실질6h", 6, 6.5), ("실질7h", 7, 6.5), ("실질8h", 8, 6.5)]:
        print(f"   {label}: {days * dpw / 7 * h:,.0f}h")

print("\n예산 → 최선 평균(Q3 개인화)")
for b in [1200, 1600, 2000, 2400, 2800, 3200, 4000, 5000]:
    a, h, gs = best_avg(pers, b)
    print(f"  {b}h: 평균 {a:.1f} {dict(zip(SUBJ, gs))} (사용 {h:.0f}h)")
