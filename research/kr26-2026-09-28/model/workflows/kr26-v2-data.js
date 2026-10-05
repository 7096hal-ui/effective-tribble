export const meta = {
  name: 'kr26-v2-data',
  description: '데이터 팩 수집(검색 상한 엄수): 산업군별 데이터 에이전트가 10/2 종가·시총·실적·이벤트를, 거시 데이터 에이전트가 10/2 금리·지수·환율·주요 사건을 WebSearch로 확인',
  phases: [{ title: 'Data', detail: '산업군별/거시 데이터 에이전트(검색 상한 명시)' }],
}

const ROOT = '/home/user/effective-tribble/research/kr26-2026-09-28'

const COMMON = `[공통 작업 맥락 — 반드시 준수]
• 프로젝트: 한국 상장사 26개 종목의 1·3·5년 기대 총주주수익률(TSR)과 위험조정수익률 순위를 산출하는 기관투자자급 멀티에이전트 리서치. 당신은 그중 데이터 수집 역할을 맡는다.
• 시점: 작업 재개 시각은 2026-10-06(화) 02:30 KST 무렵이다. 10/3(토) 개천절에 이어 10/5(월)이 대체공휴일로 휴장했을 가능성이 높으므로, 최신 공식 종가는 2026-10-02(금) KRX 정규장 종가일 것이다(휴장 여부도 확인). 앞선 단계는 2026-09-28 종가 기준이었고 이번에 최신 종가로 갱신한다. NXT(넥스트레이드) 애프터마켓 가격이나 장중가를 KRX 종가와 혼동하지 말라.
• 도구 제약: 외부 데이터 경로는 WebSearch뿐이다. 세션 전체 WebSearch 한도가 매우 작아서(모든 에이전트가 남은 약 190회를 공유) 당신에게 배정된 검색 상한을 절대 넘기지 말라. 검색할 때마다 횟수를 세고, 상한에 이르면 즉시 멈추고 확보한 것만으로 반환하라. WebFetch·curl은 거의 모든 도메인이 차단돼 있으니 시도하지 말라. WebSearch가 목록에 없으면 ToolSearch로 "select:WebSearch"를 먼저 로드하라(ToolSearch는 검색 횟수에 포함되지 않는다).
• 검색 요령: 한 번의 검색에서 여러 값을 얻도록 질의를 설계하라(예: "<종목명> 주가 10월 2일 종가 시가총액"). 검색 요약문은 날짜를 자주 혼동하므로 기사 날짜와 등락폭·등락률의 산술 정합성으로 종가를 검증하라(예: 종가 = 전일 종가 + 등락폭). 유사한 이름의 다른 종목과 혼동하지 말라.
• 출처 원칙: KRX·DART 공시(공시를 인용한 보도 포함) > 회사 IR > 정부·규제기관 > 고객사 공식발표 > 한국은행·통계청 > 금융정보업체·증권사 컨센서스 > 신뢰도 높은 언론. 익명 게시물·블로그·유튜브 주장에 의존하지 말라. 핵심 수치마다 출처(매체명, URL)와 자료 기준일을 붙이고 뉴스는 게시일과 사건일을 구분하라. 확인하지 못한 값은 추측하지 말고 null 또는 '확인 불가'로 둔다. 출처가 충돌하면 차이와 채택 근거를 적는다.
• 출력: 한국어. 최종 결과는 지정된 StructuredOutput 스키마로만 반환한다.`

const NUM = { type: ['number', 'null'] }
const STR = { type: ['string', 'null'] }
const SRC = { type: 'object', properties: { title: { type: 'string' }, url: { type: 'string' }, date: { type: 'string' } }, required: ['title', 'url'] }
const STOCK = { type: 'object', properties: {
  input_name: { type: 'string' }, legal_name_ko: { type: 'string' }, code: { type: 'string' }, market: { type: 'string' },
  tradable: { type: 'boolean' }, tradability_note: { type: 'string' },
  close: NUM, close_date: STR, prev_close: NUM, prev_close_date: STR, close_sources: { type: 'array', items: { type: 'string' } }, price_note: { type: 'string' },
  shares_common: NUM, shares_asof: STR, market_cap_krw: NUM, market_cap_asof: STR,
  high_52w: NUM, low_52w: NUM, range_note: { type: 'string' },
  latest_results: { type: 'string' }, outlook_consensus: { type: 'string' }, corporate_events: { type: 'string' },
  recent_news: { type: 'array', items: { type: 'object', properties: { date: { type: 'string' }, item: { type: 'string' }, source: { type: 'string' } }, required: ['date', 'item', 'source'] } },
  business_summary: { type: 'string' }, proposed_group: { type: 'string' },
  searches_used: { type: 'integer' }, flags: { type: 'array', items: { type: 'string' } }, sources: { type: 'array', items: SRC } },
  required: ['input_name', 'legal_name_ko', 'code', 'market', 'tradable', 'tradability_note', 'close', 'close_date', 'prev_close', 'prev_close_date', 'close_sources', 'price_note', 'shares_common', 'market_cap_krw', 'high_52w', 'low_52w', 'range_note', 'latest_results', 'outlook_consensus', 'corporate_events', 'recent_news', 'business_summary', 'proposed_group', 'searches_used', 'flags', 'sources'] }
const GROUP_SCHEMA = { type: 'object', properties: { group: { type: 'string' }, stocks: { type: 'array', items: STOCK }, total_searches_used: { type: 'integer' }, notes: { type: 'string' } }, required: ['group', 'stocks', 'total_searches_used', 'notes'] }
const DP = { type: 'object', properties: { variable: { type: 'string' }, value: { type: 'string' }, asof: { type: 'string' }, source: { type: 'string' } }, required: ['variable', 'value', 'asof', 'source'] }
const MACRO_SCHEMA = { type: 'object', properties: {
  latest_trading_day: { type: 'string' }, holiday_note: { type: 'string' },
  kospi_close: NUM, kosdaq_close: NUM, index_date: STR,
  ktb1y_pct: NUM, ktb3y_pct: NUM, ktb5y_pct: NUM, ktb10y_pct: NUM, rates_date: STR,
  usdkrw: NUM, usdkrw_date: STR, bok_rate_pct: NUM, brent_usd: NUM, ust10y_pct: NUM,
  events_since_0928: { type: 'array', items: DP }, data_points: { type: 'array', items: DP },
  searches_used: { type: 'integer' }, flags: { type: 'array', items: { type: 'string' } }, sources: { type: 'array', items: SRC } },
  required: ['latest_trading_day', 'holiday_note', 'kospi_close', 'kosdaq_close', 'index_date', 'ktb1y_pct', 'ktb3y_pct', 'ktb5y_pct', 'rates_date', 'usdkrw', 'usdkrw_date', 'bok_rate_pct', 'events_since_0928', 'data_points', 'searches_used', 'flags', 'sources'] }

function groupTask(job) {
  const lines = job.stocks.map(s => {
    const prior = s.file ? ` 기존 1단계 결과 파일: ${ROOT}/data/phase1/identify/${s.file} (먼저 Read로 읽고 이미 확인된 값은 다시 검색하지 말 것)` : ''
    return `- ${s.name} (코드 힌트: ${s.code_hint}; 상태: ${s.status}; 이 종목 검색 상한 ${s.cap}회)${prior}`
  }).join('\n')
  return `[역할: 데이터 수집 에이전트 — ${job.group}]
아래 종목들의 최신 데이터 팩을 만든다. 이 에이전트 전체 검색 상한은 ${job.cap_total}회이고 종목별 상한도 지켜라.
${lines}

종목마다 확보할 것(우선순위 순):
1) 2026-10-02(또는 확인된 최신 거래일) KRX 공식 종가, 직전 거래일 종가와 날짜, 등락률. 법인명·종목코드·시장·거래 가능 여부(거래정지·관리종목·투자경고 여부)를 함께 확인.
2) 상장 보통주식수(기준일)와 시가총액(기준일), 52주 최고·최저.
3) 최근 실적(2026년 2분기 또는 상반기: 매출·영업이익·순이익과 전년 대비)과 2026E·2027E 전망·컨센서스·목표주가·회사 가이던스.
4) 최근 6개월 기업행위와 희석 요인: 유상증자, CB·BW·EB, 자사주 매입·소각, 보호예수 해제, 최대주주 변동, 대형 수주·계약, 임상·허가, 소송.
5) 최근 3개월 주요 뉴스(날짜, 내용, 출처)와 핵심 사업 요약, 산업분류 제안(메모리·HBM밸류체인 / AI하드웨어·디스플레이·검사장비·팹리스 / 자동차·전장·SDV·부품 / 바이오·의료기기·진단 / 우주항공·위성통신·5G6G·방산RF / ESS·산업재·특수소재).
상태가 'covered'인 종목은 기존 파일에 9/28 데이터가 있으므로 10/2 종가와 9/28 이후 새 사건만 확인하라. 'partial'은 부족한 값부터 채워라. 'missing'은 기존 데이터가 없다(이전 세션에서 검색을 못 했음).
종목마다 searches_used에 실제 사용한 검색 횟수를 적고, total_searches_used에 합계를 적어라. 확인하지 못한 항목은 null 또는 '확인 불가'로 두고 flags에 적어라.`
}

const MACRO_TASK = `[역할: 거시 데이터 갱신 에이전트] 검색 상한 6회.
이전 단계의 거시 분석은 2026-09-28 기준이다(파일: ${ROOT}/data/phase1/macro/C1-macro-topdown.json, C2-macro-cycle.json — 필요한 부분만 Read로 참고). 다음을 2026-10-02(또는 최신 거래일) 기준으로 갱신하라.
1) 9/29~10/5 사이 KRX 휴장일(10/1 국군의날 임시공휴일 여부, 10/5 대체공휴일 여부)과 최신 거래일.
2) KOSPI·KOSDAQ 최신 종가와 날짜.
3) 국고채 1년·3년·5년·10년 금리 최신 종가와 날짜.
4) 원/달러 환율 최신 종가, 한국은행 기준금리, 브렌트유, 미 국채 10년.
5) 9/29~10/5 사이 중요한 거시·지정학·정책 사건(이란 전쟁·호르무즈, 연준·한은 발언, 미국 고용·물가, 관세, 반도체 업황 뉴스 등).
한 번의 검색에서 여러 값을 얻도록 질의를 설계하라(예: "10월 2일 국고채 3년 금리 원달러 환율 마감"). 사용한 검색 횟수를 searches_used에 적어라.`

phase('Data')
const out = await parallel(args.jobs.map(job => () => job.type === 'macro'
  ? agent(COMMON + '\n\n' + MACRO_TASK, { label: 'D:거시갱신', phase: 'Data', schema: MACRO_SCHEMA, effort: 'high' })
  : agent(COMMON + '\n\n' + groupTask(job), { label: 'D:' + job.group, phase: 'Data', schema: GROUP_SCHEMA, effort: 'high' })))
return out.map((r, i) => {
  const job = args.jobs[i]
  if (!r) return { job: job.group || 'macro', failed: true }
  if (job.type === 'macro') return { job: 'macro', day: r.latest_trading_day, kospi: r.kospi_close, kosdaq: r.kosdaq_close, ktb: [r.ktb1y_pct, r.ktb3y_pct, r.ktb5y_pct], usdkrw: r.usdkrw, used: r.searches_used }
  return { job: job.group, used: r.total_searches_used, stocks: r.stocks.map(s => ({ name: s.input_name, code: s.code, close: s.close, date: s.close_date, mcap: s.market_cap_krw, used: s.searches_used, nflags: s.flags.length })) }
})
