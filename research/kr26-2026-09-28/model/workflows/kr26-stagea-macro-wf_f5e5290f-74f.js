export const meta = {
  name: 'kr26-stageA-macro',
  description: '거시·시장체제: 독립 거시 분석 2건(탑다운/사이클) → 공통 거시 데크 통합 → 독립 검증·확정',
  phases: [
    { title: 'Macro-Independent', detail: 'C1 금리·환율·밸류에이션 / C2 산업사이클·실물수요' },
    { title: 'Macro-Reconcile', detail: '공통 거시 데크(시나리오 확률·무위험수익률·지수 기대수익·표준 충격)' },
    { title: 'Macro-Verify', detail: '현재값 재검증·내부 일관성 점검 후 최종 데크 확정' },
  ],
}

const COMMON = `[공통 작업 맥락 — 반드시 준수]
• 프로젝트: 한국 상장사 26개 종목의 1·3·5년 기대 총주주수익률(TSR)과 위험조정수익률 순위를 산출하는 기관투자자급 멀티에이전트 리서치. 당신은 그중 한 역할을 독립적으로 수행한다. 다른 에이전트의 결론을 추측해 맞추려 하지 말라.
• 분석 기준 시각: 2026-09-28(월) 19:50 KST 무렵. KRX 정규장은 15:30에 마감했으므로 기준 주가는 2026-09-28 KRX 공식 종가다. 지금 NXT(넥스트레이드) 애프터마켓이 열려 있을 수 있으니 NXT 체결가·장중가를 KRX 종가와 혼동하지 말라. 추석 연휴(9/24~9/26 전후)로 직전 거래일이 9/23(수)일 수 있으니 날짜를 확인하라.
• 전망 종료일: 1년 2027-09-28(화), 3년 2029-09-28(금), 5년 2031-09-28(일요일이므로 직전 거래일 종가로 평가). 통화는 원화(KRW).
• 수익률 정의: 세전·수수료 차감 전 원화 TSR = (기간 말 주당가치 + 기간 중 누적 주당배당) ÷ 기준주가 − 1 (배당 재투자 없음). 유상증자·CB/BW 전환·스톡옵션 희석과 자사주 매입·소각은 '현재 보유 1주' 기준 주당가치에 반영한다.
• 도구 제약: 외부 데이터 경로는 WebSearch뿐이다. WebFetch·curl은 네이버금융·FnGuide·DART·KIND·investing.com·언론사 등 거의 모든 도메인이 차단돼 있으니 시도하지 말라. WebSearch가 목록에 없으면 ToolSearch로 "select:WebSearch"를 먼저 로드하라. 검색 요약문은 날짜를 혼동하는 일이 잦으므로 핵심 수치는 서로 다른 검색어로 두 번 이상 교차확인하라.
• 출처 원칙: KRX·DART 공시(공시를 인용한 보도 포함) > 회사 IR·실적발표 > 정부·규제기관·임상등록 > 고객사 공식발표 > 한국은행·통계청 > 금융정보업체·증권사 컨센서스 > 신뢰도 높은 언론 순으로 우선한다. 익명 게시물, 출처 불명 블로그, 홍보성 콘텐츠, 유튜브 주장에 의존하지 말라. 핵심 사실마다 출처(매체·기관명, URL)와 자료 기준일을 붙이고, 뉴스는 게시일과 실제 사건일을 구분하라. 유료 DB에 접근한 것처럼 쓰지 말라. 확인하지 못한 값은 추측하지 말고 null 또는 '확인 불가'로 둔다. 출처가 충돌하면 차이와 채택 근거를 적는다.
• 확률 판단을 확정적 사실처럼 쓰지 말고, 지나치게 정밀한 숫자로 허위 확신을 만들지 말라.
• 출력: 한국어(고유명사·원어 용어는 원문 유지 가능). 최종 결과는 지정된 StructuredOutput 스키마로만 반환한다. 퍼센트 필드는 퍼센트 단위 숫자(예: 12.5 = +12.5%)로 쓴다.`

const SRC = { type: 'object', properties: { title: { type: 'string' }, url: { type: 'string' }, date: { type: 'string' } }, required: ['title', 'url'] }
const DATAPT = { type: 'object', properties: { variable: { type: 'string' }, value: { type: 'string' }, asof: { type: 'string' }, source: { type: 'string' } }, required: ['variable', 'value', 'asof', 'source'] }
const PATH = { type: 'object', properties: {
  bok_rate_pct: { type: ['number', 'null'] }, ktb3y_pct: { type: ['number', 'null'] }, ktb5y_pct: { type: ['number', 'null'] }, usdkrw: { type: ['number', 'null'] },
  kospi_cum_tsr_pct: { type: 'number' }, kosdaq_cum_tsr_pct: { type: 'number' },
  memory_ai: { type: 'string' }, autos: { type: 'string' }, bio_funding: { type: 'string' }, space_defense_telecom: { type: 'string' }, ess_industrial: { type: 'string' }, other: { type: 'string' } },
  required: ['bok_rate_pct', 'ktb3y_pct', 'usdkrw', 'kospi_cum_tsr_pct', 'kosdaq_cum_tsr_pct', 'memory_ai', 'autos', 'bio_funding', 'space_defense_telecom', 'ess_industrial'] }
const SCEN = { type: 'object', properties: { name: { type: 'string' }, probability_pct: { type: 'number' }, narrative: { type: 'string' }, h1: PATH, h3: PATH, h5: PATH }, required: ['name', 'probability_pct', 'narrative', 'h1', 'h3', 'h5'] }
const IDX = { type: 'object', properties: { h1_cum_pct: { type: 'number' }, h3_cum_pct: { type: 'number' }, h5_cum_pct: { type: 'number' }, dividend_yield_pct: { type: ['number', 'null'] }, current_level: { type: ['number', 'null'] }, current_level_date: { type: ['string', 'null'] }, rationale: { type: 'string' } }, required: ['h1_cum_pct', 'h3_cum_pct', 'h5_cum_pct', 'current_level', 'current_level_date', 'rationale'] }
const RF = { type: 'object', properties: { ktb1y_pct: { type: ['number', 'null'] }, ktb3y_pct: { type: ['number', 'null'] }, ktb5y_pct: { type: ['number', 'null'] }, ktb10y_pct: { type: ['number', 'null'] }, asof: { type: 'string' }, sources: { type: 'array', items: { type: 'string' } }, note: { type: 'string' } }, required: ['ktb1y_pct', 'ktb3y_pct', 'ktb5y_pct', 'asof', 'sources', 'note'] }
const SECT = { type: 'object', properties: { memory_ai_hw: { type: 'string' }, display_equipment: { type: 'string' }, autos: { type: 'string' }, bio: { type: 'string' }, space_satcom_5g6g_defense: { type: 'string' }, ess_industrial_materials: { type: 'string' } }, required: ['memory_ai_hw', 'display_equipment', 'autos', 'bio', 'space_satcom_5g6g_defense', 'ess_industrial_materials'] }
const MACRO_SCHEMA = { type: 'object', properties: {
  lens: { type: 'string' }, current_data: { type: 'array', items: DATAPT }, regime_summary: { type: 'string' },
  scenarios: { type: 'array', items: SCEN, minItems: 3 },
  index_expectations: { type: 'object', properties: { KOSPI: IDX, KOSDAQ: IDX }, required: ['KOSPI', 'KOSDAQ'] },
  sector_views: SECT, risk_free: RF, shock_assessment: { type: 'string' },
  consistency_rules: { type: 'array', items: { type: 'string' } }, key_uncertainties: { type: 'array', items: { type: 'string' } },
  sources: { type: 'array', items: SRC } },
  required: ['lens', 'current_data', 'regime_summary', 'scenarios', 'index_expectations', 'sector_views', 'risk_free', 'shock_assessment', 'consistency_rules', 'key_uncertainties', 'sources'] }
const SHOCK = { type: 'object', properties: { id: { type: 'string' }, description: { type: 'string' }, magnitude: { type: 'string' }, applies_to: { type: 'string' } }, required: ['id', 'description', 'magnitude', 'applies_to'] }
const DECK_SCHEMA = { type: 'object', properties: {
  asof_note: { type: 'string' }, current_data: { type: 'array', items: DATAPT }, regime_summary: { type: 'string' },
  scenarios: { type: 'array', items: SCEN, minItems: 3 },
  index_expectations: { type: 'object', properties: { KOSPI: IDX, KOSDAQ: IDX }, required: ['KOSPI', 'KOSDAQ'] },
  sector_assumptions: SECT, risk_free: RF, shocks: { type: 'array', items: SHOCK },
  consistency_rules: { type: 'array', items: { type: 'string' } }, disagreements: { type: 'array', items: { type: 'string' } },
  key_risks: { type: 'array', items: { type: 'string' } }, corrections_applied: { type: 'array', items: { type: 'string' } },
  sources: { type: 'array', items: SRC } },
  required: ['asof_note', 'current_data', 'regime_summary', 'scenarios', 'index_expectations', 'sector_assumptions', 'risk_free', 'shocks', 'consistency_rules', 'disagreements', 'key_risks', 'corrections_applied', 'sources'] }

const MACRO_TASK = `[역할: C. 거시경제·시장체제 에이전트 — 독립 분석]
목표: 26개 종목(메모리·HBM 밸류체인, AI 하드웨어·디스플레이·검사장비·팹리스, 자동차·부품·SDV, 바이오·진단·의료, 우주·위성통신·5G/6G·방산RF, ESS·산업재·특수소재) 분석에 공통으로 적용할 거시 시나리오를 만든다.
1) 현재값 확인(각 값에 기준일·출처): 한국은행 기준금리와 최근 결정·다음 금통위 일정; 국고채 1년(또는 통안채 1년)·3년·5년·10년 금리(가장 최근 영업일 종가); 미국 연방기금금리와 미 국채 2년·10년; 원/달러 환율(최근 종가)과 최근 1년 범위; KOSPI·KOSDAQ 최근 종가, 연초 대비·1년 수익률, 12개월 선행 PER·PBR·배당수익률, 외국인 수급; 한국 증시 제도 변화(상법 개정, 밸류업, 배당소득 분리과세, 자사주 소각 의무화, MSCI 선진지수 관찰대상 여부 등); 하이퍼스케일러 2026·2027 capex 가이던스와 AI·데이터센터·전력·ESS 수요; DRAM·NAND·HBM 가격 추이와 2026·2027 전망, 증설·capex, 공급과잉 위험; 글로벌 자동차 판매, 한국산 자동차·부품의 미국 관세율과 협상 결과, 친환경차 전환; 바이오 자금조달 환경(XBI, 美 약가·관세·BIOSECURE 등 정책, 국내 바이오 자금조달); LEO 위성통신·방산·5G/6G 투자; 경기침체 확률, 지정학(미·중, 대만, 중동, 러·우, 북한), 유가.
2) 기준·낙관·비관 3개 거시 시나리오(확률 합계 정확히 100). 각 시나리오의 1년·3년·5년 경로: 한국 기준금리, 국고채 3년·5년, 원/달러, KOSPI·KOSDAQ 누적 TSR(배당 포함, %), 메모리·AI capex, 자동차, 바이오 자금조달, 위성·방산·통신, ESS·산업재의 방향과 강도.
3) KOSPI·KOSDAQ 확률가중 기대 누적 TSR(1·3·5년, %)과 근거: 현재 밸류에이션, 이익 전망(특히 반도체 이익 비중과 사이클 정상화), 배당, 주식위험프리미엄. 최근 급등 후라면 평균회귀 가능성을 반영하라.
4) 산업별 공통 가정(메모리·AI 하드웨어, 디스플레이 장비, 자동차, 바이오, 우주·통신·방산, ESS·산업재·소재): 시나리오별 방향과 강도, 그리고 지금 시장이 이미 반영한 기대.
5) 무위험수익률: 1년·3년·5년 원화 국채(1년은 국고채 1년 또는 통안채 1년) 수익률의 최근 종가·기준일·출처.
6) 모든 산업 에이전트가 따라야 할 일관성 규칙(예: 비관 거시 시나리오에서 경기민감주의 비관 확률 하한, 환율 가정의 방향 통일 등).
7) 다음 표준 민감도 충격이 '작지만 현실적인 변화'인지 평가하고 필요하면 크기 조정을 제안하라: ①원/달러 −10%(원화 강세)·+10%(약세) ②국고채·할인율 ±100bp ③기말 밸류에이션 멀티플 −20% ④메모리 가격 −20%·AI capex −15%(반대 방향도) ⑤글로벌 자동차 수요 −10%·미국 관세 +10%p ⑥바이오 임상·허가·급여 성공확률 −10%p ⑦추가 자금조달 희석 +10% ⑧핵심 고객 매출 −20%.`

const LENS1 = `[관점: C1 탑다운] 금리·환율·유동성·밸류에이션·정책·외국인 자금흐름을 중심으로 판단하라. 산업 사이클은 공개 데이터로 점검하되 결론은 매크로 변수에서 출발하라. lens 필드에 'C1 탑다운'이라고 적어라.`
const LENS2 = `[관점: C2 사이클·실물수요] AI·데이터센터 capex, 메모리 가격·재고·증설, 자동차 판매·관세, 바이오 자금조달, 위성·방산 수주 등 실물 지표에서 출발해 그 결과를 금리·환율·지수 기대수익으로 연결하라. lens 필드에 'C2 사이클'이라고 적어라.`

phase('Macro-Independent')
const indep = await parallel([
  () => agent(COMMON + '\n\n' + MACRO_TASK + '\n\n' + LENS1, { label: 'C1-macro-topdown', phase: 'Macro-Independent', schema: MACRO_SCHEMA }),
  () => agent(COMMON + '\n\n' + MACRO_TASK + '\n\n' + LENS2, { label: 'C2-macro-cycle', phase: 'Macro-Independent', schema: MACRO_SCHEMA }),
])
const c1 = indep[0], c2 = indep[1]
log('독립 거시 분석 완료: C1=' + (c1 ? 'ok' : 'fail') + ', C2=' + (c2 ? 'ok' : 'fail'))

phase('Macro-Reconcile')
const RECON = `[역할: C. 거시 데크 통합자]
독립적으로 작성된 거시 분석 C1(탑다운)과 C2(사이클)를 통합해, 26개 종목 분석 전체가 공유할 단일 '공통 거시 데크'를 만든다. 두 분석을 단순 평균하지 말고 데이터 품질과 근거의 강도로 가중해 판단하라. 현재값이 서로 다르면 WebSearch로 재확인해 올바른 값을 채택하고 근거를 적어라. 시나리오는 이름을 정확히 '기준','낙관','비관'으로 하고 확률 합계는 정확히 100이어야 하며, index_expectations의 누적 TSR은 시나리오 경로의 확률가중값과 일치해야 한다(검산할 것). shocks에는 다음 id를 정확히 이 철자로 모두 포함하고 크기를 확정하라: FX_KRW_STRONG, FX_KRW_WEAK, RATES_UP, RATES_DOWN, MULTIPLE_DOWN, SEMI_DOWN, SEMI_UP, AUTO_DOWN, BIO_POS_DOWN, DILUTION_UP, KEY_CUSTOMER_DOWN. 두 분석 사이의 의견 차이는 숨기지 말고 disagreements에 적는다. corrections_applied는 빈 배열로 둔다.

[C1 분석]
` + JSON.stringify(c1) + `

[C2 분석]
` + JSON.stringify(c2)
const deck0 = await agent(COMMON + '\n\n' + RECON, { label: 'C-reconcile', phase: 'Macro-Reconcile', schema: DECK_SCHEMA })

phase('Macro-Verify')
const VERIFY = `[역할: C. 거시 데크 독립 검증·확정자]
아래 공통 거시 데크를 반박하는 자세로 검증하라.
(1) current_data와 risk_free의 모든 현재값(한국은행 기준금리, 국고채 1·3·5·10년, 원/달러, KOSPI·KOSDAQ 종가·밸류에이션 등)을 서로 다른 검색어로 재확인하고 틀리거나 오래된 값을 고쳐라. 검색 요약이 다른 날짜의 값을 섞는 일이 잦으니 기사 날짜를 확인하라.
(2) 시나리오 확률 합계 100, 지수 기대 누적 TSR = 시나리오 확률가중값, 누적과 연환산의 혼동 여부를 검산하라.
(3) 특정 산업(예: AI·메모리)에 낙관이 쏠렸는지, 최근 급등 후의 평균회귀를 무시했는지, 비관 시나리오가 지나치게 온건한지 점검하라.
(4) 필요한 수정만 반영한 최종 데크를 같은 스키마로 반환하고, corrections_applied에 수정 내역(무엇을, 왜, 출처)을 모두 적어라. 수정할 것이 없으면 그렇다고 적어라. shocks의 11개 id 철자는 바꾸지 말라.

[검증 대상 데크]
` + JSON.stringify(deck0)
const deck = await agent(COMMON + '\n\n' + VERIFY, { label: 'C-verify-finalize', phase: 'Macro-Verify', schema: DECK_SCHEMA })

return { ok: { c1: !!c1, c2: !!c2, deck0: !!deck0, deck: !!deck }, deck: deck || deck0 }
