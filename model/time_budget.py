"""24시간 시간 예산 검증.

모든 값은 '공부일 하루' 기준(분/일). 주간 활동(운동)은 7일 평균으로 환산한다.
실수면(actual sleep)과 침대에 머무는 시간(time in bed, TIB)을 구분한다.
  TIB = 실수면 / 수면효율(sleep efficiency)

값의 성격
  - 수면효율: 건강한 젊은 성인의 문헌 범위(간접 근거, report/evidence 참조)
  - 식사·위생·잡무·이동·전환: 분석자 가정(통계청 생활시간조사 평균보다 짧게 잡은 '최소 현실치')
  - 운동: 사용자가 제시한 주당 목표 + 분석자가 가정한 준비·샤워·이동 전환시간
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LifeBudget:
    name: str
    sleep_efficiency: float          # 실수면 / TIB
    meals: float                     # 세 끼 식사 + 준비·정리 (공부하지 않음)
    hygiene: float                   # 세면, 샤워, 옷 갈아입기
    exercise_week: float             # 주당 유산소 + 근력 운동 (분)
    exercise_sessions: int           # 주당 운동 횟수
    exercise_transition: float       # 회당 준비·이동·운동 후 샤워 추가분 (분)
    meditation: float                # 명상
    chores: float                    # 빨래·청소·장보기·행정 잡무 (일 평균)
    transitions: float               # 활동 사이 전환·버퍼 (공부 블록 밖)
    commute: float                   # 공부 장소 왕복

    def exercise_per_day(self) -> float:
        return (self.exercise_week + self.exercise_sessions * self.exercise_transition) / 7.0

    def items(self) -> dict[str, float]:
        return {
            "식사(3끼, 준비·정리 포함)": self.meals,
            "세면·샤워·옷차림": self.hygiene,
            "운동(주간 합계의 일평균, 전환 포함)": self.exercise_per_day(),
            "명상": self.meditation,
            "생활 잡무": self.chores,
            "활동 간 전환·버퍼": self.transitions,
            "공부 장소 왕복": self.commute,
        }

    def non_sleep_non_study(self) -> float:
        return sum(self.items().values())

    def tib_for(self, actual_sleep_h: float) -> float:
        return actual_sleep_h / self.sleep_efficiency


# 사용자 조건(실수면 8h, 유산소 150~300분/주, 근력 40~50분/주, 명상 30분/일)을 모두 지키는 세 가지 가정
BUDGETS = [
    LifeBudget("빠듯한 가정", sleep_efficiency=0.95, meals=60, hygiene=25,
               exercise_week=150 + 40, exercise_sessions=4, exercise_transition=15,
               meditation=30, chores=15, transitions=10, commute=0),
    LifeBudget("기준 가정", sleep_efficiency=0.93, meals=80, hygiene=35,
               exercise_week=225 + 45, exercise_sessions=5, exercise_transition=20,
               meditation=30, chores=25, transitions=15, commute=20),
    LifeBudget("여유 있는 가정", sleep_efficiency=0.90, meals=110, hygiene=50,
               exercise_week=300 + 50, exercise_sessions=6, exercise_transition=25,
               meditation=30, chores=40, transitions=25, commute=40),
]


def max_study_hours(b: LifeBudget, actual_sleep_h: float = 8.0, leisure_min: float = 0.0) -> float:
    tib = b.tib_for(actual_sleep_h)
    return 24.0 - tib - (b.non_sleep_non_study() + leisure_min) / 60.0


def report() -> str:
    lines = []
    lines.append("## 조건을 모두 지킬 때(실수면 8h) 공부에 쓸 수 있는 최대 시간\n")
    header = "| 항목 | " + " | ".join(b.name for b in BUDGETS) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(BUDGETS) + 1))
    lines.append("| 수면효율(가정) | " + " | ".join(f"{b.sleep_efficiency:.2f}" for b in BUDGETS) + " |")
    lines.append("| 침대 시간(TIB, h) | " + " | ".join(f"{b.tib_for(8.0):.2f}" for b in BUDGETS) + " |")
    keys = list(BUDGETS[0].items().keys())
    for k in keys:
        lines.append(f"| {k} (분) | " + " | ".join(f"{b.items()[k]:.0f}" for b in BUDGETS) + " |")
    lines.append("| 수면·공부 외 합계(h) | " + " | ".join(f"{b.non_sleep_non_study()/60:.2f}" for b in BUDGETS) + " |")
    lines.append("| 자유 여가 0분일 때 최대 명목 공부(h) | " + " | ".join(f"{max_study_hours(b):.2f}" for b in BUDGETS) + " |")
    lines.append("| 14h 대비 부족분(h) | " + " | ".join(f"{14 - max_study_hours(b):.2f}" for b in BUDGETS) + " |")
    for lm in (60, 90, 120):
        lines.append(f"| 자유 여가 {lm}분일 때 최대 명목 공부(h) | " + " | ".join(f"{max_study_hours(b, leisure_min=lm):.2f}" for b in BUDGETS) + " |")
    lines.append("")
    # 14h 일정에서 수면이 얼마나 남는가 (운동·명상 제외, 최소 생활만)
    lines.append("## 14h 명목 공부를 고정할 때 남는 수면(운동·명상 없이 최소 생활만)\n")
    lines.append("| 최소 생활시간(h) | TIB(h) | 실수면(h, 효율 0.90~0.95) | 깨어 있는 시간(h) |")
    lines.append("|---|---|---|---|")
    for life in (1.5, 1.75, 2.0, 2.5, 3.0):
        tib = 24 - 14 - life
        lines.append(f"| {life:.2f} | {tib:.2f} | {tib*0.90:.1f}~{tib*0.95:.1f} | {24 - tib*0.93:.1f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
