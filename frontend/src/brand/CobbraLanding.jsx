import { useEffect, useState } from 'react'
import { CobbraLogo } from './CobbraLogo'

/* ── Feature data ────────────────────────────────── */
const FEATURES = [
  {
    num: '01',
    title: 'Segment leaderboards',
    desc: 'Define segments on any road. Every upload auto-scores. Your time against every rider who crossed the same line.',
  },
  {
    num: '02',
    title: 'Power analysis',
    desc: 'Normalized power, TSS, IF, FTP curves, training stress balance. The numbers coaching books are built around.',
  },
  {
    num: '03',
    title: 'Heart rate zones',
    desc: 'Zone time distribution, HR decoupling, effort scoring. Full training picture without a power meter.',
  },
  {
    num: '04',
    title: 'AI coaching notes',
    desc: 'Every upload gets a coach-grade breakdown: pacing, effort quality, what to do next. Powered by Claude.',
  },
  {
    num: '05',
    title: 'Fitness trajectory',
    desc: "CTL, ATL, TSB graphed over time. See when you're building, peaking, or digging a hole.",
  },
  {
    num: '06',
    title: 'No social layer',
    desc: 'No activity feed, no kudos, no engagement hooks. Every design choice made for the athlete, not the algorithm.',
  },
]

/* ── Metric readout (floating, no container) ─────── */
const METRICS = [
  { label: 'Distance',    value: '127.4 km' },
  { label: 'Duration',    value: '4h 52m'   },
  { label: 'Elevation',   value: '3,840 m'  },
  { label: 'Avg HR',      value: '158 bpm'  },
  { label: 'Norm power',  value: '287 w'    },
  { label: 'TSS',         value: '142'      },
  { label: 'IF',          value: '0.88'     },
]

const ZONES = [
  { zone: 'Z1', pct: 38, color: 'oklch(54% 0.12 264)' },  // recovery — dusty blue
  { zone: 'Z2', pct: 44, color: 'oklch(58% 0.15 142)' },  // aerobic — muted green
  { zone: 'Z3', pct: 12, color: 'oklch(68% 0.14 88)'  },  // threshold — amber
  { zone: 'Z4', pct:  4, color: 'oklch(60% 0.15 38)'  },  // VO2 max — orange
  { zone: 'Z5', pct:  2, color: 'oklch(52% 0.14 20)'  },  // neuro — muted red
]

// Rows begin after metrics; bars start after zone labels appear
const METRIC_STAGGER = 35    // ms between metric rows
const ZONE_STAGGER   = 65    // ms between zone bars
const ZONE_START     = METRICS.length * METRIC_STAGGER + 80

function MetricsReadout({ active = false }) {
  const E = 'cubic-bezier(0.23, 1, 0.32, 1)'

  // Row fade+slide (opacity + tiny translateY — GPU only)
  const row = (i) => ({
    opacity: active ? 1 : 0,
    transform: `translateY(${active ? 0 : 4}px)`,
    transition: active
      ? `opacity 300ms ${E} ${i * METRIC_STAGGER}ms, transform 300ms ${E} ${i * METRIC_STAGGER}ms`
      : 'none',
  })

  return (
    <div style={{ fontFamily: 'var(--cb-mono)', paddingTop: 8 }}>

      {/* Ride identifier — first to appear */}
      <div style={{
        fontSize: 9,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--cb-text-3)',
        lineHeight: 1.7,
        marginBottom: 28,
        ...row(-1),
      }}>
        Activity output<br />
        Col du Tourmalet &middot; Sunday
      </div>

      {/* Metrics table — each row prints in sequence */}
      {METRICS.map((m, i) => (
        <div key={m.label} style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          padding: '9px 0',
          borderBottom: i < METRICS.length - 1 ? '1px solid var(--cb-border)' : 'none',
          ...row(i),
        }}>
          <span style={{
            fontSize: 10,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--cb-text-3)',
          }}>
            {m.label}
          </span>
          <span style={{
            fontSize: 15,
            fontWeight: 500,
            letterSpacing: '-0.04em',
            fontVariantNumeric: 'tabular-nums',
            color: 'var(--cb-text)',
          }}>
            {m.value}
          </span>
        </div>
      ))}

      {/* Zone distribution — appears after all metric rows */}
      <div style={{ marginTop: 28 }}>
        <div style={{
          fontSize: 9,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--cb-text-3)',
          marginBottom: 16,
          opacity: active ? 1 : 0,
          transition: active ? `opacity 260ms ${E} ${ZONE_START - 40}ms` : 'none',
        }}>
          Zone distribution
        </div>

        {ZONES.map((z, i) => {
          const delay = ZONE_START + i * ZONE_STAGGER
          return (
            <div key={z.zone} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              marginBottom: 10,
              opacity: active ? 1 : 0,
              transition: active ? `opacity 220ms ${E} ${delay}ms` : 'none',
            }}>
              <span style={{ fontSize: 9, color: 'var(--cb-text-3)', width: 16, flexShrink: 0 }}>
                {z.zone}
              </span>
              <div style={{
                flex: 1,
                height: 2,
                background: 'var(--cb-border)',
                position: 'relative',
                overflow: 'hidden',
              }}>
                <div style={{
                  position: 'absolute',
                  inset: 0,
                  background: z.color,
                  transformOrigin: 'left center',
                  transform: `scaleX(${active ? z.pct / 100 : 0})`,
                  transition: active
                    ? `transform 520ms ${E} ${delay + 40}ms`
                    : 'none',
                }} />
              </div>
              <span style={{
                fontSize: 9,
                color: 'var(--cb-text-3)',
                width: 28,
                textAlign: 'right',
                flexShrink: 0,
              }}>
                {z.pct}%
              </span>
            </div>
          )
        })}
      </div>

      {/* Coaching note — last to appear */}
      <div style={{
        marginTop: 24,
        paddingTop: 20,
        borderTop: '1px solid var(--cb-border)',
        fontSize: 11,
        lineHeight: 1.65,
        color: 'var(--cb-text-2)',
        opacity: active ? 1 : 0,
        transition: active
          ? `opacity 400ms ${E} ${ZONE_START + ZONES.length * ZONE_STAGGER + 60}ms`
          : 'none',
      }}>
        Pacing held through the col; HR decoupling at 4.2%, threshold fitness improving.
      </div>
    </div>
  )
}

/* ── Main landing ─────────────────────────────────── */

export default function CobbraLanding() {
  const [mounted, setMounted] = useState(false)
  const [readoutActive, setReadoutActive] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 20)
    return () => clearTimeout(t)
  }, [])

  // Fire readout sequence after the entry wrapper is substantially visible
  useEffect(() => {
    if (!mounted) return
    const t = setTimeout(() => setReadoutActive(true), 480)
    return () => clearTimeout(t)
  }, [mounted])

  // Entering elements only — expo-out, opacity + transform (GPU-composited)
  const E = 'cubic-bezier(0.23, 1, 0.32, 1)'
  const entry = (delay, duration = 560, dy = 12) => ({
    opacity: mounted ? 1 : 0,
    transform: `translateY(${mounted ? 0 : dy}px)`,
    transition: `opacity ${duration}ms ${E} ${delay}ms, transform ${duration}ms ${E} ${delay}ms`,
  })

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--cb-bg)',
      fontFamily: 'var(--cb-font)',
      color: 'var(--cb-text)',
    }}>

      {/* ── Nav ───────────────────────────────────────── */}
      <nav style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '20px 40px',
        borderBottom: '1px solid var(--cb-border)',
        background: 'var(--cb-bg)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <CobbraLogo height={28} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <a href="#features" className="cb-nav-link">Features</a>
          <a href="/login" className="cb-nav-link">Sign in</a>
          <a href="/register" className="cb-btn-primary" style={{ fontSize: 13, padding: '9px 20px' }}>
            Start free →
          </a>
        </div>
      </nav>

      {/* ── Hero ──────────────────────────────────────── */}
      <section className="cb-hero-grid" style={{
        padding: '100px 40px 80px',
        maxWidth: 1200,
        margin: '0 auto',
      }}>

        {/* Left: copy */}
        <div>
          <div style={{
            fontFamily: 'var(--cb-mono)',
            fontSize: 10,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: 'var(--cb-text-3)',
            marginBottom: 32,
            ...entry(0, 480, 8),
          }}>
            Cycling analytics · no noise
          </div>

          <h1 style={{
            fontFamily: 'var(--cb-font-condensed)',
            fontSize: 'clamp(80px, 11vw, 152px)',
            fontWeight: 800,
            letterSpacing: '-0.015em',
            lineHeight: 0.9,
            color: 'var(--cb-text)',
            margin: '0 0 36px',
            ...entry(60, 640, 16),
          }}>
            Every watt.<br />
            Every beat.<br />
            <span style={{ color: 'var(--cb-venom)' }}>No mercy.</span>
          </h1>

          <p style={{
            fontSize: 17,
            lineHeight: 1.75,
            color: 'var(--cb-text-2)',
            maxWidth: 440,
            margin: '0 0 40px',
            fontWeight: 400,
            ...entry(140, 560),
          }}>
            Upload GPX or FIT files. Get power analysis, HR zone
            breakdowns, segment rankings, and AI coaching notes.
            No feed, no ads, no data sold.
          </p>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
            ...entry(220, 500, 8),
          }}>
            <a href="/register" className="cb-btn-primary">
              Analyse your first ride →
            </a>
            <a href="/login" className="cb-btn-ghost">
              Sign in
            </a>
          </div>

          <p style={{
            fontFamily: 'var(--cb-mono)',
            fontSize: 11,
            color: 'var(--cb-text-3)',
            marginTop: 24,
            letterSpacing: '0.04em',
            // opacity only — no translateY on the trust line
            opacity: mounted ? 1 : 0,
            transition: `opacity 400ms ${E} 320ms`,
          }}>
            Free for 15 rides &middot; No credit card &middot; GPX &amp; FIT import
          </p>
        </div>

        {/* Right: metrics readout — no container, floats in space */}
        <div style={{ ...entry(100, 700, 20) }}>
          <MetricsReadout active={readoutActive} />
        </div>
      </section>

      {/* ── Section divider ───────────────────────────── */}
      <div style={{
        maxWidth: 1200,
        margin: '0 auto',
        padding: '0 40px',
        borderTop: '1px solid var(--cb-border)',
      }} />

      {/* ── Features ──────────────────────────────────── */}
      <section id="features" style={{
        maxWidth: 1200,
        margin: '0 auto',
        padding: '80px 40px',
      }}>
        <div style={{
          paddingBottom: 24,
          borderBottom: '1px solid var(--cb-border)',
        }}>
          <span style={{
            fontFamily: 'var(--cb-mono)',
            fontSize: 9,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: 'var(--cb-text-3)',
          }}>
            What it does
          </span>
        </div>

        {FEATURES.map(f => (
          <div key={f.num} style={{
            display: 'grid',
            gridTemplateColumns: '48px 1fr 2fr',
            gap: '0 40px',
            padding: '32px 0',
            borderBottom: '1px solid var(--cb-border)',
            alignItems: 'start',
          }}>
            <div style={{
              fontFamily: 'var(--cb-mono)',
              fontSize: 10,
              letterSpacing: '0.08em',
              color: 'var(--cb-text-3)',
              paddingTop: 2,
            }}>
              {f.num}
            </div>
            <div style={{
              fontSize: 15,
              fontWeight: 600,
              letterSpacing: '-0.02em',
              color: 'var(--cb-text)',
              lineHeight: 1.3,
            }}>
              {f.title}
            </div>
            <div style={{
              fontSize: 14,
              lineHeight: 1.75,
              color: 'var(--cb-text-2)',
              fontWeight: 400,
            }}>
              {f.desc}
            </div>
          </div>
        ))}
      </section>

      {/* ── Footer ────────────────────────────────────── */}
      <footer style={{ borderTop: '1px solid var(--cb-border)' }}>

        {/* CTA row */}
        <div style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '60px 40px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 32,
        }}>
          <div>
            <CobbraLogo height={36} />
            <p style={{
              fontFamily: 'var(--cb-mono)',
              fontSize: 11,
              color: 'var(--cb-text-3)',
              marginTop: 10,
              letterSpacing: '0.04em',
            }}>
              The precision tool for riders who measure everything.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <a href="/login" className="cb-btn-ghost" style={{ fontSize: 13 }}>Sign in</a>
            <a href="/register" className="cb-btn-primary" style={{ fontSize: 13 }}>
              Start free · 15 rides
            </a>
          </div>
        </div>

        {/* Legal row */}
        <div style={{
          borderTop: '1px solid var(--cb-border)',
          maxWidth: 1200,
          margin: '0 auto',
          padding: '16px 40px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
        }}>
          <span style={{
            fontFamily: 'var(--cb-mono)',
            fontSize: 10,
            color: 'var(--cb-text-3)',
            letterSpacing: '0.06em',
          }}>
            &copy; {new Date().getFullYear()} COBBRA
          </span>
          <div style={{ display: 'flex', gap: 20 }}>
            {['Privacy', 'Terms', 'Contact'].map(l => (
              <a key={l} href="#" className="cb-footer-link">{l}</a>
            ))}
          </div>
        </div>

      </footer>
    </div>
  )
}
