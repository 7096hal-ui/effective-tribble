export const meta = {
  name: 'kr-equity-data-forensic-risk',
  description: 'Per-stock identification/data verification (B), accounting-governance forensics (E) and quant-risk (G) passes for a group of Korean stocks',
  phases: [
    { title: 'Data', detail: 'B: identification, price, shares, financials, catalysts' },
    { title: 'Forensic', detail: 'E: accounting, governance, dilution, overhang' },
    { title: 'Risk', detail: 'G: volatility, beta, drawdown, liquidity, event risk' },
  ],
}

const CTX = `[공통 맥락 — 모든 에이전트 공통]
- 프로젝트: 한국 상장주식 26개 종목의 1년·3년·5년 총주주수익률(TSR) 전망·순위화를 위한 기관급 멀티에이전트 리서치. 당신은 그중 한 역할이다. 산출물은 최종 보고서의 근거가 되므로 정확성이 최우선이다.
- 분석 기준 시각: 2026-09-28(월) 19:40 KST, 한국거래소 정규장 마감 후. 순위 계산용 기준 주가: 2026-09-28 정규장 종가(확인 불가 시 확인 가능한 가장 최근 종가와 그 날짜를 명시).
- 전망 종료일: 1년 2027-09-28(화), 3년 2029-09-28(금), 5년 2031-09-28(일요일이므로 직전 거래일 종가). 통화 KRW.
- TSR 정의: 세전·수수료 차감 전 원화 기준. 주가 변화 + 기간 중 배당 + 자사주 소각·희석(유상증자, CB/BW 전환, 스톡옵션)에 따른 주당가치 변화를 모두 반영.
- 오케스트레이터 사전 확인(검증 필요, 검색 요약 기반): 2026-09-28 KOSPI 종가 6,889.74(-2.70%), 삼성전자 270,000원(-5.43%), SK하이닉스 1,768,000원(-5.05%) (서울신문·글로벌이코노믹 2026-09-28 기사). 삼성에피스홀딩스 코드 0126Z0, 2026-09-17 기준 335,000원·시총 약 8.1조원·52주 325,500~773,000원(검색 요약). 2026년 추석 연휴(9/24~9/26 전후)로 9/28 직전 거래일은 9/23일 가능성이 높음(검증 필요).
- 도구 제약: 이 환경에서 WebFetch와 Bash 외부 네트워크는 egress 차단(네이버·다음·KRX·DART·FnGuide·Investing·위키백과·언론사 모두 차단 확인)이다. WebSearch만 사용 가능하다(ToolSearch로 "select:WebSearch" 로드). WebSearch는 링크 목록과 모델 생성 요약을 준다. 요약은 날짜를 혼동하거나 오래된 값을 줄 수 있으므로 핵심 수치는 서로 다른 검색어로 2회 이상 교차확인하고, 출처 URL·기사 게시일·실제 사건/데이터 기준일을 구분해 기록하라. WebFetch는 시도하지 말라.
- 금지: 수치·출처·사건 날조, 유료 DB(FnGuide·Bloomberg 등) 접근 가장, 추정치를 확인된 사실처럼 쓰기. 확인 불가 값은 null 또는 "확인 불가". 확률을 확정적 사실처럼 표현하지 말 것.
- 출력은 한국어, 간결한 보고서체. 재무 금액은 억원, 주가·주당 값은 원.`

const SRC = { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, title: { type: 'string' }, pub_date: { type: 'string' }, used_for: { type: 'string' } }, required: ['url', 'used_for'] } }
const N = { type: ['number', 'null'] }
const S = { type: ['string', 'null'] }

const DATA_SCHEMA = {
  type: 'object',
  properties: {
    name_input: { type: 'string' },
    legal_name: { type: 'string' },
    code: { type: 'string' },
    market: { type: 'string', description: 'KOSPI/KOSDAQ/KONEX/비상장/상장예정 등' },
    share_class: { type: 'string', description: '보통주/우선주, 지주회사/사업회사 구분' },
    listing_date: S,
    tradable_on_asof: { type: 'boolean', description: '2026-09-28 기준 정상 거래 가능 여부' },
    status_notes: { type: 'string', description: '거래정지·관리종목·투자주의/경고/위험·불성실공시 여부. 없으면 확인 범위를 적고 "특이사항 없음"' },
    corporate_actions_history: { type: 'string', description: '사명변경·인적/물적분할·합병·재상장·IPO·액면분할·이전상장 이력(날짜 포함). 혼동 가능한 유사명 회사 명시' },
    price: { type: 'object', properties: { close_krw: N, close_date: S, change_pct_on_day: N, prev_close_krw: N, sources: { type: 'array', items: { type: 'string' } }, cross_checked: { type: 'boolean' }, note: { type: 'string' } }, required: ['close_krw', 'close_date', 'sources', 'cross_checked', 'note'] },
    range_52w: { type: 'object', properties: { high: N, low: N, asof: S }, required: ['high', 'low', 'asof'] },
    return_1y_pct: N,
    price_history_note: { type: 'string', description: '최근 1~3년 주요 가격 궤적(고점·저점 시점과 가격), 상장 이후 흐름' },
    shares: { type: 'object', properties: { common_outstanding: N, treasury: N, preferred: N, fully_diluted_estimate: N, asof: S, note: { type: 'string' } }, required: ['common_outstanding', 'treasury', 'fully_diluted_estimate', 'asof', 'note'] },
    market_cap_krw_eok: N,
    market_cap_asof: S,
    avg_daily_trading_value_eok: N,
    fiscal: { type: 'object', properties: {
      fy_end: { type: 'string' },
      latest_reported_period: { type: 'string' },
      rows: { type: 'array', items: { type: 'object', properties: { period: { type: 'string' }, revenue_eok: N, op_income_eok: N, net_income_ctrl_eok: N, ocf_eok: N, capex_eok: N, eps_krw: N, dps_krw: N, source: { type: 'string' } }, required: ['period', 'revenue_eok', 'op_income_eok', 'net_income_ctrl_eok', 'source'] } },
    }, required: ['fy_end', 'latest_reported_period', 'rows'] },
    balance_sheet: { type: 'object', properties: { asof: S, cash_eok: N, debt_eok: N, net_cash_eok: N, equity_ctrl_eok: N, bps_krw: N, note: { type: 'string' } }, required: ['asof', 'cash_eok', 'debt_eok', 'net_cash_eok', 'equity_ctrl_eok', 'note'] },
    shareholder_returns: { type: 'string', description: '배당정책, 최근 DPS, 분기배당 여부, 자사주 매입·소각 공시(날짜)' },
    dilution_instruments: { type: 'string', description: 'CB/BW/EB/RCPS 잔액·전환가·만기, 스톡옵션, 유상증자 이력·계획, 보호예수 해제 일정' },
    ownership: { type: 'string', description: '최대주주·특수관계인 지분, 주요 주주(PE/VC 포함), 외국인 지분율, 유통주식 비율' },
    business: { type: 'string', description: '핵심 사업, 매출 구성, 주요 고객·집중도, 경쟁사' },
    industry_group: { type: 'string', enum: ['SEMI_AI_DISPLAY', 'AUTO_SDV', 'BIO_MEDTECH', 'SPACE_TELECOM', 'ESS_INDUSTRIAL_MATERIALS'] },
    industry_group_rationale: { type: 'string' },
    consensus: { type: 'object', properties: { target_price_avg_krw: N, n_brokers: N, fy_estimates: { type: 'string', description: 'FY2026E/27E/28E 매출·영업이익·EPS 컨센서스(있으면)' }, asof: S, source: { type: 'string' } }, required: ['target_price_avg_krw', 'fy_estimates', 'asof', 'source'] },
    valuation_snapshot: { type: 'string', description: 'trailing/forward PER·PBR·EV/EBITDA·배당수익률(출처·기준일)' },
    recent_developments: { type: 'array', items: { type: 'object', properties: { pub_date: { type: 'string' }, event_date: { type: 'string' }, summary: { type: 'string' }, source: { type: 'string' } }, required: ['pub_date', 'event_date', 'summary', 'source'] } },
    upcoming_catalysts: { type: 'array', items: { type: 'string' } },
    data_quality: { type: 'object', properties: { grade: { type: 'string', enum: ['A', 'B', 'C', 'D'], description: 'A=핵심수치 복수출처 확인, D=대부분 확인 불가' }, unverified_items: { type: 'array', items: { type: 'string' } }, conflicts: { type: 'string', description: '출처 간 충돌과 채택 근거' } }, required: ['grade', 'unverified_items', 'conflicts'] },
    sources: SRC,
  },
  required: ['name_input', 'legal_name', 'code', 'market', 'share_class', 'tradable_on_asof', 'status_notes', 'corporate_actions_history', 'price', 'range_52w', 'return_1y_pct', 'price_history_note', 'shares', 'market_cap_krw_eok', 'market_cap_asof', 'fiscal', 'balance_sheet', 'shareholder_returns', 'dilution_instruments', 'ownership', 'business', 'industry_group', 'industry_group_rationale', 'consensus', 'valuation_snapshot', 'recent_developments', 'upcoming_catalysts', 'data_quality', 'sources'],
}

const FORENSIC_SCHEMA = {
  type: 'object',
  properties: {
    audit: { type: 'string', description: '감사인, 최근 감사의견, 강조사항·계속기업 불확실성, 핵심감사사항, 정정공시' },
    earnings_quality: { type: 'string', description: '영업현금흐름 vs 순이익 괴리, 일회성 손익, 개발비 자산화, 매출채권·재고 추이' },
    related_party: { type: 'string' },
    contingencies: { type: 'string', description: '소송, 보증, 우발채무, 규제 조사' },
    concentration: { type: 'string', description: '고객·공급자 집중도(상위 고객 매출 비중 수치)' },
    leverage_liquidity: { type: 'string', description: '순현금/순차입, 차입 만기, 이자보상' },
    dilution: { type: 'object', properties: {
      instruments: { type: 'string' },
      expected_share_increase_pct_1y: { type: 'number', description: '기대 주식수 증가율(%) — 확률가중. 자사주 소각은 음수' },
      expected_share_increase_pct_3y: { type: 'number' },
      expected_share_increase_pct_5y: { type: 'number' },
      prob_equity_raise_3y: { type: 'number', description: '0~1, 향후 3년 내 유상증자·CB/BW 신규발행 확률' },
      rationale: { type: 'string' },
    }, required: ['instruments', 'expected_share_increase_pct_1y', 'expected_share_increase_pct_3y', 'expected_share_increase_pct_5y', 'prob_equity_raise_3y', 'rationale'] },
    governance: { type: 'string', description: '최대주주, 지주회사 할인, 복잡한 지배구조, 소액주주와의 이해상충, 자사주 보유·소각·처분 가능성' },
    overhang: { type: 'string', description: '보호예수 해제, 대주주·PE/VC 매도, 블록딜' },
    red_flags: { type: 'array', items: { type: 'object', properties: { flag: { type: 'string' }, severity: { type: 'string', enum: ['high', 'medium', 'low'] }, evidence: { type: 'string' }, source: { type: 'string' } }, required: ['flag', 'severity', 'evidence', 'source'] } },
    permanent_loss_factors: { type: 'string' },
    valuation_adjustments: { type: 'string', description: '가치평가 시 반영할 조정(지주사 할인 %, 희석 %, 순차입, 비지배지분, 일회성 제거 등)' },
    forensic_score: { type: 'string', enum: ['clean', 'minor_concerns', 'material_concerns', 'severe'] },
    sources: SRC,
  },
  required: ['audit', 'earnings_quality', 'related_party', 'contingencies', 'concentration', 'leverage_liquidity', 'dilution', 'governance', 'overhang', 'red_flags', 'permanent_loss_factors', 'valuation_adjustments', 'forensic_score', 'sources'],
}

const RISK_SCHEMA = {
  type: 'object',
  properties: {
    hist_vol_annual_pct: N,
    hist_vol_basis: { type: 'string', description: '측정값 출처 또는 추정 방법(52주 범위, 섹터 유사종목 등)을 명시' },
    forward_vol_annual_pct: { type: 'number', description: '향후 1년 예상 연변동성(%). 과거 외삽이 아니라 사업구조·예정 사건을 반영' },
    downside_vol_annual_pct: { type: 'number' },
    beta_kospi: N,
    beta_basis: { type: 'string' },
    max_drawdown_hist: { type: 'string', description: '과거 최대낙폭과 기간(확인값/추정 구분)' },
    liquidity_tier: { type: 'string', enum: ['very_high', 'high', 'medium', 'low', 'very_low'] },
    liquidity_note: { type: 'string' },
    gap_risk: { type: 'string' },
    cyclicality: { type: 'string', enum: ['very_high', 'high', 'medium', 'low'] },
    financial_leverage: { type: 'string', enum: ['net_cash', 'low', 'medium', 'high'] },
    earnings_estimate_volatility: { type: 'string' },
    discrete_event_risks: { type: 'array', items: { type: 'object', properties: { event: { type: 'string' }, timing: { type: 'string' }, prob: { type: 'number', description: '0~1' }, impact_if_bad_pct: { type: 'number' }, impact_if_good_pct: { type: 'number' } }, required: ['event', 'timing', 'prob', 'impact_if_bad_pct', 'impact_if_good_pct'] } },
    extreme_downside: { type: 'object', properties: { prob_near_zero_or_delist_5y: { type: 'number', description: '0~1' }, prob_permanent_loss_50pct_5y: { type: 'number', description: '0~1, 5년 뒤에도 -50% 이하' }, rationale: { type: 'string' } }, required: ['prob_near_zero_or_delist_5y', 'prob_permanent_loss_50pct_5y', 'rationale'] },
    implied_vol_available: { type: 'boolean' },
    implied_vol_note: { type: 'string' },
    notes: { type: 'string' },
    sources: SRC,
  },
  required: ['hist_vol_annual_pct', 'hist_vol_basis', 'forward_vol_annual_pct', 'downside_vol_annual_pct', 'beta_kospi', 'beta_basis', 'max_drawdown_hist', 'liquidity_tier', 'liquidity_note', 'gap_risk', 'cyclicality', 'financial_leverage', 'earnings_estimate_volatility', 'discrete_event_risks', 'extreme_downside', 'implied_vol_available', 'implied_vol_note', 'notes', 'sources'],
}

const dataPrompt = s => `${CTX}

역할: B. 종목 식별·데이터 검증 에이전트. 대상 입력명: "${s.name}".
오케스트레이터 힌트(검증 대상일 뿐 사실로 간주하지 말 것): ${s.hint}

수행(WebSearch 15~30회 권장):
1) 정확한 법인명, 종목코드, 상장시장, 보통주/우선주·지주/사업회사 구분, 상장일, 사명변경·인적/물적분할·합병·재상장·이전상장 이력. 유사명 회사·분할 전후 회사와 혼동 금지.
2) 2026-09-28 정규장 종가(최우선). 확인 불가 시 확인 가능한 가장 최근 종가와 날짜. 두 개 이상의 독립 검색으로 교차검증. 기사 게시일과 가격 기준일 구분. 당일 등락률·전일 종가도 가능하면.
3) 52주 고저, 1년 수익률(근사), 최근 1~3년 가격 궤적, 평균 거래대금.
4) 보통주 발행주식수, 자사주, 우선주, 완전희석 추정 주식수(CB/BW/RCPS/스톡옵션 반영), 시가총액(기준일). 시가총액 = 종가×보통주 발행주식수와 대조해 모순 여부 확인.
5) FY2023·FY2024·FY2025 및 2026년 상반기(또는 최근 분기·LTM) 연결 기준 매출·영업이익·지배순이익·영업현금흐름·CAPEX·EPS·DPS.
6) 재무상태(현금성자산, 차입금, 순현금, 지배지분 자본, BPS, 기준일).
7) 배당정책·자사주 매입/소각, 희석증권·자금조달 이력과 계획, 보호예수, 최대주주·특수관계인 지분, 외국인 지분율.
8) 핵심 사업·매출구성·주요 고객 및 집중도·경쟁사, 산업군 분류(enum)와 근거. 여러 산업에 걸치면 주된 이익원 기준.
9) 증권사 컨센서스(평균 목표주가, 추정치, 기준일, 출처) — 참고용.
10) 최근 6~12개월 주요 공시·뉴스(게시일과 사건일 구분), 향후 12개월 예정 촉매(실적, 임상, 수주, 양산, 보호예수 해제 등).
11) 현재 밸류에이션 스냅샷.
확인 불가 값은 null로 두고 data_quality.unverified_items에 기록. 출처 간 충돌은 conflicts에 설명.`

const forensicPrompt = (s, d) => `${CTX}

역할: E. 회계·지배구조·포렌식 에이전트. 대상: ${s.name}.
B 에이전트의 검증 데이터(그대로 믿지 말고 필요한 부분은 재확인):
${JSON.stringify(d)}

WebSearch(10~25회 권장)로 다음을 점검하라: 영업현금흐름과 회계이익 괴리, 일회성 손익, 자본화된 개발비, 관계사·내부거래, 감사의견·강조사항·핵심감사사항, 우발채무·소송·보증, 고객·공급자 집중도(수치), 순현금/순차입과 만기, 유상증자·CB·BW·EB·RCPS(잔액·전환가·리픽싱), 스톡옵션, 최대주주 지분·보호예수·오버행(PE/VC·대주주 매도), 지주회사 할인·복잡한 지배구조, 자사주 보유·소각·처분 가능성, 소액주주와 대주주의 이해상충.
희석 기대치는 확률가중 주식수 증가율(%)로 수치화하라(자사주 소각은 음수). 근거 없는 의혹을 만들지 말고, 확인된 사실과 추정을 구분하라. DART 원문에 직접 접근할 수 없으므로 공시 내용은 검색으로 확인된 범위에서만 기술하라.`

const riskPrompt = (s, d) => `${CTX}

역할: G. 정량·위험 에이전트. 대상: ${s.name}.
B 에이전트의 검증 데이터:
${JSON.stringify(d)}

WebSearch(8~20회 권장)로 가능한 범위의 실측 위험지표(변동성, 베타, 과거 최대낙폭, 거래대금, 급락·갭 사례, 외국인 지분 변화)를 찾고, 없으면 52주 범위·가격 궤적·동종기업 수준에서 추정하되 hist_vol_basis/beta_basis에 '측정'인지 '추정'인지와 방법을 명시하라.
과거 변동성을 그대로 외삽하지 말고, 사업구조 변화·예정 사건(실적, 임상, 수주, 보호예수 해제, 지수 편입/편출)을 반영한 forward 연변동성과 하방변동성을 제시하라. 상장 이력이 짧거나 거래가 얇은 종목은 변동성을 낮게 잡지 말라.
이산적 사건위험(임상·수주·고객 채택·기술 전환·규제)은 확률과 성공/실패 시 주가 영향(%)으로 제시하고, 5년 내 주가가 0 근처로 가거나 상장폐지될 확률, 5년 뒤에도 -50% 이하일 확률을 근거와 함께 추정하라.
옵션 내재변동성은 실제로 확보한 경우에만 기재하고, 없으면 implied_vol_available=false.`

const stocks = args.stocks
const results = await pipeline(stocks,
  s => agent(dataPrompt(s), { label: `B:data:${s.name}`, phase: 'Data', schema: DATA_SCHEMA }),
  (d, s) => {
    if (!d) return { stock: s.name, error: 'data agent failed' }
    return parallel([
      () => agent(forensicPrompt(s, d), { label: `E:forensic:${s.name}`, phase: 'Forensic', schema: FORENSIC_SCHEMA }),
      () => agent(riskPrompt(s, d), { label: `G:risk:${s.name}`, phase: 'Risk', schema: RISK_SCHEMA }),
    ]).then(([f, r]) => ({ stock: s.name, data: d, forensic: f, risk: r }))
  },
)

return results.map(r => r && r.data ? ({
  stock: r.stock, code: r.data.code, market: r.data.market, tradable: r.data.tradable_on_asof,
  close: r.data.price.close_krw, close_date: r.data.price.close_date, mcap_eok: r.data.market_cap_krw_eok,
  group: r.data.industry_group, dq: r.data.data_quality.grade,
  forensic: r.forensic ? r.forensic.forensic_score : null, fwd_vol: r.risk ? r.risk.forward_vol_annual_pct : null,
}) : r)
