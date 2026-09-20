# -*- coding: utf-8 -*-
"""축별 판정을 고정한 채 가중치 배분만 바꾸어 기준 지지량을 재계산한다.

합산 규칙: 우세 작품이 해당 축의 가중치를 전부 가져가고, 대등 축은 절반씩 나눈다.
출력 수치는 합계 100으로 환산한 '기준 지지량'이며 작품의 품질 점수가 아니다.

판정 집합은 둘이다.
  RECORD  — 원문 없이 인용 단편만으로 내린 04단계의 축별 판정
  REVIEW  — 원문 확보 뒤 독립 심사 2인 + 조정 1인으로 다시 내린 10단계의 축별 판정
"""

from fractions import Fraction as F

# (축 이름, 기본 가중치)
AXES = [
    ("A. 언어의 필연성",              25),
    ("B. 형식과 내용의 상호강제",      25),
    ("C. 이미지·개념의 인식적 생산성",  20),
    ("D. 구조적 완결성",              15),
    ("E. 목소리의 일관성과 자기 인식",  10),
    ("F. 위험 감수의 성취",            5),
]

# 'A' = 「건축」 우세, 'B' = 「여행의 미래」 우세, '=' = 판정 불가
RECORD = ["=", "=", "B", "A", "B", "="]
REVIEW = ["B", "A", "B", "A", "B", "B"]


def tally(weights, verdicts):
    """weights: 축 인덱스 -> 가중치. 합계 100 환산 (건축, 여행의 미래) 반환."""
    total = sum(weights.values())
    if total == 0:
        raise ValueError("가중치 합이 0이다")
    a = F(0)
    b = F(0)
    for i in range(len(AXES)):
        w = F(weights.get(i, 0))
        v = verdicts[i]
        if v == "A":
            a += w
        elif v == "B":
            b += w
        else:
            a += w / 2
            b += w / 2
    return a * 100 / total, b * 100 / total


def base():
    return {i: w for i, (_, w) in enumerate(AXES)}


def winner(a, b):
    if a > b:
        return "「건축」"
    if b > a:
        return "「여행의 미래」"
    return "대등"


def row(name, weights, verdicts):
    a, b = tally(weights, verdicts)
    return name, float(a), float(b), winner(a, b)


def scenarios(verdicts):
    """가중치를 흔드는 시험. 축별 판정은 고정한다."""
    out = [row("기본", base(), verdicts)]
    out.append(row("전부 균등", {i: 1 for i in range(len(AXES))}, verdicts))

    # F를 단독 최대로: F=30, 나머지는 기존 비율을 유지하며 합계 70으로 축소
    rest = sum(w for i, (_, w) in enumerate(AXES) if i != 5)
    w = {i: F(wt) * 70 / rest for i, (_, wt) in enumerate(AXES) if i != 5}
    w[5] = F(30)
    out.append(row("F를 단독 최대로", w, verdicts))

    for i, (nm, _) in enumerate(AXES):
        w = base()
        del w[i]
        out.append(row(f"{nm.split('.')[0]} 제거", w, verdicts))
    return out


def swaps(verdicts):
    """F와 기존 최대 축(A 또는 B)의 가중치를 맞바꾼다."""
    out = []
    for i in (0, 1):
        w = base()
        w[i], w[5] = w[5], w[i]
        out.append(row(f"F ↔ {AXES[i][0].split('.')[0]} 맞바꿈", w, verdicts))
    return out


def weight_boundary(verdicts, axis, lo=0, hi=25):
    """한 축의 가중치를 낮춰 갈 때 판정이 뒤집히는 경계를 훑는다."""
    out = []
    for v in range(lo, hi + 1):
        w = base()
        w[axis] = v
        a, b = tally(w, verdicts)
        out.append((v, float(a), float(b), winner(a, b)))
    return out


def flip_each(verdicts):
    """가중치가 아니라 축별 판정을 하나씩 흔든다. 기록이 수행하지 않은 시험이다."""
    out = []
    for i, (nm, _) in enumerate(AXES):
        for alt in ("A", "B", "="):
            if alt == verdicts[i]:
                continue
            v = list(verdicts)
            v[i] = alt
            a, b = tally(base(), v)
            label = {"A": "「건축」 우세", "B": "「여행의 미래」 우세", "=": "판정 불가"}[alt]
            out.append((f"{nm.split('.')[0]}를 {label}로", float(a), float(b), winner(a, b)))
    return out


def report(title, verdicts):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")
    print(f"축별 판정: " + ", ".join(
        f"{nm.split('.')[0]}={v}" for (nm, _), v in zip(AXES, verdicts)))
    print("\n| 배분 | 건축 | 여행의 미래 | 우세 |")
    print("|---|---:|---:|---|")
    for nm, a, b, wn in scenarios(verdicts):
        print(f"| {nm} | {a:.2f} | {b:.2f} | {wn} |")
    print()
    for nm, a, b, wn in swaps(verdicts):
        print(f"{nm}: 건축 {a:.2f} / 여행의 미래 {b:.2f} → {wn}")
    print("\n판정 하나를 흔드는 시험 (기본 가중치):")
    for nm, a, b, wn in flip_each(verdicts):
        print(f"  {nm}: 건축 {a:.2f} / 여행의 미래 {b:.2f} → {wn}")


if __name__ == "__main__":
    report("RECORD — 04단계의 축별 판정 (원문 없이)", RECORD)
    print("\nC축 가중치를 낮출 때의 경계:")
    for c, a, b, wn in weight_boundary(RECORD, 2, 0, 7):
        print(f"  C={c:2d} → 건축 {a:.2f} / 여행의 미래 {b:.2f} → {wn}")

    report("REVIEW — 10단계의 축별 판정 (원문 확보 뒤)", REVIEW)
    print("\nA축 가중치를 낮출 때의 경계:")
    for c, a, b, wn in weight_boundary(REVIEW, 0, 0, 25):
        if c % 5 == 0 or 14 <= c <= 18:
            print(f"  A={c:2d} → 건축 {a:.2f} / 여행의 미래 {b:.2f} → {wn}")
