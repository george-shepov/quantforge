import { afterEach, describe, expect, it, vi } from 'vitest'

import { addExecutionReflection, queueExperiment, replayDataset, runCourse, scanArbitrage } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Arbitrage Lab API handoffs', () => {
  it('posts scanner parameters to the Phase 1 decision endpoint', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ opportunities: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const config = { dataset_id: 'lesson-31', min_edge_bps: 5, fee_bps: 2, max_quantity: 0.4, slippage_bps: 1, limit: 500 }

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

  it('appends reflections only after a story exists', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ reflection_id: 'r-1' }), { status: 201 }))
    vi.stubGlobal('fetch', fetch)

    await addExecutionReflection('story/with spaces', 'Depth invalidated the assumption.')

    expect(fetch).toHaveBeenCalledWith(
      '/api/research/execution-stories/story%2Fwith%20spaces/reflections',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ text: 'Depth invalidated the assumption.' }) }),
    )
  })

  it('runs the server-owned executable course provenance', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ scenario_id: 'course-1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)

    await runCourse(11)

    expect(fetch).toHaveBeenCalledWith(
      '/api/course/run',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ seed: 11 }) }),
    )
  })
})
