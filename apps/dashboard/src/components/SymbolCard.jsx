function getConfColor(confidence) {
  if (confidence >= 0.75) return 'var(--up)'
  if (confidence >= 0.5) return 'var(--neutral)'
  return 'var(--down)'
}

export default function SymbolCard({ forecast, isActive, onClick }) {
  const { symbol, presentation, confidence } = forecast
  const badge = presentation.trend_badge
  const arrow = badge === 'up' ? '▲' : badge === 'down' ? '▼' : '●'
  const base = symbol.replace('USDT', '')
  const confColor = getConfColor(confidence)

  return (
    <button
      className={`symbol-card ${isActive ? 'symbol-card--active' : ''}`}
      onClick={onClick}
      aria-pressed={isActive}
      aria-label={`Show forecast details for ${base}`}
    >
      <div className="symbol-card__top">
        <span className="symbol-card__name">
          {base}
          <span className="symbol-card__pair">/USDT</span>
        </span>
        <span className={`trend-badge trend-badge--${badge} trend-badge--sm`}>
          {arrow} {presentation.trend_label}
        </span>
      </div>

      <div className="symbol-card__price">{presentation.target_price_text}</div>

      <div className="symbol-card__bottom">
        <div className="conf-bar">
          <div
            className="conf-bar__fill"
            style={{
              width: `${confidence * 100}%`,
              background: confColor,
            }}
          />
        </div>
        <span className="symbol-card__conf">{presentation.confidence_text}</span>
      </div>

      <div className="symbol-card__status">
        <span
          className={`status-pill status-pill--${presentation.status === 'active' ? 'active' : 'expired'}`}
        >
          {presentation.status}
        </span>
      </div>
    </button>
  )
}
