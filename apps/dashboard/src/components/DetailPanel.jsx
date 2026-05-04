import ConfidenceRing from './ConfidenceRing.jsx'
import Sparkline from './Sparkline.jsx'
import HistoryTable from './HistoryTable.jsx'
import TrendBadge from './TrendBadge.jsx'

function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatCard({ label, value, variant }) {
  return (
    <div className="stat-card">
      <div className="stat-card__label">{label}</div>
      <div className={`stat-card__value${variant ? ` stat-val--${variant}` : ''}`}>{value}</div>
    </div>
  )
}

function SkeletonPanel() {
  return (
    <div className="detail-panel detail-panel--skeleton">
      <div className="skeleton skeleton--wide" />
      <div className="skeleton skeleton--hero" />
      <div className="skeleton-row">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="skeleton skeleton--stat" />
        ))}
      </div>
    </div>
  )
}

export default function DetailPanel({ forecast, history, loading, historyLoading, historyError }) {
  if (loading && !forecast) return <SkeletonPanel />

  if (!forecast) {
    return (
      <div className="detail-panel detail-panel--empty">
        <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M8 12h8M12 8v8" />
        </svg>
        <p>Select a symbol</p>
        <p className="text-muted">Choose a coin from the sidebar to view its forecast detail</p>
      </div>
    )
  }

  const {
    symbol,
    presentation,
    confidence,
    target_time,
    valid_until,
    timeframe,
    horizon,
    model_version,
  } = forecast

  const badge = presentation.trend_badge
  const base = symbol.replace('USDT', '')

  return (
    <div className="detail-panel">
      {/* Header */}
      <div className="detail-panel__header">
        <div className="detail-panel__title-group">
          <div className="detail-panel__symbol">
            {base}
            <span className="detail-panel__pair"> / USDT</span>
          </div>
          <TrendBadge trend={badge} label={presentation.trend_label} size="lg" />
        </div>
        {model_version && (
          <div className="detail-panel__model">
            <span>Model</span>
            <code>{model_version}</code>
          </div>
        )}
      </div>

      {/* Hero price card */}
      <div className={`detail-panel__hero hero--${badge}`}>
        <div>
          <div className="detail-panel__hero-label">Target Price</div>
          <div className={`detail-panel__price price--${badge}`}>
            {presentation.target_price_text}
          </div>
        </div>
        <ConfidenceRing value={confidence} size={88} />
      </div>

      {/* Stats row */}
      <div className="detail-panel__stats">
        <StatCard label="Timeframe" value={timeframe} />
        <StatCard label="Horizon" value={horizon} />
        <StatCard
          label="Status"
          value={presentation.status}
          variant={presentation.status === 'active' ? 'up' : 'muted'}
        />
        <StatCard label="Target Time" value={formatTime(target_time)} />
        <StatCard label="Valid Until" value={formatTime(valid_until)} />
      </div>

      {/* Sparkline chart */}
      {history.length > 1 && (
        <div className="detail-panel__chart">
          <div className="section-label">Price Target Trend</div>
          <Sparkline data={history} trend={badge} height={80} />
        </div>
      )}

      {/* History table */}
      <HistoryTable history={history} loading={historyLoading} error={historyError} />
    </div>
  )
}
