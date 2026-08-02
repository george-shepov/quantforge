import type {
  BacktestResponse,
  ArbitrageScanRequest,
  ArbitrageScanResponse,
  CatalogResponse,
  DatasetManifest,
  ExecutionStoryRequest,
  ExecutionStoryResponse,
  ExperimentConfig,
  ExperimentView,
  RecordingConfig,
  RecordingStatus,
  ReplayRequest,
  ReplayResponse,
  ResearchCapabilities,
  RunConfig,
  SafetyStatus,
} from './types'

const API_URL = import.meta.env.VITE_API_URL || ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail ?? payload))
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export function runBacktest(config: RunConfig) {
  return request<BacktestResponse>('/api/backtests/run', { method: 'POST', body: JSON.stringify(config) })
}

export function getCatalog() {
  return request<CatalogResponse>('/api/catalog')
}

export function getCapabilities() {
  return request<ResearchCapabilities>('/api/research/capabilities')
}

export function getExecutionSafety() {
  return request<SafetyStatus>('/api/research/execution/safety')
}

export function listRecordings() {
  return request<RecordingStatus[]>('/api/research/recordings')
}

export function startRecording(config: RecordingConfig) {
  return request<RecordingStatus>('/api/research/recordings', { method: 'POST', body: JSON.stringify(config) })
}

export function stopRecording(datasetId: string) {
  return request<RecordingStatus>(`/api/research/recordings/${encodeURIComponent(datasetId)}`, { method: 'DELETE' })
}

export function listDatasets() {
  return request<DatasetManifest[]>('/api/research/datasets')
}

export function replayDataset(config: ReplayRequest) {
  return request<ReplayResponse>('/api/research/replay', { method: 'POST', body: JSON.stringify(config) })
}

export function scanArbitrage(config: ArbitrageScanRequest) {
  return request<ArbitrageScanResponse>('/api/research/arbitrage/scan', { method: 'POST', body: JSON.stringify(config) })
}

export function queueExperiment(config: ExperimentConfig) {
  return request<ExperimentView>('/api/research/experiments', { method: 'POST', body: JSON.stringify(config) })
}

export function listExperiments(limit = 25) {
  return request<ExperimentView[]>(`/api/research/experiments?limit=${limit}`)
}

export function getExperiment(id: string) {
  return request<ExperimentView>(`/api/research/experiments/${encodeURIComponent(id)}`)
}

export function buildExecutionStory(config: ExecutionStoryRequest) {
  return request<ExecutionStoryResponse>('/api/research/execution/story', { method: 'POST', body: JSON.stringify(config) })
}
