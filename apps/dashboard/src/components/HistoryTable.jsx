function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function HistoryTable({ history, loading, error }) {
  if (loading) {
    return (
      <div className="history-section">
        <div className="section-label">Forecast History</div>
        <p className="history-table__empty">Loading history…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="history-section">
        <div className="section-label">Forecast History</div>
        <p className="history-table__empty history-table__empty--error">{error}</p>
      </div>
    )
  }

  if (!history || history.length === 0) {
    return (
      <div className="history-section">
        <div className="section-label">Forecast History</div>
        <p className="history-table__empty">No history available yet</p>
      </div>
    )
  }

  return (
    <div className="history-section">
      <div className="section-label">Forecast History</div>
      <div className="history-table">
        <div className="history-table__head">
          <span>Time</span>
          <span>Target Price</span>
          <span>Confidence</span>
          <span>Direction</span>
          <span>Status</span>
        </div>
        {history.map((item) => {
          const badge = item.presentation.trend_badge
          const arrow = badge === 'up' ? '▲' : badge === 'down' ? '▼' : '●'
          return (
            <div key={item.event_id} className="history-table__row">
              <span className="history-table__time">{formatTime(item.forecast_time)}</span>
              <span className={`history-table__price price--${badge}`}>
                {item.presentation.target_price_text}
              </span>
              <span className="history-table__conf">{item.presentation.confidence_text}</span>
              <span className={`trend-badge trend-badge--${badge} trend-badge--sm`}>
                {arrow} {item.presentation.trend_label}
              </span>
              <span
                className={`status-pill status-pill--${item.presentation.status === 'active' ? 'active' : 'expired'}`}
              >
                {item.presentation.status}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
