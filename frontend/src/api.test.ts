import { afterEach, describe, expect, it, vi } from 'vitest'

import { queueExperiment, replayDataset, scanArbitrage } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Arbitrage Lab API handoffs', () => {
  it('posts scanner parameters to the Phase 1 decision endpoint', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ opportunities: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const config = { dataset_id: 'lesson-31', min_edge_bps: 5, fee_bps: 2, max_quantity: 0.4, limit: 500 }

    await scanArbitrage(config)

    expect(fetch).toHaveBeenCalledWith('/api/research/arbitrage/scan', expect.objectContaining({ method: 'POST', body: JSON.stringify(config) }))
  })

  it('replays an opportunity through the existing deterministic replay API', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ fill_count: 2 }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const config = { dataset_id: 'lesson-31', strategy: 'cross_exchange_arbitrage' as const, parameters: { min_edge_bps: 5, fee_bps: 2, max_quantity: 0.4 }, starting_cash: 100_000, timer_interval_ms: 1_000 }

    await replayDataset(config)

    expect(fetch).toHaveBeenCalledWith('/api/research/replay', expect.objectContaining({ method: 'POST', body: JSON.stringify(config) }))
  })

  it('preserves scanner parameters when adding the opportunity to an experiment', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'experiment-1' }), { status: 202 }))
    vi.stubGlobal('fetch', fetch)
    const config = {
      dataset_id: 'lesson-31', strategy: 'cross_exchange_arbitrage' as const, starting_cash: 100_000, timer_interval_ms: 1_000,
      base_parameters: { min_edge_bps: 5, fee_bps: 2, max_quantity: 0.4 },
      parameter_grid: { min_edge_bps: [5], max_quantity: [0.4] },
      walk_forward_folds: 4, monte_carlo_runs: 500, monte_carlo_block_size: 5, seed: 7,
    }

    await queueExperiment(config)

    expect(fetch).toHaveBeenCalledWith('/api/research/experiments', expect.objectContaining({ method: 'POST', body: JSON.stringify(config) }))
  })
})
