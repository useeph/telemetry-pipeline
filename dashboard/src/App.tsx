import { useCallback, useEffect, useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type MetricBucket, type QualityReport } from './api'

const METRICS = ['speed_kph', 'temperature_c', 'battery_v', 'rpm'] as const
const COLORS = ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#dc2626', '#0891b2']

interface Props {
  pollMs?: number
}

export default function App({ pollMs = 5000 }: Props) {
  const [metric, setMetric] = useState<string>('speed_kph')
  const [rows, setRows] = useState<MetricBucket[]>([])
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [m, q] = await Promise.all([api.metrics(60), api.quality()])
      setRows(m)
      setQuality(q)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, pollMs)
    return () => clearInterval(id)
  }, [load, pollMs])

  // Pivot rows into one series per device for the selected metric.
  const { data, devices } = useMemo(() => {
    const filtered = rows.filter((r) => r.metric === metric)
    const devs = [...new Set(filtered.map((r) => r.device_id))].sort()
    const byTime = new Map<string, Record<string, number | string>>()
    for (const r of filtered) {
      const t = new Date(r.bucket_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      const point = byTime.get(t) ?? { time: t }
      point[r.device_id] = r.avg
      byTime.set(t, point)
    }
    return { data: [...byTime.values()], devices: devs }
  }, [rows, metric])

  return (
    <main className="app">
      <header>
        <h1>Device Telemetry</h1>
        {error ? (
          <span role="alert" className="badge bad">
            API unavailable: {error}
          </span>
        ) : (
          quality && (
            <span className={`badge ${quality.passed ? 'good' : 'bad'}`}>
              Data quality: {quality.passed ? 'passing' : 'failing'}
            </span>
          )
        )}
      </header>

      {quality && (
        <section className="checks" aria-label="data quality checks">
          {quality.checks.map((c) => (
            <div key={c.name} className={`check ${c.passed ? 'good' : 'bad'}`}>
              <div className="name">{c.name.replace(/_/g, ' ')}</div>
              <div className="value">{(c.value * 100).toFixed(1)}%</div>
              <div className="threshold">limit {(c.threshold * 100).toFixed(0)}%</div>
            </div>
          ))}
          <div className={`check ${quality.stale_devices.length ? 'bad' : 'good'}`}>
            <div className="name">stale devices</div>
            <div className="value">{quality.stale_devices.length}</div>
            <div className="threshold">{quality.stale_devices.join(', ') || 'none'}</div>
          </div>
        </section>
      )}

      <section className="chart">
        <label>
          Metric{' '}
          <select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {METRICS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        {data.length === 0 ? (
          <p className="empty">No data yet. Run the simulator to send telemetry.</p>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Legend />
              {devices.map((d, i) => (
                <Line key={d} type="monotone" dataKey={d} stroke={COLORS[i % COLORS.length]} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </section>
    </main>
  )
}
