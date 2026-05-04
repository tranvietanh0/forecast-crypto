import { useCallback, useEffect, useRef, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const AUTO_REFRESH_MS = 60_000

export function buildUrl(path, params = {}) {
  const normalizedBaseUrl = API_BASE_URL.endsWith('/') ? API_BASE_URL : `${API_BASE_URL}/`
  const normalizedPath = path.startsWith('/') ? path.slice(1) : path
  const url = new URL(normalizedPath, normalizedBaseUrl)
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== '') url.searchParams.set(k, v)
  })
  return url.toString()
}

export async function fetchJson(path, params = {}, signal) {
  const res = await fetch(buildUrl(path, params), { signal })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error || `HTTP ${res.status}`)
  }
  return res.json()
}

export function useForecasts(watchlist, timeframe, horizon) {
  const watchlistKey = watchlist.join(',')
  const requestIdRef = useRef(0)
  const controllerRef = useRef(null)
  const [state, setState] = useState({ data: null, loading: true, error: null, lastUpdated: null })

  const runRequest = useCallback(async (path) => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId

    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    if (watchlist.length === 0) {
      setState({
        data: { forecasts: [], timeframe, horizon, forecast_batch_id: null },
        loading: false,
        error: null,
        lastUpdated: new Date(),
      })
      return
    }

    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const data = await fetchJson(path, {
        timeframe,
        horizon,
        watchlist: watchlistKey,
      }, controller.signal)
      if (requestIdRef.current !== requestId) return
      setState({ data, loading: false, error: null, lastUpdated: new Date() })
    } catch (err) {
      if (err.name === 'AbortError' || requestIdRef.current !== requestId) {
        return
      }
      setState((prev) => ({ ...prev, loading: false, error: err.message, data: null }))
    }
  }, [horizon, timeframe, watchlist, watchlistKey])

  const load = useCallback(async () => {
    await runRequest('forecasts/latest')
  }, [runRequest])

  const refresh = useCallback(async () => {
    await runRequest('forecasts/refresh')
  }, [runRequest])

  useEffect(() => {
    load()
    const timer = setInterval(load, AUTO_REFRESH_MS)
    return () => {
      clearInterval(timer)
      controllerRef.current?.abort()
    }
  }, [load])

  return { ...state, refresh, refreshKey: state.lastUpdated?.toISOString() ?? null }
}
