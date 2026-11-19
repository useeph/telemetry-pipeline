import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import App from './App'

class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
;(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO

function mockFetch(handler: (url: string) => unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = handler(url)
      return { ok: true, status: 200, json: async () => body } as Response
    }),
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders quality checks and flags stale devices', async () => {
    mockFetch((url) =>
      url.includes('/quality')
        ? {
            passed: false,
            checks: [
              { name: 'reject_rate', value: 0.01, threshold: 0.05, passed: true },
              { name: 'stale_device_rate', value: 0.5, threshold: 0.1, passed: false },
            ],
            stale_devices: ['truck-2'],
          }
        : [],
    )
    render(<App pollMs={60000} />)
    expect(await screen.findByText('Data quality: failing')).toBeInTheDocument()
    expect(screen.getByText('reject rate')).toBeInTheDocument()
    expect(screen.getByText('truck-2')).toBeInTheDocument()
    expect(screen.getByText(/No data yet/)).toBeInTheDocument()
  })

  it('shows an alert when the API is down', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('Failed to fetch')
      }),
    )
    render(<App pollMs={60000} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable: Failed to fetch')
  })
})
