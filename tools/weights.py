# -*- coding: utf-8 -*-
"""축별 판정을 고정한 채 가중치 배분만 바꾸어 기준 지지량을 재계산한다.

합산 규칙: 우세 작품이 해당 축의 가중치를 전부 가져가고, 대등 축은 절반씩 나눈다.
출력 수치는 합계 100으로 환산한 '기준 지지량'이며 작품의 품질 점수가 아니다.
"""

from fractions import Fraction as F

# 축: (이름, 기본 가중치, 판정) — 'A' = 「건축」 우세, 'B' = 「여행의 미래」 우세, '=' = 판정 불가
AXES = [
    ("A. 언어의 필연성",        25, "="),
    ("B. 형식과 내용의 상호강제", 25, "="),
    ("C. 이미지·개념의 인식적 생산성", 20, "B"),
    ("D. 구조적 완결성",        15, "A"),
    ("E. 목소리의 일관성과 자기 인식", 10, "B"),
    ("F. 위험 감수의 성취",       5, "="),
]

LABEL = {"A": "건축", "B": "여행의 미래"}


def tally(weights):
    """weights: 축 인덱스 -> 가중치. 합계 100 환산 (건축, 여행의 미래) 반환."""
    total = sum(weights.values())
    if total == 0:
        raise ValueError("가중치 합이 0이다")
    a = F(0)
    b = F(0)
    for i, (_, _, verdict) in enumerate(AXES):
        w = F(weights.get(i, 0))
        if verdict == "A":
            a += w
        elif verdict == "B":
            b += w
        else:
            a += w / 2
            b += w / 2
    return a * 100 / total, b * 100 / total


def base():
    return {i: w for i, (_, w, _) in enumerate(AXES)}


def winner(a, b):
    if a > b:
        return "「건축」"
    if b > a:
        return "「여행의 미래」"
    return "대등"


def row(name, weights):
    a, b = tally(weights)
    return name, float(a), float(b), winner(a, b)


def scenarios():
    out = [row("기본", base())]
    out.append(row("전부 균등", {i: 1 for i in range(len(AXES))}))

    # F를 단독 최대로: F=30, 나머지는 기존 비율을 유지하며 합계 70으로 축소
    rest = sum(w for i, (_, w, _) in enumerate(AXES) if i != 5)
    w = {i: F(wt) * 70 / rest for i, (_, wt, _) in enumerate(AXES) if i != 5}
    w[5] = F(30)
    out.append(row("F를 단독 최대로", w))

    for i, (nm, _, _) in enumerate(AXES):
        w = base()
        del w[i]
        out.append(row(f"{nm.split('.')[0]} 제거", w))
    return out


def swaps():
    """F와 기존 최대 축(A 또는 B)의 가중치를 맞바꾼다."""
    out = []
    for i in (0, 1):
        w = base()
        w[i], w[5] = w[5], w[i]
        out.append(row(f"F ↔ {AXES[i][0].split('.')[0]} 맞바꿈", w))
    return out


def c_boundary():
    """C축 가중치를 낮출 때 판정이 뒤집히는 경계를 찾는다."""
    res = []
    for c in range(0, 21):
        w = base()
        w[2] = c
        a, b = tally(w)
        res.append((c, float(a), float(b), winner(a, b)))
    return res


def verdict_flip():
    """대등 축 하나를 「건축」 우세로 돌리면 어떻게 되는가 (기록이 수행하지 않은 시험)."""
    out = []
    for i in (0, 1, 5):
        saved = AXES[i]
        AXES[i] = (saved[0], saved[1], "A")
        a, b = tally(base())
        out.append((f"{saved[0].split('.')[0]}를 「건축」 우세로", float(a), float(b), winner(a, b)))
        AXES[i] = saved
    return out


if __name__ == "__main__":
    print("| 배분 | 건축 | 여행의 미래 | 우세 |")
    print("|---|---:|---:|---|")
    for nm, a, b, wn in scenarios():
        print(f"| {nm} | {a:.2f} | {b:.2f} | {wn} |")
    print()
    for nm, a, b, wn in swaps():
        print(f"{nm}: 건축 {a:.2f} / 여행의 미래 {b:.2f} → {wn}")
    print()
    print("C축 가중치별 경계:")
    for c, a, b, wn in c_boundary():
        if c <= 7:
            print(f"  C={c:2d} → 건축 {a:.2f} / 여행의 미래 {b:.2f} → {wn}")
    print()
    print("대등 축을 한쪽 우세로 돌리는 시험 (기본 가중치):")
    for nm, a, b, wn in verdict_flip():
        print(f"  {nm}: 건축 {a:.2f} / 여행의 미래 {b:.2f} → {wn}")
