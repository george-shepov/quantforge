import { describe, expect, it } from 'vitest'

import type { ArbitrageOpportunity } from '../types'
import { filterOpportunities, modeGuidance, opportunityLesson } from './ArbitrageWorkspace'

const accepted: ArbitrageOpportunity = {
  opportunity_id: 'accepted-1',
  timestamp_ns: 2,
  source_event_checksum: 'abc',
  symbol: 'BTC',
  buy_exchange: 'hyperliquid',
  sell_exchange: 'bybit',
  buy_price: 100,
  sell_price: 100.2,
  quantity: 0.4,
  gross_edge_bps: 20,
  fee_cost_bps: 4,
  expected_edge_bps: 16,
  estimated_profit: 0.064,
  decision: 'accepted',
  rejection_reasons: [],
  explanation: 'Gross edge 20 bps - fees 4 bps = expected edge 16 bps. Accepted.',
}

const rejected: ArbitrageOpportunity = {
  ...accepted,
  opportunity_id: 'rejected-1',
  buy_exchange: 'bybit',
  sell_exchange: 'hyperliquid',
  expected_edge_bps: -24,
  estimated_profit: -0.096,
  decision: 'rejected',
  rejection_reasons: ['Expected edge is below the minimum.'],
  explanation: 'Rejected because expected edge is below the minimum.',
}

describe('Arbitrage Lab presentation helpers', () => {
  it('filters accepted and rejected rows without modifying their calculations', () => {
    expect(filterOpportunities([accepted, rejected], 'accepted')).toEqual([accepted])
    expect(filterOpportunities([accepted, rejected], 'rejected')).toEqual([rejected])
    expect(filterOpportunities([accepted, rejected], 'all')).toEqual([accepted, rejected])
  })

  it('turns the selected replay evidence into a watch-and-learn lesson', () => {
    const lesson = opportunityLesson(rejected)
    expect(lesson).toContain('Buy BTC on bybit')
    expect(lesson).toContain(rejected.explanation)
    expect(lesson).toContain('Modeled profit')
  })

  it('defines teaching copy for every supported mode', () => {
    expect(Object.keys(modeGuidance).sort()).toEqual(['build', 'expert', 'guided', 'watch'])
  })
})
