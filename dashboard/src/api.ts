// Typed client for the telemetry API.

export interface MetricBucket {
  bucket_start: string
  device_id: string
  metric: string
  count: number
  avg: number
  min: number
  max: number
}

export interface QualityCheck {
  name: string
  value: number
  threshold: number
  passed: boolean
}

export interface QualityReport {
  passed: boolean
  checks: QualityCheck[]
  stale_devices: string[]
}

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`)
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return (await res.json()) as T
}

export const api = {
  metrics: (bucketSeconds = 60, deviceId?: string) => {
    const params = new URLSearchParams({ bucket_seconds: String(bucketSeconds) })
    if (deviceId) params.set('device_id', deviceId)
    return getJson<MetricBucket[]>(`/metrics?${params.toString()}`)
  },
  quality: () => getJson<QualityReport>('/quality'),
}
