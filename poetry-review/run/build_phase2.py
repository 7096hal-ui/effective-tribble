"""2차 병렬 작업(H_A, H_B, Q) 프롬프트와 워크플로 스크립트 생성기.

입력: 두 원문(+행 번호 사본), 고정 규약, issues.md, 익명화한 1차 보고서 네 개.
전달하지 않는 것: 모델 이름, 다수/소수 표시, 가중 종합 수치, 조정자 대응표(J_1/J_2 이름).
설계 선택: 가설 검사자에게는 검사 대상 가설이 앞세우는 작품을 '뒤에' 제시한다
(1차에서 두 비교 보고서가 모두 먼저 제시된 작품을 앞세웠으므로, 가설 쪽에 순서 이점을 주지 않기 위함).
감사자 Q에게는 사용자가 제시한 순서(「건축」→「여행의 미래」)를 쓴다.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = ROOT / "run"

def read(p):
    return (ROOT / p).read_text(encoding="utf-8")

POEM = {"A": read("originals/poem_A.txt"), "B": read("originals/poem_B.txt")}
NUM = {"A": read("originals/numbered_A.txt"), "B": read("originals/numbered_B.txt")}
TITLE = {"A": "건축", "B": "여행의 미래"}
COMMON = read("run/common_rules.md")
CRITERIA_FULL = read("criteria.md")
start = CRITERIA_FULL.index("다음 기준과 기본 가중치를")
CRITERIA = CRITERIA_FULL[start:].strip()
ISSUES = read("issues.md")
REPORTS = [
    ("정독(건)", "「건축」만 받은 정독 보고서", read("reports/reading_A.md")),
    ("정독(여)", "「여행의 미래」만 받은 정독 보고서", read("reports/reading_B.md")),
    ("비교 甲", "두 작품을 P=「건축」, Q=「여행의 미래」 순서로 받은 비교 보고서. 비교값 d의 양수는 「건축」 쪽", read("reports/judge_1.md")),
    ("비교 乙", "두 작품을 P=「여행의 미래」, Q=「건축」 순서로 받은 비교 보고서. 비교값 d의 양수는 「여행의 미래」 쪽", read("reports/judge_2.md")),
]

OPS = """[조정자 운영 지시]
- 너는 시 비교 비평 작업의 후속 검토자 한 명이다. 이 메시지에 들어 있는 입력만 사용하라.
- 어떤 도구도 사용하지 마라. 파일 읽기·검색·셸·웹 조회를 하지 말고, 작업 디렉터리의 파일도 열지 마라.
- 원문은 '원문(수정 금지)'과 '참고용 행 번호 사본'으로 제공된다. [건NN]·[여NN] 표지는 조정자가 붙인 위치 표지일 뿐 원문의 일부가 아니다. 위치는 이 표지로 적어라.
- 원문 첫 줄의 '제목:'은 제출 양식의 표지이며, 작품 제목은 그 뒤의 말이다.
- 이 단계는 앞선 보고서를 참고하는 후속 검토이며 새로운 독립 표본이 아니다. 보고서는 작성자를 익명화했다. 보고서의 수, 판정의 일치나 불일치, 서술의 자신감을 근거로 삼지 마라. 보고서는 새로운 관찰의 공급원이지 원문 대신 인용할 권위가 아니다. 모든 주장은 원문으로 다시 확인하라.
- 평가 축은 '축 A~F'로, 작품은 제목으로 적어 축과 작품을 혼동하지 마라.
- 보고서는 한국어로 쓴다. 최종 응답 전체가 보고서 본문이다. 앞뒤에 인사·설명·메타 발언을 붙이지 마라."""

def hyp_task(fav, other):
    t, o = TITLE[fav], TITLE[other]
    return f"""[과업: 「{t}」 우위 가설 검사]
'「{t}」이(가) 「{o}」보다 더 뛰어나다'는 가설을 고정 평가 규약 아래에서 검사하라.

두 작품 모두에 같은 호의와 엄격함을 적용해도 「{t}」 우위를 성립시킬 수 있는 가장 강한 논증을 세워라. 「{o}」에 대한 기존의 불리한 평가도 가장 강한 대안 독해와 대조하라. 「{t}」를 이기게 만드는 것이 임무는 아니다.

그 논증이 성립하지 않으면 성립하지 않는다고 보고하라. 「{t}」 우위 가설의 가장 약한 핵심 고리, 이를 무너뜨릴 수 있는 관찰, 실제 반증 여부를 적어라. 논점은 최대 3개다.

산출: 공백·줄바꿈·기호 포함 1,600자 이내(여유를 두고 1,400자 안팎을 목표로 하라).
형식 권장: 논점 1~3(각 논점에 관련 축, 원문 위치와 짧은 인용, 「{o}」 쪽 대안 독해와의 대조) → 가장 약한 핵심 고리 → 그 고리를 무너뜨릴 관찰과 실제 반증 여부 → 마지막 줄에 '가설 판정: 성립 / 부분 성립 / 불성립' 중 하나와 한 문장 이유."""

AUDIT_TASK = """[과업: 텍스트·논증·형식 편향 감사]
아래 1차 보고서 네 개와 쟁점표를 원문과 대조하여, 판정에 중요한 문제만 보고하라.
- 실제 원문에 없는 인용, 잘못된 위치·구문·화자·사건 기술.
- 요약 과정의 손실, 해석을 사실로 둔갑시킨 주장, 작품 바깥 지식에만 의존한 주장.
- 양쪽에 다른 잣대를 적용한 사례, 장르의 차이 자체를 결함으로 취급한 사례.
- 대체·삭제 시험을 원문상의 사실처럼 사용한 사례.
- 하나의 효과를 여러 축에서 중복 계산한 사례.
- 원문과 연결되지 않는 취향을 객관적 결함으로 선언한 사례.
- 정당한 반론 없이 결함이나 합의를 만들어 낸 사례.

문제마다 원문 근거, 오류인지 의심인지, 바로잡을 내용, 판정 영향을 표시하라. 확인하지 못했다는 이유만으로 오류라고 확정하지 마라. 쟁점표(조정자 작성)도 감사 대상에 포함된다.

산출: 공백·줄바꿈·기호 포함 1,800자 이내(여유를 두고 1,600자 안팎을 목표로 하라). 문제는 판정 영향이 큰 순서로 적어라."""

def poem_block(key):
    return (f"### 「{TITLE[key]}」\n\n원문(수정 금지):\n```text\n{POEM[key]}```\n\n"
            f"참고용 행 번호 사본:\n```text\n{NUM[key]}```")

def reports_block():
    parts = ["[1차 보고서 — 익명]"]
    for name, desc, body in REPORTS:
        parts.append(f"=== {name} ({desc}) ===\n{body.strip()}\n=== {name} 끝 ===")
    return "\n\n".join(parts)

def build(task, order):
    return "\n\n".join([
        OPS, COMMON, "## 고정 평가 규약\n\n" + CRITERIA, task,
        "[입력 원문] (제시 순서는 서열이 아니다)", poem_block(order[0]), poem_block(order[1]),
        "[쟁점표 — 조정자 작성]\n\n" + ISSUES.strip(), reports_block(),
    ])

PROMPTS = {
    "H_A": build(hyp_task("A", "B"), ("B", "A")),
    "H_B": build(hyp_task("B", "A"), ("A", "B")),
    "Q": build(AUDIT_TASK, ("A", "B")),
}
for k, v in PROMPTS.items():
    for banned in ("J_1", "J_2", "R_A", "R_B", "Claude", "Opus", "모델 이름:", "S ="):
        assert banned not in v, (k, banned)
    assert POEM["A"] in v and POEM["B"] in v
    (RUN / "prompts" / f"{k}.txt").write_text(v, encoding="utf-8")

JS = r"""export const meta = {
  name: 'poetry-phase2-hypotheses-audit',
  description: '2차 병렬: 「건축」 우위 가설 검사(H_A), 「여행의 미래」 우위 가설 검사(H_B), 텍스트·논증·형식 편향 감사(Q)',
  phases: [
    { title: 'Review', detail: 'H_A, H_B, Q 서로 결과 비공유' },
    { title: 'Length', detail: '분량 상한 초과 시에만 원본 보존 후 압축' },
  ],
}

const PROMPTS = __PROMPTS__
const LIMIT = { H_A: 1600, H_B: 1600, Q: 1800 }

function compressPrompt(text, limit) {
  const target = Math.floor(limit * 0.85)
  return `아래는 한 검토자의 보고서다. 이 보고서를 공백·줄바꿈·기호 포함 ${limit}자 이내로 줄여라(목표 ${target}자 안팎).
- 새로운 주장·관찰·인용·판단을 추가하지 마라.
- 인용문은 한 글자도 바꾸지 말고 그대로 두거나 통째로 빼라.
- 판단의 방향과 강도(가설 판정, 오류/의심 구분, 판정 영향 포함)를 바꾸지 마라.
- 구조를 유지하라. 마지막 줄의 판정 문장은 그대로 둬라.
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

phase('Review')
const [H_A, H_B, Q] = await parallel([
  () => agent(PROMPTS.H_A, { label: 'H_A 「건축」 우위 가설', phase: 'Review', effort: 'xhigh' }).then(t => t && fitLength('H_A', t.trim())),
  () => agent(PROMPTS.H_B, { label: 'H_B 「여행의 미래」 우위 가설', phase: 'Review', effort: 'xhigh' }).then(t => t && fitLength('H_B', t.trim())),
  () => agent(PROMPTS.Q, { label: 'Q 근거 감사', phase: 'Review', effort: 'xhigh' }).then(t => t && fitLength('Q', t.trim())),
])
return { H_A, H_B, Q }
"""
JS = JS.replace("__PROMPTS__", json.dumps(PROMPTS, ensure_ascii=False, indent=2))
(RUN / "phase2_workflow.js").write_text(JS, encoding="utf-8")
print({k: len(v) for k, v in PROMPTS.items()})
