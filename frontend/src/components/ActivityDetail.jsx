import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { getActivity, deleteActivity, renameActivity, exportCsv, exportGpx, updateNotes, getActivitySegments, getAnalysis, clearAnalysis, getSettings, getHydrationAnalysis, updateHydrationIntake } from '../services/api'
import { format } from 'date-fns'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid
} from 'recharts'
import { MapContainer, TileLayer, Polyline } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { ArrowLeft, Trash2, Pencil, Download, FileText, Cloud, Wind, Thermometer, Sparkles, RefreshCw, Droplets } from 'lucide-react'
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

function downsample(arr, maxPoints = 500) {
  if (arr.length <= maxPoints) return arr
  const step = Math.ceil(arr.length / maxPoints)
  return arr.filter((_, i) => i % step === 0)
}

const CAD_ZONES = [
  { label: 'Very Low',  max: 60,       color: '#8888aa' },
  { label: 'Low',       max: 75,       color: '#4da6ff' },
  { label: 'Optimal',   max: 90,       color: '#6dffb8' },
  { label: 'High',      max: 100,      color: '#ffd93d' },
  { label: 'Very High', max: Infinity, color: '#ff8c42' },
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
  { label: 'Z1 Recovery',   min: 0,    max: 0.60, color: '#6dffb8' },
  { label: 'Z2 Endurance',  min: 0.60, max: 0.70, color: '#4da6ff' },
  { label: 'Z3 Tempo',      min: 0.70, max: 0.80, color: '#ffd93d' },
  { label: 'Z4 Threshold',  min: 0.80, max: 0.90, color: '#ff8c42' },
  { label: 'Z5 VO2 Max',    min: 0.90, max: 1.00, color: '#ff4d6d' },
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

// ── Power analysis ────────────────────────────────────────────────────────────

const POWER_ZONES = [
  { label: 'Z1', name: 'Active Recovery',  min: 0,    max: 0.55,     color: '#6dffb8' },
  { label: 'Z2', name: 'Endurance',        min: 0.55, max: 0.75,     color: '#4da6ff' },
  { label: 'Z3', name: 'Tempo',            min: 0.75, max: 0.90,     color: '#ffd93d' },
  { label: 'Z4', name: 'Threshold',        min: 0.90, max: 1.05,     color: '#ff8c42' },
  { label: 'Z5', name: 'VO2 Max',          min: 1.05, max: 1.20,     color: '#ff4d6d' },
  { label: 'Z6', name: 'Anaerobic',        min: 1.20, max: 1.50,     color: '#c084fc' },
  { label: 'Z7', name: 'Neuromuscular',    min: 1.50, max: Infinity, color: 'oklch(98% 0.005 142)' },
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
      [{ key: 'Q3', label: 'Strength',     sub: 'Low cad · High torque', pct: pct(q3), color: '#ffd93d', count: q3 },
       { key: 'Q2', label: 'Sprint Power', sub: 'High cad · High torque', pct: pct(q2), color: '#ff4d6d', count: q2 }],
      [{ key: 'Q4', label: 'Recovery',     sub: 'Low cad · Low torque',   pct: pct(q4), color: '#6dffb8', count: q4 },
       { key: 'Q1', label: 'Aerobic Spin', sub: 'High cad · Low torque',  pct: pct(q1), color: '#4da6ff', count: q1 }],
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
  const [hydration, setHydration] = useState(null)
  const [intakeInput,  setIntakeInput]  = useState('')
  const [intakeSaving, setIntakeSaving] = useState(false)
  const [intakeMsg,    setIntakeMsg]    = useState('')
  const notesTimer = useRef(null)

  useEffect(() => {
    getActivity(id)
      .then(r => {
        setActivity(r.data)
        setNewName(r.data.name)
        setNotes(r.data.notes ?? '')
      })
      .catch(() => setError('Activity not found'))
      .finally(() => setLoading(false))
    getActivitySegments(id).then(r => setSegmentEfforts(r.data)).catch(() => {})
    getAnalysis(id).then(r => setAnalysis(r.data.analysis)).catch(() => {})
    getSettings().then(r => {
      setFtp(r.data.ftp || null)
      setWeightKg(r.data.weight_kg || null)
    }).catch(() => {})
    getHydrationAnalysis(id).then(r => {
      setHydration(r.data)
      setIntakeInput(r.data.reported_intake_ml != null ? String(r.data.reported_intake_ml) : '')
    }).catch(() => {})
  }, [id])

  const handleDelete = async () => {
    if (!confirm('Delete this activity?')) return
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
    try {
      const res = await getAnalysis(id)
      setAnalysis(res.data.analysis)
    } catch (e) {
      setAnalysisError(e.response?.data?.detail || 'Failed to generate analysis')
    } finally {
      setAnalysisLoading(false)
    }
  }

  const handleClearAnalysis = async () => {
    await clearAnalysis(id).catch(() => {})
    setAnalysis(null)
  }

  const handleLogIntake = async () => {
    const ml = parseInt(intakeInput, 10)
    if (isNaN(ml) || ml < 0 || ml > 20000) { setIntakeMsg('Enter a value between 0 and 20 000 ml.'); return }
    setIntakeSaving(true); setIntakeMsg('')
    try {
      const res = await updateHydrationIntake(id, ml)
      setHydration(res.data)
      setIntakeMsg('Saved.')
      setTimeout(() => setIntakeMsg(''), 2500)
    } catch { setIntakeMsg('Failed to save intake.') }
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

  if (loading) return <div className="loading-center"><div className="spinner" /></div>
  if (error) return <div className="empty-state"><h3>{error}</h3></div>

  const { track_points: pts, laps } = activity
  const mapPoints = pts.filter(p => p.lat && p.lon).map(p => [p.lat, p.lon])
  const center = mapPoints.length > 0 ? mapPoints[Math.floor(mapPoints.length / 2)] : [38.5, -9.0]

  const chartData = downsample(
    pts.filter(p => p.distance_m != null).map(p => ({
      d: Math.round(p.distance_m),
      speed: p.speed_kmh,
      hr: p.heart_rate_bpm,
      cad: p.cadence_rpm,
      ele: p.elevation,
      pwr: p.power_w,
    }))
  )

  const hasHR  = pts.some(p => p.heart_rate_bpm != null)
  const hasCad = pts.some(p => p.cadence_rpm != null)
  const hasEle = pts.some(p => p.elevation != null)
  const hasPwr = pts.some(p => p.power_w != null)
  const hasWeather = activity.weather_temp_c != null || activity.weather_desc

  const hrZones  = hasHR  ? computeHrZones(pts, activity.max_heart_rate_bpm) : null
  const cadZones = hasCad ? computeCadenceZones(pts) : null
  const efforts  = computeBestEfforts(pts)

  // Power analysis — only meaningful with power data
  const np       = hasPwr ? computeNP(pts) : null
  const pwrZones = hasPwr ? computePowerZones(pts, ftp) : null
  const mmp      = hasPwr ? computeMMP(pts) : []
  const cpModel  = mmp.length >= 2 ? fitCPModel(mmp) : null
  const eFtp     = estimateFTP(mmp)
  const ifVal    = np && ftp ? (np / ftp).toFixed(2) : null
  const tss      = np && ftp && activity.duration_seconds
    ? Math.round((activity.duration_seconds * np * (np / ftp)) / (ftp * 3600) * 100)
    : null
  const wPerKg   = np && weightKg ? (np / weightKg).toFixed(2) : null

  // HR Decoupling and VAM — available even without power
  const hrDecoupling = (hasHR && activity.duration_seconds > 900) ? computeHRDecoupling(pts) : null
  const vam          = hasEle ? computeVAM(pts) : null

  // Advanced power metrics
  const durability   = hasPwr ? computeDurability(pts) : null
  const pwrQuadrant  = hasPwr ? computePowerQuadrant(pts) : null

  // Auto split distance based on ride length if user hasn't picked one
  const autoSplitKm = activity.distance_km >= 50 ? 10 : activity.distance_km >= 15 ? 5 : 1
  const activeSplitKm = splitKm ?? autoSplitKm
  const splits = computeSplits(pts, activeSplitKm)
  const SPLITS_PREVIEW = 8

  const metrics = [
    { label: 'Distance', value: `${activity.distance_km.toFixed(2)}`, unit: 'km', color: 'var(--accent)' },
    { label: 'Moving Time', value: fmtDuration(activity.duration_seconds), unit: '', color: 'var(--text-primary)' },
    ...(activity.suffer_score != null ? [{ label: 'Suffer Score', value: activity.suffer_score, unit: '', color: 'var(--heart)' }] : []),
    { label: 'Avg Speed', value: activity.avg_speed_kmh.toFixed(1), unit: 'km/h', color: 'var(--speed)' },
    { label: 'Max Speed', value: activity.max_speed_kmh.toFixed(1), unit: 'km/h', color: 'var(--speed)' },
    ...(hasHR ? [
      { label: 'Avg HR', value: Math.round(activity.avg_heart_rate_bpm), unit: 'bpm', color: 'var(--heart)' },
      { label: 'Max HR', value: Math.round(activity.max_heart_rate_bpm), unit: 'bpm', color: 'var(--heart)' },
    ] : []),
    ...(hasCad ? [
      { label: 'Avg Cadence', value: Math.round(activity.avg_cadence_rpm), unit: 'rpm', color: 'var(--cadence)' },
      { label: 'Max Cadence', value: Math.round(activity.max_cadence_rpm), unit: 'rpm', color: 'var(--cadence)' },
    ] : []),
    ...(hasPwr ? [
      { label: 'Avg Power', value: Math.round(activity.avg_power_w), unit: 'W', color: 'var(--power)' },
      { label: 'Max Power', value: Math.round(activity.max_power_w), unit: 'W', color: 'var(--power)' },
    ] : []),
    { label: 'Elevation ↑', value: activity.elevation_gain_m.toFixed(0), unit: 'm', color: 'var(--elevation)' },
    { label: 'Elevation ↓', value: activity.elevation_loss_m.toFixed(0), unit: 'm', color: 'var(--text-secondary)' },
    ...(activity.calories
      ? [{ label: 'Calories', value: activity.calories, unit: 'kcal', color: 'var(--heart)' }]
      : (() => { const est = estimateCalories(activity.duration_seconds, activity.avg_speed_kmh, weightKg); return est ? [{ label: 'Est. Calories', value: est, unit: 'kcal', color: 'var(--heart)' }] : [] })()
    ),
  ]

  return (
    <div>
      <Link to="/activities" className="back-link">
        <ArrowLeft size={14} /> All Activities
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
                style={{
                  background: 'var(--bg-card)', border: '1px solid var(--accent)',
                  color: 'var(--text-primary)', borderRadius: 6, padding: '6px 12px',
                  fontSize: 20, fontFamily: 'var(--font-display)', fontWeight: 700, outline: 'none',
                }}
              />
              <button className="btn btn-primary" onClick={handleRename}>Save</button>
              <button className="btn btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 className="page-title">{activity.name}</h1>
              <button className="btn btn-ghost" style={{ padding: '4px 8px' }} aria-label="Edit activity name" onClick={() => setEditing(true)}>
                <Pencil size={13} />
              </button>
            </div>
          )}
          <p className="page-subtitle" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {format(new Date(activity.date), 'EEEE, d MMMM yyyy')}
            {' · '}
            <span className={`badge badge-${activity.file_type}`}>{activity.file_type.toUpperCase()}</span>
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
          <button className="btn btn-danger" onClick={handleDelete}>
            <Trash2 size={14} /> Delete
          </button>
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
            <div className="chart-title">Speed <InfoTip text="Your speed over the ride in km/h. Consistent lines = steady pacing. Sharp dips = climbs or braking. A gradual drop in the second half may indicate fatigue." /></div>
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
              <div className="chart-title">Heart Rate <InfoTip text="Heart rate in BPM throughout the ride. A gradual rise is normal (cardiac drift). Spikes without speed change may indicate heat or fatigue. Aerobic base rides should stay in Z2: 60–70% of your max HR." /></div>
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
              <div className="chart-title">Cadence <InfoTip text="Pedal revolutions per minute (rpm). Optimal range is 75–90 rpm. High cadence (>90) means more cardiovascular load with less muscle fatigue. Low cadence (<70) stresses the muscles more and raises lactate." /></div>
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
              <div className="chart-title">Power <InfoTip text="Raw power output in watts. Spikes are normal for sprints and climbs. Sustained output above your FTP means threshold or harder effort. Compare with Normalized Power (NP) for the physiological cost of the whole ride." /></div>
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
              <div className="chart-title">Elevation <InfoTip text="Altitude profile showing your terrain. Sharp spikes = steep climbs (or GPS noise). Total elevation gain is shown in the metrics above. Big climbs later in the ride are harder — check if your speed drops on them." /></div>
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
              Splits <InfoTip text="Ride broken into equal distance chunks. Compare speed and HR across splits to spot pacing issues — if speed drops and HR rises in later splits, you went out too hard or are fatigued." />
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
                  <th scope="col">Time</th>
                  <th scope="col">Speed</th>
                  {splits.some(s => s.avgHr) && <th scope="col">Avg HR</th>}
                  {splits.some(s => s.avgCad) && <th scope="col">Avg Cad</th>}
                  {splits.some(s => s.elevGain != null) && <th scope="col">Elev +</th>}
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
                ? 'Show less'
                : `Show ${splits.length - SPLITS_PREVIEW} more splits`}
            </button>
          )}
        </div>
      )}

      {/* Best Efforts */}
      {efforts.length > 0 && (
        <div className="chart-section">
          <div className="chart-title">Best Efforts <InfoTip text="Fastest time for each target distance using a sliding window across the whole ride. These are your personal bests for this session — compare across rides to track fitness gains." /></div>
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
          <div className="chart-title">Laps</div>
          <div className="table-wrapper" style={{ border: 'none' }}>
            <table className="table splits-table">
              <thead>
                <tr>
                  <th scope="col">Lap</th>
                  <th scope="col">Distance</th>
                  <th scope="col">Time</th>
                  <th scope="col">Avg Speed</th>
                  {laps.some(l => l.avg_hr) && <th scope="col">Avg HR</th>}
                  {laps.some(l => l.avg_cadence) && <th scope="col">Avg Cad</th>}
                  {laps.some(l => l.elevation_gain_m) && <th scope="col">Elev +</th>}
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
          <div className="chart-title">Power Analysis <InfoTip text="Advanced metrics from your power meter. NP (Normalized Power) is the physiological cost of the ride. IF (Intensity Factor) shows effort vs FTP. TSS is training load: <150 = overnight recovery, >300 = needs multiple easy days." /></div>

          {/* Key power metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 10, marginBottom: 20 }}>
            {[
              np     && { label: 'Norm. Power', value: np,     unit: 'W',    color: 'var(--power)', hint: 'Coggan NP — physiological cost of variable effort' },
              ifVal  && { label: 'Int. Factor',  value: ifVal,  unit: 'IF',   color: '#c084fc',      hint: '< 0.75 easy · 0.85 tempo · 1.0 threshold' },
              tss    && { label: 'TSS',           value: tss,    unit: 'pts',  color: '#ffd93d',      hint: '< 150 recoverable · > 300 needs days off' },
              wPerKg && { label: 'W / kg',        value: wPerKg, unit: 'w/kg', color: '#6dffb8',      hint: 'Norm. power per kg bodyweight' },
              eFtp   && { label: 'eFTP',           value: eFtp,  unit: 'W',    color: 'var(--power-model)',      hint: '95% of best 20-min power — estimated FTP' },
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
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 2 }}>Critical Power</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--power-model)', fontFamily: 'var(--font-display)' }}>{cpModel.cp} <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)' }}>W</span></div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 2 }}>W′ (Anaerobic reserve)</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#c084fc', fontFamily: 'var(--font-display)' }}>{cpModel.wPrimeKj} <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)' }}>kJ</span></div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', flex: 1, minWidth: 160, lineHeight: 1.5 }}>
                CP = sustainable power indefinitely · W′ = anaerobic energy store depleted above CP. Fitted from 2–20 min MMP.
              </div>
            </div>
          )}

          {/* Power zones */}
          {pwrZones && ftp && (
            <>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                Power zones based on FTP of <strong style={{ color: 'var(--text-primary)' }}>{ftp} W</strong>
              </div>
              <div className="hr-zones" style={{ marginBottom: 20 }}>
                {pwrZones.map(z => (
                  <div key={z.label} className="hr-zone-row">
                    <div className="hr-zone-label" style={{ color: z.color }}>{z.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', width: 120, flexShrink: 0 }}>{z.name}</div>
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
                Mean Maximal Power (MMP) — best average power by duration
                {!ftp && <span style={{ opacity: 0.6 }}> · Set FTP in Settings to see zones</span>}
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
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>Durability / Fatigue Resistance <InfoTip text="Compares your power output fresh (first 40% of kJ) vs fatigued (remaining). <5% drop = excellent — you hold power well when tired. Pros typically drop <10%, amateurs 15–25%. Score = 100 − (avg drop% × 4)." /></div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Fresh MMP (first {durability.thresholdKj} kJ) vs Fatigued (after) — {durability.totalKj} kJ total work
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 32, fontWeight: 900, fontFamily: 'var(--font-display)', lineHeight: 1,
                    color: durability.score >= 80 ? '#6dffb8' : durability.score >= 60 ? '#ffd93d' : '#ff8c42' }}>
                    {durability.score}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>durability score / 100</div>
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
                  <Line type="monotone" dataKey="freshWatts"    stroke="var(--power)" strokeWidth={2} dot={false} name="Fresh" />
                  <Line type="monotone" dataKey="fatiguedWatts" stroke="var(--heart)"  strokeWidth={2} dot={false} strokeDasharray="5 3" name="Fatigued" />
                </LineChart>
              </ResponsiveContainer>

              {/* Drop table */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(90px, 1fr))', gap: 6, marginTop: 10 }}>
                {durability.drops.map(d => (
                  <div key={d.label} style={{ background: 'var(--bg-secondary)', border: `1px solid ${d.dropPct < 5 ? '#6dffb840' : d.dropPct < 12 ? '#ffd93d40' : '#ff4d6d40'}`, borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3 }}>{d.label}</div>
                    <div style={{ fontSize: 16, fontWeight: 800, color: d.dropPct < 5 ? '#6dffb8' : d.dropPct < 12 ? '#ffd93d' : '#ff8c42', fontFamily: 'var(--font-display)' }}>
                      {d.dropPct > 0 ? '-' : '+'}{Math.abs(d.dropPct)}%
                    </div>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>{d.freshWatts}→{d.fatiguedWatts}W</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8 }}>
                Avg drop: {durability.avgDrop}% · &lt;5% pro level · 15–25% typical amateur · score = 100 − (drop% × 4)
              </div>
            </div>
          )}

          {/* Power Quadrant */}
          {pwrQuadrant && (
            <div style={{ marginTop: 24 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Power Quadrant Analysis <InfoTip text="Breaks riding time into 4 quadrants by cadence and torque. Aerobic Spin (high cad, low torque) = efficient pedaling. Strength (low cad, high torque) = climbing. Sprint Power = short max efforts. More time in Aerobic Spin = better cycling economy." /></div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
                Cadence split: {pwrQuadrant.cadSplit} rpm · Torque split: {pwrQuadrant.medTorque} Nm (median)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {pwrQuadrant.grid.map((row, ri) =>
                  row.map(q => (
                    <div key={q.key} style={{
                      background: 'var(--bg-secondary)', border: `2px solid ${q.color}30`,
                      borderRadius: 10, padding: '14px 16px',
                    }}>
                      <div style={{ fontSize: 32, fontWeight: 900, color: q.color, fontFamily: 'var(--font-display)', lineHeight: 1 }}>{q.pct}%</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>{q.label}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{q.sub}</div>
                    </div>
                  ))
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
                <span>↑ High torque</span><span>·</span>
                <span>→ High cadence ({pwrQuadrant.cadSplit}+ rpm)</span>
              </div>
            </div>
          )}

          {/* Nudge to set FTP if missing */}
          {!ftp && (
            <div style={{ marginTop: 14, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)' }}>
              Set your FTP in <strong style={{ color: 'var(--text-primary)' }}>Settings → Fitness Profile</strong> to unlock power zones, TSS, and intensity factor.
            </div>
          )}
        </div>
      )}

      {/* HR Decoupling + VAM — shown when applicable regardless of power */}
      {(hrDecoupling || vam) && (
        <div className="chart-section">
          <div className="chart-title">Aerobic Metrics <InfoTip text="HR Decoupling: how much your heart rate drifts up relative to pace across the ride. Below 5% = good aerobic base. Above 5% = fatigue, heat, or went too hard. VAM: your average climbing speed in m/h — 800 = solid endurance, 1500+ = pro climber." /></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
            {hrDecoupling && (
              <div style={{ background: 'var(--bg-secondary)', border: `1px solid ${hrDecoupling.aerobic ? '#6dffb840' : '#ff4d6d40'}`, borderRadius: 10, padding: '14px 16px' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>{hrDecoupling.label} Decoupling</div>
                <div style={{ fontSize: 26, fontWeight: 800, color: hrDecoupling.aerobic ? '#6dffb8' : '#ff8c42', fontFamily: 'var(--font-display)' }}>
                  {hrDecoupling.pct > 0 ? '+' : ''}{hrDecoupling.pct}%
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                  {hrDecoupling.aerobic ? 'Good aerobic efficiency' : 'Aerobic drift — fatigue or underfuelled'}
                  {' · '}&lt;5% = well-conditioned
                </div>
              </div>
            )}
            {vam && (
              <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>VAM</div>
                <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--elevation)', fontFamily: 'var(--font-display)' }}>
                  {vam.toLocaleString()} <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-muted)' }}>m/h</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                  Climbing rate on ascending segments · 800 endurance · 1500+ pro climber
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* HR Zones */}
      {hrZones && (
        <div className="chart-section">
          <div className="chart-title">Heart Rate Zones <InfoTip text="Time in each HR zone based on your max HR. Z1–Z2 (60–70%) = aerobic base. Z3 (70–80%) = tempo. Z4–Z5 (80–100%) = high intensity. For endurance improvement, aim for 80%+ of your training time in Z1–Z2." /></div>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 14 }}>
            Based on max HR of {Math.round(activity.max_heart_rate_bpm)} bpm
          </p>
          <div className="hr-zones">
            {hrZones.map(z => (
              <div key={z.label} className="hr-zone-row">
                <div className="hr-zone-label" style={{ color: z.color }}>{z.label}</div>
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
          <div className="chart-title">Cadence Zones <InfoTip text="Distribution of cadence across the ride. Optimal zone (75–90 rpm) = efficient pedaling with balanced cardiovascular and muscular load. Most time here = good technique. More time in Very Low (<60 rpm) suggests you may be grinding gears." /></div>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 14 }}>
            Optimal zone: 75–90 rpm · Avg: {Math.round(activity.avg_cadence_rpm)} rpm
          </p>
          <div className="hr-zones">
            {cadZones.map(z => (
              <div key={z.label} className="hr-zone-row">
                <div className="hr-zone-label" style={{ color: z.color }}>{z.label}</div>
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
        const RISK_COLOR = { low: '#6dffb8', moderate: '#ffd93d', high: '#ff8c42', critical: '#ff4d6d' }
        const riskColor = RISK_COLOR[hydration.risk_level] || '#aaa'
        const recs = (() => { try { return JSON.parse(hydration.recommendations_json || '[]') } catch { return [] } })()
        const sweatL  = (hydration.estimated_total_sweat_ml / 1000).toFixed(1)
        const intakeL = hydration.reported_intake_ml != null ? (hydration.reported_intake_ml / 1000).toFixed(1) : null
        const deficitL = hydration.deficit_ml != null ? (hydration.deficit_ml / 1000).toFixed(1) : null
        const targetMlH = Math.round(hydration.estimated_sweat_rate_ml_h * 0.75)
        return (
          <div className="chart-section">
            <div className="chart-title" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Droplets size={14} style={{ color: '#4da6ff' }} />
              Hydration &amp; Heat Analysis
              <InfoTip text="Estimates your sweat loss and fluid needs based on weather, ride duration, and intensity. Log your intake to see your deficit and personalised recommendations." />
              <span style={{ marginLeft: 'auto', padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700, background: `${riskColor}18`, border: `1px solid ${riskColor}45`, color: riskColor, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {hydration.risk_level} risk
              </span>
            </div>

            {/* Key numbers */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, marginBottom: 16 }}>
              {[
                { label: 'Est. Sweat Loss', value: `${sweatL} L`, color: '#4da6ff', hint: `~${Math.round(hydration.estimated_sweat_rate_ml_h)} ml/h` },
                intakeL != null && { label: 'Fluid Intake', value: `${intakeL} L`, color: '#6dffb8', hint: 'Logged intake' },
                deficitL != null && { label: 'Deficit', value: `${deficitL} L`, color: riskColor, hint: hydration.deficit_body_pct != null ? `${hydration.deficit_body_pct}% body weight` : '' },
                { label: 'Target Rate', value: `${targetMlH} ml/h`, color: 'var(--text-secondary)', hint: '75% of sweat rate' },
                hydration.humidity_pct != null && { label: 'Humidity', value: `${hydration.humidity_pct}%`, color: 'var(--text-secondary)', hint: `${hydration.avg_temperature_c}°C` },
                { label: 'Analysis Quality', value: hydration.analysis_quality.charAt(0).toUpperCase() + hydration.analysis_quality.slice(1), color: hydration.analysis_quality === 'high' ? '#6dffb8' : hydration.analysis_quality === 'medium' ? '#ffd93d' : '#aaa', hint: '' },
              ].filter(Boolean).map(({ label, value, color, hint }) => (
                <div key={label} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: '12px 14px' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>{label}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color, fontFamily: 'var(--font-display)' }}>{value}</div>
                  {hint && <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>{hint}</div>}
                </div>
              ))}
            </div>

            {/* HR & performance impact */}
            {(hydration.estimated_hr_drift_heat_bpm > 0 || hydration.estimated_hr_drift_dehydration_bpm != null) && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
                {hydration.estimated_hr_drift_heat_bpm > 0 && (
                  <div style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    HR drift from heat <strong style={{ color: '#ff8c42', fontFamily: 'var(--font-display)' }}>+{hydration.estimated_hr_drift_heat_bpm} bpm</strong>
                  </div>
                )}
                {hydration.estimated_hr_drift_dehydration_bpm != null && (
                  <div style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    HR drift from dehydration <strong style={{ color: riskColor, fontFamily: 'var(--font-display)' }}>+{hydration.estimated_hr_drift_dehydration_bpm} bpm</strong>
                  </div>
                )}
                {hydration.estimated_performance_loss_pct != null && hydration.estimated_performance_loss_pct > 0 && (
                  <div style={{ padding: '8px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    Est. performance impact <strong style={{ color: '#ff4d6d', fontFamily: 'var(--font-display)' }}>−{hydration.estimated_performance_loss_pct}%</strong>
                  </div>
                )}
              </div>
            )}

            {/* Log intake */}
            <div style={{ padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
                {hydration.reported_intake_ml != null ? 'Update your fluid intake' : 'Log your fluid intake for this ride'}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  type="number" min={0} max={20000} step={50}
                  value={intakeInput}
                  onChange={e => setIntakeInput(e.target.value)}
                  placeholder="e.g. 800"
                  style={{ width: 110, background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-primary)', borderRadius: 6, padding: '6px 10px', fontSize: 13 }}
                />
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>ml</span>
                <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={handleLogIntake} disabled={intakeSaving}>
                  {intakeSaving ? 'Saving…' : 'Save'}
                </button>
                {intakeMsg && <span style={{ fontSize: 12, color: intakeMsg === 'Saved.' ? '#6dffb8' : '#ff8c42' }}>{intakeMsg}</span>}
              </div>
            </div>

            {/* Recommendations */}
            {recs.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Recommendations</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {recs.map((rec, i) => (
                    <div key={i} style={{ display: 'flex', gap: 10, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, padding: '7px 12px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
                      <Droplets size={13} style={{ color: '#4da6ff', flexShrink: 0, marginTop: 1 }} />
                      {rec}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {/* Segments */}
      {segmentEfforts.length > 0 && (
        <div className="chart-section">
          <div className="chart-title">Segments</div>
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

      {/* AI Analysis */}
      <div className="chart-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div className="chart-title" style={{ marginBottom: 0 }}>
            <Sparkles size={14} style={{ display: 'inline', marginRight: 6, color: 'var(--accent)' }} />
            AI Ride Analysis
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {analysis && (
              <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 12 }} onClick={handleClearAnalysis}>
                <RefreshCw size={12} /> Regenerate
              </button>
            )}
            {!analysis && !analysisLoading && (
              <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 13 }} onClick={handleAnalyse}>
                <Sparkles size={13} /> Analyse Ride
              </button>
            )}
          </div>
        </div>

        {analysisLoading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 13, padding: '12px 0' }}>
            <div className="spinner" style={{ width: 16, height: 16 }} />
            Generating analysis…
          </div>
        )}

        {analysisError && (
          <div className="alert alert-error">{analysisError}</div>
        )}

        {analysis && !analysisLoading && (
          <p className="ai-analysis-text">{analysis}</p>
        )}

        {!analysis && !analysisLoading && !analysisError && (
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            Click "Analyse Ride" to get a coach-style breakdown of this ride.
          </p>
        )}
      </div>

      {/* Notes */}
      <div className="chart-section">
        <div className="chart-title">Notes</div>
        <textarea
          className="notes-textarea"
          placeholder="Add notes about this ride…"
          value={notes}
          onChange={e => handleNotesChange(e.target.value)}
          rows={4}
        />
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
          Auto-saved · Notes are scanned by AI for prohibited content (hate speech, harassment). See our <a href="/privacy" style={{ color: 'var(--text-muted)', textDecoration: 'underline' }}>Privacy Policy</a>.
        </div>
      </div>
    </div>
  )
}
