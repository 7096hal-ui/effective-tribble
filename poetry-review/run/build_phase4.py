"""최종 점검(판정을 다시 내리지 않는 품질 점검) 프롬프트와 워크플로 생성기.

V1: 규약 11절 준수와 문서 간 일관성 점검. V2: 최종 보고서의 원문 사실 주장 적대적 검증.
두 점검자 모두 시의 우열을 새로 판단하지 않는다.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = ROOT / "run"

def read(p):
    return (ROOT / p).read_text(encoding="utf-8")

NUM_A, NUM_B = read("originals/numbered_A.txt"), read("originals/numbered_B.txt")
POEM_A, POEM_B = read("originals/poem_A.txt"), read("originals/poem_B.txt")
REPORT = read("final_report.md")

OPS = """[조정자 운영 지시]
- 너는 시 비교 비평의 최종 보고서를 점검하는 품질 점검자다. 이 메시지의 입력만 사용하라.
- 어떤 도구도 사용하지 마라. 파일 읽기·검색·셸·웹 조회를 하지 말고 작업 디렉터리의 파일도 열지 마라.
- 두 시의 우열이나 축별 값을 새로 판단하지 마라. 네 임무는 아래에 적힌 점검뿐이다.
- [건NN]·[여NN]은 조정자가 붙인 위치 표지다. 원문 첫 줄의 '제목:'은 제출 양식의 표지다.
- 문제가 없으면 없다고 짧게 말하라. 분량을 채우지 마라. 한국어로 쓰고, 최종 응답 전체가 점검 보고서다."""

V1_TASK = f"""[과업 V1: 규약 준수와 문서 간 일관성]
(1) 최종 보고서가 아래 '규약 11절'의 요구를 빠짐없이 지키는지 항목별로 점검하라. 순서, 1절의 한 문장 요건(판정 선택지, 이유, 조건이 같은 문장에 있는지), 각 작품 비평의 독립성과 깊이의 대칭, 4절 표와 결정적 이유 2~3개, 형식 차이와 수행 차이의 구분, 5절의 세 가지 구별(바꾼 것, 바꾸지 못한 것, 남은 불일치), 6절의 실행 형태 한 문장, 7절의 등급·해소 조건·개작 방향 최대 3개·다른 작품 방식 강요 금지·편집 판단 한 문장, 8절이 규정된 선택지 중 하나로 끝나는지, 분량 10,000자 이내인지를 본다.
(2) 최종 보고서의 수치와 판단이 '종합 문서 요약'과 어긋나는 곳이 있는지 점검하라.
(3) 보고서 안에서 서로 모순되는 진술이 있는지 점검하라.
산출: 문제마다 [위치] [문제] [고칠 방향] [중요도: 높음/중간/낮음]. 1,200자 이내.

[규약 11절]
{read("run/section11.md")}

[종합 문서 요약 — 조정자가 확정한 값]
- 최종 축 값(양수 = 「건축」 쪽): A 0, B 0, C 0, D +1, E −1, F 0. 기본 가중치 S = +0.1.
- 14개 가중치 설정: 「건축」 쪽 11, 동률 1(균등), 「여행의 미래」 쪽 2(축 D 제거, 축 E 40%).
- 한 축만 한 단계 옮기면 역전되는 경우: C −1, D 0, A −1. 강화되는 경우: B +1, E 0, A +1.
- 하위 에이전트: 실질 13개(정독 2, 비교 2, 가설 2, 감사 1, 표적 재독 6), 분량 압축 7개, 합계 20개.
- 편집 판단: 두 작품 모두 조건부 진행. 판정 채택: 조건부 진행."""

V2_TASK = """[과업 V2: 원문 사실 주장의 적대적 검증]
아래 최종 보고서에서 원문에 관한 사실 주장을 모두 찾아 행 번호 사본과 대조하라. 대상은 인용의 정확성, 위치 표지, 횟수·개수, 구문 기술(예: 어떤 말이 몇째 행에 도착한다, 무엇이 한 문장이다, 연 경계를 건넌다, 마침표로 닫힌다), 어떤 말이 뒤에서 다시 나오는지 여부 등이다.
원문에서 확인되지 않거나 부정확한 주장만 보고하라. 해석이나 가치 판단은 그렇다고 표시되어 있는 한 대상이 아니다. 다만 해석이 사실처럼 서술된 곳은 보고하라. 확실하지 않으면 '의심'으로 표시하라.
참고로 조정자가 세어 둔 수치는 다음과 같다. 네가 직접 원문으로 다시 확인하라.
- 「건축」 본문(제사 제외): '유일한' 6회, '오로지' 5회.
- 「건축」: "저주" 문장과 "마음 편안히" 문장 사이에 아홉 문장.
- 「여행의 미래」: 연 21개, 연 경계 20개, 그중 통사가 건너가는 경계 12개(2개는 독해에 따라 갈림).
산출: 문제마다 [보고서 위치] [주장] [원문 대조 결과] [오류/의심] [고칠 방향]. 1,200자 이내."""

def block():
    return (f"[원문 「건축」 — 수정 금지]\n```text\n{POEM_A}```\n[행 번호 사본]\n```text\n{NUM_A}```\n\n"
            f"[원문 「여행의 미래」 — 수정 금지]\n```text\n{POEM_B}```\n[행 번호 사본]\n```text\n{NUM_B}```")

PROMPTS = {
    "V1": "\n\n".join([OPS, V1_TASK, block(), "[최종 보고서]\n" + REPORT]),
    "V2": "\n\n".join([OPS, V2_TASK, block(), "[최종 보고서]\n" + REPORT]),
}
for k, v in PROMPTS.items():
    (RUN / "prompts" / f"{k}.txt").write_text(v, encoding="utf-8")

JS = r"""export const meta = {
  name: 'poetry-phase4-final-check',
  description: '최종 점검: 규약 11절 준수·문서 간 일관성(V1)과 원문 사실 주장 적대적 검증(V2). 판정은 다시 내리지 않음',
  phases: [{ title: 'Check', detail: 'V1, V2 병렬' }],
}
const PROMPTS = __PROMPTS__
phase('Check')
const [V1, V2] = await parallel([
  () => agent(PROMPTS.V1, { label: 'V1 규약·일관성 점검', phase: 'Check', effort: 'high' }),
  () => agent(PROMPTS.V2, { label: 'V2 원문 사실 검증', phase: 'Check', effort: 'xhigh' }),
])
return { V1, V2 }
"""
JS = JS.replace("__PROMPTS__", json.dumps(PROMPTS, ensure_ascii=False, indent=2))
(RUN / "phase4_workflow.js").write_text(JS, encoding="utf-8")
print({k: len(v) for k, v in PROMPTS.items()})
