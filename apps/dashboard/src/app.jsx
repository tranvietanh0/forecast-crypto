import { useEffect, useMemo, useState } from 'react'
import { useForecasts } from './hooks/useForecasts.js'
import { useHistory } from './hooks/useHistory.js'
import Header from './components/Header.jsx'
import SymbolCard from './components/SymbolCard.jsx'
import DetailPanel from './components/DetailPanel.jsx'

const TIMEFRAME = '1h'
const HORIZON = '4h'
const DEFAULT_WATCHLIST = ['BTCUSDT', 'ETHUSDT']

export default function App() {
  const [watchlistInput, setWatchlistInput] = useState(DEFAULT_WATCHLIST.join(','))
  const [selectedSymbol, setSelectedSymbol] = useState(DEFAULT_WATCHLIST[0])

  const watchlist = useMemo(
    () => watchlistInput.split(',').map((s) => s.trim()).filter(Boolean),
    [watchlistInput],
  )

  const { data, loading, error, lastUpdated, refresh, refreshKey } = useForecasts(watchlist, TIMEFRAME, HORIZON)
  const { history, loading: historyLoading, error: historyError } = useHistory(selectedSymbol, TIMEFRAME, HORIZON, 10, refreshKey)

  const forecasts = data?.forecasts ?? []
  const selectedForecast = forecasts.find((f) => f.symbol === selectedSymbol) ?? null

  useEffect(() => {
    if (forecasts.length > 0 && !forecasts.some((f) => f.symbol === selectedSymbol)) {
      setSelectedSymbol(forecasts[0].symbol)
    }
  }, [forecasts, selectedSymbol])

  return (
    <div className="app-shell">
      <Header
        watchlistInput={watchlistInput}
        onWatchlistChange={setWatchlistInput}
        lastUpdated={lastUpdated}
        onRefresh={refresh}
        loading={loading}
      />

      {error && (
        <div className="error-banner">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          {error}
        </div>
      )}

      <div className="dashboard-body">
        <aside className="symbol-sidebar">
          <div className="sidebar-label">Watchlist</div>

          {loading && forecasts.length === 0 ? (
            <>
              <div className="symbol-card-skeleton" />
              <div className="symbol-card-skeleton" />
            </>
          ) : forecasts.length === 0 ? (
            <p className="sidebar-empty">No forecasts found</p>
          ) : (
            forecasts.map((forecast) => (
              <SymbolCard
                key={forecast.symbol}
                forecast={forecast}
                isActive={forecast.symbol === selectedSymbol}
                onClick={() => setSelectedSymbol(forecast.symbol)}
              />
            ))
          )}
        </aside>

        <main className="dashboard-main">
          <DetailPanel
            forecast={selectedForecast}
            history={history}
            loading={loading}
            historyLoading={historyLoading}
            historyError={historyError}
          />
        </main>
      </div>
    </div>
  )
}
