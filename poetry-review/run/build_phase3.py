"""표적 재독(규약 7절, 최대 1회) 프롬프트와 워크플로 생성기.

대상: 종합 부호를 바꿀 수 있는 축 B·C·E (조정자 잠정표에서 한 단계 변동만으로 S의 부호가 바뀌는 축).
각 질문을 제시 순서를 뒤집은 두 에이전트에게 준다(작품 순서와 주장 순서를 함께 뒤집음).
입력: 원문, 공통 규칙, 해당 축 규약, 질문, 출처를 밝히지 않은 상충 주장 두 개. 1차·2차 보고서 전문은 주지 않는다.
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
CRIT = read("criteria.md")

def axis_text(letter):
    start = CRIT.index(f"\n{letter}. ") + 1
    end = CRIT.index("\n\n", start)
    return CRIT[start:end]

OPS = """[조정자 운영 지시]
- 너는 시 비교 비평의 '표적 재독'을 맡은 검토자다. 이 메시지의 입력만 사용하라.
- 어떤 도구도 사용하지 마라. 파일 읽기·검색·셸·웹 조회를 하지 말고 작업 디렉터리의 파일도 열지 마라.
- [건NN]·[여NN]은 조정자가 붙인 위치 표지이며 원문의 일부가 아니다. 원문 첫 줄의 '제목:'은 제출 양식의 표지다.
- 아래 '상충 주장'은 앞선 검토에서 나온 주장을 출처 없이 옮긴 것이다. 어느 쪽도 권위가 아니다. 원문으로 직접 확인해 판단하라. 두 주장 외의 제3의 판단도 가능하다.
- 한 축만 판단하라. 다른 축의 장단점을 이 축에 끌어오지 마라(중복 계산 금지).
- 보고서는 한국어로 쓴다. 최종 응답 전체가 보고서 본문이다."""

QUESTIONS = {
    "B": {
        "q": "축 B(형식과 내용의 상호작용)에서 두 작품을 같은 잣대로 비교하라. (1) 「여행의 미래」에서 연 경계를 건너는 통사(예: 여02~04, 여07~09, 여20~28, 여29~32, 여36~37, 여41~45, 여52~55, 여60~62), 산문 행 전환(여58~59), \"마치.\"(여61)가 작품 전체의 경험을 조직하는가, 아니면 효과가 결말부에 몰리고 나머지는 분할에 그치는가. (2) 「건축」의 인칭·시제 설계(건06~12), 문단·쉼표 리듬, 건09/건10의 문장 중간 행갈이(의도 미확인)는 작품 전체를 얼마나 조직하는가. (3) 각 형식의 기능과 비용을 대칭적으로 따져 축 B 값을 정하라.",
        "claims": [
            "「건축」의 인칭·시제 이동(욕망→당위→예언→완료→현재의 보수)이 작품 전체를 조직해 '짓기'를 문법으로 수행한다. 「여행의 미래」의 형식 효과는 산문 행 전환·'라는'에 의한 되돌림·'마치.'가 있는 결말부에 몰려 있고, 중반의 행갈이는 주로 나열을 나누는 데 그친다. → 「건축」 근소 우세.",
            "「여행의 미래」는 거의 모든 연 경계를 통사가 건너가 한 번의 승차를 '정거장처럼 끊기며 이어지는' 하나의 발화로 조직한다(소리 목록이 여러 연을 지나 '까지'에서 닫히고 '교향시'로 명명됨, 머리 명사 '목소리;'가 여41에서 시작한 구의 다섯째 행(여45)에야 도착, '정거장마다' 뒤의 연 구분). 여기에 결말부의 형식 사건이 더해지므로 「건축」의 전면적 시제 설계와 대등하다. → 대등.",
        ],
    },
    "C": {
        "q": "축 C(이미지·개념·관계의 인식적 생산성)에서 두 작품을 같은 잣대로 비교하라. 외부 전승(예: 카산드라 신화의 함의)과 작품 바깥의 익숙함 비교는 판단 근거에서 빼고, 규약 C의 주의(감각적 이미지만을 시적 사고로 인정하지 말 것)를 지켜라. 각 작품의 이미지·개념 연결이 대상을 새롭게 보게 하는지, 이후 전개에서 의미를 확장하는지를 원문으로 비교해 축 C 값을 정하라.",
        "claims": [
            "「여행의 미래」는 버스 소음을 지명을 짜는 직조·교향시로, 안내 음성을 몸 없는 예언으로, 승객을 조상·후손으로, 조약돌을 말 없는 아이로 다시 보게 하고, 이것들이 제목의 '미래'와 발화 불능으로 수렴한다. 「건축」의 '말의 집'은 선언된 등식이고, 확장은 주로 역설 진술로 이루어진다. → 「여행의 미래」 근소 우세.",
            "'익숙함'은 작품 밖 비교이고 '추상에 머문다'는 규약 C가 금한 감각 우대다. 「건축」은 결여를 소유로 뒤집고, 제사가 말한 글의 결함(반복)을 꿈의 조건으로, '홀로 살 것'을 '무수한 인물이 등장하는 곳'으로, 대답하지 못하는 글을 '출구를 아는 당신'으로 바꾼다. → 대등.",
        ],
    },
    "E": {
        "q": "축 E(목소리의 통제와 정서적 설득력)에서 두 작품을 같은 잣대로 비교하라. 「건축」의 서법(\"저주라고 느낄 수도 있을 것이다\"), 행동 동사(\"허우적대기\", \"발버둥칠\"), 반복(\"늙을 것이고 끝을 볼 때까지 늙을 것이고\"), 짧은 과거형(\"갖고 싶었다\"/\"가졌다\"), 화법 전환(건12)과, 「여행의 미래」의 의인화 수식(\"흐느끼는\", \"가련한\", \"미소 짓는다\"), 발화 불능(여58~60), \"아무 일도 없던 듯이 / 아무 일도 없었지만\", \"마치.\", 조약돌을 같은 기준으로 검토해, 정서가 언어와 사태의 조직으로 뒷받침되는 정도와 어조 통제를 비교하고 축 E 값을 정하라. 비인격적 화법이나 자기모순을 그 자체로 결함으로 보지 마라.",
        "claims": [
            "「여행의 미래」의 중심 정서는 말하지 못하는 사태와 '사랑하고 있습니다. / 라는' 구문이 받친다. 「건축」의 정서는 '저주라고 느낄 수도', '발버둥칠', '마음 편안히'처럼 주로 진술된다. → 「여행의 미래」 근소 우세.",
            "'저주라고 느낄 수도 있을 것이다'는 가능성 서법이고 '발버둥칠'·'허우적대기'는 행동이다. 「건축」도 '늙을 것이고' 반복, '갖고 싶었다/가졌다', 건12의 화법 전환으로 정서를 조직한다. 반면 「여행의 미래」의 '흐느끼는'·'가련한'·'미소 짓는다'는 사물에 정서를 선언한다. → 대등.",
        ],
    },
}

OUTPUT = """[산출 형식] 공백·줄바꿈·기호 포함 1,100자 이내(여유를 두고 950자 안팎).
1) 핵심 관찰 최대 3개. 각 관찰에 원문 위치와 짧은 인용(1회 2행·120자 이내), 관찰→효과→축 기준과의 관계를 적는다.
2) 상충 주장 두 개 각각에 대해 '유효 / 부분 유효 / 기각'과 한 문장 이유.
3) 이 판단을 바꿀 원문 관찰 한 가지.
4) 마지막 줄은 정확히 다음 형식: `축 {X} 값: <+2|+1|0|-1|-2|U> (양수 = 「건축」 쪽, 음수 = 「여행의 미래」 쪽)`"""

def poem_block(key):
    return (f"### 「{TITLE[key]}」\n\n원문(수정 금지):\n```text\n{POEM[key]}```\n\n"
            f"참고용 행 번호 사본:\n```text\n{NUM[key]}```")

def build(axis, order, claim_order):
    q = QUESTIONS[axis]
    claims = [q["claims"][i] for i in claim_order]
    claim_txt = "\n".join(f"- 주장 {n}: {c}" for n, c in zip(("ㄱ", "ㄴ"), claims))
    return "\n\n".join([
        OPS, COMMON, f"## 해당 축 규약\n\n{axis_text(axis)}",
        f"[질문]\n{q['q']}", f"[상충 주장]\n{claim_txt}", OUTPUT.replace("{X}", axis),
        "[입력 원문] (제시 순서는 서열이 아니다)", poem_block(order[0]), poem_block(order[1]),
    ])

PROMPTS = {}
for axis in ("B", "C", "E"):
    PROMPTS[f"T{axis}_1"] = build(axis, ("A", "B"), (0, 1))
    PROMPTS[f"T{axis}_2"] = build(axis, ("B", "A"), (1, 0))
for k, v in PROMPTS.items():
    assert POEM["A"] in v and POEM["B"] in v
    (RUN / "prompts" / f"{k}.txt").write_text(v, encoding="utf-8")

JS = r"""export const meta = {
  name: 'poetry-phase3-targeted-reread',
  description: '표적 재독 1회: 부호를 좌우하는 축 B·C·E를 제시 순서를 뒤집은 두 검토자에게 각각 질의',
  phases: [
    { title: 'Reread', detail: '축 B·C·E × 제시 순서 2' },
    { title: 'Length', detail: '분량 상한 초과 시에만 원본 보존 후 압축' },
  ],
}
const PROMPTS = __PROMPTS__
const LIMIT = 1100

function compressPrompt(text) {
  return `아래 보고서를 공백·줄바꿈·기호 포함 ${LIMIT}자 이내로 줄여라(목표 950자). 새 주장·인용·판단을 추가하지 말고, 인용문은 그대로 두거나 통째로 빼며, 판정(유효/부분 유효/기각, 축 값)과 마지막 줄을 바꾸지 마라. 도구를 쓰지 마라. 최종 응답 전체가 줄인 보고서다.

----- 보고서 시작 -----
${text}
----- 보고서 끝 -----`
}
async function fit(key, text) {
  const out = { original: text, originalLength: text.length, compressed: false }
  let cur = text
  for (let i = 0; i < 2 && cur.length > LIMIT; i++) {
    log(`${key}: ${cur.length}자 > ${LIMIT}자, 압축 ${i + 1}회차`)
    const c = await agent(compressPrompt(cur), { label: `compress:${key}:${i + 1}`, phase: 'Length', effort: 'medium' })
    if (!c) break
    cur = c.trim(); out.compressed = true
  }
  out.final = cur; out.finalLength = cur.length; out.withinLimit = cur.length <= LIMIT
  return out
}
phase('Reread')
const keys = Object.keys(PROMPTS)
const results = await parallel(keys.map(k => () =>
  agent(PROMPTS[k], { label: `표적 재독 ${k}`, phase: 'Reread', effort: 'xhigh' }).then(t => t && fit(k, t.trim()))))
const out = {}
keys.forEach((k, i) => { out[k] = results[i] })
return out
"""
JS = JS.replace("__PROMPTS__", json.dumps(PROMPTS, ensure_ascii=False, indent=2))
(RUN / "phase3_workflow.js").write_text(JS, encoding="utf-8")
print({k: len(v) for k, v in PROMPTS.items()})
print(axis_text("B")[:60], "|", axis_text("E")[:40])
