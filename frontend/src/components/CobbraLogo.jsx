/**
 * Inline SVG logo — inherits the page's Barlow font.
 *
 * Props:
 *   height   – rendered height in px (default 28); width scales automatically
 *   variant  – 'full' (icon + wordmark) | 'icon' (cobblestone only)
 *   color    – fill colour (default: brand accent #c8ff00)
 */
export default function CobbraLogo({ height = 28, variant = 'full', color = '#c8ff00' }) {
  if (variant === 'icon') {
    return (
      <svg
        height={height}
        width={height}
        viewBox="-2 -2 52 52"
        fill={color}
        aria-label="Cobbra"
        role="img"
      >
        <rect x="0"  y="0"  width="24" height="20" rx="3" />
        <rect x="28" y="0"  width="20" height="24" rx="3" />
        <rect x="0"  y="24" width="20" height="24" rx="3" />
        <rect x="24" y="28" width="24" height="20" rx="3" />
      </svg>
    )
  }

  // viewBox: x -2 to 246, y -40 to 14  →  248 wide × 54 tall
  const width = Math.round(height * (248 / 54))
  return (
    <svg
      height={height}
      width={width}
      viewBox="-2 -40 248 54"
      fill={color}
      aria-label="Cobbra"
      role="img"
    >
      {/* cobblestone icon — vertically centred with text cap-height */}
      <rect x="0"  y="-36" width="24" height="20" rx="3" />
      <rect x="28" y="-36" width="20" height="24" rx="3" />
      <rect x="0"  y="-12" width="20" height="24" rx="3" />
      <rect x="24" y="-8"  width="24" height="20" rx="3" />
      {/* wordmark */}
      <text
        x="68"
        y="0"
        fontFamily="Barlow, sans-serif"
        fontWeight="600"
        fontSize="48"
        letterSpacing="0.5"
      >
        cobbra
      </text>
    </svg>
  )
}
