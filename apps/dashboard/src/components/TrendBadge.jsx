export default function TrendBadge({ trend, label, size = 'md' }) {
  const arrow = trend === 'up' ? '▲' : trend === 'down' ? '▼' : '●'
  return (
    <span className={`trend-badge trend-badge--${trend} trend-badge--${size}`}>
      {arrow} {label}
    </span>
  )
}
