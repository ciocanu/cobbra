import './cobbra.css'

/**
 * CobbraLogo
 *
 * The wordmark with its defining mark: the "bb" in toxic green,
 * underlined by a sine wave that draws itself on mount — one stroke,
 * like a fang leaving its mark.
 *
 * Props:
 *   height   — rendered height in px (width is proportional)
 *   animated — whether the snake underline animates on mount (default: true)
 *   mono     — if true, renders in monospace for data-dense contexts
 */
export function CobbraLogo({ height = 32, animated = true, mono = false }) {
  const fontSize   = height * 0.82
  const snakeId    = `cb-snake-${height}`

  return (
    <div
      aria-label="cobbra"
      style={{
        display: 'inline-flex',
        alignItems: 'baseline',
        fontFamily: mono ? 'var(--cb-mono)' : 'var(--cb-font)',
        fontWeight: 700,
        fontSize,
        letterSpacing: '-0.038em',
        lineHeight: 1,
        userSelect: 'none',
      }}
    >
      {/* "co" — base color */}
      <span style={{ color: 'var(--cb-text)' }}>co</span>

      {/* "bb" — the venom mark */}
      <span style={{
        color: 'var(--cb-venom)',
        position: 'relative',
        display: 'inline-block',
        /* Hairline letter-spacing tightening between the two b's
           makes them read as a unit — a pair, a coil, two eyes */
        letterSpacing: '-0.05em',
      }}>
        bb

        {/* Serpentine underline — the defining brand mark */}
        <svg
          aria-hidden="true"
          focusable="false"
          style={{
            position: 'absolute',
            /* sits just below the baseline */
            bottom: -Math.round(height * 0.1),
            left: '2%',
            width: '96%',
            height: Math.round(height * 0.22),
            overflow: 'visible',
            pointerEvents: 'none',
          }}
          viewBox="0 0 100 12"
          preserveAspectRatio="none"
        >
          <defs>
            {/* Inline style for the animation so it scopes to this SVG */}
            <style>{`
              #${snakeId} {
                stroke-dasharray: 160;
                stroke-dashoffset: ${animated ? 160 : 0};
                ${animated
                  ? `animation: cb-snake-draw 0.65s cubic-bezier(0.16,1,0.3,1) forwards 0.15s;`
                  : ''}
              }
            `}</style>
          </defs>

          {/* One sinuous stroke — a single serpentine wave */}
          <path
            id={snakeId}
            d="M0,6 C12,1 24,11 38,6 C52,1 64,11 76,6 C88,1 95,4 100,6"
            stroke="#39FF14"
            strokeWidth="1.6"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.85"
          />
        </svg>
      </span>

      {/* "ra" — base color */}
      <span style={{ color: 'var(--cb-text)' }}>ra</span>
    </div>
  )
}

/**
 * CobbraIcon — minimal square icon mark for favicons, app icons, etc.
 * The double-b rendered large, the wave below it.
 */
export function CobbraIcon({ size = 40 }) {
  return (
    <div
      aria-label="cobbra icon"
      style={{
        width: size,
        height: size,
        background: 'var(--cb-bg)',
        border: '1px solid var(--cb-border)',
        borderRadius: 'var(--cb-r-sm)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Faint diagonal accent line — speed, road */}
      <div style={{
        position: 'absolute',
        bottom: -2,
        right: -8,
        width: size * 0.9,
        height: 1,
        background: 'var(--cb-venom)',
        opacity: 0.25,
        transform: 'rotate(-18deg)',
        transformOrigin: 'right center',
      }} />

      <span style={{
        fontFamily: 'var(--cb-font)',
        fontWeight: 700,
        fontSize: size * 0.44,
        color: 'var(--cb-venom)',
        letterSpacing: '-0.05em',
        lineHeight: 1,
        position: 'relative',
        zIndex: 1,
      }}>
        bb
      </span>
    </div>
  )
}

export default CobbraLogo
