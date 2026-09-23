"""1차 병렬 작업(R_A, R_B, J_1, J_2) 프롬프트와 워크플로 스크립트 생성기.

원문 파일에서 텍스트를 그대로 읽어 JSON 문자열로 박아 넣으므로, 프롬프트 속 원문은
originals/*.txt 와 바이트 단위로 같다. 생성된 프롬프트는 run/prompts/ 에 보존한다.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = ROOT / "run"
(RUN / "prompts").mkdir(exist_ok=True)

def read(p):
    return (ROOT / p).read_text(encoding="utf-8")

POEM = {"A": read("originals/poem_A.txt"), "B": read("originals/poem_B.txt")}
NUM = {"A": read("originals/numbered_A.txt"), "B": read("originals/numbered_B.txt")}
TITLE = {"A": "건축", "B": "여행의 미래"}
COMMON = read("run/common_rules.md")
CRITERIA_FULL = read("criteria.md")
# 심사자에게는 규약 본문만 준다(조정자용 머리 주석과 강건성 지시 문단 제외).
crit_lines = CRITERIA_FULL.split("\n")
start = next(i for i, l in enumerate(crit_lines) if l.startswith("다음 기준과 기본 가중치를"))
CRITERIA = "\n".join(
    l for l in crit_lines[start:]
    if not l.startswith("기본 비중은 언어·형식·인식·구조를")
    and not l.startswith("기본 판정을 내리기 위해")
).replace("\n\n\n", "\n\n").strip()
CRITERIA += "\n\n기본 판정을 내리기 위해 기준이나 가중치를 사후 변경하지 마라."

OPS_READER = """[조정자 운영 지시]
- 너는 시 비평 작업의 한 부분만 맡은 하위 검토자다. 이 메시지에 들어 있는 입력만 사용하라.
- 어떤 도구도 사용하지 마라. 파일 읽기·검색·셸·웹 조회를 하지 말고, 작업 디렉터리의 파일도 열지 마라.
- 원문은 '원문(수정 금지)'과 '참고용 행 번호 사본' 두 형태로 제공된다. 사본의 __MARKS__ 같은 표지는 조정자가 붙인 위치 표지일 뿐 원문의 일부가 아니다. 위치는 이 표지로 적어라.
- 원문 첫 줄의 '제목:'은 제출 양식의 표지이며, 작품 제목은 그 뒤의 말이다.
- 보고서는 한국어로 쓴다."""

OPS_JUDGE = OPS_READER.replace(
    "어떤 도구도 사용하지 마라.",
    "결과 제출용 StructuredOutput 외에는 어떤 도구도 사용하지 마라.",
).replace("__MARKS__", "[건NN]·[여NN]")
MARK = {"A": "[건NN]", "B": "[여NN]"}

READER_TASK = """[정독 과업]
너는 아래 작품 한 편만 전담하여 정독한다. 산출물은 정독 보고서 하나이며, 공백·줄바꿈·기호 포함 2,200자 이내로 쓴다(여유를 두고 1,900자 안팎을 목표로 하라).

1. 텍스트에 명시된 사태·발화의 전개를 최소한의 해석으로 요약한다. 요약이 완전히 해석 중립적이라고 주장하지 않는다.
2. 형식, 호흡, 인칭·시제, 어휘, 반복과 주요 전환을 기술한다. 세지 않은 수치나 음운 패턴을 만들어 내지 않는다.
3. 작품이 수행하는 과제를 근거와 함께 잠정 구성한다. 저자의 의도가 아니다. 중요한 대안이 있을 때만 두 번째 과제를 제시한다.
4. 가장 설득력 있는 호의적 독해를 전개한다. 이 구획에서는 결함을 섞지 않는다. 시작부터 결말까지의 연결을 설명한다.
5. 그 독해와 자기 과제를 기준으로 성취와 실패 후보를 각각 최대 3개 검토한다. 문제마다 비판을 철회하게 할 원문상의 관찰을 적는다.

다른 작품과 비교하거나, 공통 기준의 점수를 매기거나, 종합 순위를 내리지 마라.

형식: 1~5를 같은 번호의 소제목으로 구분하라. 최종 응답 전체가 보고서 본문이다. 앞뒤에 인사·설명·메타 발언을 붙이지 마라."""

JUDGE_TASK = """[비교 과업]
아래에 두 작품이 P, Q 순서로 제시된다. P는 먼저 제시된 작품, Q는 나중에 제시된 작품을 가리키는 표기일 뿐 서열이 아니다. 작품 제목은 그대로 둔다.

1. 두 작품을 모두 직접 읽고, 각 작품의 중심 과제와 전체 작동 방식을 짧게 기술한다.
2. 형식·장르의 단순한 차이와, 그 선택이 만든 실제 성취의 차이를 구별한다. 특정 형식의 취향을 공통 기준으로 위장하지 않는다.
3. 여섯 축 각각에 대해 양쪽의 짧은 인용, 관찰, 효과, 비교 이유, 판단을 제시한다. 한쪽의 장점과 다른 쪽의 결함을 서로 다른 잣대로 비교하지 않는다.
4. 축별 비교값 d를 아래 규칙으로 표시한다.
   +2: P의 우세가 뚜렷함
   +1: P가 근소 우세
    0: 근거상 대등함
   -1: Q가 근소 우세
   -2: Q의 우세가 뚜렷함
   근거 부족이나 중요한 해석의 미결정은 U로 표시한다. U를 0으로 바꾸지 않는다.
   비교값은 이유의 요약이지 미적 가치의 측정값이 아니다. 뚜렷함과 근소함은 결정적인 텍스트 효과의 차이로 설명한다.
5. 핵심 대목들이 작품 전체에서 어떻게 결합하는지 별도로 검토한다. 축별 장단점의 목록으로 전체 평가를 대체하지 않는다. 전체 효과도 선언한 기준과 연결하며, 숨겨진 일곱 번째 잣대를 도입하지 않는다.
6. 잠정 종합 판정 한 문장, 그 판단을 좌우하는 근거 최대 3개, 이를 뒤집을 수 있는 가장 강한 대안 독해를 제출한다.

[제출 형식] StructuredOutput으로 제출한다.
- report: 비교 심사 보고서 본문(마크다운). 공백·줄바꿈·기호 포함 3,200자 이내(여유를 두고 2,800자 안팎을 목표로 하라). 1~6을 같은 번호의 소제목으로 구분하되 3과 4는 축별로 묶어도 된다. 축별 d 값을 본문에도 적는다.
- d: 축 A~F 각각의 비교값("+2", "+1", "0", "-1", "-2", "U" 중 하나). 본문에 적은 값과 일치해야 한다.
- verdict: 6의 잠정 종합 판정 한 문장(본문과 같은 문장).
- 가중치를 곱한 종합 수치는 조정자가 따로 다루므로 보고서에 쓰지 마라."""

def poem_block(label, key):
    head = f"### {label}「{TITLE[key]}」" if label else f"### 작품「{TITLE[key]}」"
    return (
        f"{head}\n\n원문(수정 금지):\n```text\n{POEM[key]}```\n\n"
        f"참고용 행 번호 사본:\n```text\n{NUM[key]}```"
    )

def reader_prompt(key):
    return "\n\n".join([OPS_READER.replace("__MARKS__", MARK[key]), COMMON, READER_TASK, "[입력 원문]", poem_block(None, key)])

def judge_prompt(first, second):
    return "\n\n".join([
        OPS_JUDGE, COMMON, "## 고정 평가 규약\n\n" + CRITERIA, JUDGE_TASK,
        "[입력 원문]", poem_block("P: ", first), poem_block("Q: ", second),
    ])

PROMPTS = {
    "R_A": reader_prompt("A"),
    "R_B": reader_prompt("B"),
    "J_1": judge_prompt("A", "B"),  # P=A「건축」, Q=B「여행의 미래」
    "J_2": judge_prompt("B", "A"),  # P=B「여행의 미래」, Q=A「건축」
}

# 격리 점검: 정독자 프롬프트에 다른 작품의 고유 구절이 없어야 한다.
assert "버스" not in PROMPTS["R_A"] and "카산드라" not in PROMPTS["R_A"]
assert "파이드로스" not in PROMPTS["R_B"] and "말의 집" not in PROMPTS["R_B"]
assert "가중치" not in PROMPTS["R_A"] and "가중치" not in PROMPTS["R_B"]
assert "[여" not in PROMPTS["R_A"] and "[건" not in PROMPTS["R_B"] and "__MARKS__" not in "".join(PROMPTS.values())
for k in ("J_1", "J_2"):
    assert POEM["A"] in PROMPTS[k] and POEM["B"] in PROMPTS[k]
    assert "J_1" not in PROMPTS[k] and "J_2" not in PROMPTS[k]
assert PROMPTS["J_1"].index("「건축」") < PROMPTS["J_1"].index("「여행의 미래」")
assert PROMPTS["J_2"].index("「여행의 미래」") < PROMPTS["J_2"].index("「건축」")

for k, v in PROMPTS.items():
    (RUN / "prompts" / f"{k}.txt").write_text(v, encoding="utf-8")

JS = r"""export const meta = {
  name: 'poetry-phase1-independent',
  description: '1차 병렬: 작품별 독립 정독 2개(R_A, R_B) + 제시 순서를 뒤집은 독립 비교 심사 2개(J_1, J_2)',
  phases: [
    { title: 'Independent', detail: 'R_A, R_B, J_1, J_2 서로 결과 비공유' },
    { title: 'Length', detail: '분량 상한 초과 시에만 원본 보존 후 압축' },
  ],
}

const PROMPTS = __PROMPTS__
const LIMIT = { R_A: 2200, R_B: 2200, J_1: 3200, J_2: 3200 }
const DVAL = { type: 'string', enum: ['+2', '+1', '0', '-1', '-2', 'U'] }
const JUDGE_SCHEMA = {
  type: 'object',
  properties: {
    report: { type: 'string' },
    d: {
      type: 'object',
      properties: { A: DVAL, B: DVAL, C: DVAL, D: DVAL, E: DVAL, F: DVAL },
      required: ['A', 'B', 'C', 'D', 'E', 'F'],
    },
    verdict: { type: 'string' },
  },
  required: ['report', 'd', 'verdict'],
}

function compressPrompt(text, limit) {
  const target = Math.floor(limit * 0.85)
  return `아래는 한 검토자의 보고서다. 이 보고서를 공백·줄바꿈·기호 포함 ${limit}자 이내로 줄여라(목표 ${target}자 안팎).
- 새로운 주장·관찰·인용·판단을 추가하지 마라.
- 인용문은 한 글자도 바꾸지 말고 그대로 두거나 통째로 빼라.
- 판단의 방향과 강도(비교값 d, 판정 문장 포함)를 바꾸지 마라.
- 소제목 구조를 유지하라.
- 어떤 도구도 사용하지 마라. 최종 응답 전체가 줄인 보고서 본문이다.

----- 보고서 시작 -----
${text}
----- 보고서 끝 -----`
}

async function fitLength(key, text) {
  const limit = LIMIT[key]
  const out = { original: text, originalLength: text.length, final: text, compressed: false }
  let cur = text
  for (let i = 0; i < 2 && cur.length > limit; i++) {
    log(`${key}: ${cur.length}자 > ${limit}자, 압축 ${i + 1}회차`)
    const c = await agent(compressPrompt(cur, limit), { label: `compress:${key}:${i + 1}`, phase: 'Length', effort: 'medium' })
    if (!c) break
    cur = c.trim()
    out.compressed = true
  }
  out.final = cur
  out.finalLength = cur.length
  out.withinLimit = cur.length <= limit
  return out
}

phase('Independent')
const jobs = [
  () => agent(PROMPTS.R_A, { label: 'R_A 정독', phase: 'Independent', effort: 'high' })
          .then(t => t && fitLength('R_A', t.trim())),
  () => agent(PROMPTS.R_B, { label: 'R_B 정독', phase: 'Independent', effort: 'high' })
          .then(t => t && fitLength('R_B', t.trim())),
  () => agent(PROMPTS.J_1, { label: 'J_1 비교(P=건축)', phase: 'Independent', effort: 'xhigh', schema: JUDGE_SCHEMA })
          .then(async r => r && ({ d: r.d, verdict: r.verdict, text: await fitLength('J_1', r.report.trim()) })),
  () => agent(PROMPTS.J_2, { label: 'J_2 비교(P=여행의 미래)', phase: 'Independent', effort: 'xhigh', schema: JUDGE_SCHEMA })
          .then(async r => r && ({ d: r.d, verdict: r.verdict, text: await fitLength('J_2', r.report.trim()) })),
]
const [R_A, R_B, J_1, J_2] = await parallel(jobs)
const missing = Object.entries({ R_A, R_B, J_1, J_2 }).filter(([, v]) => !v).map(([k]) => k)
if (missing.length) log(`결과 없음: ${missing.join(', ')}`)
return { R_A, R_B, J_1, J_2 }
"""
JS = JS.replace("__PROMPTS__", json.dumps(PROMPTS, ensure_ascii=False, indent=2))
(RUN / "phase1_workflow.js").write_text(JS, encoding="utf-8")
print({k: len(v) for k, v in PROMPTS.items()})
