import { useEffect, useState } from 'react'

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4v5h5" />
      <path d="M20 20v-5h-5" />
      <path d="M4 9a8 8 0 0114.54-3" />
      <path d="M19.91 15a8 8 0 01-14.54 3" />
    </svg>
  )
}

function ZapIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

function timeAgo(date) {
  if (!date) return null
  const seconds = Math.floor((Date.now() - date) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return `${Math.floor(minutes / 60)}h ago`
}

export default function Header({ watchlistInput, onWatchlistChange, lastUpdated, onRefresh, loading }) {
  const [, setTick] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 15_000)
    return () => clearInterval(t)
  }, [])

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <div className="app-header__logo">
          <ZapIcon />
        </div>
        <div>
          <h1 className="app-header__title">ForecastCrypto</h1>
          <p className="app-header__sub">ML-powered price predictions</p>
        </div>
      </div>

      <div className="app-header__controls">
        {lastUpdated && (
          <div className="app-header__meta">
            <span className={`status-dot ${loading ? 'status-dot--loading' : 'status-dot--ok'}`} />
            <span>{loading ? 'Updating…' : `Updated ${timeAgo(lastUpdated)}`}</span>
          </div>
        )}

        <div className="watchlist-field">
          <label htmlFor="watchlist-input">Watchlist</label>
          <input
            id="watchlist-input"
            value={watchlistInput}
            onChange={(e) => onWatchlistChange(e.target.value)}
            placeholder="BTCUSDT,ETHUSDT"
            spellCheck={false}
          />
        </div>

        <button
          className="refresh-btn"
          onClick={onRefresh}
          disabled={loading}
          title="Refresh now"
          aria-label="Refresh forecasts"
        >
          <span className={loading ? 'spin' : ''}>
            <RefreshIcon />
          </span>
        </button>
      </div>
    </header>
  )
}
