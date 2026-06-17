// Metric visualization colors.
// These mirror the CSS custom properties in index.css so JSX inline styles
// (e.g. Recharts stroke/fill props) have a single source of truth.
// When the CSS vars change, update here too.

export const colors = {
  accent:    '#39FF14',  // --accent (--cb-venom)   primary brand / venom
  speed:     '#4da6ff',  // --speed       blue
  heart:     '#ff4d6d',  // --heart       red-pink
  cadence:   '#ffd93d',  // --cadence     yellow
  elevation: '#6dffb8',  // --elevation   mint green
  power:     '#b57bee',  // --power       purple
  warning:   '#ff8c42',  // no CSS var    amber / high-stress
}
