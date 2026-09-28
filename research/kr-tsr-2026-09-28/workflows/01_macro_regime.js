export const meta = {
  name: 'kr-macro-regime',
  description: 'Macro & market-regime agent: verified market/rates/FX facts, sector cycle notes, and common base/bull/bear scenarios for Korean equity TSR forecasting',
  phases: [
    { title: 'Facts', detail: 'C1: verify market, rates, FX facts as of 2026-09-28' },
    { title: 'Cycles', detail: 'C3 semis/AI cycle, C4 auto/bio/space/ESS cycles' },
    { title: 'Scenarios', detail: 'C2: common macro scenarios with probabilities' },
  ],
}

const CTX = `[공통 맥락]
- 프로젝트: 한국 상장주식 26개 종목(SK하이닉스, 삼성전자, 삼성바이오로직스, 삼성에피스홀딩스, 현대차, 현대모비스, 현대오토에버, 에이치브이엠, 사피엔반도체, 라온텍, 퓨런티어, 화신, 엘앤씨바이오, 바이오다인, 선익시스템, 서진시스템, 이수페타시스, 한중엔시에스, RFHIC, 인텔리안테크, 쎄트렉아이, HPSP, 케이엠더블유, 고영, 와이씨, 한미반도체)의 1년·3년·5년 총주주수익률(TSR) 전망 및 순위화를 위한 기관급 멀티에이전트 리서치. 당신은 C. 거시경제·시장체제 에이전트 팀의 일원이다. 당신의 산출물은 모든 산업·종목 에이전트가 공통으로 쓰는 가정이 된다.
- 분석 기준 시각: 2026-09-28(월) 19:40 KST, 한국거래소 정규장 마감 후. 전망 종료일: 1년 2027-09-28, 3년 2029-09-28, 5년 2031-09-28(일요일이므로 직전 거래일). 통화 KRW.
- 오케스트레이터 사전 확인(검증 필요): 검색 요약에 따르면 2026-09-28 KOSPI 종가 6,889.74(전일 7,080.92 대비 -2.70%), 삼성전자 270,000원(-5.43%), SK하이닉스 1,768,000원(-5.05%). 하락 원인으로 추석 연휴 중 미국 10년물 금리 장중 5.23% 급등, 오라클 데이터센터 사업 지연 보도가 언급됨(서울신문·글로벌이코노믹 2026-09-28).
- 도구 제약: WebFetch와 Bash 외부 네트워크는 egress 차단되어 있다. WebSearch만 사용 가능하다(ToolSearch로 "select:WebSearch" 로드). WebSearch는 링크와 모델 생성 요약을 주며, 요약은 날짜를 혼동하거나 오래된 값을 줄 수 있다. 핵심 수치는 서로 다른 검색어로 2회 이상 교차확인하고, 출처 URL·기사 게시일·실제 사건/데이터 기준일을 구분해 기록하라. WebFetch는 시도하지 말라.
- 금지: 수치·출처 날조, 유료 DB 접근 가장, 추정을 사실처럼 쓰기. 확인 불가 값은 null 또는 "확인 불가". 확률을 확정적 사실처럼 표현하지 말 것.
- 출력은 한국어, 간결한 보고서체.`

const FACTS_SCHEMA = {
  type: 'object',
  properties: {
    trading_calendar_note: { type: 'string', description: '2026년 추석 연휴 KRX 휴장일, 2026-09-28이 거래일인지, 직전 거래일' },
    kospi: { type: 'object', properties: { close: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, prev_close: { type: ['number', 'null'] }, change_1y_pct: { type: ['number', 'null'] }, high_52w: { type: ['number', 'null'] }, low_52w: { type: ['number', 'null'] }, valuation: { type: 'string', description: 'trailing/forward PER, PBR와 기준일·출처' }, source: { type: 'string' } }, required: ['close', 'date', 'change_1y_pct', 'valuation', 'source'] },
    kosdaq: { type: 'object', properties: { close: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, change_1y_pct: { type: ['number', 'null'] }, source: { type: 'string' } }, required: ['close', 'date', 'change_1y_pct', 'source'] },
    usdkrw: { type: 'object', properties: { value: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, trend_note: { type: 'string' }, source: { type: 'string' } }, required: ['value', 'date', 'trend_note', 'source'] },
    korea_rates: { type: 'object', properties: { bok_base_rate: { type: ['number', 'null'] }, bok_note: { type: 'string' }, ktb_1y: { type: ['number', 'null'] }, ktb_3y: { type: ['number', 'null'] }, ktb_5y: { type: ['number', 'null'] }, ktb_10y: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, source: { type: 'string' } }, required: ['bok_base_rate', 'ktb_1y', 'ktb_3y', 'ktb_5y', 'ktb_10y', 'date', 'source'] },
    us_rates: { type: 'object', properties: { fed_funds: { type: 'string' }, ust_2y: { type: ['number', 'null'] }, ust_10y: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, note: { type: 'string' }, source: { type: 'string' } }, required: ['fed_funds', 'ust_2y', 'ust_10y', 'date', 'source'] },
    flows_and_policy: { type: 'string', description: '외국인·기관 수급, 밸류업·상법개정·배당소득 분리과세 등 한국 증시 제도 변화, 공매도 등 (날짜·출처)' },
    growth_inflation: { type: 'string', description: '한국·미국 성장률/물가/수출(특히 반도체 수출) 최신 지표' },
    geopolitics: { type: 'string' },
    other_facts: { type: 'string' },
    sources: { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, title: { type: 'string' }, pub_date: { type: 'string' }, used_for: { type: 'string' } }, required: ['url', 'used_for'] } },
  },
  required: ['trading_calendar_note', 'kospi', 'kosdaq', 'usdkrw', 'korea_rates', 'us_rates', 'flows_and_policy', 'growth_inflation', 'geopolitics', 'sources'],
}

const CYCLE_SCHEMA = {
  type: 'object',
  properties: {
    topics: { type: 'array', items: { type: 'object', properties: { topic: { type: 'string' }, current_state: { type: 'string', description: '확인된 최신 사실(수치·날짜·출처)' }, outlook_1y: { type: 'string' }, outlook_3y: { type: 'string' }, outlook_5y: { type: 'string' }, key_risks: { type: 'string' }, base_rates_or_history: { type: 'string', description: '과거 사이클의 기간·진폭 등 참고할 역사적 베이스레이트' } }, required: ['topic', 'current_state', 'outlook_1y', 'outlook_3y', 'outlook_5y', 'key_risks', 'base_rates_or_history'] } },
    sources: { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, title: { type: 'string' }, pub_date: { type: 'string' }, used_for: { type: 'string' } }, required: ['url', 'used_for'] } },
  },
  required: ['topics', 'sources'],
}

const IDX = { type: 'object', properties: { kospi_1y: { type: 'number' }, kospi_3y_cum: { type: 'number' }, kospi_5y_cum: { type: 'number' }, kosdaq_1y: { type: 'number' }, kosdaq_3y_cum: { type: 'number' }, kosdaq_5y_cum: { type: 'number' } }, required: ['kospi_1y', 'kospi_3y_cum', 'kospi_5y_cum', 'kosdaq_1y', 'kosdaq_3y_cum', 'kosdaq_5y_cum'], description: '누적 TSR(%), 배당 포함' }

const SCEN_SCHEMA = {
  type: 'object',
  properties: {
    risk_free: { type: 'object', properties: { h1_pct: { type: 'number' }, h3_pct: { type: 'number' }, h5_pct: { type: 'number' }, basis: { type: 'string', description: '어떤 만기 국고채/통안채, 기준일' } }, required: ['h1_pct', 'h3_pct', 'h5_pct', 'basis'] },
    equity_risk_premium_and_discount_rates: { type: 'string', description: '한국 대형주/중소형주/바이오/적자 성장주에 공통 적용할 할인율(COE, WACC) 가이드와 근거' },
    scenarios: { type: 'array', minItems: 3, items: { type: 'object', properties: {
      name: { type: 'string', enum: ['base', 'bull', 'bear'] },
      prob: { type: 'number', description: '0~1, 세 시나리오 합=1' },
      narrative: { type: 'string' },
      rates_path: { type: 'string' }, usdkrw_path: { type: 'string', description: '1년/3년/5년 말 수준 제시' },
      ai_datacenter_capex: { type: 'string' }, memory_semi_cycle: { type: 'string' },
      auto: { type: 'string' }, bio: { type: 'string' }, space_defense_telecom: { type: 'string' }, ess_industrial: { type: 'string' },
      recession_geopolitics: { type: 'string' },
      korea_equity_valuation: { type: 'string' },
      index_tsr: IDX,
    }, required: ['name', 'prob', 'narrative', 'rates_path', 'usdkrw_path', 'ai_datacenter_capex', 'memory_semi_cycle', 'auto', 'bio', 'space_defense_telecom', 'ess_industrial', 'recession_geopolitics', 'korea_equity_valuation', 'index_tsr'] } },
    expected_index_tsr: IDX,
    industry_common_assumptions: { type: 'object', properties: { semi_ai_display: { type: 'string' }, auto_sdv: { type: 'string' }, bio_medtech: { type: 'string' }, space_telecom: { type: 'string' }, ess_industrial_materials: { type: 'string' }, fx_rates: { type: 'string' } }, required: ['semi_ai_display', 'auto_sdv', 'bio_medtech', 'space_telecom', 'ess_industrial_materials', 'fx_rates'] },
    sensitivity_shocks_definition: { type: 'string', description: '민감도 분석에 쓸 표준 충격 정의: 환율(USD/KRW +10%), 할인율 +100bp, 최종 멀티플 -20%, 반도체 가격·AI 설비투자 하향, 자동차 수요 -5%/관세 +10%p, 바이오 성공확률 -25%(상대), 희석 +10%, 핵심고객 매출 -20% 등의 거시적 의미와 개연성' },
    key_uncertainties: { type: 'array', items: { type: 'string' } },
    sources: { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, title: { type: 'string' }, pub_date: { type: 'string' }, used_for: { type: 'string' } }, required: ['url', 'used_for'] } },
  },
  required: ['risk_free', 'equity_risk_premium_and_discount_rates', 'scenarios', 'expected_index_tsr', 'industry_common_assumptions', 'sensitivity_shocks_definition', 'key_uncertainties', 'sources'],
}

phase('Facts')
const facts = await agent(`${CTX}

역할: C1. 시장·금리·환율 사실 검증 에이전트.
다음을 WebSearch로 확인하고 교차검증하라(검색 15~30회 권장):
1) 2026년 추석 연휴 KRX 휴장일과 2026-09-28이 정상 거래일인지, 직전 거래일.
2) KOSPI·KOSDAQ 2026-09-28 종가, 전일 종가, 1년 등락률, 52주 고저, KOSPI trailing/forward PER·PBR.
3) 원/달러 환율(2026-09-28 또는 최근), 최근 1년 추세.
4) 한국은행 기준금리와 최근 결정(날짜), 국고채 1년(또는 통안채 1년)·3년·5년·10년 금리(최근일).
5) 미국 연방기금금리, 미 국채 2년·10년 금리(최근일, 연휴 중 급등 보도 포함).
6) 외국인·기관 수급 동향, 한국 증시 제도 변화(밸류업, 상법 개정, 배당소득 분리과세, 자사주 소각 의무화 등)와 시행 시점.
7) 한국·미국 성장·물가·수출(특히 반도체 수출) 최신 지표, 주요 지정학 이슈.
모든 값에 기준일·출처. 확인 불가는 null.`, { label: 'C1:facts', phase: 'Facts', schema: FACTS_SCHEMA })

const factsTxt = JSON.stringify(facts)

phase('Cycles')
const [semi, others] = await parallel([
  () => agent(`${CTX}

역할: C3. 반도체·AI 설비투자 사이클 리서처. 아래 C1 검증 사실을 공통 전제로 사용하라.
C1 사실: ${factsTxt}

WebSearch로 최신 정보를 확인해 다음 topic별로 정리하라(검색 20~35회 권장):
1) 하이퍼스케일러(마이크로소프트·구글·아마존·메타·오라클 등) 2026년 설비투자 실적과 2027년 가이던스, AI 데이터센터 투자 지연/취소 보도(오라클 등) 
2) DRAM·HBM·NAND 계약가격 추이와 전망(트렌드포스 등), HBM3E/HBM4 공급 구조, SK하이닉스·삼성전자·마이크론 점유율, 중국 CXMT 등 신규 공급
3) 메모리 업체 설비투자 계획과 WFE(반도체 장비) 전망, 후공정(TC본더·하이브리드본딩) 투자
4) AI 서버용 PCB/네트워크(800G/1.6T), 디스플레이(OLED 8.6세대 IT, 마이크로디스플레이·XR) 투자
5) 과거 메모리 사이클(2017~2019, 2020~2023 등)의 상승·하락 기간과 진폭, 메모리주 주가 고점이 이익 고점보다 선행한 정도 — 베이스레이트
각 topic에 대해 current_state(수치·날짜·출처), 1/3/5년 전망, 핵심 위험, 역사적 베이스레이트를 작성.`, { label: 'C3:semi-ai-cycle', phase: 'Cycles', schema: CYCLE_SCHEMA }),
  () => agent(`${CTX}

역할: C4. 자동차·바이오·우주/통신·ESS/산업재 사이클 리서처. 아래 C1 검증 사실을 공통 전제로 사용하라.
C1 사실: ${factsTxt}

WebSearch로 최신 정보를 확인해 다음 topic별로 정리하라(검색 20~35회 권장):
1) 글로벌 자동차 수요, 미국의 한국산 자동차·부품 관세율(현행·변경 이력·날짜), 현대차그룹 미국 현지생산(HMGMA), 하이브리드/EV 전환, SDV·자율주행
2) 바이오: CDMO 수요, 미국 생물보안법·의약품 관세·약가 정책(MFN), 바이오시밀러 시장, 국내 바이오 자금조달(유상증자·CB) 환경, 금리의 영향
3) 우주·위성통신: LEO 위성통신(스타링크, 원웹/유텔샛, 아마존 카이퍼 등) 지상단말 수요, 지구관측 위성, 방산 예산, 5G/6G 통신장비 투자 사이클
4) ESS·전력 인프라: 미국 ESS 설치 전망, AI 데이터센터 전력 수요, IRA/관세·FEOC 규정, 유럽 수요
5) 글로벌 경기침체 확률, 지정학(미중, 중동, 한반도) 위험
각 topic에 대해 current_state(수치·날짜·출처), 1/3/5년 전망, 핵심 위험, 역사적 베이스레이트를 작성.`, { label: 'C4:other-cycles', phase: 'Cycles', schema: CYCLE_SCHEMA }),
])

phase('Scenarios')
const scen = await agent(`${CTX}

역할: C2. 거시 시나리오 설계 에이전트. 아래 C1·C3·C4 결과를 통합해 모든 산업 에이전트가 모순 없이 쓸 공통 기준·낙관·비관 시나리오를 작성하라. 필요시 WebSearch로 보완하되 새 사실에는 출처를 붙여라.

C1 사실: ${factsTxt}
C3 반도체·AI 사이클: ${JSON.stringify(semi)}
C4 기타 산업 사이클: ${JSON.stringify(others)}

요구사항:
- 시나리오 3개(base/bull/bear)와 확률(합계 정확히 1.0). 각 시나리오에 금리·환율(1/3/5년 말 수준)·AI 설비투자·메모리 사이클·자동차·바이오·우주/방산/통신·ESS·경기/지정학·한국 증시 밸류에이션 경로를 서술.
- 각 시나리오의 KOSPI·KOSDAQ 누적 TSR(%, 배당 포함): 1년, 3년 누적, 5년 누적. 그리고 확률가중 기대값(expected_index_tsr)을 산술적으로 정확히 계산. KOSPI가 이미 1년간 크게 상승했고 반도체 비중이 매우 높다는 점(지수 구성 집중도)을 반영하라.
- 무위험수익률: 1년·3년·5년 만기 국고채(또는 통안채) 금리를 기간별 무위험수익률로 제시(연율 %).
- 할인율 가이드: 대형 우량주, 중형주, 소형·신규상장주, 적자 바이오/성장주에 적용할 자기자본비용 범위와 근거.
- 산업별 공통 가정(industry_common_assumptions): 반도체·AI·디스플레이, 자동차·SDV, 바이오·의료기기, 우주·통신, ESS·산업재·소재, 환율·금리 — 산업 에이전트가 그대로 인용할 수 있게 구체적 수치 경로(예: DRAM 가격 연도별 방향, 관세율, 환율 레인지)로 작성.
- 민감도 분석용 표준 충격의 정의와 개연성.
- 핵심 불확실성.
확률을 확정적 사실처럼 쓰지 말고, 사실과 가정을 구분하라.`, { label: 'C2:scenarios', phase: 'Scenarios', schema: SCEN_SCHEMA })

return { facts, semi, others, scen }
