export const meta = {
  name: 'kr-equity-delta-update',
  description: 'Refresh prices, market anchors and material news between the 2026-09-28 data snapshot and the current run date',
  phases: [
    { title: 'Market', detail: 'KRX calendar, index/FX/rates at latest close, macro events since 9/28' },
    { title: 'Stocks', detail: 'latest close and material disclosures/news per stock since 9/28' },
  ],
}

const CTX = `[공통 맥락]
- 한국 상장주식 26개 종목의 1·3·5년 총주주수익률(TSR) 순위 프로젝트. 펀더멘털 자료는 2026-09-28(월) 장마감 기준으로 이미 수집했다. 지금은 실행 시점(${args.runTime})까지의 변동분만 갱신한다.
- 도구: WebSearch만 가능(ToolSearch로 "select:WebSearch" 로드). WebFetch·Bash 네트워크는 egress 차단. 세션 검색 예산이 있으니 권장 횟수 이내로. "web search budget" 메시지가 나오면 검색을 멈추고 확보한 정보만으로 작성하라.
- WebSearch 요약은 날짜를 혼동할 수 있다. 가격은 서로 다른 검색어로 교차확인하고, 기사 게시일과 가격·사건 기준일을 구분하라. 날조 금지, 확인 불가는 null.
- 한국어, 간결한 보고서체.`

const MARKET_SCHEMA = {
  type: 'object',
  properties: {
    calendar: { type: 'string', description: '2026-09-29~실행일 사이 KRX 거래일·휴장일(개천절 대체공휴일 등)과 가장 최근 정규장 거래일' },
    latest_trading_day: { type: 'string' },
    kospi: { type: 'object', properties: { close: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, source: { type: 'string' } }, required: ['close', 'date', 'source'] },
    kosdaq: { type: 'object', properties: { close: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, source: { type: 'string' } }, required: ['close', 'date', 'source'] },
    usdkrw: { type: 'object', properties: { value: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, source: { type: 'string' } }, required: ['value', 'date', 'source'] },
    ktb: { type: 'object', properties: { y1: { type: ['number', 'null'] }, y3: { type: ['number', 'null'] }, y5: { type: ['number', 'null'] }, y10: { type: ['number', 'null'] }, date: { type: ['string', 'null'] }, source: { type: 'string' } }, required: ['y1', 'y3', 'y5', 'y10', 'date', 'source'] },
    ust10y: { type: 'object', properties: { value: { type: ['number', 'null'] }, date: { type: ['string', 'null'] } }, required: ['value', 'date'] },
    events: { type: 'array', items: { type: 'object', properties: { pub_date: { type: 'string' }, event_date: { type: 'string' }, summary: { type: 'string' }, source: { type: 'string' } }, required: ['pub_date', 'event_date', 'summary', 'source'] } },
    material_change_vs_0928: { type: 'string', description: '9/28 거시 시나리오(기준 50%·낙관 20%·비관 30%)의 확률이나 경로를 바꿔야 할 만큼 중요한 변화가 있었는지와 근거' },
  },
  required: ['calendar', 'latest_trading_day', 'kospi', 'kosdaq', 'usdkrw', 'ktb', 'ust10y', 'events', 'material_change_vs_0928'],
}

const STOCKS_SCHEMA = {
  type: 'object',
  properties: {
    stocks: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' },
      close_krw: { type: ['number', 'null'] }, close_date: { type: ['string', 'null'] },
      cross_checked: { type: 'boolean' }, price_sources: { type: 'array', items: { type: 'string' } },
      also_found_0928_close: { type: ['number', 'null'], description: '9/28 종가를 새로 확인했다면 그 값(9/28 기준가 보정용)' },
      news: { type: 'array', items: { type: 'object', properties: { pub_date: { type: 'string' }, event_date: { type: 'string' }, summary: { type: 'string' }, source: { type: 'string' }, materiality: { type: 'string', enum: ['high', 'medium', 'low'] } }, required: ['pub_date', 'event_date', 'summary', 'source', 'materiality'] } },
      thesis_impact: { type: 'string', description: '9/28 이후 사건이 투자논지·실적·희석·지배구조에 주는 영향. 없으면 "중대한 변화 없음(확인 범위: …)"' },
    }, required: ['name', 'close_krw', 'close_date', 'cross_checked', 'price_sources', 'also_found_0928_close', 'news', 'thesis_impact'] } },
  },
  required: ['stocks'],
}

phase('Market')
const market = agent(`${CTX}

역할: C1-Δ. 시장 변동분 갱신. 검색 최대 10회.
1) 2026-09-29~${args.runDate} KRX 거래일과 휴장일(2026-10-03 개천절이 토요일이라 10-05(월) 대체공휴일인지 등)을 확인하고 가장 최근 정규장 거래일을 정하라.
2) 그 거래일의 KOSPI·KOSDAQ 종가, 원/달러 종가, 국고채 1·3·5·10년 금리, 미 국채 10년 금리.
3) 9/29 이후 한국 증시·금리·환율·반도체·자동차·바이오 업황에 중요한 사건(게시일·사건일 구분).
4) 9/28 기준 거시 시나리오(기준 50%·낙관 20%·비관 30%, 메모리 2027년 상반기 고점, 한국 기준금리 3.00%, 미 연방기금 3.75~4.00%)를 바꿔야 할 변화가 있는지 판단.`, { label: 'C1-delta:market', phase: 'Market', schema: MARKET_SCHEMA, effort: 'medium' })

phase('Stocks')
const batches = await parallel(args.batches.map((b, i) => () => agent(`${CTX}

역할: B-Δ. 종목 변동분 갱신. 대상 종목과 9/28 스냅샷의 기준가:
${b.map(s => `- ${s.name} (${s.code}, ${s.market}): ${s.P0}원 (${s.P0_date} 종가)`).join('\n')}

각 종목마다(종목당 검색 최대 3회):
1) 가장 최근 정규장 종가와 그 날짜(실행일 ${args.runDate} 기준 가장 최근 거래일, 아마 2026-10-02(금)). 교차확인하고 출처를 적어라. 찾지 못하면 null.
2) 스냅샷 기준가가 9/28 종가가 아니었던 종목은 9/28 종가도 찾으면 also_found_0928_close에 기록.
3) 9/29 이후 주요 공시·뉴스(실적 잠정치·가이던스, 수주·계약, 유상증자·CB·자사주, 최대주주 변동, 임상·허가, 소송, 거래정지 등)와 투자논지에 대한 영향.`, { label: `B-delta:batch${i + 1}`, phase: 'Stocks', schema: STOCKS_SCHEMA, effort: 'medium' })))

const m = await market
return { market: m, stocks: batches.filter(Boolean).flatMap(x => x.stocks) }
