import { useEffect, useState } from 'react'
import { fetchJson } from './useForecasts.js'

export function useHistory(symbol, timeframe, horizon, limit = 10, refreshKey = null) {
  const [state, setState] = useState({ history: [], loading: false, error: null })

  useEffect(() => {
    if (!symbol) {
      setState({ history: [], loading: false, error: null })
      return
    }

    const controller = new AbortController()
    setState((prev) => ({ ...prev, loading: true, error: null }))
    fetchJson('forecasts/history', { symbol, timeframe, horizon, limit: String(limit) }, controller.signal)
      .then((payload) => {
        setState({ history: payload.history, loading: false, error: null })
      })
      .catch((err) => {
        if (err.name === 'AbortError') {
          return
        }
        setState({ history: [], loading: false, error: err.message })
      })
    return () => {
      controller.abort()
    }
  }, [symbol, timeframe, horizon, limit, refreshKey])

  return state
}
