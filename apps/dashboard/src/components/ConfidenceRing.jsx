export default function ConfidenceRing({ value, size = 72 }) {
  const strokeWidth = 5
  const r = (size - strokeWidth * 2) / 2
  const circumference = 2 * Math.PI * r
  const filled = circumference * value
  const gap = circumference - filled
  const color = value >= 0.75 ? 'var(--up)' : value >= 0.5 ? 'var(--neutral)' : 'var(--down)'
  const cx = size / 2
  const cy = size / 2

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="conf-ring">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border-subtle)" strokeWidth={strokeWidth} />
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={`${filled} ${gap}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
        style={{ transition: 'stroke-dasharray 0.45s ease' }}
      />
      <text
        x={cx}
        y={cy + 4}
        textAnchor="middle"
        fontSize={size < 56 ? '10' : '13'}
        fontWeight="700"
        fill={color}
        style={{ fontFamily: 'inherit' }}
      >
        {Math.round(value * 100)}%
      </text>
    </svg>
  )
}
