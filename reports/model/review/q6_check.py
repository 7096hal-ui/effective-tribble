# 3번 Q6 구조모형 검산 + 학급 내 위치 분포를 넣은 혼합 계산(4번 검토용)
import numpy as np
from math import erf, sqrt
Phi = np.vectorize(lambda z: 0.5*(1+erf(z/sqrt(2))))
from statistics import NormalDist
N = NormalDist()
cut = N.inv_cdf(0.30)   # 하위 30% = C+ 이하
x, w = np.polynomial.hermite_e.hermegauss(81); w = w/w.sum()
def p_f(f, rho):
    return 1 - Phi((cut - sqrt(rho)*f)/sqrt(1-rho))
print("cut", round(cut,3))
for k in (4,5,6):
    print(k, "과목 동급생 전체 충족비율:", [round(float(np.sum(w*p_f(x,r)**k)),2) for r in (0.5,0.7,0.85)])
print("잠재 위치별(5과목):")
for pct in (20,35,50,65,80):
    f = N.inv_cdf(pct/100)
    print(pct, [round(float(p_f(np.array([f]),r)[0]**5),2) for r in (0.5,0.7,0.85)])
# 위치를 하나의 값이 아니라 분포로 두면(예: 중앙 50, SD 20백분위 상당) 결과 범위
for mu_pct, sd_z in ((40,0.6),(50,0.6),(60,0.6),(50,1.0)):
    mu = N.inv_cdf(mu_pct/100)
    fs = mu + sd_z*x
    print("위치분포 중앙", mu_pct, "SDz", sd_z, [round(float(np.sum(w*p_f(fs,r)**5)),2) for r in (0.5,0.7,0.85)])
