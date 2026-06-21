import { useEffect, useState, useRef, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getActivity, deleteActivity, renameActivity, exportCsv, exportGpx, updateNotes, getActivitySegments, getAnalysis, clearAnalysis, getSettings, getHydrationAnalysis, updateHydrationIntake, getDurabilityAnalysis, overrideEnvironment, getActivityClimbs } from '../services/api'
import { format } from 'date-fns'
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid
} from 'recharts'
import { MapContainer, TileLayer, Polyline } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { ArrowLeft, Trash2, Pencil, Download, FileText, Cloud, Wind, Thermometer, Sparkles, RefreshCw, Droplets, Home, Trees, TrendingUp, ChevronDown, ChevronUp } from 'lucide-react'
import InfoTip from './InfoTip'
import { colors } from '../tokens'

function fmtDuration(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}

function fmtPace(seconds) {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--border-bright)',
      borderRadius: 6, padding: '8px 12px', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{(label / 1000).toFixed(1)} km</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, fontFamily: 'var(--font-display)', fontSize: 15 }}>
          {p.value?.toFixed(1)} <span style={{ fontSize: 11, opacity: 0.7 }}>{p.name}</span>
        </div>
      ))}
    </div>
  )
}

// Platform → i18n key suffix (resolved against activityDetail.platform.* at render)
const PLATFORM_LABEL_KEYS = {
  zwift: 'zwift', trainerroad: 'trainerroad', wahoo: 'wahoo',
  mywhoosh: 'mywhoosh', rolo: 'rolo', other: 'other',
}

function EnvBadge({ activity, onOverride }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  const isIndoor = activity.ride_environment === 'indoor'
  const label = isIndoor
    ? t(`activityDetail.platform.${PLATFORM_LABEL_KEYS[activity.indoor_platform] || 'indoor'}`)
    : t('activityDetail.platform.outdoor')
  const color = isIndoor ? 'var(--text-secondary)' : 'var(--status-good)'
  const Icon  = isIndoor ? Home : Trees

  const doOverride = async (env, platform = null) => {
    setSaving(true)
    try {
      const res = await overrideEnvironment(activity.id, { environment: env, platform })
      onOverride({
        ride_environment: env,
        ride_environment_source: 'user_override',
        indoor_platform: platform,
        corrected_tss: res.data.corrected_tss,
      })
      setOpen(false)
    } catch { /* silently ignore */ } finally { setSaving(false) }
  }

  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer',
          background: `${color}18`, border: `1px solid ${color}55`, borderRadius: 6,
          padding: '2px 8px', fontSize: 11, fontWeight: 600, color }}
        onClick={() => setOpen(v => !v)}
      >
        <Icon size={10} /> {label}
        {activity.ride_environment_source === 'user_override' && (
          <span style={{ fontSize: 9, opacity: 0.6, marginLeft: 2 }}>✎</span>
        )}
      </span>
      {open && (
        <div style={{
          position: 'absolute', top: '110%', left: 0, zIndex: 50, minWidth: 160,
          background: 'var(--bg-card)', border: '1px solid var(--border-bright)',
          borderRadius: 8, padding: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
        }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' }}>
            {t('activityDetail.changeClassification')}
          </div>
          {[
            { env: 'outdoor', platform: null,    labelKey: 'outdoor' },
            { env: 'indoor',  platform: 'zwift', labelKey: 'zwift' },
            { env: 'indoor',  platform: 'trainerroad', labelKey: 'trainerroad' },
            { env: 'indoor',  platform: 'rolo',  labelKey: 'rolo' },
            { env: 'indoor',  platform: 'other', labelKey: 'other' },
          ].map(opt => (
            <div key={opt.labelKey}
              onClick={() => !saving && doOverride(opt.env, opt.platform)}
              style={{
                padding: '5px 8px', borderRadius: 5, cursor: saving ? 'wait' : 'pointer',
                fontSize: 12, color: 'var(--text-primary)',
                background: activity.ride_environment === opt.env && activity.indoor_platform === opt.platform
                  ? 'var(--bg-secondary)' : 'transparent',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-secondary)'}
              onMouseLeave={e => e.currentTarget.style.background =
                activity.ride_environment === opt.env && activity.indoor_platform === opt.platform
                  ? 'var(--bg-secondary)' : 'transparent'}
            >
              {t(`activityDetail.classifyOption.${opt.labelKey}`)}
            </div>
          ))}
        </div>
      )}
    </span>
  )
}

function downsample(arr, maxPoints = 500) {
  if (arr.length <= maxPoints) return arr
  const step = Math.ceil(arr.length / maxPoints)
  return arr.filter((_, i) => i % step === 0)
}

const CAD_ZONES = [
  { key: 'veryLow',  max: 60,       color: '#8888aa' },
  { key: 'low',      max: 75,       color: '#4da6ff' },
  { key: 'optimal',  max: 90,       color: '#6dffb8' },
  { key: 'high',     max: 100,      color: '#ffd93d' },
  { key: 'veryHigh', max: Infinity, color: '#ff8c42' },
]

function computeCadenceZones(trackPoints) {
  const pts = trackPoints.filter(p => p.cadence_rpm != null && p.cadence_rpm > 0)
  if (pts.length === 0) return null
  const counts = CAD_ZONES.map(() => 0)
  pts.forEach(p => {
    const idx = CAD_ZONES.findIndex(z => p.cadence_rpm < z.max)
    if (idx >= 0) counts[idx]++
  })
  const total = counts.reduce((a, b) => a + b, 0)
  return CAD_ZONES.map((z, i) => ({
    ...z,
    pct: total > 0 ? Math.round((counts[i] / total) * 100) : 0,
  }))
}

const HR_ZONES = [
  { key: 'z1',   min: 0,    max: 0.60, color: '#6dffb8' },
  { key: 'z2',   min: 0.60, max: 0.70, color: '#4da6ff' },
  { key: 'z3',   min: 0.70, max: 0.80, color: '#ffd93d' },
  { key: 'z4',   min: 0.80, max: 0.90, color: '#ff8c42' },
  { key: 'z5',   min: 0.90, max: 1.00, color: '#ff4d6d' },
]

function computeHrZones(trackPoints, maxHr) {
  if (!maxHr) return null
  const pts = trackPoints.filter(p => p.heart_rate_bpm != null)
  if (pts.length === 0) return null
  const counts = HR_ZONES.map(() => 0)
  pts.forEach(p => {
    const pct = p.heart_rate_bpm / maxHr
    const idx = HR_ZONES.findIndex(z => pct >= z.min && pct < z.max)
    if (idx >= 0) counts[idx]++
    else if (pct >= 1.0) counts[4]++
  })
  const total = counts.reduce((a, b) => a + b, 0)
  return HR_ZONES.map((z, i) => ({
    ...z,
    count: counts[i],
    pct: total > 0 ? Math.round((counts[i] / total) * 100) : 0,
  }))
}

// Compute splits every N km
function computeSplits(pts, splitKm = 1) {
  const hasDist = pts.some(p => p.distance_m != null)
  if (!hasDist || pts.length < 2) return []
  const splits = []
  let splitEnd = splitKm * 1000
  let splitStart = 0
  let startIdx = 0

  for (let i = 1; i < pts.length; i++) {
    const d = pts[i].distance_m ?? 0
    if (d >= splitEnd) {
      const startPt = pts[startIdx]
      const endPt = pts[i]
      const distM = d - (startPt.distance_m ?? 0)
      const timeS = startPt.timestamp && endPt.timestamp
        ? (new Date(endPt.timestamp) - new Date(startPt.timestamp)) / 1000
        : null
      const hrPts = pts.slice(startIdx, i + 1).filter(p => p.heart_rate_bpm != null)
      const cadPts = pts.slice(startIdx, i + 1).filter(p => p.cadence_rpm != null)
      splits.push({
        num: splits.length + 1,
        distM,
        timeS,
        avgSpeed: timeS && distM > 0 ? (distM / timeS) * 3.6 : null,
        avgHr: hrPts.length > 0 ? Math.round(hrPts.reduce((a, p) => a + p.heart_rate_bpm, 0) / hrPts.length) : null,
        avgCad: cadPts.length > 0 ? Math.round(cadPts.reduce((a, p) => a + p.cadence_rpm, 0) / cadPts.length) : null,
        elevGain: endPt.elevation != null && startPt.elevation != null
          ? Math.max(0, endPt.elevation - startPt.elevation)
          : null,
      })
      startIdx = i
      splitEnd += splitKm * 1000
    }
  }
  return splits
}

// Best efforts: sliding-window fastest time for each target distance
const EFFORT_DISTANCES = [
  { label: '400m',  m: 400 },
  { label: '1 km',  m: 1000 },
  { label: '5 km',  m: 5000 },
  { label: '10 km', m: 10000 },
  { label: '20 km', m: 20000 },
  { label: '40 km', m: 40000 },
]

function computeBestEfforts(pts) {
  const valid = pts.filter(p => p.distance_m != null && p.timestamp != null)
  if (valid.length < 2) return []
  const results = []
  for (const { label, m } of EFFORT_DISTANCES) {
    const maxDist = valid[valid.length - 1].distance_m ?? 0
    if (maxDist < m) continue
    let best = null
    let j = 0
    for (let i = 0; i < valid.length; i++) {
      while (j < valid.length - 1 && (valid[j].distance_m - valid[i].distance_m) < m) j++
      if ((valid[j].distance_m - valid[i].distance_m) >= m) {
        const secs = (new Date(valid[j].timestamp) - new Date(valid[i].timestamp)) / 1000
        if (secs > 0 && (best === null || secs < best)) best = secs
      }
    }
    if (best !== null) {
      const speed = (m / 1000) / (best / 3600)
      results.push({ label, secs: best, speed })
    }
  }
  return results
}

// ── AI Analysis helpers ───────────────────────────────────────────────────────

function parseAnalysis(raw) {
  if (!raw) return []
  const lines = raw.split('\n').filter(l => !/^#{1,6}\s/.test(l))
  const paras = lines.join('\n').split(/\n{2,}/).map(p => p.replace(/\n/g, ' ').trim()).filter(Boolean)
  const last = paras.length - 1
  return paras.map((text, i) => {
    const isTip = i === last && /\btip\b|\bnext time\b|\brecommend\b|\btry\b.{0,60}(next|ride|week)/i.test(text)
    return { text, type: i === 0 ? 'lead' : isTip ? 'tip' : 'body' }
  })
}

function MetricSpan({ text }) {
  const re = /\b(\d+(?:[.,]\d+)?)\s*(km\/h|bpm|rpm|W\/kg|kJ|km(?=[\s,.]|$)|%|°C)\b/g
  const parts = []
  let last = 0, m, key = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(<span key={key++}>{text.slice(last, m.index)}</span>)
    parts.push(
      <span key={key++} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.88em', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
        {m[0]}
      </span>
    )
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(<span key={key++}>{text.slice(last)}</span>)
  return <>{parts}</>
}

function AnalysisRenderer({ text }) {
  const paragraphs = parseAnalysis(text)
  const bodyParas = paragraphs.filter(p => p.type !== 'tip')
  const tip = paragraphs.find(p => p.type === 'tip')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {bodyParas.map((para, i) => (
        <p key={i} style={{
          margin: 0,
          fontSize: para.type === 'lead' ? 15 : 14,
          fontWeight: para.type === 'lead' ? 500 : 400,
          lineHeight: 1.78,
          color: para.type === 'lead' ? 'var(--text-primary)' : 'var(--text-secondary)',
          maxWidth: '72ch',
          paddingBottom: (i < bodyParas.length - 1 || tip) ? 16 : 0,
          marginBottom: (i < bodyParas.length - 1 || tip) ? 16 : 0,
          borderBottom: (i < bodyParas.length - 1 || tip) ? '1px solid var(--border)' : 'none',
        }}>
          <MetricSpan text={para.text} />
        </p>
      ))}
      {tip && (
        <div style={{
          background: 'color-mix(in srgb, #39FF14 5%, transparent)',
          border: '1px solid color-mix(in srgb, #39FF14 16%, transparent)',
          borderRadius: 8,
          padding: '14px 16px',
        }}>
          <div style={{
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: '#39FF14',
            marginBottom: 8,
          }}>
            Coaching Tip
          </div>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.75, color: 'var(--text-secondary)' }}>
            <MetricSpan text={tip.text} />
          </p>
        </div>
      )}
    </div>
  )
}

// ── Power analysis ────────────────────────────────────────────────────────────

const POWER_ZONES = [
  { label: 'Z1', nameKey: 'activeRecovery', min: 0,    max: 0.55,     color: '#6dffb8' },
  { label: 'Z2', nameKey: 'endurance',      min: 0.55, max: 0.75,     color: '#4da6ff' },
  { label: 'Z3', nameKey: 'tempo',          min: 0.75, max: 0.90,     color: '#ffd93d' },
  { label: 'Z4', nameKey: 'threshold',      min: 0.90, max: 1.05,     color: '#ff8c42' },
  { label: 'Z5', nameKey: 'vo2max',         min: 1.05, max: 1.20,     color: '#ff4d6d' },
  { label: 'Z6', nameKey: 'anaerobic',      min: 1.20, max: 1.50,     color: '#c084fc' },
  { label: 'Z7', nameKey: 'neuromuscular',  min: 1.50, max: Infinity, color: 'oklch(98% 0.005 142)' },
]

// Standard MMP durations in actual seconds
const MMP_DURATIONS = [
  { label: '5s',    secs: 5 },
  { label: '10s',   secs: 10 },
  { label: '30s',   secs: 30 },
  { label: '1 min', secs: 60 },
  { label: '2 min', secs: 120 },
  { label: '5 min', secs: 300 },
  { label: '10 min',secs: 600 },
  { label: '20 min',secs: 1200 },
  { label: '60 min',secs: 3600 },
]

// Coggan NP: time-based 30-second rolling average → 4th power mean → 4th root
function computeNP(trackPoints) {
  const pts = trackPoints
    .filter(p => p.power_w != null && p.timestamp != null)
    .map(p => ({ t: new Date(p.timestamp).getTime() / 1000, w: p.power_w }))
    .sort((a, b) => a.t - b.t)
  if (pts.length < 2) return null

  const WINDOW_S = 30
  const rollingAvgs = []
  let j = 0
  let windowSum = 0

  for (let i = 0; i < pts.length; i++) {
    windowSum += pts[i].w
    while ((pts[i].t - pts[j].t) > WINDOW_S) {
      windowSum -= pts[j].w
      j++
    }
    rollingAvgs.push(windowSum / (i - j + 1))
  }

  if (rollingAvgs.length === 0) return null
  const mean4 = rollingAvgs.reduce((s, v) => s + Math.pow(v, 4), 0) / rollingAvgs.length
  return Math.round(Math.pow(mean4, 0.25))
}

function computePowerZones(trackPoints, ftp) {
  if (!ftp) return null
  const pts = trackPoints.filter(p => p.power_w != null)
  if (pts.length === 0) return null
  const counts = POWER_ZONES.map(() => 0)
  pts.forEach(p => {
    const ratio = p.power_w / ftp
    const idx = POWER_ZONES.findIndex(z => ratio >= z.min && ratio < z.max)
    if (idx >= 0) counts[idx]++
  })
  const total = counts.reduce((a, b) => a + b, 0)
  return POWER_ZONES.map((z, i) => ({
    ...z,
    pct: total > 0 ? Math.round((counts[i] / total) * 100) : 0,
    count: counts[i],
  }))
}

// MMP (Mean Maximal Power): best average power for each standard duration, time-based sliding window
function computeMMP(trackPoints) {
  const pts = trackPoints
    .filter(p => p.power_w != null && p.timestamp != null)
    .map(p => ({ t: new Date(p.timestamp).getTime() / 1000, w: p.power_w }))
    .sort((a, b) => a.t - b.t)
  if (pts.length < 2) return []

  const totalDuration = pts[pts.length - 1].t - pts[0].t

  return MMP_DURATIONS
    .filter(d => d.secs <= totalDuration)
    .map(d => {
      let best = 0
      let j = 0
      let windowSum = 0

      for (let i = 0; i < pts.length; i++) {
        windowSum += pts[i].w
        while ((pts[i].t - pts[j].t) > d.secs) {
          windowSum -= pts[j].w
          j++
        }
        const avg = windowSum / (i - j + 1)
        if (avg > best) best = avg
      }

      return { label: d.label, secs: d.secs, watts: Math.round(best) }
    })
    .filter(d => d.watts > 0)
}

// CP model: linear regression on W_total = W' + CP×t, fitted to 2–20 min MMP points
function fitCPModel(mmp) {
  const fitPts = mmp.filter(d => d.secs >= 120 && d.secs <= 1200 && d.watts > 0)
  if (fitPts.length < 2) return null

  const n = fitPts.length
  const xs = fitPts.map(d => d.secs)
  const ys = fitPts.map(d => d.watts * d.secs)  // total joules

  const xMean = xs.reduce((a, b) => a + b, 0) / n
  const yMean = ys.reduce((a, b) => a + b, 0) / n
  const ssXX = xs.reduce((s, x) => s + (x - xMean) ** 2, 0)
  const ssXY = xs.reduce((s, x, i) => s + (x - xMean) * (ys[i] - yMean), 0)

  if (ssXX === 0) return null
  const cp = ssXY / ssXX
  const wPrime = yMean - cp * xMean

  if (cp <= 0 || wPrime <= 0) return null
  return { cp: Math.round(cp), wPrimeKj: Math.round(wPrime / 100) / 10 }
}

// eFTP = 95% of best 20-min power
function estimateFTP(mmp) {
  const d20 = mmp.find(d => d.secs === 1200)
  if (!d20 || d20.watts === 0) return null
  return Math.round(d20.watts * 0.95)
}

// HR Decoupling (Pw:HR or Pa:HR): split-half efficiency drift
// < 5% = aerobically well-conditioned for this effort
function computeHRDecoupling(trackPoints) {
  const pts = trackPoints.filter(p => p.heart_rate_bpm != null && p.timestamp != null)
  if (pts.length < 20) return null

  const hasPower = pts.some(p => p.power_w != null)
  const hasSpeed = pts.some(p => p.speed_kmh != null)
  if (!hasPower && !hasSpeed) return null

  const mid = Math.floor(pts.length / 2)
  const first = pts.slice(0, mid)
  const second = pts.slice(mid)

  const avgOf = (arr, key) => {
    const vals = arr.filter(p => p[key] != null).map(p => p[key])
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }

  let firstRatio, secondRatio, label
  if (hasPower) {
    firstRatio  = avgOf(first,  'power_w') / avgOf(first,  'heart_rate_bpm')
    secondRatio = avgOf(second, 'power_w') / avgOf(second, 'heart_rate_bpm')
    label = 'Pw:HR'
  } else {
    firstRatio  = avgOf(first,  'speed_kmh') / avgOf(first,  'heart_rate_bpm')
    secondRatio = avgOf(second, 'speed_kmh') / avgOf(second, 'heart_rate_bpm')
    label = 'Pa:HR'
  }

  if (!firstRatio || !secondRatio || firstRatio === 0) return null
  const pct = ((firstRatio - secondRatio) / firstRatio) * 100
  return { pct: Math.round(pct * 10) / 10, label, aerobic: pct < 5 }
}

// VAM (Velocità Ascensionale Media): elevation gain rate on ascending segments, m/h
function computeVAM(trackPoints) {
  const pts = trackPoints.filter(p => p.elevation != null && p.timestamp != null)
  if (pts.length < 2) return null

  let totalGain = 0
  let climbSeconds = 0

  for (let i = 1; i < pts.length; i++) {
    const dElev = pts[i].elevation - pts[i - 1].elevation
    if (dElev > 0) {
      const dt = (new Date(pts[i].timestamp) - new Date(pts[i - 1].timestamp)) / 1000
      if (dt > 0 && dt < 300) {
        totalGain += dElev
        climbSeconds += dt
      }
    }
  }

  if (climbSeconds < 60 || totalGain < 10) return null
  return Math.round((totalGain / climbSeconds) * 3600)
}

// Durability: compare MMP fresh (first 40% kJ) vs fatigued (remaining)
function computeDurability(trackPoints) {
  const pts = trackPoints
    .filter(p => p.power_w != null && p.timestamp != null)
    .map(p => ({ t: new Date(p.timestamp).getTime() / 1000, w: p.power_w }))
    .sort((a, b) => a.t - b.t)
  if (pts.length < 120) return null

  // Cumulative kJ (clamp dt to 10 s to skip gaps)
  const cumKj = [0]
  for (let i = 1; i < pts.length; i++) {
    const dt = Math.min(pts[i].t - pts[i - 1].t, 10)
    cumKj.push(cumKj[i - 1] + pts[i].w * dt / 1000)
  }
  const totalKj = cumKj[pts.length - 1]
  if (totalKj < 200) return null

  const splitKj = totalKj * 0.4
  const splitIdx = cumKj.findIndex(v => v >= splitKj)
  if (splitIdx < 30 || splitIdx >= pts.length - 30) return null

  const freshPts    = pts.slice(0, splitIdx)
  const fatiguedPts = pts.slice(splitIdx)

  const mmpFor = (pArr) => {
    const dur = pArr[pArr.length - 1].t - pArr[0].t
    return MMP_DURATIONS
      .filter(d => d.secs <= dur * 0.9 && d.secs <= 1200)
      .map(d => {
        let best = 0, j = 0, sum = 0
        for (let i = 0; i < pArr.length; i++) {
          sum += pArr[i].w
          while ((pArr[i].t - pArr[j].t) > d.secs) { sum -= pArr[j].w; j++ }
          const avg = sum / (i - j + 1)
          if (avg > best) best = avg
        }
        return { label: d.label, secs: d.secs, watts: Math.round(best) }
      })
      .filter(d => d.watts > 0)
  }

  const freshMMP    = mmpFor(freshPts)
  const fatiguedMMP = mmpFor(fatiguedPts)

  const drops = []
  for (const f of freshMMP) {
    const fat = fatiguedMMP.find(d => d.label === f.label)
    if (!fat || f.watts === 0) continue
    drops.push({
      label:         f.label,
      freshWatts:    f.watts,
      fatiguedWatts: fat.watts,
      dropPct:       Math.round(((f.watts - fat.watts) / f.watts) * 1000) / 10,
    })
  }
  if (drops.length === 0) return null

  const avgDrop = drops.reduce((s, d) => s + d.dropPct, 0) / drops.length
  return {
    drops,
    thresholdKj: Math.round(splitKj),
    totalKj:     Math.round(totalKj),
    avgDrop:     Math.round(avgDrop * 10) / 10,
    score:       Math.max(0, Math.round(100 - avgDrop * 4)),
  }
}

// Power Quadrant: % time in each cadence × torque quadrant
function computePowerQuadrant(trackPoints) {
  const pts = trackPoints.filter(p => p.power_w != null && p.cadence_rpm != null && p.cadence_rpm > 20)
  if (pts.length < 20) return null

  const withTorque = pts.map(p => ({
    cadence: p.cadence_rpm,
    torque:  p.power_w * 9.5493 / p.cadence_rpm,  // Nm = W × 60/(2π×rpm)
  }))

  const sorted    = [...withTorque].map(p => p.torque).sort((a, b) => a - b)
  const medTorque = sorted[Math.floor(sorted.length / 2)]
  const CAD_SPLIT = 90

  let q1 = 0, q2 = 0, q3 = 0, q4 = 0
  withTorque.forEach(({ cadence, torque }) => {
    const hi = cadence >= CAD_SPLIT
    const ht = torque  >= medTorque
    if ( hi && !ht) q1++   // Aerobic Spin
    if ( hi &&  ht) q2++   // Sprint Power
    if (!hi &&  ht) q3++   // Strength / Climbing
    if (!hi && !ht) q4++   // Recovery / Coasting
  })

  const total = withTorque.length
  const pct   = n => Math.round(n / total * 100)
  return {
    cadSplit:   CAD_SPLIT,
    medTorque:  Math.round(medTorque * 10) / 10,
    // arranged as 2×2: top row = high torque, left = low cadence, right = high cadence
    grid: [
      [{ key: 'Q3', labelKey: 'strength',    subKey: 'lowCadHighTorque',  pct: pct(q3), color: '#ffd93d', count: q3 },
       { key: 'Q2', labelKey: 'sprintPower', subKey: 'highCadHighTorque', pct: pct(q2), color: '#ff4d6d', count: q2 }],
      [{ key: 'Q4', labelKey: 'recovery',    subKey: 'lowCadLowTorque',   pct: pct(q4), color: '#6dffb8', count: q4 },
       { key: 'Q1', labelKey: 'aerobicSpin', subKey: 'highCadLowTorque',  pct: pct(q1), color: '#4da6ff', count: q1 }],
    ],
  }
}

function estimateCalories(durationSeconds, avgSpeedKmh, weightKg) {
  if (!weightKg) return null
  const speed = avgSpeedKmh || 0
  const met = speed < 16 ? 6 : speed < 19 ? 8 : speed < 22 ? 10 : speed < 25 ? 12 : 14
  return Math.round(met * weightKg * (durationSeconds / 3600))
}

export default function ActivityDetail() {
  const { t, i18n } = useTranslation()
  const { id } = useParams()
  const navigate = useNavigate()
  const [activity, setActivity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [newName, setNewName] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const [segmentEfforts, setSegmentEfforts] = useState([])
  const [splitKm, setSplitKm] = useState(null)      // null = auto
  const [showAllSplits, setShowAllSplits] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [ftp,       setFtp]       = useState(null)
  const [weightKg,  setWeightKg]  = useState(null)
  const [profileMaxHr, setProfileMaxHr] = useState(null)
  const [hydration, setHydration] = useState(null)
  const [intakeInput,  setIntakeInput]  = useState('')
  const [intakeSaving, setIntakeSaving] = useState(false)
  const [intakeMsg,    setIntakeMsg]    = useState('')
  const [durabilityData, setDurabilityData] = useState(null)
  const [durabilityLoading, setDurabilityLoading] = useState(true)
  const [climbs,    setClimbs]    = useState([])
  const [expandedClimb, setExpandedClimb] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [showHydrationSources, setShowHydrationSources] = useState(false)
  const notesTimer     = useRef(null)
  const intakeMsgTimer = useRef(null)

  useEffect(() => {
    const fetchActivity = (attempt = 0) => {
      getActivity(id)
        .then(r => {
          setActivity(r.data)
          setNewName(r.data.name)
          setNotes(r.data.notes ?? '')
          if (r.data.has_ai_analysis) {
            getAnalysis(id).then(r2 => setAnalysis(r2.data.analysis)).catch(() => {})
          }
          setLoading(false)
        })
        .catch(e => {
          const status = e.response?.status
          if (status === 404) {
            setError(t('activityDetail.notFound'))
            setLoading(false)
          } else if (attempt < 3) {
            // Transient server error (e.g. DB busy after upload) — retry up to 3×
            setTimeout(() => fetchActivity(attempt + 1), 800 * (attempt + 1))
          } else {
            setError(t('activityDetail.notFound'))
            setLoading(false)
          }
        })
    }
    fetchActivity()
    getActivitySegments(id).then(r => setSegmentEfforts(r.data)).catch(() => {})
    getActivityClimbs(id).then(r => setClimbs(r.data)).catch(() => {})
    getSettings().then(r => {
      setFtp(r.data.ftp || null)
      setWeightKg(r.data.weight_kg || null)
      setProfileMaxHr(r.data.max_hr || null)
    }).catch(() => {})
    getHydrationAnalysis(id).then(r => {
      setHydration(r.data)
      setIntakeInput(r.data.reported_intake_ml != null ? String(r.data.reported_intake_ml) : '')
    }).catch(() => {})
    getDurabilityAnalysis(id).then(r => setDurabilityData(r.data)).catch(() => {}).finally(() => setDurabilityLoading(false))
  }, [id])

  const handleDelete = async () => {
    await deleteActivity(id)
    navigate('/activities')
  }

  const handleRename = async () => {
    if (!newName.trim()) return
    await renameActivity(id, newName.trim())
    setActivity(a => ({ ...a, name: newName.trim() }))
    setEditing(false)
  }

  const handleNotesChange = (val) => {
    setNotes(val)
    clearTimeout(notesTimer.current)
    notesTimer.current = setTimeout(() => {
      updateNotes(id, val).catch(() => {})
    }, 800)
  }

  const handleAnalyse = async () => {
    setAnalysisLoading(true)
    setAnalysisError('')
    setAnalysis('')
    try {
      const res = await fetch(`/api/activities/${id}/analysis/stream?lang=${encodeURIComponent(i18n.resolvedLanguage || i18n.language)}`, {
        credentials: 'include',
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || t('activityDetail.analysisFailed'))
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const msg = JSON.parse(line.slice(6))
          if (msg.error) throw new Error(msg.error)
          if (msg.cached) {
            setAnalysis(msg.text)
          } else if (msg.text) {
            setAnalysis(prev => prev + msg.text)
          }
          if (msg.done) { setAnalysisLoading(false); return }
        }
      }
    } catch (e) {
      setAnalysisError(e.message || t('activityDetail.analysisFailed'))
    } finally {
      setAnalysisLoading(false)
    }
  }

  const handleClearAnalysis = async () => {
    await clearAnalysis(id).catch(() => {})
    setAnalysis(null)
  }

  const handleRegenerateAnalysis = async () => {
    await clearAnalysis(id).catch(() => {})
    handleAnalyse()
  }

  const handleLogIntake = async () => {
    const ml = parseInt(intakeInput, 10)
    if (isNaN(ml) || ml < 0 || ml > 20000) { setIntakeMsg('range'); return }
    setIntakeSaving(true); setIntakeMsg('')
    try {
      const res = await updateHydrationIntake(id, ml)
      setHydration(res.data)
      // Refresh activity to pick up updated decoupling values (hydration affects the correction)
      getActivity(id).then(r => setActivity(r.data)).catch(() => {})
      setIntakeMsg('saved')
      clearTimeout(intakeMsgTimer.current)
      intakeMsgTimer.current = setTimeout(() => setIntakeMsg(''), 2500)
    } catch { setIntakeMsg('failed') }
    finally { setIntakeSaving(false) }
  }

  const handleExportCsv = async () => {
    const res = await exportCsv(id)
    triggerDownload(res)
  }

  const handleExportGpx = async () => {
    const res = await exportGpx(id)
    triggerDownload(res)
  }

  function triggerDownload(res) {
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    const cd = res.headers['content-disposition'] || ''
    const match = cd.match(/filename="?([^"]+)"?/)
    a.download = match ? match[1] : `activity_${id}`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Hooks must be called unconditionally — before any early returns
  const pts = activity?.track_points ?? []

  const mapPoints = useMemo(() => pts.filter(p => p.lat && p.lon).map(p => [p.lat, p.lon]), [pts])
  const center = mapPoints.length > 0 ? mapPoints[Math.floor(mapPoints.length / 2)] : [38.5, -9.0]

  const avgCad = useMemo(() => {
    const active = pts.filter(p => p.cadence_rpm > 0)
    return active.length > 0 ? Math.round(active.reduce((s, p) => s + p.cadence_rpm, 0) / active.length) : null
  }, [pts])

  const chartData = useMemo(() => downsample(
    pts.filter(p => p.distance_m != null).map(p => ({
      d: Math.round(p.distance_m),
      speed: p.speed_kmh,
      hr: p.heart_rate_bpm,
      cad: (p.cadence_rpm && p.cadence_rpm > 0) ? p.cadence_rpm : avgCad,
      ele: p.elevation,
      pwr: p.power_w,
    }))
  ), [pts, avgCad])

  const hasHR  = pts.some(p => p.heart_rate_bpm != null)
  const hasCad = pts.some(p => p.cadence_rpm != null)
  const hasEle = pts.some(p => p.elevation != null)
  const hasPwr = pts.some(p => p.power_w != null)

  // Zones must be based on the rider's true physiological max HR (profile),
  // not this ride's peak — using the ride's own peak as the denominator
  // shrinks it on any ride that wasn't an all-out effort, inflating every
  // point's %max and skewing the whole distribution into higher zones.
  const hrZones      = useMemo(() => hasHR  ? computeHrZones(pts, profileMaxHr || activity?.max_heart_rate_bpm) : null, [pts, hasHR, profileMaxHr, activity?.max_heart_rate_bpm])
  const cadZones     = useMemo(() => hasCad ? computeCadenceZones(pts) : null, [pts, hasCad])
  const efforts      = useMemo(() => computeBestEfforts(pts), [pts])
  const np           = useMemo(() => hasPwr ? computeNP(pts) : null, [pts, hasPwr])
  const mmp          = useMemo(() => hasPwr ? computeMMP(pts) : [], [pts, hasPwr])
  const pwrZones     = useMemo(() => hasPwr ? computePowerZones(pts, ftp) : null, [pts, hasPwr, ftp])
  const cpModel      = useMemo(() => mmp.length >= 2 ? fitCPModel(mmp) : null, [mmp])
  const eFtp         = useMemo(() => estimateFTP(mmp), [mmp])
  const hrDecoupling = useMemo(() => (hasHR && (activity?.duration_seconds ?? 0) > 900) ? computeHRDecoupling(pts) : null, [pts, hasHR, activity?.duration_seconds])
  const vam          = useMemo(() => hasEle ? computeVAM(pts) : null, [pts, hasEle])
  const durability   = useMemo(() => hasPwr ? computeDurability(pts) : null, [pts, hasPwr])
  const pwrQuadrant  = useMemo(() => hasPwr ? computePowerQuadrant(pts) : null, [pts, hasPwr])

  const ifVal  = np && ftp ? (np / ftp).toFixed(2) : null
  const tss    = np && ftp && activity?.duration_seconds
    ? Math.round((activity.duration_seconds * np * (np / ftp)) / (ftp * 3600) * 100)
    : null
  const wPerKg = np && weightKg ? (np / weightKg).toFixed(2) : null

  const autoSplitKm  = (activity?.distance_km ?? 0) >= 50 ? 10 : (activity?.distance_km ?? 0) >= 15 ? 5 : 1
  const activeSplitKm = splitKm ?? autoSplitKm
  const splits = useMemo(() => computeSplits(pts, activeSplitKm), [pts, activeSplitKm])
  const SPLITS_PREVIEW = 8

  if (loading) return <div className="loading-center"><div className="spinner" /></div>
  if (error) return <div className="empty-state"><h3>{error}</h3></div>

  const { laps } = activity
  const hasWeather = activity.weather_temp_c != null || activity.weather_desc

  const metrics = [
    { label: t('common.distance'), value: `${activity.distance_km.toFixed(2)}`, unit: 'km', color: 'var(--accent)' },
    { label: t('activityDetail.metric.movingTime'), value: fmtDuration(activity.duration_seconds), unit: '', color: 'var(--text-primary)' },
    ...(activity.suffer_score != null ? [{ label: t('activityDetail.metric.sufferScore'), value: activity.suffer_score, unit: '', color: 'var(--heart)' }] : []),
    { label: t('common.avgSpeed'), value: activity.avg_speed_kmh.toFixed(1), unit: 'km/h', color: 'var(--speed)' },
    { label: t('common.maxSpeed'), value: activity.max_speed_kmh.toFixed(1), unit: 'km/h', color: 'var(--speed)' },
    ...(hasHR ? [
      { label: t('common.avgHr'), value: Math.round(activity.avg_heart_rate_bpm), unit: 'bpm', color: 'var(--heart)' },
      { label: t('activityDetail.metric.maxHr'), value: Math.round(activity.max_heart_rate_bpm), unit: 'bpm', color: 'var(--heart)' },
    ] : []),
    ...(hasCad ? [
      { label: t('activityDetail.metric.avgCadence'), value: Math.round(activity.avg_cadence_rpm), unit: 'rpm', color: 'var(--cadence)' },
      { label: t('activityDetail.metric.maxCadence'), value: Math.round(activity.max_cadence_rpm), unit: 'rpm', color: 'var(--cadence)' },
    ] : []),
    ...(hasPwr ? [
      { label: t('common.avgPower'), value: Math.round(activity.avg_power_w), unit: 'W', color: 'var(--power)' },
      { label: t('activityDetail.metric.maxPower'), value: Math.round(activity.max_power_w), unit: 'W', color: 'var(--power)' },
    ] : []),
    { label: t('activityDetail.metric.elevationGain'), value: activity.elevation_gain_m.toFixed(0), unit: 'm', color: 'var(--elevation)' },
    { label: t('activityDetail.metric.elevationLoss'), value: activity.elevation_loss_m.toFixed(0), unit: 'm', color: 'var(--text-secondary)' },
    ...(activity.calories
      ? [{ label: t('activityDetail.metric.calories'), value: activity.calories, unit: 'kcal', color: 'var(--heart)' }]
      : (() => { const est = estimateCalories(activity.duration_seconds, activity.avg_speed_kmh, weightKg); return est ? [{ label: t('activityDetail.metric.estCalories'), value: est, unit: 'kcal', color: 'var(--heart)' }] : [] })()
    ),
  ]

  return (
    <div>
      <Link to="/activities" className="back-link">
        <ArrowLeft size={14} /> {t('activityDetail.allActivities')}
      </Link>

      {/* Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          {editing ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleRename()}
                autoFocus
                aria-label={t('activityDetail.activityNameAria')}
                style={{
                  background: 'var(--bg-card)', border: '1px solid var(--accent)',
                  color: 'var(--text-primary)', borderRadius: 6, padding: '6px 12px',
                  fontSize: 20, fontFamily: 'var(--font-display)', fontWeight: 700, outline: 'none',
                }}
              />
              <button className="btn btn-primary" onClick={handleRename}>{t('activityDetail.save')}</button>
              <button className="btn btn-ghost" onClick={() => setEditing(false)}>{t('activityDetail.cancel')}</button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 className="page-title">{activity.name}</h1>
              <button className="btn btn-ghost" style={{ padding: '4px 8px' }} aria-label={t('activityDetail.editActivityNameAria')} onClick={() => setEditing(true)}>
                <Pencil size={13} />
              </button>
            </div>
          )}
          <p className="page-subtitle" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {format(new Date(activity.date), 'EEEE, d MMMM yyyy')}
            {' · '}
            <span className={`badge badge-${activity.file_type}`}>{activity.file_type.toUpperCase()}</span>
            {activity.ride_environment && activity.ride_environment !== 'unknown' && (
              <EnvBadge activity={activity} onOverride={env => setActivity(a => ({ ...a, ...env }))} />
            )}
            {hasWeather && (
              <span className="weather-badge">
                {activity.weather_temp_c != null && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Thermometer size={11} /> {activity.weather_temp_c}°C
                  </span>
                )}
                {activity.weather_wind_kmh != null && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Wind size={11} /> {activity.weather_wind_kmh} km/h
                  </span>
                )}
                {activity.weather_desc && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Cloud size={11} /> {activity.weather_desc}
                  </span>
                )}
              </span>
            )}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={handleExportCsv}>
            <Download size={14} /> CSV
          </button>
          <button className="btn btn-ghost" onClick={handleExportGpx}>
            <FileText size={14} /> GPX
          </button>
          {deleteConfirm ? (
            <>
              <button className="btn btn-danger" onClick={handleDelete}>{t('activityDetail.confirmDelete')}</button>
              <button className="btn btn-ghost" onClick={() => setDeleteConfirm(false)}>{t('activityDetail.cancel')}</button>
            </>
          ) : (
            <button className="btn btn-danger" onClick={() => setDeleteConfirm(true)}>
              <Trash2 size={14} /> {t('activityDetail.delete')}
            </button>
          )}
        </div>
      </div>

      {/* Metrics */}
      <div className="metrics-grid">
        {metrics.map(({ label, value, unit, color }) => (
          <div className="metric-card" key={label}>
            <div className="metric-label">{label}</div>
            <div className="metric-value" style={{ color }}>
              {value}
              {unit && <span className="metric-unit">{unit}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Indoor correction card */}
      {activity.ride_environment === 'indoor' && (
        <div className="chart-section" style={{ padding: '14px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Home size={14} style={{ color: 'var(--text-secondary)' }} />
            <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-secondary)' }}>{t('activityDetail.indoorCorrection.title')}</span>
          </div>
          {activity.power_correction_factor != null && activity.corrected_tss != null ? (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.indoorCorrection.correctionFactor')}</div>
                <div style={{ fontSize: 22, fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--accent)' }}>
                  +{((activity.power_correction_factor - 1) * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('activityDetail.indoorCorrection.appliedToTss')}</div>
              </div>
              {activity.tss != null && (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.indoorCorrection.trainingStressScore')}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-display)' }}>
                    <span style={{ fontSize: 18, color: 'var(--text-secondary)', textDecoration: 'line-through' }}>
                      {Math.round(activity.tss)}
                    </span>
                    <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>→</span>
                    <span style={{ fontSize: 22, fontWeight: 700, color: 'var(--accent)' }}>
                      {Math.round(activity.corrected_tss)}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('activityDetail.indoorCorrection.correctedTss')}</div>
                </div>
              )}
              <div style={{ fontSize: 11, color: 'var(--text-muted)', maxWidth: 280, lineHeight: 1.5, alignSelf: 'center' }}>
                {t('activityDetail.indoorCorrection.indoorExplanation')}
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
              {t('activityDetail.indoorCorrection.noCorrection')}
              <br />
              {t('activityDetail.indoorCorrection.calibratePrompt')}{' '}
              <Link to="/settings" style={{ color: 'var(--accent)' }}>{t('activityDetail.indoorCorrection.calibrateLink')}</Link>{' '}
              {t('activityDetail.indoorCorrection.calibrateSuffix')}
            </div>
          )}
        </div>
      )}

      {/* Map */}
      {mapPoints.length > 0 && (
        <div className="map-container">
          <MapContainer
            center={center}
            zoom={13}
            style={{ height: '100%', width: '100%', background: '#0d0d1a' }}
            zoomControl={true}
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://carto.com/">CARTO</a>'
            />
            <Polyline
              positions={mapPoints}
              pathOptions={{ color: colors.accent, weight: 3, opacity: 0.9 }}
            />
          </MapContainer>
        </div>
      )}

      {/* Charts */}
      {chartData.length > 0 && (
        <>
          <div className="chart-section">
            <div className="chart-title">{t('activityDetail.chart.speed')} <InfoTip text={t('activityDetail.chart.speedTip')} /></div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" hide />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} unit=" km/h" width={52} />
                <Tooltip content={<ChartTooltip />} />
                <Line type="monotone" dataKey="speed" stroke="var(--speed)" dot={false} strokeWidth={2} name="km/h" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {hasHR && (
            <div className="chart-section">
              <div className="chart-title">{t('activityDetail.chart.heartRate')} <InfoTip text={t('activityDetail.chart.heartRateTip')} /></div>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="d" hide />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} unit=" bpm" width={52} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="hr" stroke="var(--heart)" dot={false} strokeWidth={2} name="bpm" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {hasCad && (
            <div className="chart-section">
              <div className="chart-title">{t('activityDetail.chart.cadence')} <InfoTip text={t('activityDetail.chart.cadenceTip')} /></div>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="d" hide />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} unit=" rpm" width={52} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="cad" stroke="var(--cadence)" dot={false} strokeWidth={2} name="rpm" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {hasPwr && (
            <div className="chart-section">
              <div className="chart-title">{t('activityDetail.chart.power')} <InfoTip text={t('activityDetail.chart.powerTip')} /></div>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="d" hide />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} unit=" W" width={52} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="pwr" stroke="var(--power)" dot={false} strokeWidth={2} name="W" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {hasEle && (
            <div className="chart-section">
              <div className="chart-title">{t('activityDetail.chart.elevation')} <InfoTip text={t('activityDetail.chart.elevationTip')} /></div>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="d" hide />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} unit=" m" width={52} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="ele" stroke="var(--elevation)" dot={false} strokeWidth={2} name="m" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      {/* Splits table */}
      {splits.length > 0 && (
        <div className="chart-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div className="chart-title" style={{ marginBottom: 0 }}>
              {t('activityDetail.splits.title')} <InfoTip text={t('activityDetail.splits.tip')} />
            </div>
            <div className="split-toggle">
              {[1, 5, 10].map(km => (
                <button
                  key={km}
                  className={`split-toggle-btn${activeSplitKm === km ? ' active' : ''}`}
                  onClick={() => { setSplitKm(km); setShowAllSplits(false) }}
                >
                  {km} km
                </button>
              ))}
            </div>
          </div>
          <div className="table-wrapper" style={{ border: 'none' }}>
            <table className="table splits-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">{t('activityDetail.splits.colTime')}</th>
                  <th scope="col">{t('activityDetail.splits.colSpeed')}</th>
                  {splits.some(s => s.avgHr) && <th scope="col">{t('activityDetail.splits.colAvgHr')}</th>}
                  {splits.some(s => s.avgCad) && <th scope="col">{t('activityDetail.splits.colAvgCad')}</th>}
                  {splits.some(s => s.elevGain != null) && <th scope="col">{t('activityDetail.splits.colElevGain')}</th>}
                </tr>
              </thead>
              <tbody>
                {(showAllSplits ? splits : splits.slice(0, SPLITS_PREVIEW)).map(s => (
                  <tr key={s.num} style={{ cursor: 'default' }}>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12, width: 32 }}>{s.num}</td>
                    <td style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--text-primary)' }}>
                      {s.timeS ? fmtDuration(Math.round(s.timeS)) : '—'}
                    </td>
                    <td style={{ color: 'var(--speed)' }}>
                      {s.avgSpeed ? `${s.avgSpeed.toFixed(1)} km/h` : '—'}
                    </td>
                    {splits.some(x => x.avgHr) && (
                      <td style={{ color: 'var(--heart)' }}>{s.avgHr ? `${s.avgHr} bpm` : '—'}</td>
                    )}
                    {splits.some(x => x.avgCad) && (
                      <td style={{ color: 'var(--cadence)' }}>{s.avgCad ? `${s.avgCad} rpm` : '—'}</td>
                    )}
                    {splits.some(x => x.elevGain != null) && (
                      <td style={{ color: 'var(--elevation)' }}>{s.elevGain != null ? `+${s.elevGain.toFixed(0)} m` : '—'}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {splits.length > SPLITS_PREVIEW && (
            <button
              className="btn btn-ghost"
              style={{ width: '100%', marginTop: 8, fontSize: 12 }}
              onClick={() => setShowAllSplits(v => !v)}
            >
              {showAllSplits
                ? t('activityDetail.splits.showLess')
                : t('activityDetail.splits.showMore', { count: splits.length - SPLITS_PREVIEW })}
            </button>
          )}
        </div>
      )}

      {/* Best Efforts */}
      {efforts.length > 0 && (
        <div className="chart-section">
          <div className="chart-title">{t('activityDetail.bestEfforts.title')} <InfoTip text={t('activityDetail.bestEfforts.tip')} /></div>
          <div className="efforts-grid">
            {efforts.map(e => (
              <div key={e.label} className="effort-card">
                <div className="effort-label">{e.label}</div>
                <div className="effort-time">{fmtDuration(Math.round(e.secs))}</div>
                <div className="effort-speed">{e.speed.toFixed(1)} km/h</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Laps */}
      {laps && laps.length > 0 && (
        <div className="chart-section">
          <div className="chart-title">{t('activityDetail.laps.title')}</div>
          <div className="table-wrapper" style={{ border: 'none' }}>
            <table className="table splits-table">
              <thead>
                <tr>
                  <th scope="col">{t('activityDetail.laps.colLap')}</th>
                  <th scope="col">{t('activityDetail.laps.colDistance')}</th>
                  <th scope="col">{t('activityDetail.laps.colTime')}</th>
                  <th scope="col">{t('activityDetail.laps.colAvgSpeed')}</th>
                  {laps.some(l => l.avg_hr) && <th scope="col">{t('activityDetail.laps.colAvgHr')}</th>}
                  {laps.some(l => l.avg_cadence) && <th scope="col">{t('activityDetail.laps.colAvgCad')}</th>}
                  {laps.some(l => l.elevation_gain_m) && <th scope="col">{t('activityDetail.laps.colElevGain')}</th>}
                </tr>
              </thead>
              <tbody>
                {laps.map(l => (
                  <tr key={l.id} style={{ cursor: 'default' }}>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{l.lap_number}</td>
                    <td style={{ color: 'var(--accent)', fontFamily: 'var(--font-display)' }}>
                      {l.distance_m ? `${(l.distance_m / 1000).toFixed(2)} km` : '—'}
                    </td>
                    <td style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}>
                      {l.elapsed_seconds ? fmtDuration(Math.round(l.elapsed_seconds)) : '—'}
                    </td>
                    <td style={{ color: 'var(--speed)' }}>
                      {l.avg_speed_kmh ? `${l.avg_speed_kmh.toFixed(1)} km/h` : '—'}
                    </td>
                    {laps.some(x => x.avg_hr) && (
                      <td style={{ color: 'var(--heart)' }}>{l.avg_hr ? `${Math.round(l.avg_hr)} bpm` : '—'}</td>
                    )}
                    {laps.some(x => x.avg_cadence) && (
                      <td style={{ color: 'var(--cadence)' }}>{l.avg_cadence ? `${Math.round(l.avg_cadence)} rpm` : '—'}</td>
                    )}
                    {laps.some(x => x.elevation_gain_m) && (
                      <td style={{ color: 'var(--elevation)' }}>{l.elevation_gain_m ? `+${l.elevation_gain_m.toFixed(0)} m` : '—'}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Power Analysis — only shown when power data exists */}
      {hasPwr && (np || pwrZones || mmp.length > 0) && (
        <div className="chart-section">
          <div className="chart-title">{t('activityDetail.powerAnalysis.title')} <InfoTip text={t('activityDetail.powerAnalysis.tip')} /></div>

          {/* Key power metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 10, marginBottom: 20 }}>
            {[
              np     && { label: t('activityDetail.powerAnalysis.normPower'), value: np,     unit: 'W',    color: 'var(--power)', hint: t('activityDetail.powerAnalysis.normPowerHint') },
              ifVal  && { label: t('activityDetail.powerAnalysis.intFactor'),  value: ifVal,  unit: 'IF',   color: '#c084fc',      hint: t('activityDetail.powerAnalysis.intFactorHint') },
              tss    && { label: t('activityDetail.powerAnalysis.tss'),        value: tss,    unit: 'pts',  color: 'var(--cadence)',   hint: t('activityDetail.powerAnalysis.tssHint') },
              wPerKg && { label: t('activityDetail.powerAnalysis.wPerKg'),     value: wPerKg, unit: 'w/kg', color: 'var(--elevation)', hint: t('activityDetail.powerAnalysis.wPerKgHint') },
              eFtp   && { label: t('activityDetail.powerAnalysis.eFtp'),       value: eFtp,  unit: 'W',    color: 'var(--power-model)',      hint: t('activityDetail.powerAnalysis.eFtpHint') },
            ].filter(Boolean).map(({ label, value, unit, color, hint }) => (
              <div key={label} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color, fontFamily: 'var(--font-display)' }}>
                  {value} <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)' }}>{unit}</span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.4 }}>{hint}</div>
              </div>
            ))}
          </div>

          {/* CP model */}
          {cpModel && (
            <div style={{ marginBottom: 20, padding: '12px 16px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 2 }}>{t('activityDetail.powerAnalysis.criticalPower')}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--power-model)', fontFamily: 'var(--font-display)' }}>{cpModel.cp} <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)' }}>W</span></div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 2 }}>{t('activityDetail.powerAnalysis.wPrime')}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#c084fc', fontFamily: 'var(--font-display)' }}>{cpModel.wPrimeKj} <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)' }}>kJ</span></div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', flex: 1, minWidth: 160, lineHeight: 1.5 }}>
                {t('activityDetail.powerAnalysis.cpDesc')}
              </div>
            </div>
          )}

          {/* Power zones */}
          {pwrZones && ftp && (
            <>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                {t('activityDetail.powerAnalysis.zonesBasedOnFtp')} <strong style={{ color: 'var(--text-primary)' }}>{ftp} W</strong>
              </div>
              <div className="hr-zones" style={{ marginBottom: 20 }}>
                {pwrZones.map(z => (
                  <div key={z.label} className="hr-zone-row">
                    <div className="hr-zone-label" style={{ color: z.color }}>{z.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', width: 120, flexShrink: 0 }}>{t(`activityDetail.powerAnalysis.powerZone.${z.nameKey}`)}</div>
                    <div className="hr-zone-bar-wrap">
                      <div className="hr-zone-bar" style={{ transform: `scaleX(${z.pct / 100})`, background: z.color }} />
                    </div>
                    <div className="hr-zone-pct">{z.pct}%</div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* MMP curve */}
          {mmp.length > 0 && (
            <>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                {t('activityDetail.powerAnalysis.mmpTitle')}
                {!ftp && <span style={{ opacity: 0.6 }}>{t('activityDetail.powerAnalysis.mmpSetFtp')}</span>}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: 8 }}>
                {mmp.map(({ label, secs, watts }) => {
                  const pct = ftp ? watts / ftp : null
                  const zone = pct ? POWER_ZONES.find(z => pct >= z.min && pct < z.max) : null
                  return (
                    <div key={label} style={{
                      background: 'var(--bg-secondary)', border: `1px solid ${zone ? zone.color + '40' : 'var(--border)'}`,
                      borderRadius: 8, padding: '10px 12px', textAlign: 'center',
                    }}>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 18, fontWeight: 800, color: zone ? zone.color : 'var(--power)', fontFamily: 'var(--font-display)' }}>{watts}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>W{ftp ? ` · ${(watts / ftp).toFixed(2)} IF` : ''}</div>
                    </div>
                  )
                })}
              </div>
            </>
          )}

          {/* Durability / Fatigue Resistance */}
          {durability && (
            <div style={{ marginTop: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>{t('activityDetail.powerAnalysis.durability.title')} <InfoTip text={t('activityDetail.powerAnalysis.durability.tip')} /></div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {t('activityDetail.powerAnalysis.durability.freshVsFatigued', { thresholdKj: durability.thresholdKj, totalKj: durability.totalKj })}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 32, fontWeight: 900, fontFamily: 'var(--font-display)', lineHeight: 1,
                    color: durability.score >= 80 ? 'var(--status-good)' : durability.score >= 60 ? 'var(--status-warn)' : 'var(--status-alert)' }}>
                    {durability.score}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{t('activityDetail.powerAnalysis.durability.scoreLabel')}</div>
                </div>
              </div>

              {/* Overlay chart: fresh vs fatigued MMP */}
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={durability.drops} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} unit="W" width={46} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-bright)', borderRadius: 6, fontSize: 12 }}
                    formatter={(v, name) => [`${v} W`, name]}
                  />
                  <Line type="monotone" dataKey="freshWatts"    stroke="var(--power)" strokeWidth={2} dot={false} name={t('activityDetail.powerAnalysis.durability.freshLabel')} />
                  <Line type="monotone" dataKey="fatiguedWatts" stroke="var(--heart)"  strokeWidth={2} dot={false} strokeDasharray="5 3" name={t('activityDetail.powerAnalysis.durability.fatiguedLabel')} />
                </LineChart>
              </ResponsiveContainer>

              {/* Drop table */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(90px, 1fr))', gap: 6, marginTop: 10 }}>
                {durability.drops.map(d => (
                  <div key={d.label} style={{ background: 'var(--bg-secondary)', border: `1px solid ${d.dropPct < 5 ? 'color-mix(in srgb, var(--status-good) 25%, transparent)' : d.dropPct < 12 ? 'color-mix(in srgb, var(--status-warn) 25%, transparent)' : 'color-mix(in srgb, var(--status-critical) 25%, transparent)'}`, borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3 }}>{d.label}</div>
                    <div style={{ fontSize: 16, fontWeight: 800, color: d.dropPct < 5 ? 'var(--status-good)' : d.dropPct < 12 ? 'var(--status-warn)' : 'var(--status-alert)', fontFamily: 'var(--font-display)' }}>
                      {d.dropPct > 0 ? '-' : '+'}{Math.abs(d.dropPct)}%
                    </div>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>{d.freshWatts}→{d.fatiguedWatts}W</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8 }}>
                {t('activityDetail.powerAnalysis.durability.avgDrop', { pct: durability.avgDrop })}
              </div>
            </div>
          )}

          {/* Power Quadrant */}
          {pwrQuadrant && (
            <div style={{ marginTop: 24 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{t('activityDetail.powerAnalysis.powerQuadrant.title')} <InfoTip text={t('activityDetail.powerAnalysis.powerQuadrant.tip')} /></div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
                {t('activityDetail.powerAnalysis.powerQuadrant.cadenceSplit', { rpm: pwrQuadrant.cadSplit, nm: pwrQuadrant.medTorque })}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {pwrQuadrant.grid.map((row, ri) =>
                  row.map(q => (
                    <div key={q.key} style={{
                      background: 'var(--bg-secondary)', border: `2px solid ${q.color}30`,
                      borderRadius: 10, padding: '14px 16px',
                    }}>
                      <div style={{ fontSize: 32, fontWeight: 900, color: q.color, fontFamily: 'var(--font-display)', lineHeight: 1 }}>{q.pct}%</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>{t(`activityDetail.powerAnalysis.powerQuadrant.${q.labelKey}`)}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{t(`activityDetail.powerAnalysis.powerQuadrant.${q.subKey}`)}</div>
                    </div>
                  ))
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
                <span>{t('activityDetail.powerAnalysis.powerQuadrant.highTorque')}</span><span>·</span>
                <span>{t('activityDetail.powerAnalysis.powerQuadrant.highCadence', { rpm: pwrQuadrant.cadSplit })}</span>
              </div>
            </div>
          )}

          {/* Nudge to set FTP if missing */}
          {!ftp && (
            <div style={{ marginTop: 14, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)' }}>
              {t('activityDetail.powerAnalysis.noFtpNudge')}
            </div>
          )}
        </div>
      )}

      {/* Adjusted Decoupling + VAM */}
      {(activity.decoupling_adjusted != null || hrDecoupling || vam) && (() => {
        const S_GOOD  = 'var(--status-good)'
        const S_WARN  = 'var(--status-warn)'
        const S_ALERT = 'var(--status-alert)'

        const adjVal   = activity.decoupling_adjusted
        const rawVal   = activity.decoupling_raw
        const quality  = activity.decoupling_quality
        const warning  = activity.decoupling_warning
        const components = (() => { try { return JSON.parse(activity.decoupling_components_json || 'null') } catch { return null } })()

        const adjColor     = adjVal == null ? 'var(--text-muted)' : adjVal < 5 ? S_GOOD : adjVal < 8 ? S_WARN : S_ALERT
        const qualityColor = quality === 'high' ? S_GOOD : quality === 'medium' ? S_WARN : 'var(--text-muted)'

        const infoText = adjVal != null
          ? t('activityDetail.aerobicMetrics.tipAdj')
          : t('activityDetail.aerobicMetrics.tipRaw')

        return (
          <div className="chart-section">
            <div className="chart-title">{t('activityDetail.aerobicMetrics.title')} <InfoTip text={infoText} /></div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10 }}>

              {/* Adjusted decoupling card — preferred over raw */}
              {adjVal != null ? (
                <div style={{ background: 'var(--bg-secondary)', border: `1px solid color-mix(in srgb, ${adjColor} 25%, transparent)`, borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{t('activityDetail.aerobicMetrics.adjustedDecoupling')}</div>
                    {quality && (
                      <span style={{ marginLeft: 'auto', padding: '1px 7px', borderRadius: 8, fontSize: 9, fontWeight: 700, background: `color-mix(in srgb, ${qualityColor} 10%, transparent)`, border: `1px solid color-mix(in srgb, ${qualityColor} 28%, transparent)`, color: qualityColor, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        {quality}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: adjColor, fontFamily: 'var(--font-display)' }}>
                    {adjVal > 0 ? '+' : ''}{adjVal.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                    {components?.category ?? (adjVal < 5 ? t('activityDetail.aerobicMetrics.goodAerobic') : adjVal < 8 ? t('activityDetail.aerobicMetrics.moderateDrift') : t('activityDetail.aerobicMetrics.significantDrift'))}
                    {' · '}{t('activityDetail.aerobicMetrics.wellConditioned')}
                  </div>
                  {/* Correction breakdown */}
                  {components && (
                    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                        <span>{t('activityDetail.aerobicMetrics.rawDrift')}</span>
                        <span style={{ fontFamily: 'var(--font-display)', color: 'var(--text-secondary)' }}>
                          {rawVal != null ? `${rawVal > 0 ? '+' : ''}${rawVal.toFixed(1)}%` : '—'}
                        </span>
                      </div>
                      {components.expected_heat_drift_pct > 0 && (
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                          <span>{t('activityDetail.aerobicMetrics.heatDrift')}</span>
                          <span style={{ fontFamily: 'var(--font-display)', color: 'var(--warning)' }}>
                            {components.expected_heat_drift_pct.toFixed(1)}%
                          </span>
                        </div>
                      )}
                      {components.expected_hydration_drift_pct > 0 && (
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                          <span>{t('activityDetail.aerobicMetrics.hydrationDrift')}</span>
                          <span style={{ fontFamily: 'var(--font-display)', color: 'oklch(65% 0.10 235)' }}>
                            {components.expected_hydration_drift_pct.toFixed(1)}%
                          </span>
                        </div>
                      )}
                      {components.flat_minutes_analyzed != null && (
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                          {t('activityDetail.aerobicMetrics.flatMinutes', { min: components.flat_minutes_analyzed })}
                        </div>
                      )}
                    </div>
                  )}
                  {warning && (
                    <div style={{ marginTop: 8, padding: '6px 8px', borderRadius: 6, background: 'color-mix(in srgb, var(--status-warn) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--status-warn) 30%, transparent)', fontSize: 10, color: 'var(--status-warn)', lineHeight: 1.4 }}>
                      ⚠ {warning}
                    </div>
                  )}
                </div>
              ) : hrDecoupling ? (
                <div style={{ background: 'var(--bg-secondary)', border: `1px solid color-mix(in srgb, ${hrDecoupling.aerobic ? 'var(--status-good)' : 'var(--status-alert)'} 25%, transparent)`, borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>{hrDecoupling.label} {t('activityDetail.aerobicMetrics.decoupling')}</div>
                  <div style={{ fontSize: 26, fontWeight: 800, color: hrDecoupling.aerobic ? 'var(--status-good)' : 'var(--status-alert)', fontFamily: 'var(--font-display)' }}>
                    {hrDecoupling.pct > 0 ? '+' : ''}{hrDecoupling.pct}%
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                    {hrDecoupling.aerobic ? t('activityDetail.aerobicMetrics.goodAerobic') : t('activityDetail.aerobicMetrics.aerobicDrift')}
                    {' · '}{t('activityDetail.aerobicMetrics.wellConditioned')}
                  </div>
                </div>
              ) : null}

              {vam && (
                <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>VAM</div>
                  <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--elevation)', fontFamily: 'var(--font-display)' }}>
                    {vam.toLocaleString()} <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-muted)' }}>m/h</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                    {t('activityDetail.aerobicMetrics.vamDesc')}
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      {/* HR Zones */}
      {hrZones && (
        <div className="chart-section">
          <div className="chart-title">{t('activityDetail.hrZones.title')} <InfoTip text={t('activityDetail.hrZones.tip')} /></div>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 14 }}>
            {t('activityDetail.hrZones.basedOnMaxHr', { bpm: Math.round(activity.max_heart_rate_bpm) })}
          </p>
          <div className="hr-zones">
            {hrZones.map(z => (
              <div key={z.key} className="hr-zone-row">
                <div className="hr-zone-label" style={{ color: z.color }}>{t(`activityDetail.hrZones.${z.key}`)}</div>
                <div className="hr-zone-bar-wrap">
                  <div className="hr-zone-bar" style={{ transform: `scaleX(${z.pct / 100})`, background: z.color }} />
                </div>
                <div className="hr-zone-pct">{z.pct}%</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Cadence Zones */}
      {cadZones && (
        <div className="chart-section">
          <div className="chart-title">{t('activityDetail.cadenceZones.title')} <InfoTip text={t('activityDetail.cadenceZones.tip')} /></div>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 14 }}>
            {t('activityDetail.cadenceZones.optimalRange', { avg: Math.round(activity.avg_cadence_rpm) })}
          </p>
          <div className="hr-zones">
            {cadZones.map(z => (
              <div key={z.key} className="hr-zone-row">
                <div className="hr-zone-label" style={{ color: z.color }}>{t(`activityDetail.cadenceZones.${z.key}`)}</div>
                <div className="hr-zone-bar-wrap">
                  <div className="hr-zone-bar" style={{ transform: `scaleX(${z.pct / 100})`, background: z.color }} />
                </div>
                <div className="hr-zone-pct">{z.pct}%</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hydration & Heat Analysis */}
      {hydration && (() => {
        const S_GOOD     = 'var(--status-good)'
        const S_WARN     = 'var(--status-warn)'
        const S_ALERT    = 'var(--status-alert)'
        const S_CRITICAL = 'var(--status-critical)'
        const RISK_COLOR = { low: S_GOOD, moderate: S_WARN, high: S_ALERT, critical: S_CRITICAL }
        const riskColor  = RISK_COLOR[hydration.risk_level] || 'var(--text-muted)'
        const recs       = (() => { try { return JSON.parse(hydration.recommendations_json || '[]') } catch { return [] } })()
        const sweatL     = (hydration.estimated_total_sweat_ml / 1000).toFixed(1)
        const intakeL    = hydration.reported_intake_ml != null ? (hydration.reported_intake_ml / 1000).toFixed(1) : null
        const deficitL   = hydration.deficit_ml != null ? (hydration.deficit_ml / 1000).toFixed(1) : null
        const targetMlH  = Math.round(hydration.estimated_sweat_rate_ml_h * 0.75)
        const qualColor  = { high: S_GOOD, medium: S_WARN }
        const isCalibrated = hydration.model_method === 'calibrated'
        const hasWindCooling = hydration.wind_cooling_c != null && hydration.wind_cooling_c > 0
        const showSources = showHydrationSources
        const setShowSources = setShowHydrationSources

        return (
          <div className="chart-section">
            <div className="chart-title" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Droplets size={14} style={{ color: 'var(--text-secondary)' }} />
              {t('activityDetail.hydration.title')}
              <InfoTip text={t('activityDetail.hydration.tip')} />
              <span style={{ marginLeft: 'auto', padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700, background: `color-mix(in srgb, ${riskColor} 12%, transparent)`, border: `1px solid color-mix(in srgb, ${riskColor} 35%, transparent)`, color: riskColor, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {t('activityDetail.hydration.riskLabel', { level: hydration.risk_level })}
              </span>
            </div>

            {/* Primary metrics */}
            <div style={{ display: 'flex', gap: 32, marginBottom: 16, flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 4 }}>{t('activityDetail.hydration.estSweatLoss')}</div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, color: S_WARN, lineHeight: 1 }}>{sweatL} L</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>{t('activityDetail.hydration.sweatRate', { rate: Math.round(hydration.estimated_sweat_rate_ml_h) })}</div>
                {isCalibrated && hydration.population_sweat_rate_ml_h && (
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                    {t('activityDetail.hydration.genericModel', { rate: Math.round(hydration.population_sweat_rate_ml_h) })}
                  </div>
                )}
              </div>
              {intakeL != null && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 4 }}>{t('activityDetail.hydration.fluidIntake')}</div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, color: S_GOOD, lineHeight: 1 }}>{intakeL} L</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>{t('activityDetail.hydration.logged')}</div>
                </div>
              )}
              {deficitL != null && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 4 }}>{t('activityDetail.hydration.deficit')}</div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, color: riskColor, lineHeight: 1 }}>{deficitL} L</div>
                  {hydration.deficit_body_pct != null && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>{t('activityDetail.hydration.deficitBodyPct', { pct: hydration.deficit_body_pct })}</div>}
                </div>
              )}
            </div>

            {/* Secondary conditions row */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>
              <span>{t('activityDetail.hydration.target')} <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-display)' }}>{targetMlH} ml/h</strong></span>
              {hydration.humidity_pct != null && (
                <span>
                  {t('activityDetail.hydration.conditions')} <strong style={{ color: 'var(--text-primary)' }}>
                    {hydration.avg_temperature_c}°C
                    {hasWindCooling && <span style={{ color: 'var(--text-muted)' }}> {t('activityDetail.hydration.windCoolingFelt', { temp: hydration.effective_temp_c })}</span>}
                    {' · '}{hydration.humidity_pct}% RH
                  </strong>
                </span>
              )}
              <span>
                {t('activityDetail.hydration.model')} <strong style={{ color: isCalibrated ? S_GOOD : 'var(--text-muted)' }}>
                  {isCalibrated ? t('activityDetail.hydration.personal') : t('activityDetail.hydration.population')}
                </strong>
              </span>
            </div>

            {/* Calculation sources accordion */}
            <button
              onClick={() => setShowSources(v => !v)}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, padding: '4px 0', marginBottom: showSources ? 8 : 12, letterSpacing: '0.04em' }}
            >
              {showSources ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {t('activityDetail.hydration.howCalculated')}
            </button>
            {showSources && (
              <div style={{ marginBottom: 12, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 11, lineHeight: 1.7 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 12, rowGap: 2 }}>
                  <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{t('activityDetail.hydration.sourceTemp')}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {t('activityDetail.hydration.sourceTempValue', { raw: hydration.avg_temperature_c })}
                    {hasWindCooling && t('activityDetail.hydration.sourceTempWind', { eff: hydration.effective_temp_c, cooling: hydration.wind_cooling_c })}
                  </span>

                  {hydration.wind_speed_kmh != null && (
                    <>
                      <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{t('activityDetail.hydration.sourceWind')}</span>
                      <span style={{ color: 'var(--text-secondary)' }}>{t('activityDetail.hydration.sourceWindValue', { speed: hydration.wind_speed_kmh })}</span>
                    </>
                  )}

                  <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{t('activityDetail.hydration.sourceSweatModel')}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {isCalibrated
                      ? t('activityDetail.hydration.sourceSweatCalibrated', { rate: Math.round(hydration.estimated_sweat_rate_ml_h) })
                      : t('activityDetail.hydration.sourceSweatPopulation', { rate: Math.round(hydration.estimated_sweat_rate_ml_h) })
                    }
                  </span>

                  {isCalibrated && hydration.population_sweat_rate_ml_h && (
                    <>
                      <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{t('activityDetail.hydration.sourceReference')}</span>
                      <span style={{ color: 'var(--text-secondary)' }}>
                        {t('activityDetail.hydration.sourceReferenceValue', { rate: Math.round(hydration.population_sweat_rate_ml_h) })}
                        {Math.abs(hydration.estimated_sweat_rate_ml_h - hydration.population_sweat_rate_ml_h) > 300 &&
                          t('activityDetail.hydration.sourceReferenceLargeGap')}
                      </span>
                    </>
                  )}

                  <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{t('activityDetail.hydration.sourceQuality')}</span>
                  <span style={{ color: qualColor[hydration.analysis_quality] ?? 'var(--text-muted)' }}>
                    {hydration.analysis_quality.charAt(0).toUpperCase() + hydration.analysis_quality.slice(1)}
                    {!isCalibrated && hydration.analysis_quality !== 'high' && t('activityDetail.hydration.noSweatTestNote')}
                  </span>
                </div>
              </div>
            )}

            {/* HR & performance impact */}
            {(hydration.estimated_hr_drift_heat_bpm > 0 || hydration.estimated_hr_drift_dehydration_bpm != null) && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
                {hydration.estimated_hr_drift_heat_bpm > 0 && (
                  <div style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {t('activityDetail.hydration.hrDriftHeat')} <strong style={{ color: 'var(--status-warn)', fontFamily: 'var(--font-display)' }}>+{hydration.estimated_hr_drift_heat_bpm} bpm</strong>
                  </div>
                )}
                {hydration.estimated_hr_drift_dehydration_bpm != null && (
                  <div style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {t('activityDetail.hydration.hrDriftDehydration')} <strong style={{ color: riskColor, fontFamily: 'var(--font-display)' }}>+{hydration.estimated_hr_drift_dehydration_bpm} bpm</strong>
                  </div>
                )}
                {hydration.estimated_performance_loss_pct != null && hydration.estimated_performance_loss_pct > 0 && (
                  <div style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {t('activityDetail.hydration.performanceImpact')} <strong style={{ color: 'var(--status-critical)', fontFamily: 'var(--font-display)' }}>−{hydration.estimated_performance_loss_pct}%</strong>
                  </div>
                )}
              </div>
            )}

            {/* Log intake */}
            <div style={{ padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
                {hydration.reported_intake_ml != null ? t('activityDetail.hydration.logIntakeUpdate') : t('activityDetail.hydration.logIntakeNew')}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  type="number" min={0} max={20000} step={50}
                  value={intakeInput}
                  onChange={e => setIntakeInput(e.target.value)}
                  placeholder={t('activityDetail.hydration.intakePlaceholder')}
                  aria-label={t('activityDetail.hydration.intakeAriaLabel')}
                  className="filter-input"
                  style={{ width: 110, padding: '6px 10px', fontSize: 13 }}
                />
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('activityDetail.hydration.intakeMl')}</span>
                <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={handleLogIntake} disabled={intakeSaving}>
                  {intakeSaving ? t('activityDetail.hydration.savingIntake') : t('activityDetail.hydration.saveIntake')}
                </button>
                {intakeMsg && <span style={{ fontSize: 12, color: intakeMsg === 'saved' ? 'var(--status-good)' : 'var(--status-alert)' }}>
                  {intakeMsg === 'saved' ? t('activityDetail.hydration.intakeMsgSaved') : intakeMsg === 'range' ? t('activityDetail.hydration.intakeMsgRange') : t('activityDetail.hydration.intakeMsgFailed')}
                </span>}
              </div>
            </div>

            {/* Recommendations */}
            {recs.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>{t('activityDetail.hydration.recommendations')}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {recs.map((rec, i) => {
                    const text = typeof rec === 'string'
                      ? rec
                      : t(`activityDetail.hydration.rec.${rec.key}`, rec)
                    return (
                      <div key={i} style={{ display: 'flex', gap: 10, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, padding: '7px 12px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
                        <Droplets size={13} style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: 1 }} />
                        {text}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {/* Durability Analysis */}
      {(() => {
        const DUR_COLORS = { excellent: 'var(--status-good)', good: 'oklch(65% 0.10 235)', moderate: 'var(--status-warn)', poor: 'var(--status-alert)', very_poor: 'var(--status-critical)' }
        const catColor = durabilityData?.durability_category ? (DUR_COLORS[durabilityData.durability_category] ?? 'var(--text-primary)') : 'var(--text-muted)'
        const methodLabel = {
          power: t('activityDetail.durabilityIndex.method.power'),
          hr_speed: t('activityDetail.durabilityIndex.method.hr_speed'),
          climbing_power: t('activityDetail.durabilityIndex.method.climbing_power'),
        }
        const unitLabel = {
          speed_hr_ratio: 'km/h÷bpm',
          W: 'W',
          watts: 'W',
        }

        if (durabilityLoading) return (
          <div className="chart-section">
            <div className="chart-title">{t('activityDetail.durabilityIndex.title')}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 13, padding: '12px 0' }}>
              <div className="spinner" style={{ width: 16, height: 16 }} /> {t('activityDetail.durabilityIndex.analysing')}
            </div>
          </div>
        )

        if (!durabilityData) return (
          <div className="chart-section">
            <div className="chart-title">{t('activityDetail.durabilityIndex.title')}</div>
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              {t('activityDetail.durabilityIndex.notAvailable')}
            </p>
          </div>
        )

        const quarters = [
          { label: 'Q1', value: durabilityData.q1_output },
          { label: 'Q2', value: durabilityData.q2_output },
          { label: 'Q3', value: durabilityData.q3_output },
          { label: 'Q4', value: durabilityData.q4_output },
        ].filter(q => q.value != null)

        const unit = durabilityData.output_unit ?? ''
        const displayUnit = unitLabel[unit] ?? unit

        return (
          <div className="chart-section">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <div className="chart-title" style={{ marginBottom: 0 }}>{t('activityDetail.durabilityIndex.title')}</div>
                {durabilityData.durability_category && (
                  <span style={{ fontSize: 11, fontWeight: 600, color: catColor, textTransform: 'capitalize', paddingBottom: 1 }}>
                    {durabilityData.durability_category.replace('_', ' ')}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700, color: catColor, lineHeight: 1 }}>
                  {durabilityData.durability_index != null ? durabilityData.durability_index.toFixed(1) : '—'}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>/ 100</span>
                {durabilityData.quality && (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, padding: '2px 8px', marginLeft: 6 }}>
                    {durabilityData.quality === 'good' ? t('activityDetail.durabilityIndex.qualityGood') : durabilityData.quality === 'fair' ? t('activityDetail.durabilityIndex.qualityFair') : durabilityData.quality}
                  </span>
                )}
              </div>
            </div>

            {/* Quarter bar chart */}
            {quarters.length === 4 && (
              <div style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
                  {t('activityDetail.durabilityIndex.outputPerQuarter', { unit: displayUnit })}
                </div>
                <ResponsiveContainer width="100%" height={120}>
                  <BarChart data={quarters} barCategoryGap="30%">
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip
                      content={({ active, payload }) => active && payload?.length ? (
                        <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-bright)', borderRadius: 6, padding: '6px 10px', fontSize: 12 }}>
                          <span style={{ fontFamily: 'var(--font-display)', fontSize: 15, color: catColor }}>{payload[0].value?.toFixed(1)}</span>
                          <span style={{ color: 'var(--text-muted)', marginLeft: 4 }}>{displayUnit}</span>
                        </div>
                      ) : null}
                    />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {quarters.map((q, i) => (
                        <Cell key={q.label} fill={i === 0 ? catColor : `color-mix(in srgb, ${catColor} ${Math.round(100 - i * 15)}%, var(--bg-secondary))`} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Context row */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>
              {durabilityData.fade_rate_pct_per_hour != null && (
                <span>{t('activityDetail.durabilityIndex.fadeRate')} <strong style={{ color: durabilityData.fade_rate_pct_per_hour > 10 ? 'var(--warning)' : 'var(--text-primary)' }}>{durabilityData.fade_rate_pct_per_hour.toFixed(1)}%/h</strong></span>
              )}
              {durabilityData.total_work_kj != null && (
                <span>{t('activityDetail.durabilityIndex.work')} <strong style={{ color: 'var(--text-primary)' }}>{Math.round(durabilityData.total_work_kj)} kJ</strong></span>
              )}
              {durabilityData.tsb_at_start != null && (
                <span>{t('activityDetail.durabilityIndex.tsbAtStart')} <strong style={{ color: durabilityData.tsb_at_start >= 5 ? 'var(--status-good)' : durabilityData.tsb_at_start <= -20 ? 'var(--status-critical)' : 'var(--text-primary)' }}>{durabilityData.tsb_at_start > 0 ? '+' : ''}{durabilityData.tsb_at_start.toFixed(0)}</strong></span>
              )}
              {durabilityData.temperature_avg_c != null && (
                <span>{t('activityDetail.durabilityIndex.avgTemp')} <strong style={{ color: 'var(--text-primary)' }}>{durabilityData.temperature_avg_c.toFixed(0)}°C</strong></span>
              )}
              <span style={{ color: 'var(--text-muted)' }}>{t('activityDetail.durabilityIndex.via')} {methodLabel[durabilityData.method] ?? durabilityData.method}</span>
            </div>

            {durabilityData.quality_reason && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '8px 12px', background: 'var(--bg-secondary)', borderRadius: 6, border: '1px solid var(--border)' }}>
                {durabilityData.quality_reason}
              </div>
            )}
          </div>
        )
      })()}

      {/* Segments */}
      {segmentEfforts.length > 0 && (
        <div className="chart-section">
          <div className="chart-title">{t('activityDetail.segments.title')}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
            {segmentEfforts.map(e => {
              const s = Math.round(e.elapsed_seconds)
              const m = Math.floor(s / 60), sec = s % 60
              const time = `${m}:${String(sec).padStart(2, '0')}`
              return (
                <div key={e.id} className="segment-effort-row">
                  <div style={{ flex: 1 }}>
                    <span style={{ fontWeight: 600 }}>{e.segment_name}</span>
                    {e.is_pr && <span className="badge badge-fit" style={{ marginLeft: 8 }}>PR</span>}
                  </div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: e.is_pr ? 'var(--accent)' : 'var(--text-primary)' }}>{time}</div>
                  {e.avg_speed_kmh && <div style={{ color: 'var(--speed)', fontSize: 13, minWidth: 80, textAlign: 'right' }}>{e.avg_speed_kmh} km/h</div>}
                  {e.avg_hr && <div style={{ color: 'var(--heart)', fontSize: 13, minWidth: 70, textAlign: 'right' }}>{Math.round(e.avg_hr)} bpm</div>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Climbs */}
      {(climbs.length > 0 || !weightKg) && (
        <div className="chart-section">
          <div className="chart-title" style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <TrendingUp size={14} style={{ color: 'var(--accent)' }} />
            {t('activityDetail.climbs.title')}
            {climbs.length > 0 && (
              <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 4 }}>
                {t('activityDetail.climbs.count', { count: climbs.length })}
              </span>
            )}
          </div>

          {!weightKg && (
            <div style={{ padding: '10px 14px', borderRadius: 8, background: 'color-mix(in srgb, var(--accent) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--accent) 20%, transparent)', fontSize: 13, color: 'var(--text-secondary)', marginBottom: climbs.length ? 14 : 0 }}>
              {t('activityDetail.climbs.addWeightPrompt')} <a href="/settings" style={{ color: 'var(--accent)' }}>{t('activityDetail.climbs.addWeightSettings')}</a> {t('activityDetail.climbs.addWeightSuffix')}
            </div>
          )}

          {climbs.length > 0 && (
            <div role="list" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {climbs.map((c, i) => {
                const expanded = expandedClimb === c.id
                const qColor = c.estimation_quality === 'high' ? 'var(--status-good)' : c.estimation_quality === 'medium' ? 'var(--status-warn)' : 'var(--status-alert)'
                const pacingLabel = c.pacing_type === 'negative' ? t('activityDetail.climbs.pacingNegative') : c.pacing_type === 'positive' ? t('activityDetail.climbs.pacingPositive') : c.pacing_type === 'even' ? t('activityDetail.climbs.pacingEven') : null
                const mins = Math.floor((c.duration_seconds || 0) / 60)
                const secs = (c.duration_seconds || 0) % 60
                return (
                  <div key={c.id} role="listitem" style={{ border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
                    <button
                      onClick={() => setExpandedClimb(expanded ? null : c.id)}
                      aria-expanded={expanded}
                      aria-controls={`climb-detail-${c.id}`}
                      className="climb-accordion-btn"
                      style={{ width: '100%', background: 'var(--bg-secondary)', border: 'none', cursor: 'pointer', padding: '12px 14px', textAlign: 'left' }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                          <span style={{ fontWeight: 600, fontSize: 14 }}>{t('activityDetail.climbs.climbLabel', { num: i + 1 })}</span>
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{((c.distance_m || 0) / 1000).toFixed(1)} km</span>
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{(c.avg_gradient_pct || 0).toFixed(1)}% avg</span>
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{mins}:{String(secs).padStart(2, '0')}</span>
                          {c.vam_m_per_hour != null && (
                            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>VAM {Math.round(c.vam_m_per_hour)} m/h</span>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                          {c.estimation_quality && (
                            <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 10, background: `color-mix(in srgb, ${qColor} 10%, transparent)`, border: `1px solid color-mix(in srgb, ${qColor} 25%, transparent)`, color: qColor, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                              {c.estimation_quality}
                            </span>
                          )}
                          {expanded ? <ChevronUp size={14} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} />}
                        </div>
                      </div>

                      {c.estimated_power_w != null && (
                        <div style={{ display: 'flex', gap: 16, marginTop: 8, flexWrap: 'wrap' }}>
                          <span style={{ fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--accent)' }}>
                            {Math.round(c.estimated_power_w)}W
                          </span>
                          {c.estimated_power_low_w != null && c.estimated_power_high_w != null && (
                            <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'flex-end', paddingBottom: 2 }}>
                              ({Math.round(c.estimated_power_low_w)}–{Math.round(c.estimated_power_high_w)}W range)
                            </span>
                          )}
                          {c.estimated_wkg != null && (
                            <span style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--text-secondary)', alignSelf: 'flex-end', paddingBottom: 1 }}>
                              {c.estimated_wkg.toFixed(2)} W/kg
                            </span>
                          )}
                        </div>
                      )}
                    </button>

                    {expanded && (
                      <div id={`climb-detail-${c.id}`} style={{ padding: '12px 14px', borderTop: '1px solid var(--border)', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
                        <div>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.climbs.elevationGain')}</div>
                          <div style={{ fontFamily: 'var(--font-display)', fontSize: 16 }}>{Math.round(c.elevation_gain_m || 0)} m</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.climbs.maxGradient')}</div>
                          <div style={{ fontFamily: 'var(--font-display)', fontSize: 16 }}>{(c.max_gradient_pct || 0).toFixed(1)}%</div>
                        </div>
                        {c.avg_speed_kmh != null && (
                          <div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.climbs.avgSpeed')}</div>
                            <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--speed)' }}>{c.avg_speed_kmh.toFixed(1)} km/h</div>
                          </div>
                        )}
                        {c.avg_heart_rate != null && (
                          <div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.climbs.avgHr')}</div>
                            <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--heart)' }}>{c.avg_heart_rate} bpm</div>
                          </div>
                        )}
                        {c.max_heart_rate != null && (
                          <div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.climbs.maxHr')}</div>
                            <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--heart)' }}>{c.max_heart_rate} bpm</div>
                          </div>
                        )}
                        {pacingLabel && (
                          <div style={{ gridColumn: '1 / -1' }}>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('activityDetail.climbs.pacing')}</div>
                            <div style={{ fontSize: 13, color: c.pacing_type === 'negative' ? 'var(--status-good)' : c.pacing_type === 'positive' ? 'var(--status-alert)' : 'var(--text-secondary)' }}>
                              {pacingLabel}
                            </div>
                          </div>
                        )}
                        {c.estimation_method && (
                          <div style={{ gridColumn: '1 / -1', fontSize: 11, color: 'var(--text-muted)', paddingTop: 4, borderTop: '1px solid var(--border)' }}>
                            {c.estimation_method === 'calibrated' ? t('activityDetail.climbs.powerEstimatedCalibrated') : t('activityDetail.climbs.powerEstimated')}. {t('activityDetail.climbs.notMeasured')}
                            {' '}Climb ID: <code style={{ fontFamily: 'monospace', background: 'var(--bg-primary)', padding: '1px 4px', borderRadius: 3 }}>{c.id}</code>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* AI Analysis */}
      <div className="chart-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <div className="chart-title" style={{ marginBottom: 0 }}>
            <Sparkles size={14} style={{ display: 'inline', marginRight: 6, color: 'var(--accent)' }} />
            {t('activityDetail.aiAnalysis.title')}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {analysis && !analysisLoading && (
              <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 12 }} onClick={handleRegenerateAnalysis}>
                <RefreshCw size={12} /> {t('activityDetail.aiAnalysis.regenerate')}
              </button>
            )}
            {!analysis && !analysisLoading && (
              <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 13 }} onClick={handleAnalyse}>
                <Sparkles size={13} /> {t('activityDetail.aiAnalysis.analyseRide')}
              </button>
            )}
          </div>
        </div>

        {analysisError && (
          <div className="alert alert-error">{analysisError}</div>
        )}

        {/* Skeleton: initial loading before first token arrives */}
        {analysisLoading && !analysis && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9, maxWidth: '72ch' }}>
            {[0.95, 0.88, 0.72, 0.97, 0.82, 0.60, 0.91, 0.75, 0.46].map((w, i) => (
              <div key={i} className="analysis-skel-line" style={{ width: `${w * 100}%`, animationDelay: `${i * 80}ms` }} />
            ))}
          </div>
        )}

        {/* Streaming: plain text with cursor while tokens arrive */}
        {analysisLoading && analysis && (
          <p style={{ margin: 0, maxWidth: '72ch', fontSize: 14, lineHeight: 1.78, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
            {analysis.replace(/^#[^\n]*\n?/m, '')}
            <span className="analysis-cursor">▌</span>
          </p>
        )}

        {/* Rich view: structured paragraphs with metric highlighting */}
        {!analysisLoading && analysis && (
          <AnalysisRenderer text={analysis} />
        )}

        {/* Empty state */}
        {!analysis && !analysisLoading && !analysisError && (
          <div style={{ textAlign: 'center', padding: '28px 0 20px' }}>
            <Sparkles size={20} style={{ color: 'var(--text-muted)', opacity: 0.35, display: 'block', margin: '0 auto 10px' }} />
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>
              {t('activityDetail.aiAnalysis.prompt')}
            </p>
          </div>
        )}
      </div>

      {/* Notes */}
      <div className="chart-section">
        <div className="chart-title">{t('activityDetail.notes.title')}</div>
        <textarea
          className="notes-textarea"
          placeholder={t('activityDetail.notes.placeholder')}
          value={notes}
          onChange={e => handleNotesChange(e.target.value)}
          rows={4}
        />
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
          {t('activityDetail.notes.autoSaved')} <a href="/privacy" style={{ color: 'var(--text-muted)', textDecoration: 'underline' }}>{t('activityDetail.notes.privacyPolicy')}</a>.
        </div>
      </div>
    </div>
  )
}
