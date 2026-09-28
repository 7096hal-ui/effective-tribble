export const meta = {
  name: 'kr-equity-analysis',
  description: 'Per-stock independent industry-specialist and generalist valuations, then base-rate calibration and synthesis into 1/3/5-year TSR scenario sets',
  phases: [
    { title: 'Specialist', detail: 'D: industry specialist valuation & scenarios' },
    { title: 'Generalist', detail: 'independent non-industry analyst valuation & scenarios' },
    { title: 'Calibrate', detail: 'H: base-rate calibration and weighted synthesis' },
  ],
}

const CTX = `[공통 맥락]
- 프로젝트: 한국 상장주식 26개 종목의 1년·3년·5년 총주주수익률(TSR) 전망·순위화를 위한 기관급 멀티에이전트 리서치. 당신은 그중 한 역할이다.
- 분석 기준 시각 2026-09-28(월) 19:40 KST(장마감 후). 기준 주가 P0는 아래에 종목별로 주어진 값(대부분 2026-09-28 종가)을 그대로 사용하라.
- 전망 종료일: 1년 2027-09-28, 3년 2029-09-28, 5년 2031-09-28(직전 거래일). 통화 KRW.
- TSR 정의: 세전·수수료 차감 전. tsr_cum_pct = (기말 주가 + 기간 중 누적 주당배당) / P0 - 1 (%). 기말 주가는 희석(유상증자·CB/BW 전환·스톡옵션)과 자사주 소각을 반영한 '현재 1주' 기준 값이어야 한다.
- 입력 파일(Read로 읽어라): 거시 공통 시나리오 ${args.macroPath}, 종목 도시에(B 데이터·E 포렌식·G 위험) ${args.dossierDir}/<종목명>.json.
- 도구: WebSearch만 사용 가능(ToolSearch로 "select:WebSearch" 로드). WebFetch·Bash 네트워크는 차단. 세션 검색 예산이 있으니 꼭 필요한 보완 검색만 하라(아래 권장 횟수 이내). 검색 결과가 "web search budget" 메시지를 주면 검색을 멈추고 확보한 정보만으로 작성하라.
- 원칙: 수치·출처 날조 금지. 확인된 사실/추정/가정/의견을 구분. 확률을 확정적 사실처럼 쓰지 말 것. 거시 공통 가정(금리·환율·AI 설비투자·메모리 사이클·관세·바이오 자금조달 등)과 모순되는 가정을 쓰지 말고, 다르게 보려면 이유를 명시.
- 가치평가 원칙: 최소 2개 방법. 경기순환주는 고점 이익에 낮은 PER을 적용하는 오류를 피하고 정상화(중간사이클) 이익을 함께 계산. 바이오·진단은 임상·허가·급여·상업화 성공확률과 현금소진·증자 가능성 반영(성공확률에 반영한 위험을 할인율에 중복 반영 금지). 신규상장·실적 이력이 짧으면 비교기업·산업 베이스레이트를 쓰고 신뢰도를 낮춰라. 5년 전망에서 영구 고성장·최고 마진 지속을 가정하지 말고 경쟁 심화와 멀티플 정상화를 반영. 주당가치에 집중. 증권사 목표주가는 참고일 뿐. 현재 주가가 암시하는 성장률·마진·점유율을 역산하라.
- 시나리오: 기간별로 최소 bear/base/bull 3개(확률 합 정확히 1.0). 임상·대형 수주·고객 채택·기술표준처럼 이산적인 사건이 가치를 좌우하면 사건확률 트리를 쓰고, 트리의 잎(leaf)을 추가 시나리오로 나열해도 된다(각 잎에 확률과 TSR). 상장폐지·주가 0 근처 같은 꼬리 위험이 의미 있으면(≥2%) 별도 tail 시나리오로 넣어라.
- 출력은 한국어, 간결한 보고서체.`

const SRC = { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, title: { type: 'string' }, pub_date: { type: 'string' }, used_for: { type: 'string' } }, required: ['url', 'used_for'] } }
const SCEN = { type: 'object', properties: {
  name: { type: 'string' }, prob: { type: 'number' }, end_price_krw: { type: 'number' }, cum_dividends_krw: { type: 'number' },
  tsr_cum_pct: { type: 'number' }, key_assumptions: { type: 'string' } }, required: ['name', 'prob', 'end_price_krw', 'cum_dividends_krw', 'tsr_cum_pct', 'key_assumptions'] }
const HZ = { type: 'object', properties: {
  scenarios: { type: 'array', minItems: 3, items: SCEN },
  event_tree: { type: 'string', description: '사건확률 트리를 썼으면 노드·확률 설명, 아니면 빈 문자열' },
  expected_tsr_cum_pct: { type: 'number', description: 'Σ prob × tsr_cum_pct' },
  median_view_note: { type: 'string', description: '기대값과 중앙값이 크게 다를 이유가 있으면 설명' },
}, required: ['scenarios', 'event_tree', 'expected_tsr_cum_pct', 'median_view_note'] }

const ANALYST_SCHEMA = {
  type: 'object',
  properties: {
    thesis: { type: 'string' },
    implied_expectations: { type: 'string', description: 'Reverse DCF/멀티플 역산: 현재 주가가 암시하는 매출 성장률·마진·점유율·최종 멀티플' },
    normalized_earnings: { type: 'string', description: '정상화(중간사이클) 이익과 근거' },
    forecast: { type: 'array', items: { type: 'object', properties: { fy: { type: 'string' }, revenue_eok: { type: ['number', 'null'] }, op_income_eok: { type: ['number', 'null'] }, net_income_eok: { type: ['number', 'null'] }, fcf_eok: { type: ['number', 'null'] }, eps_krw: { type: ['number', 'null'] }, dps_krw: { type: ['number', 'null'] } }, required: ['fy', 'revenue_eok', 'op_income_eok', 'eps_krw'] }, description: 'FY2026E, FY2027E, FY2028E, FY2031E(정상화) 최소' },
    valuation: { type: 'array', minItems: 2, items: { type: 'object', properties: { method: { type: 'string' }, key_assumptions: { type: 'string' }, fv_low_krw: { type: 'number' }, fv_mid_krw: { type: 'number' }, fv_high_krw: { type: 'number' } }, required: ['method', 'key_assumptions', 'fv_low_krw', 'fv_mid_krw', 'fv_high_krw'] } },
    fair_value_krw: { type: 'object', properties: { low: { type: 'number' }, mid: { type: 'number' }, high: { type: 'number' } }, required: ['low', 'mid', 'high'] },
    market_vs_own: { type: 'string', description: '시장(컨센서스·주가 암시) 전망과 자체 전망의 차이' },
    horizons: { type: 'object', properties: { y1: HZ, y3: HZ, y5: HZ }, required: ['y1', 'y3', 'y5'] },
    catalysts: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
    invalidation: { type: 'array', items: { type: 'string' }, description: '투자논지가 무효화되는 구체적 조건' },
    kpis: { type: 'array', items: { type: 'string' }, description: '다음 실적·공시에서 확인할 지표' },
    confidence: { type: 'string', enum: ['높음', '보통', '낮음'] },
    confidence_reason: { type: 'string' },
    sources: SRC,
  },
  required: ['thesis', 'implied_expectations', 'normalized_earnings', 'forecast', 'valuation', 'fair_value_krw', 'market_vs_own', 'horizons', 'catalysts', 'risks', 'invalidation', 'kpis', 'confidence', 'confidence_reason', 'sources'],
}

const SENS3 = { type: 'object', properties: { y1: { type: 'number' }, y3: { type: 'number' }, y5: { type: 'number' } }, required: ['y1', 'y3', 'y5'], description: '기대 누적 TSR 변화(%p)' }
const FHZ = { type: 'object', properties: {
  scenarios: { type: 'array', minItems: 3, items: SCEN },
  display_bear_base_bull: { type: 'string', description: '잎이 3개보다 많으면 bear/base/bull로 묶은 요약(확률·TSR)' },
  expected_tsr_cum_pct: { type: 'number' },
  pre_shrink_expected_tsr_cum_pct: { type: 'number', description: '축소 전(두 분석가 가중 결합 직후) 기대 누적 TSR' },
  shrinkage: { type: 'string', description: '어떤 사전분포(산업·시장 베이스레이트) 쪽으로 얼마나, 왜 축소했는지. 축소 안 했으면 이유' },
  confidence: { type: 'string', enum: ['높음', '보통', '낮음'] },
  key_driver: { type: 'string', description: '이 기간 순위를 결정할 핵심 요인 한 문장' },
}, required: ['scenarios', 'display_bear_base_bull', 'expected_tsr_cum_pct', 'pre_shrink_expected_tsr_cum_pct', 'shrinkage', 'confidence', 'key_driver'] }

const SYNTH_SCHEMA = {
  type: 'object',
  properties: {
    horizons: { type: 'object', properties: { y1: FHZ, y3: FHZ, y5: FHZ }, required: ['y1', 'y3', 'y5'] },
    forward_vol_annual_pct: { type: 'number', description: 'G 추정을 검토해 채택한 향후 연변동성' },
    tail: { type: 'object', properties: { prob_near_zero_5y: { type: 'number' }, prob_permanent_loss_50pct_5y: { type: 'number' } }, required: ['prob_near_zero_5y', 'prob_permanent_loss_50pct_5y'] },
    disagreement: { type: 'object', properties: {
      specialist_expected: SENS3, generalist_expected: SENS3,
      key_assumption_diff: { type: 'string' }, weighting: { type: 'string', description: '어느 쪽에 어떤 가중치를 왜 두었는지(데이터 품질·전문성·가정 타당성)' } }, required: ['specialist_expected', 'generalist_expected', 'key_assumption_diff', 'weighting'] },
    implied_expectations: { type: 'string' },
    optimism_priced_in: { type: 'integer', minimum: 1, maximum: 5, description: '현재 주가에 반영된 낙관 정도 1(비관 반영)~5(낙관 과다 반영)' },
    optimism_rationale: { type: 'string' },
    market_vs_own: { type: 'string' },
    forecast_summary: { type: 'string', description: '매출·영업이익·FCF 경로 요약(연도·수치)' },
    valuation_summary: { type: 'string', description: '사용한 방법과 적정가치 범위' },
    fair_value_krw: { type: 'object', properties: { low: { type: 'number' }, mid: { type: 'number' }, high: { type: 'number' } }, required: ['low', 'mid', 'high'] },
    catalysts: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
    invalidation: { type: 'array', items: { type: 'string' } },
    kpis: { type: 'array', items: { type: 'string' } },
    upside_triggers: { type: 'string', description: '어떤 변화가 생기면 순위가 크게 올라갈 수 있는지' },
    sensitivities: { type: 'object', description: '각 표준 충격이 이 종목의 기대 누적 TSR에 주는 변화(%p). 해당 없으면 0',
      properties: { fx_usdkrw_up10: SENS3, rates_up100bp: SENS3, terminal_multiple_down20: SENS3, semi_ai_down: SENS3, auto_tariff_demand: SENS3, bio_pos_down25: SENS3, dilution_up10: SENS3, key_customer_down20: SENS3 },
      required: ['fx_usdkrw_up10', 'rates_up100bp', 'terminal_multiple_down20', 'semi_ai_down', 'auto_tariff_demand', 'bio_pos_down25', 'dilution_up10', 'key_customer_down20'] },
    sensitivity_notes: { type: 'string' },
  },
  required: ['horizons', 'forward_vol_annual_pct', 'tail', 'disagreement', 'implied_expectations', 'optimism_priced_in', 'optimism_rationale', 'market_vs_own', 'forecast_summary', 'valuation_summary', 'fair_value_krw', 'catalysts', 'risks', 'invalidation', 'kpis', 'upside_triggers', 'sensitivities', 'sensitivity_notes'],
}

const GUIDE = {
  SEMI_AI_DISPLAY: '반도체·AI 하드웨어·디스플레이 장비 전문가. 점검: 메모리(DRAM·HBM·NAND) 가격·공급 경로(증설, 중국 업체, 3사 점유율), HBM 세대 전환과 고객 인증, 고객사(메모리·파운드리·OSAT·패널) 설비투자 사이클 위치와 수주 가시성, 기술 전환·대체 위험(TC본더→하이브리드본딩, 고압 어닐링 경쟁·특허, 테스터 경쟁, OLED 증착 방식, 마이크로디스플레이 채택 속도, 고다층 PCB 층수·소재), 고점 이익에 낮은 PER 적용 오류 회피와 정상화 이익, 고객 집중·단가 인하·이원화.',
  AUTO_SDV: '자동차·전장·SDV·자동차부품 전문가. 점검: 판매량·믹스·인센티브, 환율 효과, 미국 관세(현행 세율·현지생산 비중), 하이브리드/EV 수요, 품질비용, 그룹 캡티브 물량과 단가 인하, SDV 전환 속도와 소프트웨어 수익화, 지배구조 개편·주주환원(배당·자사주 소각), 경기 정상화 마진.',
  BIO_MEDTECH: '바이오의약품·의료기기·진단 전문가. 점검: CDMO 수주잔고·가동률·공장별 증설·단가, 바이오시밀러 파이프라인·출시·가격 침식, 신약/플랫폼의 rNPV(임상 단계별 성공확률은 공개된 업계 베이스레이트 사용·출처 명시), 허가·보험급여·상업화 일정, 파트너 계약 구조(마일스톤·로열티), 현금소진과 추가 증자, 미국 관세·생물보안법·약가정책. 성공확률에 반영한 위험을 할인율에 중복 반영하지 말 것.',
  SPACE_TELECOM: '우주항공·위성통신·5G/6G 전문가. 점검: LEO 위성망 배치 일정과 지상국·단말 수요, 방산·정부 예산, 수주잔고의 매출 전환율과 프로젝트 마진, 통신사 CAPEX 사이클(5G 성숙·6G 시점), GaN 채택, 고객 집중, 수주 지연 위험.',
  ESS_INDUSTRIAL_MATERIALS: 'ESS·산업재·특수소재 전문가. 점검: 미국·유럽 ESS 설치량 전망, AI 데이터센터 전력 수요, 주요 고객 의존도와 계약 구조, 관세·FEOC·IRA, 증설 CAPEX와 운전자본, 원자재 가격, 특수금속 수요(반도체·우주항공)와 증설 램프업, 마진 지속성.',
}

const stockLine = s => `대상: ${s.name} (${s.code}, ${s.market}), P0 = ${s.P0}원 (${s.P0_date} 종가), 산업군 ${s.group}. 도시에 파일: ${args.dossierDir}/${s.name}.json`

const specialistPrompt = s => `${CTX}

역할: D. 산업 전문 에이전트 — ${GUIDE[s.group] || GUIDE.SEMI_AI_DISPLAY}
${stockLine(s)}

거시 공통 시나리오 파일과 도시에 파일을 먼저 Read로 읽어라. 필요한 보완 검색(동종기업 멀티플, 컨센서스, 최신 수주·고객 동향 등)은 최대 6회(엄격한 상한).
해당 산업 전문가로서 독립적으로 가치평가(최소 2개 방법)와 1·3·5년 시나리오를 작성하라. 다른 분석가의 결과는 보지 못한다.`

const generalistPrompt = s => `${CTX}

역할: 산업에 소속되지 않은 독립 일반 분석가. 산업 서사를 그대로 받아들이지 말고 (1) 현재 주가가 암시하는 기대를 역산하고, (2) 비슷한 성장단계·규모·재무구조 기업의 베이스레이트(고성장 지속 확률, 멀티플 평균회귀, 경기 정점 이후 주가 경로, 한국 소형주·신규상장주의 상장 후 성과, 대형 수주의 주주수익 전환율 등)를 적용하며, (3) 산업 전문가가 놓치기 쉬운 희석·지배구조·유동성·경기 정점 위험을 따져라. 베이스레이트를 인용할 때는 출처를 달거나 '일반 경험칙(검증 필요)'이라고 명시하라. 결과에 맞춰 비교사례를 고르지 말라(체리피킹 금지).
${stockLine(s)}

거시 공통 시나리오 파일과 도시에 파일을 먼저 Read로 읽어라. 보완 검색은 최대 4회(엄격한 상한).
독립적으로 가치평가(최소 2개 방법)와 1·3·5년 시나리오를 작성하라. 다른 분석가의 결과는 보지 못한다.`

const synthPrompt = (s, sp, ge) => `${CTX}

역할: H. 베이스레이트·예측 보정 에이전트 겸 종목별 심사. ${stockLine(s)}
거시 공통 시나리오 파일과 도시에 파일을 Read로 읽고, 아래 두 독립 분석을 통합해 이 종목의 최종(반대심문 전) 시나리오 세트를 만들어라. 추가 검색은 원칙적으로 하지 말고, 두 분석이 사실관계에서 충돌할 때만 1~3회 확인하라.

[산업 전문가 분석]
${JSON.stringify(sp)}

[독립 일반 분석가 분석]
${JSON.stringify(ge)}

통합 규칙:
1) 단순 산술평균 금지. 데이터 품질, 산업 전문성, 가정의 타당성(거시 공통 가정과의 정합성 포함)에 따라 가중치를 정하고 이유를 disagreement.weighting에 적어라. 두 분석가의 기대 누적 TSR을 specialist_expected/generalist_expected에 그대로 옮겨 적어라.
2) 데이터가 부족하거나 두 분석의 차이가 크면, 극단적 추정치를 산업 또는 시장 베이스레이트(거시 파일의 KOSPI/KOSDAQ 기대 TSR을 베타·산업 특성으로 조정한 값) 쪽으로 합리적으로 축소하라. 축소 전·후 기대값과 방법을 기록하라. 신뢰도 점수를 곱해 이중으로 벌점을 주지 말라. 정보가 적다는 이유로 소형주에 높은 기대수익률을 주지 말라.
3) 각 시나리오의 tsr_cum_pct가 (end_price_krw + cum_dividends_krw)/P0 - 1과 일치하고, 확률 합이 정확히 1.0이며, expected_tsr_cum_pct = Σ prob × tsr가 되도록 직접 검산하라. 누적과 연환산을 혼동하지 말라.
4) forward_vol_annual_pct: G 에이전트 추정을 검토해 채택(상장 이력이 짧거나 거래가 얇으면 낮게 잡지 말 것).
5) 민감도: 표준 충격(USD/KRW +10%, 할인율 +100bp, 최종 멀티플 -20%, 반도체 가격·AI 설비투자 하향 시나리오, 자동차 수요 -5%·관세 +10%p, 바이오 성공확률 상대 -25%, 추가 희석 +10%, 핵심고객 매출 -20%)이 기대 누적 TSR을 몇 %p 바꾸는지 기간별로. 관련 없으면 0.
6) optimism_priced_in: 현재 주가에 낙관이 얼마나 반영됐는지 1~5.
7) 두 분석가 사이의 중요한 의견 차이를 숨기지 말라.`

const results = await pipeline(args.stocks,
  s => parallel([
    () => agent(specialistPrompt(s), { label: `D:spec:${s.name}`, phase: 'Specialist', schema: ANALYST_SCHEMA }),
    () => agent(generalistPrompt(s), { label: `GEN:${s.name}`, phase: 'Generalist', schema: ANALYST_SCHEMA }),
  ]),
  ([sp, ge], s) => {
    if (!sp || !ge) return { stock: s.name, error: `analyst missing: spec=${!!sp} gen=${!!ge}`, sp, ge }
    return agent(synthPrompt(s, sp, ge), { label: `H:calib:${s.name}`, phase: 'Calibrate', schema: SYNTH_SCHEMA })
      .then(fin => ({ stock: s.name, sp, ge, fin }))
  },
)

return results.map(r => r && r.fin ? ({
  stock: r.stock,
  spec: [r.sp.horizons.y1.expected_tsr_cum_pct, r.sp.horizons.y3.expected_tsr_cum_pct, r.sp.horizons.y5.expected_tsr_cum_pct],
  gen: [r.ge.horizons.y1.expected_tsr_cum_pct, r.ge.horizons.y3.expected_tsr_cum_pct, r.ge.horizons.y5.expected_tsr_cum_pct],
  fin: [r.fin.horizons.y1.expected_tsr_cum_pct, r.fin.horizons.y3.expected_tsr_cum_pct, r.fin.horizons.y5.expected_tsr_cum_pct],
  vol: r.fin.forward_vol_annual_pct,
}) : (r ? { stock: r.stock, error: r.error } : null))
