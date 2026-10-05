export const meta = {
  name: 'kr26-v2-analysis1',
  description: '독립 분석 1차(검색 없음): 산업군별 E 포렌식·G 정량위험·H 베이스레이트, 종목별 D-전문가·D-일반(F 가치평가 포함)',
  phases: [
    { title: 'EGH', detail: '산업군별 포렌식·정량위험·베이스레이트' },
    { title: 'Analysts', detail: '종목별 산업 전문가 / 독립 일반 분석가' },
  ],
}

const ROOT = '/home/user/effective-tribble/research/kr26-2026-09-28'
const DECK = ROOT + '/data/final/macro_deck.md'

const COMMON = `[공통 작업 맥락 — 반드시 준수]
• 프로젝트: 한국 상장사 26개 종목의 1·3·5년 기대 총주주수익률(TSR)과 위험조정수익률 순위를 산출하는 기관투자자급 멀티에이전트 리서치. 당신은 그중 한 역할을 독립적으로 수행한다. 다른 에이전트의 결론을 추측해 맞추려 하지 말라.
• 기준: 분석 기준 시각 2026-10-06(화) KST. 기준 주가는 데이터 팩의 KRX 종가(원칙적으로 2026-10-02 금요일 종가). 전망 종료일: 1년 2027-10-02(토요일이므로 직전 거래일 종가), 3년 2029-10-02, 5년 2031-10-02(휴장 시 직전 거래일). 통화 KRW.
• 수익률 정의: 세전·수수료 차감 전 원화 TSR = (기간 말 주당가치 + 기간 중 누적 주당배당) ÷ 기준주가 − 1 (배당 재투자 없음). 유상증자·CB/BW 전환·스톡옵션 희석과 자사주 매입·소각은 '현재 보유 1주' 기준 주당가치에 반영한다.
• 검색 금지: 이 역할은 WebSearch·WebFetch를 쓰지 않는다(세션 전체 검색 한도가 거의 소진돼 데이터 수집 단계에만 배정됨). 입력 파일과 당신의 사전지식(2026년 6월까지 학습)만 쓴다. 사전지식에서 온 사실·수치는 반드시 '사전지식(미검증)'으로 표시하고, 데이터 팩의 최신 값과 충돌하면 데이터 팩을 따른다. 사전지식은 2026년 7월 이후의 실적·주가·지정학 변화를 모른다는 점을 감안하라. 데이터 팩에 없는 최신 수치를 지어내지 말라.
• 공통 거시 데크(${DECK})를 반드시 Read로 읽고 그 시나리오 확률·금리·환율·산업 공통가정을 따르라. 다른 가정을 쓰려면 이유를 적어라.
• 확률을 확정적 사실처럼 쓰지 말고, 과도한 정밀성으로 허위 확신을 만들지 말라.
• 출력: 한국어. StructuredOutput 스키마로만 반환한다. 퍼센트 필드는 퍼센트 단위 숫자(예: 12.5 = +12.5%), 금액은 원 단위 숫자.`

const NUM = { type: ['number', 'null'] }
const H3 = { type: 'object', properties: { h1: { type: 'number' }, h3: { type: 'number' }, h5: { type: 'number' } }, required: ['h1', 'h3', 'h5'] }
const H3S = { type: 'object', properties: { h1: { type: 'string' }, h3: { type: 'string' }, h5: { type: 'string' } }, required: ['h1', 'h3', 'h5'] }
const CONF = { type: 'string', enum: ['높음', '보통', '낮음'] }
const LABEL = { type: 'string', enum: ['극단비관', '비관', '기준', '낙관', '극단낙관'] }
const SC = { type: 'object', properties: { label: LABEL, probability_pct: { type: 'number' }, value_per_share_krw: { type: 'number' }, cum_dividend_per_share_krw: { type: 'number' }, description: { type: 'string' } }, required: ['label', 'probability_pct', 'value_per_share_krw', 'cum_dividend_per_share_krw', 'description'] }
const SCS = { type: 'array', items: SC, minItems: 3, maxItems: 6 }

const E_STOCK = { type: 'object', properties: {
  code: { type: 'string' }, name: { type: 'string' },
  earnings_quality: { type: 'string' }, related_party_audit_contingent: { type: 'string' }, concentration: { type: 'string' }, balance_sheet: { type: 'string' },
  dilution_instruments: { type: 'string' }, expected_dilution_pct: H3, capital_raise_note: { type: 'string' },
  dps_path: { type: 'string' }, cum_dividend_per_share_krw: H3, buyback_cancellation: { type: 'string' },
  ownership_governance: { type: 'string' },
  red_flags: { type: 'array', items: { type: 'object', properties: { flag: { type: 'string' }, severity: { type: 'string', enum: ['높음', '중간', '낮음'] }, evidence: { type: 'string' } }, required: ['flag', 'severity', 'evidence'] } },
  forensic_risk_level: { type: 'string', enum: ['높음', '중간', '낮음'] }, per_share_value_adjustments: { type: 'string' }, knowledge_vs_data: { type: 'string' } },
  required: ['code', 'name', 'earnings_quality', 'related_party_audit_contingent', 'concentration', 'balance_sheet', 'dilution_instruments', 'expected_dilution_pct', 'capital_raise_note', 'dps_path', 'cum_dividend_per_share_krw', 'buyback_cancellation', 'ownership_governance', 'red_flags', 'forensic_risk_level', 'per_share_value_adjustments', 'knowledge_vs_data'] }
const E_SCHEMA = { type: 'object', properties: { group: { type: 'string' }, stocks: { type: 'array', items: E_STOCK }, group_notes: { type: 'string' } }, required: ['group', 'stocks', 'group_notes'] }

const G_STOCK = { type: 'object', properties: {
  code: { type: 'string' }, name: { type: 'string' }, observed_inputs: { type: 'string' },
  sigma1_pct: { type: 'number' }, sigma_lr_pct: { type: 'number' }, beta_estimate: NUM, downside_skew: { type: 'string' },
  liquidity: { type: 'string' }, liquidity_risk: { type: 'string', enum: ['높음', '중간', '낮음'] }, gap_risk: { type: 'string' },
  cyclicality: { type: 'string' }, leverage: { type: 'string' }, estimate_dispersion: { type: 'string' },
  event_calendar: { type: 'array', items: { type: 'object', properties: { window: { type: 'string' }, event: { type: 'string' }, impact: { type: 'string' } }, required: ['window', 'event', 'impact'] } },
  extreme_loss_prob_pct: H3, rationale: { type: 'string' } },
  required: ['code', 'name', 'observed_inputs', 'sigma1_pct', 'sigma_lr_pct', 'beta_estimate', 'downside_skew', 'liquidity', 'liquidity_risk', 'gap_risk', 'cyclicality', 'leverage', 'estimate_dispersion', 'event_calendar', 'extreme_loss_prob_pct', 'rationale'] }
const G_SCHEMA = { type: 'object', properties: { group: { type: 'string' }, method: { type: 'string' }, stocks: { type: 'array', items: G_STOCK } }, required: ['group', 'method', 'stocks'] }

const H_STOCK = { type: 'object', properties: {
  code: { type: 'string' }, name: { type: 'string' }, reference_classes: { type: 'array', items: { type: 'string' } }, characteristics: { type: 'string' },
  prior_ann_pct: H3, prior_rationale: { type: 'string' }, growth_base_rates: { type: 'string' }, red_line_thresholds: { type: 'string' }, event_base_rates: { type: 'string' } },
  required: ['code', 'name', 'reference_classes', 'characteristics', 'prior_ann_pct', 'prior_rationale', 'growth_base_rates', 'red_line_thresholds', 'event_base_rates'] }
const H_SCHEMA = { type: 'object', properties: { group: { type: 'string' }, selection_rules: { type: 'string' }, evidence: { type: 'array', items: { type: 'object', properties: { topic: { type: 'string' }, finding: { type: 'string' }, source_type: { type: 'string' } }, required: ['topic', 'finding', 'source_type'] } }, stocks: { type: 'array', items: H_STOCK } }, required: ['group', 'selection_rules', 'evidence', 'stocks'] }

const AN_SCHEMA = { type: 'object', properties: {
  analyst_type: { type: 'string' }, name: { type: 'string' }, code: { type: 'string' }, p0_used_krw: { type: 'number' },
  business_and_position: { type: 'string' }, recent_performance: { type: 'string' }, financial_outlook: { type: 'string' }, normalized_earnings: { type: 'string' }, capex_roic: { type: 'string' },
  valuation_methods: { type: 'array', minItems: 2, items: { type: 'object', properties: { method: { type: 'string' }, fair_value_low_krw: { type: 'number' }, fair_value_base_krw: { type: 'number' }, fair_value_high_krw: { type: 'number' }, key_assumptions: { type: 'string' } }, required: ['method', 'fair_value_low_krw', 'fair_value_base_krw', 'fair_value_high_krw', 'key_assumptions'] } },
  fair_value_summary: { type: 'string' }, reverse_dcf: { type: 'string' }, market_vs_own: { type: 'string' },
  scenarios: { type: 'object', properties: { h1: SCS, h3: SCS, h5: SCS }, required: ['h1', 'h3', 'h5'] },
  expected_tsr_pct: H3, confidence: { type: 'object', properties: { h1: CONF, h3: CONF, h5: CONF }, required: ['h1', 'h3', 'h5'] },
  catalysts: { type: 'array', items: { type: 'string' } }, risks: { type: 'array', items: { type: 'string' } }, invalidation: { type: 'array', items: { type: 'string' } }, kpis: { type: 'array', items: { type: 'string' } },
  knowledge_flags: { type: 'array', items: { type: 'string' } } },
  required: ['analyst_type', 'name', 'code', 'p0_used_krw', 'business_and_position', 'recent_performance', 'financial_outlook', 'normalized_earnings', 'capex_roic', 'valuation_methods', 'fair_value_summary', 'reverse_dcf', 'market_vs_own', 'scenarios', 'expected_tsr_pct', 'confidence', 'catalysts', 'risks', 'invalidation', 'kpis', 'knowledge_flags'] }

function packList(g) { return g.stocks.map(s => `- ${s.name}(${s.code}, ${s.market}): ${ROOT}/data/pack/${s.code}.json`).join('\n') }

function eTask(g) {
  return `[역할: E. 회계·지배구조·포렌식 에이전트 — 산업군 '${g.group}']
아래 종목의 데이터 팩을 모두 Read로 읽고 종목별로 점검하라.
${packList(g)}
점검 항목: 영업현금흐름과 회계이익의 괴리, 일회성 손익, 자본화된 개발비, 관계사·내부거래, 감사의견과 주석, 우발채무·소송·보증, 고객·공급자 집중도, 순현금·순차입금과 차입 만기, 유상증자·CB·BW, 스톡옵션과 잠재 희석, 최대주주 지분·보호예수·오버행, 지주회사 할인이나 복잡한 지배구조, 자사주 보유·소각·처분 가능성, 소액주주와 대주주 사이 이해상충.
정량 산출: expected_dilution_pct는 기준일 대비 기간 말 주식수의 확률가중 누적 증가율(%; 소각이면 음수). cum_dividend_per_share_krw는 기준 시나리오의 기간 중 누적 주당배당(원). 근거가 데이터 팩인지 사전지식인지 knowledge_vs_data에 구분하라. 확인 불가한 항목은 그렇다고 쓰고 위험을 과소평가하지 말라.`
}

function gTask(g) {
  return `[역할: G. 정량·위험 에이전트 — 산업군 '${g.group}']
아래 종목의 데이터 팩을 모두 Read로 읽어라.
${packList(g)}
이 환경에서는 일별 주가 시계열을 받을 수 없어 역사적 변동성·베타·최대낙폭을 직접 계산할 수 없다. 그 사실을 method에 밝히고, 다음 정보를 결합해 전망형 위험 모수를 추정하라: 52주 고저폭(무추세 브라운 운동에서 1년 로그 고저폭의 기댓값은 약 1.6σ이며, 뚜렷한 추세가 있으면 고저폭이 변동성을 과대평가한다), 데이터 팩의 최근 급등락과 고점 대비 낙폭, 시가총액 규모·업종·사업모델의 경기민감도, 재무레버리지, 예정된 이산 사건. 과거 변동성을 그대로 외삽하지 말고 사업구조 변화와 예정 사건을 반영하라. 옵션 내재변동성은 확보할 수 없으니 만들어내지 말라. 같은 산업군 안에서 모수가 서로 일관되게 하라.
sigma1_pct는 향후 12개월 연환산 변동성(로그수익률 기준), sigma_lr_pct는 3~5년차 장기 연환산 변동성이다. extreme_loss_prob_pct는 기간 중 상장폐지·완전자본잠식 등으로 −80% 이상 손실이 날 확률(%)이다. event_calendar에는 향후 12개월의 실적발표·임상·수주·보호예수 해제·금통위 등 예정 사건을 적어라.`
}

function hTask(g) {
  return `[역할: H. 베이스레이트·예측 보정 에이전트 — 산업군 '${g.group}']
아래 종목의 데이터 팩을 Read로 읽어라. 다른 분석가의 결론은 보지 않는다(독립 사전분포).
${packList(g)}
종목마다 (1) 사전에 정한 선정 기준으로 참조집단(reference class)을 고르고(결과에 맞춰 고르는 체리피킹 금지), (2) 그 집단의 베이스레이트 근거(학술·업계 연구, 예: 고성장 지속 확률, IPO 장기성과, 장기 반전·모멘텀, 사이클 정점 이후 수익률, 임상 단계별 성공확률, 수주→매출 전환율, 메자닌 발행 기업의 장기 수익률)를 정리하고, (3) 기간별 사전 기대 연환산 TSR(prior_ann_pct)을 제시하라.
사전분포 규칙: 공통 거시 데크의 해당 시장 지수(KOSPI 또는 KOSDAQ) 기대 연환산수익률에서 출발해, 회사 고유의 스토리가 아니라 관찰 가능한 특성(규모, 밸류에이션 수준, 최근 급등락에 따른 반전, 상장 연차, 레버리지·희석 성향, 사이클 위치)으로만 조정하라. 조정폭은 원칙적으로 1년 ±6%p, 3·5년 ±4%p 이내로 하고, 넘기려면 근거를 적어라. 정보가 적다는 이유만으로 높은 기대수익을 주지 말라.
red_line_thresholds에는 '이 가정을 넘으면 베이스레이트상 극단적'이라고 볼 기준(예: 5년 매출 CAGR 30% 초과를 유지한 기업 비율)을 적어라.`
}

function anTask(s, type) {
  const role = type === '전문가'
    ? `[역할: D. 산업 전문 애널리스트 — ${s.group}] 당신은 이 산업의 구조·사이클·경쟁·기술 로드맵·고객 capex를 깊이 아는 전문가다. 업계 지식으로 평가하되 업계 통념에 휩쓸리지 말라.`
    : `[역할: D. 독립 제너럴리스트 애널리스트] 당신은 특정 산업에 소속되지 않은 독립 분석가다. 업계 내러티브에 기대지 말고 재무제표, 밸류에이션, 자본배분, 베이스레이트, 고객 협상력, 희석 관점에서 독립적으로 평가하라.`
  return `${role}
대상: ${s.name}(${s.code}, ${s.market}). 데이터 팩: ${ROOT}/data/pack/${s.code}.json (Read로 읽을 것). 기준주가 p0는 데이터 팩의 close 값을 그대로 쓴다.
F. 기업가치·펀더멘털 원칙을 적용하라: 적합한 평가방법 2개 이상(DCF/FCFF, 배당할인, SOTP, 정상화·중간사이클 이익, 국내외 비교기업 멀티플, 자체 역사적 밸류에이션 범위, Reverse DCF, 바이오 rNPV, 적자 성장기업의 시나리오별 EV/Sales, 수주산업의 수주잔고 전환율). 경기순환주는 고점 이익에 낮은 PER을 주는 오류를 피하고 정상화 이익을 함께 계산하라. 바이오·진단은 임상·허가·급여·상업화 성공확률과 현금 소진·추가 증자 가능성을 반영하라. 신규 상장·짧은 이력 기업은 비교기업과 산업 베이스레이트를 쓰되 신뢰도를 낮춰라. 5년 전망에서는 영구 고성장을 가정하지 말고 경쟁 심화와 멀티플 정상화를 반영하라. 매출·이익보다 최종 주당가치에 초점을 맞추고, 증권사 목표주가는 참고만 하라. 현재 주가가 암시하는 성장률·마진·점유율을 역산하라(reverse_dcf).
기간별 초점: 1년은 실적 추정 변화·사이클·수주·일정·주주환원·리레이팅·수급, 3년은 구조적 성장·점유율·신사업 수익화·capex와 감가상각·ROIC 대 WACC·재무구조, 5년은 장기 TAM·기술 해자와 대체위험·규모의 경제·자본배분·장기 희석·성숙기 정상 마진·합리적 최종 밸류에이션·생존확률.
시나리오 작성 규칙: 기간마다 최소 비관·기준·낙관을 쓰고, 이산적 사건(임상, 대형 수주, 고객 채택, 표준 선정)이나 상장폐지급 꼬리위험이 있으면 극단비관·극단낙관으로 사건확률 트리의 가지를 표현하라. 확률 합계는 정확히 100. value_per_share_krw는 기간 말 '현재 1주' 기준 주당가치(희석·소각 반영), cum_dividend_per_share_krw는 기간 중 누적 주당배당이다. 각 시나리오 값은 그 시나리오의 평균적 결과를 뜻한다(엔진이 시나리오 내부 분산을 따로 더한다). 공통 거시 데크의 비관 확률보다 경기민감주의 비관 확률을 낮게 잡으려면 이유를 적어라. expected_tsr_pct에는 Σ확률×((주당가치+누적배당)/p0−1)을 계산해 적어라(검산용).
사전지식에서 온 사실은 knowledge_flags에 모두 적어라.`
}

const out = { E: [], G: [], H: [], spec: [], gen: [] }
if (args.mode === 'egh') {
  phase('EGH')
  const res = await parallel(args.groups.flatMap(g => [
    () => agent(COMMON + '\n\n' + eTask(g), { label: 'E:' + g.group, phase: 'EGH', schema: E_SCHEMA, effort: 'high' }),
    () => agent(COMMON + '\n\n' + gTask(g), { label: 'G:' + g.group, phase: 'EGH', schema: G_SCHEMA, effort: 'high' }),
    () => agent(COMMON + '\n\n' + hTask(g), { label: 'H:' + g.group, phase: 'EGH', schema: H_SCHEMA, effort: 'high' }),
  ]))
  return res.map((r, i) => ({ job: ['E', 'G', 'H'][i % 3] + ':' + args.groups[Math.floor(i / 3)].group, ok: !!r, n: r ? r.stocks.length : 0 }))
}
phase('Analysts')
const res = await parallel(args.stocks.flatMap(s => [
  () => agent(COMMON + '\n\n' + anTask(s, '전문가'), { label: 'D전문가:' + s.name, phase: 'Analysts', schema: AN_SCHEMA, effort: 'high' }),
  () => agent(COMMON + '\n\n' + anTask(s, '일반'), { label: 'D일반:' + s.name, phase: 'Analysts', schema: AN_SCHEMA, effort: 'high' }),
]))
return res.map((r, i) => {
  const s = args.stocks[Math.floor(i / 2)]
  return { job: (i % 2 ? 'gen:' : 'spec:') + s.name, ok: !!r, exp: r ? r.expected_tsr_pct : null }
})
