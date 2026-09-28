export const meta = {
  name: 'kr26-stageA-identify',
  description: 'B 종목 식별·데이터 검증: 종목별 독립 에이전트가 코드·시장·거래상태·기업행위·종가·주식수·희석·실적·위험용 시장데이터를 WebSearch로 확인',
  phases: [{ title: 'Identify', detail: '종목별 B 에이전트(WebSearch 교차확인)' }],
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
const EVT = { type: 'object', properties: { type: { type: 'string' }, date: { type: 'string' }, detail: { type: 'string' }, source: { type: 'string' } }, required: ['type', 'detail'] }
const NUM = { type: ['number', 'null'] }
const STR = { type: ['string', 'null'] }
const B_SCHEMA = { type: 'object', properties: {
  input_name: { type: 'string' }, legal_name_ko: { type: 'string' }, legal_name_en: STR, code: { type: 'string' },
  market: { type: 'string' }, share_class: { type: 'string' }, listing_date: STR,
  tradable_on_2026_09_28: { type: 'boolean' }, tradability_note: { type: 'string' },
  status_designations: { type: 'array', items: EVT }, corporate_actions: { type: 'array', items: EVT },
  price: { type: 'object', properties: { krx_close_krw: NUM, close_date: STR, prev_close_krw: NUM, prev_close_date: STR, pct_change: NUM, nxt_note: { type: 'string' }, sources: { type: 'array', items: { type: 'string' } }, cross_check_note: { type: 'string' } }, required: ['krx_close_krw', 'close_date', 'prev_close_krw', 'prev_close_date', 'sources', 'cross_check_note'] },
  shares: { type: 'object', properties: { common_listed: NUM, preferred_listed: NUM, treasury_common: NUM, asof: STR, source: { type: 'string' } }, required: ['common_listed', 'treasury_common', 'asof', 'source'] },
  dilution: { type: 'object', properties: {
    instruments: { type: 'array', items: { type: 'object', properties: { type: { type: 'string' }, potential_shares: NUM, conversion_price: NUM, maturity_or_exercise: STR, note: { type: 'string' } }, required: ['type', 'potential_shares', 'note'] } },
    total_potential_shares: NUM, fully_diluted_shares: NUM, note: { type: 'string' } }, required: ['instruments', 'total_potential_shares', 'fully_diluted_shares', 'note'] },
  market_cap: { type: 'object', properties: { value_krw: NUM, asof: STR, method: { type: 'string' } }, required: ['value_krw', 'asof', 'method'] },
  fiscal: { type: 'object', properties: { latest_annual_period: STR, latest_quarter_period: STR, annual: { type: 'string' }, latest_quarter: { type: 'string' }, audit_opinion: STR, sources: { type: 'array', items: { type: 'string' } } }, required: ['latest_annual_period', 'latest_quarter_period', 'annual', 'latest_quarter', 'audit_opinion'] },
  business: { type: 'object', properties: { core: { type: 'string' }, segments: { type: 'string' }, key_customers: { type: 'string' }, proposed_group: { type: 'string' } }, required: ['core', 'segments', 'key_customers', 'proposed_group'] },
  risk_market_data: { type: 'object', properties: {
    high_52w: NUM, high_52w_date: STR, low_52w: NUM, low_52w_date: STR, all_time_high: NUM, all_time_high_date: STR,
    returns: { type: 'string' }, avg_daily_trading_value_krw: NUM, adtv_note: { type: 'string' }, beta_reported: NUM,
    gap_events: { type: 'string' }, index_membership: { type: 'string' }, foreign_ownership_pct: NUM },
    required: ['high_52w', 'low_52w', 'returns', 'avg_daily_trading_value_krw', 'adtv_note', 'gap_events', 'index_membership'] },
  consensus: { type: 'string' },
  recent_news: { type: 'array', items: { type: 'object', properties: { date: { type: 'string' }, item: { type: 'string' }, significance: { type: 'string' }, source: { type: 'string' } }, required: ['date', 'item'] } },
  data_flags: { type: 'array', items: { type: 'string' } },
  confidence: { type: 'string', enum: ['높음', '보통', '낮음'] },
  sources: { type: 'array', items: SRC } },
  required: ['input_name', 'legal_name_ko', 'code', 'market', 'share_class', 'tradable_on_2026_09_28', 'tradability_note', 'status_designations', 'corporate_actions', 'price', 'shares', 'dilution', 'market_cap', 'fiscal', 'business', 'risk_market_data', 'consensus', 'recent_news', 'data_flags', 'confidence', 'sources'] }

function task(s) {
  return `[역할: B. 종목 식별·데이터 검증 에이전트]
대상 종목(사용자 입력명): ${s.name}  (참고용 코드 힌트: ${s.code_hint} — 검증되지 않은 힌트이니 반드시 스스로 확인)
다음을 확정하라.
1) 정확한 법인명(국문·영문), 종목코드(2024년 이후 신규 상장은 영숫자 코드일 수 있음), 상장시장(KOSPI/KOSDAQ/KONEX), 분석 대상 주식 구분(보통주), 상장일.
2) 2026-09-28 현재 거래 가능 여부와 최근 12개월 거래정지·관리종목·투자주의/경고/위험 지정·상장적격성 실질심사·불성실공시 이력.
3) 최근 5년 사명 변경·인적분할·물적분할·합병·재상장·액면분할/병합·무상증자 이력. 분할 전후 회사나 이름이 비슷한 회사와 혼동하지 말라.
4) 2026-09-28 KRX 공식 종가(원), 전일 대비 등락률, 직전 거래일 종가와 날짜. 날짜를 반드시 확인하고 서로 다른 검색어로 교차확인하라. 9/28 종가를 끝내 확보하지 못하면 가장 최근에 확인된 종가와 날짜를 쓰고 data_flags에 적어라.
5) 상장주식수(보통주·우선주), 자기주식 수, 기준일. 시가총액 = 종가 × 상장 보통주식수(우선주는 별도) — 기준일과 계산방식 명시.
6) 완전희석 주식수: 미상환 CB/BW/EB/RCPS(전환가·잠재주식수·만기·리픽싱 조건), 스톡옵션·RSU, 예정된 유상증자. 잠재주식 합계와 완전희석 주식수. 해당 사항이 없음을 확인했다면 instruments를 빈 배열로 두고 note에 근거를 적어라.
7) 최근 결산 기준일(연간·분기), 최근 연간 및 최근 분기 매출·영업이익·순이익(전년 대비 증감), 감사의견.
8) 핵심 사업(부문별 매출 비중), 주요 제품·고객, 그리고 다음 6개 중 하나의 산업분류 제안: 메모리·HBM밸류체인 / AI하드웨어·디스플레이·검사장비·팹리스 / 자동차·전장·SDV·부품 / 바이오·의료기기·진단 / 우주항공·위성통신·5G6G·방산RF / ESS·산업재·특수소재.
9) 위험 분석용 시장데이터: 52주 최고·최저(날짜), 상장 후 최고가와 현재 낙폭, 최근 1개월·3개월·6개월·1년·3년 주가수익률(확인 가능한 것만, 기준일 명시), 최근 평균 일거래대금(원), 공표된 베타, 최근 1년 내 일간 ±10% 이상 급등락·갭 사례, KOSPI200·KOSDAQ150 편입 여부, 외국인 지분율.
10) 컨센서스 스냅샷(참고용): 평균 목표주가, 커버 증권사 수, 2026E·2027E 매출·영업이익·EPS(출처·일자). 없으면 '확인 불가'.
11) 최근 3개월 중요 뉴스·공시(날짜, 내용, 중요도).
12) 데이터상 특이사항(보호예수 해제 일정, 오버행, 짧은 주가이력, 대규모 메자닌 등)을 data_flags에.
모든 수치에 기준일과 출처를 붙이고, 확인하지 못한 필드는 null로 두고 data_flags에 사유를 적어라.`
}

phase('Identify')
const out = await parallel(args.stocks.map(s => () =>
  agent(COMMON + '\n\n' + task(s), { label: 'B:' + s.name, phase: 'Identify', schema: B_SCHEMA, effort: 'high' })))
return out.map((r, i) => {
  const s = args.stocks[i]
  if (!r) return { no: s.no, name: s.name, failed: true }
  return { no: s.no, name: s.name, legal: r.legal_name_ko, code: r.code, market: r.market, tradable: r.tradable_on_2026_09_28,
    close: r.price.krx_close_krw, close_date: r.price.close_date, prev: r.price.prev_close_krw, prev_date: r.price.prev_close_date,
    shares: r.shares.common_listed, mcap: r.market_cap.value_krw, fd_shares: r.dilution.fully_diluted_shares,
    group: r.business.proposed_group, conf: r.confidence, flags: r.data_flags }
})
