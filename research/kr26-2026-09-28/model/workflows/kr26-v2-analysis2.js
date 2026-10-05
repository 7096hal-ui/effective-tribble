export const meta = {
  name: 'kr26-v2-analysis2',
  description: '반대심문·최종심사(검색 없음): 종목별 I 약세론 에이전트가 독립 분석을 공격하고, J 최종심사 에이전트가 가중 통합해 MC 입력(시나리오·변동성·민감도)을 확정',
  phases: [
    { title: 'Bear', detail: '종목별 반대심문(I)' },
    { title: 'Judge', detail: '종목별 최종심사(J)' },
  ],
}

const ROOT = '/home/user/effective-tribble/research/kr26-2026-09-28'
const DECK = ROOT + '/data/final/macro_deck.md'

const COMMON = `[공통 작업 맥락 — 반드시 준수]
• 프로젝트: 한국 상장사 26개 종목의 1·3·5년 기대 총주주수익률(TSR)과 위험조정수익률 순위를 산출하는 기관투자자급 멀티에이전트 리서치. 당신은 그중 한 역할을 독립적으로 수행한다.
• 기준: 분석 기준 시각 2026-10-06(화) KST. 기준 주가는 데이터 팩의 KRX 종가(원칙적으로 2026-10-02 금요일 종가). 전망 종료일: 1년 2027-10-02(토요일이므로 직전 거래일 종가), 3년 2029-10-02, 5년 2031-10-02(휴장 시 직전 거래일). 통화 KRW.
• 수익률 정의: 세전·수수료 차감 전 원화 TSR = (기간 말 주당가치 + 기간 중 누적 주당배당) ÷ 기준주가 − 1 (배당 재투자 없음). 희석과 자사주 소각은 '현재 보유 1주' 기준 주당가치에 반영한다.
• 검색 금지: 이 역할은 WebSearch·WebFetch를 쓰지 않는다(세션 검색 한도 보존). 입력 파일과 사전지식(2026년 6월까지)만 쓰고, 사전지식에서 온 사실은 '사전지식(미검증)'으로 표시하며, 데이터 팩의 최신 값과 충돌하면 데이터 팩을 따른다. 데이터 팩에 없는 최신 수치를 지어내지 말라.
• 공통 거시 데크(${DECK})를 Read로 읽고 따르라.
• 확률을 확정적 사실처럼 쓰지 말고, 과도한 정밀성으로 허위 확신을 만들지 말라.
• 출력: 한국어. StructuredOutput 스키마로만 반환한다. 퍼센트 필드는 퍼센트 단위 숫자, 금액은 원 단위 숫자.`

const NUM = { type: ['number', 'null'] }
const H3 = { type: 'object', properties: { h1: { type: 'number' }, h3: { type: 'number' }, h5: { type: 'number' } }, required: ['h1', 'h3', 'h5'] }
const H3S = { type: 'object', properties: { h1: { type: 'string' }, h3: { type: 'string' }, h5: { type: 'string' } }, required: ['h1', 'h3', 'h5'] }
const CONF = { type: 'string', enum: ['높음', '보통', '낮음'] }
const LABEL = { type: 'string', enum: ['극단비관', '비관', '기준', '낙관', '극단낙관'] }
const SC = { type: 'object', properties: { label: LABEL, probability_pct: { type: 'number' }, value_per_share_krw: { type: 'number' }, cum_dividend_per_share_krw: { type: 'number' }, description: { type: 'string' } }, required: ['label', 'probability_pct', 'value_per_share_krw', 'cum_dividend_per_share_krw', 'description'] }
const SCS = { type: 'array', items: SC, minItems: 3, maxItems: 6 }
const SEV = { type: 'string', enum: ['높음', '중간', '낮음'] }

const BEAR_SCHEMA = { type: 'object', properties: {
  name: { type: 'string' }, code: { type: 'string' }, strongest_bear_case: { type: 'string' },
  critiques: { type: 'array', items: { type: 'object', properties: { target: { type: 'string' }, issue: { type: 'string' }, doc_question: { type: 'integer' }, evidence: { type: 'string' }, severity: SEV, recommended_adjustment: { type: 'string' } }, required: ['target', 'issue', 'doc_question', 'evidence', 'severity', 'recommended_adjustment'] } },
  checks: { type: 'object', properties: { priced_in: { type: 'string' }, base_rate: { type: 'string' }, margin_cashflow: { type: 'string' }, customer_power: { type: 'string' }, tech_market: { type: 'string' }, dilution_funding: { type: 'string' }, liquidity: { type: 'string' }, dependency: { type: 'string' }, success_probability: { type: 'string' }, terminal_multiple: { type: 'string' } }, required: ['priced_in', 'base_rate', 'margin_cashflow', 'customer_power', 'tech_market', 'dilution_funding', 'liquidity', 'dependency', 'success_probability', 'terminal_multiple'] },
  recommended_changes: H3S, what_would_prove_bear_wrong: { type: 'string' } },
  required: ['name', 'code', 'strongest_bear_case', 'critiques', 'checks', 'recommended_changes', 'what_would_prove_bear_wrong'] }

const SHOCKS = ['FX_KRW_STRONG', 'FX_KRW_WEAK', 'RATES_UP', 'RATES_DOWN', 'MULTIPLE_DOWN', 'SEMI_DOWN', 'SEMI_UP', 'AUTO_DOWN', 'BIO_POS_DOWN', 'DILUTION_UP', 'KEY_CUSTOMER_DOWN']
const SENS = { type: 'object', properties: Object.fromEntries(SHOCKS.map(k => [k, H3])), required: SHOCKS }
const JH = { type: 'object', properties: { scenarios: SCS, confidence: CONF, one_line_driver: { type: 'string' } }, required: ['scenarios', 'confidence', 'one_line_driver'] }
const NARR_KEYS = ['thesis', 'priced_in', 'market_vs_own', 'outlook', 'valuation_and_fair_value', 'scenario_summary', 'catalysts', 'downside_risks', 'invalidation', 'kpis', 'low_rank_or_upside_triggers']
const JUDGE_SCHEMA = { type: 'object', properties: {
  name: { type: 'string' }, code: { type: 'string' }, p0_krw: { type: 'number' }, investable: { type: 'boolean' }, investable_note: { type: 'string' },
  integration_summary: { type: 'string' },
  weights: { type: 'object', properties: { specialist_pct: { type: 'number' }, generalist_pct: { type: 'number' }, rationale: { type: 'string' } }, required: ['specialist_pct', 'generalist_pct', 'rationale'] },
  disagreements: { type: 'array', items: { type: 'object', properties: { topic: { type: 'string' }, specialist: { type: 'string' }, generalist: { type: 'string' }, bear: { type: 'string' }, resolution: { type: 'string' } }, required: ['topic', 'specialist', 'generalist', 'bear', 'resolution'] } },
  bear_accepted: { type: 'array', items: { type: 'string' } }, bear_rejected: { type: 'array', items: { type: 'string' } },
  final: { type: 'object', properties: { h1: JH, h3: JH, h5: JH }, required: ['h1', 'h3', 'h5'] },
  vol: { type: 'object', properties: { sigma1_pct: { type: 'number' }, sigma_lr_pct: { type: 'number' }, rationale: { type: 'string' } }, required: ['sigma1_pct', 'sigma_lr_pct', 'rationale'] },
  sensitivities: SENS,
  narrative: { type: 'object', properties: Object.fromEntries(NARR_KEYS.map(k => [k, { type: 'string' }])), required: NARR_KEYS },
  optimism_priced_in_score: { type: 'integer', minimum: 1, maximum: 5 }, optimism_rationale: { type: 'string' },
  permanent_loss_note: { type: 'string' }, data_quality_note: { type: 'string' } },
  required: ['name', 'code', 'p0_krw', 'investable', 'investable_note', 'integration_summary', 'weights', 'disagreements', 'bear_accepted', 'bear_rejected', 'final', 'vol', 'sensitivities', 'narrative', 'optimism_priced_in_score', 'optimism_rationale', 'permanent_loss_note', 'data_quality_note'] }

function files(s) {
  return `- 데이터 팩: ${ROOT}/data/pack/${s.code}.json
- D-전문가 분석: ${ROOT}/data/phase2/spec/${s.code}.json
- D-일반 분석: ${ROOT}/data/phase2/gen/${s.code}.json
- E 포렌식: ${ROOT}/data/phase2/E/${s.code}.json
- G 정량·위험: ${ROOT}/data/phase2/G/${s.code}.json
- H 베이스레이트: ${ROOT}/data/phase2/H/${s.code}.json`
}

function bearTask(s) {
  return `[역할: I. 반대심문·약세론 에이전트]
대상: ${s.name}(${s.code}, ${s.market}, ${s.group}). 아래 파일을 모두 Read로 읽어라.
${files(s)}
두 독립 분석(전문가·일반)과 포렌식·정량·베이스레이트 결과를 공격하라. 무조건 반대하지 말고 근거 있는 반론만 세우되, 가장 강한 반론을 빠뜨리지 말라. 원 지시문의 10개 질문을 모두 점검하고 critiques의 doc_question에 번호를 적어라:
1 시장이 이미 낙관론을 주가에 반영하지 않았는가? 2 예상 성장률이 업계 베이스레이트보다 지나치게 높은가? 3 매출이 늘어도 마진과 현금흐름이 악화될 수 있는가? 4 고객사의 자체개발·이원화·가격인하 요구가 있는가? 5 기술이 대체되거나 시장이 예상보다 작을 가능성은? 6 자금조달이나 희석을 누락하지 않았는가? 7 낮은 유동성이 기대수익률을 왜곡하지 않는가? 8 단일 수주·임상·고객·정책에 과도하게 의존하지 않는가? 9 성공 시나리오 확률을 과대평가하지 않았는가? 10 5년 뒤 적용한 멀티플이 성숙기업으로서 너무 높은가?
recommended_changes에는 기간별로 시나리오 확률·주당가치를 어떻게 바꿔야 하는지 구체적 숫자로 적어라(예: '낙관 25→15%, 비관 주당가치 80,000→60,000원'). 분석이 타당하면 바꿀 필요가 없다고 적어도 된다.`
}

function judgeTask(s, bear) {
  return `[역할: J. 최종심사 에이전트]
대상: ${s.name}(${s.code}, ${s.market}, ${s.group}). 아래 파일을 모두 Read로 읽어라.
${files(s)}
[I 반대심문 결과]
${JSON.stringify(bear)}

임무: 독립 분석과 반대심문을 통합해 몬테카를로 엔진에 들어갈 최종 입력을 확정한다.
1) 단순 산술평균이 아니라 데이터 품질, 산업 전문성, 가정의 타당성에 따라 전문가·일반 분석가의 가중치를 정하고 이유를 적어라(weights). 중요한 의견 차이는 숨기지 말고 disagreements에 적어라.
2) 반대심문의 각 비판을 수용(bear_accepted) 또는 기각(bear_rejected)하고 이유를 적어라. 타당한 비판은 시나리오 확률과 주당가치에 실제로 반영하라.
3) final의 기간별 시나리오: 최소 비관·기준·낙관, 필요하면 극단비관·극단낙관(사건확률 트리 가지나 G가 추정한 −80% 이상 손실 꼬리). 확률 합계는 정확히 100. value_per_share_krw는 기간 말 '현재 1주' 기준 주당가치(E의 희석·소각 반영), cum_dividend_per_share_krw는 누적 주당배당(E 참고). 각 값은 그 시나리오의 평균적 결과다. 엔진이 G의 변동성으로 시나리오 내부 분산을 더하므로 값에 분산을 섞지 말라.
4) 베이스레이트 축소는 엔진이 H의 사전분포와 분석가 간 이견·데이터 품질로 기계적으로 적용한다. 당신은 결과를 사전분포 쪽으로 미리 끌어당기지 말고(이중 축소 금지), 베이스레이트 근거는 특정 가정이 비현실적인지 판단하는 데만 써라. 신뢰도 점수를 곱하는 식의 이중 벌점도 금지한다.
5) confidence는 데이터 품질과 추정 난이도를 반영해 기간별로 정하라(데이터 팩의 기준주가가 단일 출처이거나 사전지식 의존이 크면 낮춰라).
6) vol: G의 sigma1·sigma_lr를 검토해 확정하라. Sortino가 낮은 변동성 추정이나 짧은 주가이력 때문에 과대평가되지 않게 하라.
7) sensitivities: 공통 거시 데크 8절의 11개 표준 충격 각각에 대해, 기간별 확률가중 기대 누적 TSR이 몇 %p 변하는지(부호 포함) 추정하라. 해당 노출이 없으면 0에 가깝게 둔다. 노출 크기와 서로 일관되게 하라(예: 수출 비중, 메모리 매출 비중, 최대고객 비중).
8) narrative: 보고서에 쓸 근거를 기간별 관점 차이를 살려 간결하게 적어라 — 핵심 투자논지, 현재 주가가 암시하는 기대, 시장 전망과 자체 전망의 차이, 매출·이익·현금흐름 전망, 가치평가 방법과 적정가치 범위, 비관·기준·낙관 요약, 핵심 촉매, 핵심 하방위험, 논지가 무효화되는 구체적 조건, 다음 실적·공시에서 확인할 지표, 순위가 낮다면 그 원인과 순위를 끌어올릴 변화.
9) optimism_priced_in_score(1~5, 5가 현재 주가에 낙관이 가장 많이 반영됨)와 근거, 영구자본손실 위험, 데이터 품질 한계를 적어라.
10) 데이터 팩에 신뢰할 만한 기준주가가 없거나 거래가 불가능하면 investable=false로 두고 사유를 적되, 가능한 범위의 참고 추정은 남겨라.`
}

function expTsr(j) {
  const p0 = j.p0_krw
  const f = sc => sc.reduce((a, x) => a + x.probability_pct / 100 * ((x.value_per_share_krw + x.cum_dividend_per_share_krw) / p0 - 1), 0)
  return { h1: +(f(j.final.h1.scenarios) * 100).toFixed(1), h3: +(f(j.final.h3.scenarios) * 100).toFixed(1), h5: +(f(j.final.h5.scenarios) * 100).toFixed(1) }
}

const res = await pipeline(args.stocks,
  s => agent(COMMON + '\n\n' + bearTask(s), { label: 'I약세론:' + s.name, phase: 'Bear', schema: BEAR_SCHEMA, effort: 'high' }),
  (bear, s) => agent(COMMON + '\n\n' + judgeTask(s, bear), { label: 'J최종심사:' + s.name, phase: 'Judge', schema: JUDGE_SCHEMA, effort: 'high' }),
)
return res.map((j, i) => j ? { name: args.stocks[i].name, code: j.code, investable: j.investable, exp: expTsr(j), conf: [j.final.h1.confidence, j.final.h3.confidence, j.final.h5.confidence], vol: [j.vol.sigma1_pct, j.vol.sigma_lr_pct] } : { name: args.stocks[i].name, failed: true })
