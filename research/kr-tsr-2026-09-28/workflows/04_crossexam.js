export const meta = {
  name: 'kr-equity-crossexam',
  description: 'Cross-sectional bias check, bear-case cross-examination of provisional leaders, and final judging of scenario sets',
  phases: [
    { title: 'Coordinator', detail: 'A+H: industry bias and base-rate check over the full provisional table' },
    { title: 'Bear', detail: 'I: attack each provisional leader / flagged stock' },
    { title: 'Judge', detail: 'J: integrate, revise scenarios, re-check arithmetic' },
  ],
}

const CTX = `[공통 맥락]
- 한국 상장주식 26개 종목의 1년·3년·5년 총주주수익률(TSR) 전망·순위화 프로젝트. 기준 2026-09-28(월) 장마감 후, 원화, 세전·수수료 차감 전. 전망 종료일 2027-09-28 / 2029-09-28 / 2031-09-28.
- tsr_cum_pct = (기말 주가 + 누적 주당배당)/P0 - 1. 기말 주가는 희석·자사주 소각 반영 현재 1주 기준.
- 파일(Read): 거시 ${args.macroPath}, 종목 도시에 ${args.dossierDir}/<종목명>.json, 종목 분석(산업전문가 sp·일반분석가 ge·보정 fin) ${args.analysisDir}/<종목명>.json, 잠정 순위표 ${args.tablePath}.
- 도구: WebSearch만 가능(ToolSearch "select:WebSearch"). 세션 검색 예산이 있으니 권장 횟수 이내로. "web search budget" 메시지가 나오면 검색을 멈춰라.
- 원칙: 날조 금지, 사실/추정/의견 구분, 확률을 확정처럼 쓰지 말 것. 한국어, 간결한 보고서체.`

const SRC = { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, title: { type: 'string' }, pub_date: { type: 'string' }, used_for: { type: 'string' } }, required: ['url', 'used_for'] } }
const SCEN = { type: 'object', properties: { name: { type: 'string' }, prob: { type: 'number' }, end_price_krw: { type: 'number' }, cum_dividends_krw: { type: 'number' }, tsr_cum_pct: { type: 'number' }, key_assumptions: { type: 'string' } }, required: ['name', 'prob', 'end_price_krw', 'cum_dividends_krw', 'tsr_cum_pct', 'key_assumptions'] }
const FHZ = { type: 'object', properties: { scenarios: { type: 'array', minItems: 3, items: SCEN }, display_bear_base_bull: { type: 'string' }, expected_tsr_cum_pct: { type: 'number' }, confidence: { type: 'string', enum: ['높음', '보통', '낮음'] }, key_driver: { type: 'string' } }, required: ['scenarios', 'display_bear_base_bull', 'expected_tsr_cum_pct', 'confidence', 'key_driver'] }
const SENS3 = { type: 'object', properties: { y1: { type: 'number' }, y3: { type: 'number' }, y5: { type: 'number' } }, required: ['y1', 'y3', 'y5'] }

const COORD_SCHEMA = {
  type: 'object',
  properties: {
    industry_bias_findings: { type: 'array', items: { type: 'object', properties: { industry: { type: 'string' }, finding: { type: 'string' }, affected: { type: 'array', items: { type: 'string' } } }, required: ['industry', 'finding', 'affected'] } },
    consistency_issues: { type: 'array', items: { type: 'string' }, description: '같은 산업 내 종목 간 공통 가정 불일치(예: 메모리 가격 경로, 관세율, 환율)' },
    flags: { type: 'array', items: { type: 'object', properties: {
      stock: { type: 'string' }, horizon: { type: 'string', enum: ['1y', '3y', '5y', 'all'] },
      direction: { type: 'string', enum: ['too_optimistic', 'too_pessimistic', 'risk_understated', 'risk_overstated'] },
      severity: { type: 'string', enum: ['material', 'minor'] }, rationale: { type: 'string' } }, required: ['stock', 'horizon', 'direction', 'severity', 'rationale'] } },
    base_rate_notes: { type: 'string' },
  },
  required: ['industry_bias_findings', 'consistency_issues', 'flags', 'base_rate_notes'],
}

const BEAR_SCHEMA = {
  type: 'object',
  properties: {
    attacks: { type: 'array', items: { type: 'object', properties: { question: { type: 'string' }, finding: { type: 'string' }, severity: { type: 'string', enum: ['high', 'medium', 'low', 'none'] }, evidence: { type: 'string' } }, required: ['question', 'finding', 'severity', 'evidence'] } },
    strongest_counterargument: { type: 'string' },
    proposed_revisions: { type: 'object', properties: { y1: FHZ, y3: FHZ, y5: FHZ }, required: ['y1', 'y3', 'y5'], description: '약세론 관점에서 타당하다고 보는 수정 시나리오 세트(수정 불필요하면 기존 세트를 그대로)' },
    sources: SRC,
  },
  required: ['attacks', 'strongest_counterargument', 'proposed_revisions', 'sources'],
}

const JUDGE_SCHEMA = {
  type: 'object',
  properties: {
    horizons: { type: 'object', properties: { y1: FHZ, y3: FHZ, y5: FHZ }, required: ['y1', 'y3', 'y5'] },
    forward_vol_annual_pct: { type: 'number' },
    tail: { type: 'object', properties: { prob_near_zero_5y: { type: 'number' }, prob_permanent_loss_50pct_5y: { type: 'number' } }, required: ['prob_near_zero_5y', 'prob_permanent_loss_50pct_5y'] },
    sensitivities: { type: 'object', properties: { fx_usdkrw_up10: SENS3, rates_up100bp: SENS3, terminal_multiple_down20: SENS3, semi_ai_down: SENS3, auto_tariff_demand: SENS3, bio_pos_down25: SENS3, dilution_up10: SENS3, key_customer_down20: SENS3 }, required: ['fx_usdkrw_up10', 'rates_up100bp', 'terminal_multiple_down20', 'semi_ai_down', 'auto_tariff_demand', 'bio_pos_down25', 'dilution_up10', 'key_customer_down20'] },
    accepted_attacks: { type: 'array', items: { type: 'string' } },
    rejected_attacks: { type: 'array', items: { type: 'string' }, description: '기각한 반론과 이유' },
    change_summary: { type: 'string', description: '반대심문 전후 기대 누적 TSR 변화(기간별 %p)와 이유' },
    weighting_rationale: { type: 'string', description: '어느 쪽 전망에 더 큰 가중치를 두었는지와 이유' },
    arithmetic_check: { type: 'string', description: '확률합·TSR 재계산·기대값 검산 결과' },
  },
  required: ['horizons', 'forward_vol_annual_pct', 'tail', 'sensitivities', 'accepted_attacks', 'rejected_attacks', 'change_summary', 'weighting_rationale', 'arithmetic_check'],
}

phase('Coordinator')
const coord = await agent(`${CTX}

역할: A. 총괄 조정 에이전트 겸 H. 베이스레이트 보정 에이전트(횡단면 점검). 잠정 순위표 파일과 거시 파일을 Read로 읽어라. 필요하면 개별 종목 분석 파일도 읽어라. 검색은 0~4회.
점검:
1) 최종 순위가 특정 산업의 낙관적 가정에 편향되지 않았는가(예: 반도체 종목들이 모두 같은 업사이클 지속을 가정, 우주/ESS 종목들이 같은 수주 급증을 가정).
2) 같은 산업 내 종목 간 공통 가정 불일치.
3) 소형·신규상장 종목에 데이터 부족으로 과도한 기대수익률이 부여됐는가, 정보가 적다는 이유로 기대값이 부풀었는가.
4) 기대값과 중앙값, 누적과 연환산의 혼동, 5년 멀티플 과다, 고점 이익 외삽.
5) 반대로 지나치게 비관적으로 평가된 종목.
flags에 종목별로 방향과 심각도(material/minor)와 근거를 적어라. 결과에 맞춘 사례 선택을 하지 말라.`, { label: 'A+H:coordinator', phase: 'Coordinator', schema: COORD_SCHEMA })

const material = new Set((coord.flags || []).filter(f => f.severity === 'material').map(f => f.stock))
const targets = args.candidates.slice()
for (const s of args.universe) {
  if (material.has(s.name) && !targets.find(t => t.name === s.name)) targets.push({ ...s, reason: 'coordinator material flag' })
}
log(`cross-examining ${targets.length} stocks (${args.candidates.length} provisional leaders + ${targets.length - args.candidates.length} coordinator-flagged)`)

const flagsFor = name => JSON.stringify((coord.flags || []).filter(f => f.stock === name))
const coordTxt = JSON.stringify({ industry_bias_findings: coord.industry_bias_findings, consistency_issues: coord.consistency_issues, base_rate_notes: coord.base_rate_notes })

const results = await pipeline(targets,
  s => agent(`${CTX}

역할: I. 반대심문·약세론 에이전트. 대상: ${s.name} (${s.code}, ${s.market}), P0 ${s.P0}원(${s.P0_date}). 선정 사유: ${s.reason}.
도시에·분석 파일을 Read로 읽어라. 총괄 조정 에이전트의 횡단면 소견: ${coordTxt}
이 종목에 대한 플래그: ${flagsFor(s.name)}

다음을 하나씩 공격하라(보완 검색 3~6회 이내):
1) 시장이 이미 낙관론을 주가에 반영하지 않았는가? 2) 예상 성장률이 업계 베이스레이트보다 지나치게 높은가? 3) 매출이 늘어도 마진·현금흐름이 악화될 수 있는가? 4) 고객사의 자체개발·이원화·가격인하 요구는? 5) 기술 대체·시장이 예상보다 작을 가능성은? 6) 자금조달·희석을 누락하지 않았는가? 7) 낮은 유동성이 기대수익률을 왜곡하지 않는가? 8) 단일 수주·임상·고객·정책 의존은? 9) 성공 시나리오 확률을 과대평가하지 않았는가? 10) 5년 뒤 적용 멀티플이 성숙기업으로서 너무 높은가?
무조건 공격하지 말고, 근거가 약한 반론은 severity를 low/none으로 두라. 타당한 반론이 있으면 proposed_revisions에 기간별 수정 시나리오 세트를 제시하라(확률합 1, TSR 공식 준수).`, { label: `I:bear:${s.name}`, phase: 'Bear', schema: BEAR_SCHEMA }),
  (bear, s) => agent(`${CTX}

역할: J. 최종 심사 에이전트. 대상: ${s.name} (${s.code}), P0 ${s.P0}원(${s.P0_date}).
도시에·분석 파일(sp, ge, fin)을 Read로 읽어라. 검색은 원칙적으로 하지 말고 사실 충돌 시에만 1~2회.
총괄 조정 소견: ${coordTxt}
이 종목 플래그: ${flagsFor(s.name)}
약세론 에이전트 결과: ${JSON.stringify(bear)}

독립 분석(fin)과 반대심문 결과를 통합해 최종 시나리오 세트를 확정하라. 단순 평균이 아니라 데이터 품질, 산업 전문성, 가정의 타당성에 따라 가중치를 정하라. 반론이 타당하면 수익률 분포를 실제로 수정하고, 타당하지 않으면 기각 이유를 적어라. 분석가 간 중요한 의견 차이를 숨기지 말라.
발표 전에 각 시나리오의 tsr_cum_pct = (end_price_krw + cum_dividends_krw)/P0 - 1, 확률합 = 1.0, expected = Σ prob×tsr를 검산하고 arithmetic_check에 적어라. 민감도(표준 충격별 기대 누적 TSR 변화 %p)도 수정 후 기준으로 다시 제시하라.`, { label: `J:judge:${s.name}`, phase: 'Judge', schema: JUDGE_SCHEMA })
    .then(j => ({ stock: s.name, bear, judge: j })),
)

return {
  coord,
  targets: targets.map(t => t.name),
  summary: results.filter(Boolean).map(r => ({ stock: r.stock, change: r.judge ? r.judge.change_summary : null })),
}
