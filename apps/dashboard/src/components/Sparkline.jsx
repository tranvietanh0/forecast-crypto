export default function Sparkline({ data, trend, height = 80 }) {
  if (!data || data.length < 2) {
    return <div className="sparkline-empty">Not enough data</div>
  }

  const VW = 600
  const VH = height
  const pad = 6

  const prices = data.map((d) => d.target_price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1
  const usableW = VW - pad * 2
  const usableH = VH - pad * 2

  const pts = prices.map((price, i) => {
    const x = pad + (i / (prices.length - 1)) * usableW
    const y = pad + usableH - ((price - min) / range) * usableH
    return [x, y]
  })

  const polyline = pts.map(([x, y]) => `${x},${y}`).join(' ')

  const areaPath = [
    `M ${pts[0][0]},${VH}`,
    ...pts.map(([x, y]) => `L ${x},${y}`),
    `L ${pts[pts.length - 1][0]},${VH}`,
    'Z',
  ].join(' ')

  const color = trend === 'up' ? 'var(--up)' : trend === 'down' ? 'var(--down)' : 'var(--neutral)'
  const gradId = `sg-${trend}`
  const [lx, ly] = pts[pts.length - 1]

  return (
    <svg
      viewBox={`0 0 ${VW} ${VH}`}
      preserveAspectRatio="none"
      style={{ width: '100%', height: `${VH}px`, display: 'block' }}
      className="sparkline"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} />
      <polyline
        points={polyline}
        fill="none"
        stroke={color}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lx} cy={ly} r="4" fill={color} />
    </svg>
  )
}
