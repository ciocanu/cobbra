import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { format } from 'date-fns'
import { getSettings, updateSettings, getMe, createCheckout, changePassword, requestEmailChange, stravaAuthUrl, stravaStatus, stravaDisconnect, stravaSync, exportMyData, deleteAccount, getHeatProfile, recordSweatTest, setSweatRateDirect, resetSweatRate, getIndoorOutdoorProfile, recalculateIndoorOutdoor, calibrateIndoorOutdoor, calibratePower, resetPowerCalibration } from '../services/api'
import { markLoggedOut } from '../services/auth'
import {
  Save, Heart, CreditCard, CheckCircle, Zap, Star,
  Lock, Eye, EyeOff, ChevronDown, ChevronUp, Shield, Mail, Send, Bike,
  RefreshCw, Link2, Link2Off, Download, Trash2, AlertTriangle, Droplets, Thermometer, Home,
} from 'lucide-react'
import Alert from './Alert'

// â"€â"€ Constants â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

const TIER_STYLE = {
  free:     { color: 'var(--text-muted)',    bg: 'color-mix(in srgb, var(--text-muted) 5%, transparent)',    border: 'color-mix(in srgb, var(--text-muted) 14%, transparent)' },
  pro:      { color: 'var(--accent)',        bg: 'color-mix(in srgb, var(--accent) 6%, transparent)',        border: 'color-mix(in srgb, var(--accent) 20%, transparent)' },
  annual:   { color: 'var(--status-warn)',   bg: 'color-mix(in srgb, var(--status-warn) 7%, transparent)',   border: 'color-mix(in srgb, var(--status-warn) 22%, transparent)' },
  lifetime: { color: 'var(--tier-lifetime)', bg: 'color-mix(in srgb, var(--tier-lifetime) 7%, transparent)', border: 'color-mix(in srgb, var(--tier-lifetime) 22%, transparent)' },
}

const TIER_RANK = { free: 0, pro: 1, annual: 2, lifetime: 3 }

const STRAVA_COLOR = '#FC4C02'

const TIER_FEATURES = {
  free:     ['15 activities total', 'Basic stats & charts', 'Segment tracking', 'Personal records & goals'],
  pro:      ['Unlimited activities', 'AI ride analysis', '10 AI training plans / month', 'CSV & GPX export', 'Segment tracking & records'],
  annual:   ['Everything in Pro', 'Early access to new features', 'Best value: save 50%'],
  lifetime: ['Everything in Pro & Annual', 'All future features included', 'Never pay again'],
}

const UPGRADE_PLANS = [
  { tier: 'pro',    label: 'Pro',    price: 'â‚¬5 / month', features: TIER_FEATURES.pro },
  { tier: 'annual', label: 'Annual', price: 'â‚¬30 / year', sub: 'Save 50%', features: TIER_FEATURES.annual },
]

const HR_ZONES = [
  { label: 'Z1', name: 'Recovery',  range: [0,    0.60], color: 'oklch(54% 0.12 264)', desc: 'Very light: warm-up, cool-down, active recovery.' },
  { label: 'Z2', name: 'Endurance', range: [0.60, 0.70], color: 'oklch(58% 0.15 142)', desc: 'Comfortable aerobic effort. Builds base fitness.' },
  { label: 'Z3', name: 'Tempo',     range: [0.70, 0.80], color: 'oklch(68% 0.14 88)',  desc: 'Moderately hard. Improves lactate threshold.' },
  { label: 'Z4', name: 'Threshold', range: [0.80, 0.90], color: 'oklch(60% 0.15 38)',  desc: 'Hard. Speed endurance. Sustainable ~20 min.' },
  { label: 'Z5', name: 'VO2 Max',   range: [0.90, 1.00], color: 'oklch(52% 0.14 20)',  desc: 'Maximum effort. Peak power. Short intervals only.' },
]

// â"€â"€ Helpers â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

function avatarColor(name = '') {
  const colors = [
    'oklch(62% 0.14 230)', // steel blue
    'oklch(70% 0.14 55)',  // warm amber
    'oklch(64% 0.14 170)', // teal
    'oklch(65% 0.13 30)',  // terracotta
    'oklch(60% 0.12 290)', // muted violet
    'oklch(62% 0.15 10)',  // coral
  ]
  let hash = 0
  for (const c of name) hash = (hash * 31 + c.charCodeAt(0)) & 0xffff
  return colors[hash % colors.length]
}

function Card({ children, style }) {
  return (
    <div className="settings-card" style={{ marginBottom: 0, ...style }}>
      {children}
    </div>
  )
}

function CardTitle({ icon: Icon, color = 'var(--accent)', children }) {
  return (
    <div className="settings-section-title" style={{ marginBottom: 18 }}>
      <Icon size={14} style={{ color }} />
      {children}
    </div>
  )
}

function Divider() {
  return <div style={{ height: 1, background: 'var(--border)', margin: '16px 0' }} />
}

function CollapsibleRow({ icon: Icon, label, open, onToggle, children, id }) {
  const panelId = id || `collapsible-${label.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <>
      <Divider />
      <button
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 0', minHeight: 44 }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>
          <Icon size={14} style={{ color: 'var(--text-muted)' }} />
          {label}
        </div>
        {open
          ? <ChevronUp  size={15} style={{ color: 'var(--text-muted)' }} />
          : <ChevronDown size={15} style={{ color: 'var(--text-muted)' }} />}
      </button>
      {open && <div id={panelId} style={{ marginTop: 14 }}>{children}</div>}
    </>
  )
}

// â"€â"€ Main â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

export default function Settings() {
  const [searchParams] = useSearchParams()
  const justUpgraded   = searchParams.get('upgraded') === '1'

  const [user,      setUser]      = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [activeTab, setActiveTab] = useState('training')

  // HR
  const [maxHr,   setMaxHr]   = useState('')
  const [saving,  setSaving]  = useState(false)
  const [saved,   setSaved]   = useState(false)
  const [hrError, setHrError] = useState('')

  // Fitness profile
  const [age,             setAge]             = useState('')
  const [restingHr,       setRestingHr]       = useState('')
  const [weightKg,        setWeightKg]        = useState('')
  const [ftp,             setFtp]             = useState('')
  const [experienceLevel, setExperienceLevel] = useState('')
  const [bikeType,        setBikeType]        = useState('')
  const [bikeWeightKg,    setBikeWeightKg]    = useState('')
  const [fitnessSaving,   setFitnessSaving]   = useState(false)
  const [fitnessSaved,    setFitnessSaved]    = useState(false)
  const [fitnessError,    setFitnessError]    = useState('')

  // Power calibration
  const [calibSource,     setCalibSource]     = useState(null)
  const [calibCda,        setCalibCda]        = useState(null)
  const [calibFtp,        setCalibFtp]        = useState('')
  const [calibClimbId,    setCalibClimbId]    = useState('')
  const [calibPower,      setCalibPower]      = useState('')
  const [calibSaving,     setCalibSaving]     = useState(false)
  const [calibMsg,        setCalibMsg]        = useState('')
  const [calibMsgType,    setCalibMsgType]    = useState('')

  // Upgrade
  const [checking,      setChecking]      = useState(null)
  const [checkoutError, setCheckoutError] = useState('')

  // Email change
  const [emailOpen,    setEmailOpen]    = useState(false)
  const [newEmail,     setNewEmail]     = useState('')
  const [emailSending, setEmailSending] = useState(false)
  const [emailSent,    setEmailSent]    = useState(false)
  const [emailError,   setEmailError]   = useState('')

  // Password
  const [pwOpen,   setPwOpen]   = useState(false)
  const [oldPw,    setOldPw]    = useState('')
  const [newPw,    setNewPw]    = useState('')
  const [showOld,  setShowOld]  = useState(false)
  const [showNew,  setShowNew]  = useState(false)
  const [pwSaving, setPwSaving] = useState(false)
  const [pwError,  setPwError]  = useState('')
  const [pwSaved,  setPwSaved]  = useState(false)

  // Data & Privacy
  const [exporting,        setExporting]        = useState(false)
  const [exportError,      setExportError]      = useState('')
  const [deleteOpen,       setDeleteOpen]       = useState(false)
  const [deletePw,         setDeletePw]         = useState('')
  const [deleteConfirm,    setDeleteConfirm]    = useState('')
  const [deleting,         setDeleting]         = useState(false)
  const [deleteError,      setDeleteError]      = useState('')

  // Heat & Hydration
  const [heatProfile,         setHeatProfile]         = useState(null)
  const [sweatTestOpen,       setSweatTestOpen]       = useState(false)
  const [sweatBefore,         setSweatBefore]         = useState('')
  const [sweatAfter,          setSweatAfter]          = useState('')
  const [sweatIntake,         setSweatIntake]         = useState('')
  const [sweatDuration,       setSweatDuration]       = useState('')
  const [sweatSaving,         setSweatSaving]         = useState(false)
  const [sweatMsg,            setSweatMsg]            = useState('')
  const [sweatMsgType,        setSweatMsgType]        = useState('')
  const [directSweatRate,     setDirectSweatRate]     = useState('')
  const [directSweatSaving,   setDirectSweatSaving]   = useState(false)
  const [directSweatMsg,      setDirectSweatMsg]      = useState('')
  const [directSweatMsgType,  setDirectSweatMsgType]  = useState('')
  const [resetSweatSaving,    setResetSweatSaving]    = useState(false)
  const [resetSweatMsg,       setResetSweatMsg]       = useState('')

  // Indoor / Outdoor profile
  const [indoorProfile,      setIndoorProfile]      = useState(null)
  const [recalculating,      setRecalculating]      = useState(false)
  const [indoorMsg,          setIndoorMsg]          = useState('')
  const [indoorMsgType,      setIndoorMsgType]      = useState('')
  const [ftpCalibOpen,       setFtpCalibOpen]       = useState(false)
  const [indoorFtp,          setIndoorFtp]          = useState('')
  const [outdoorFtp,         setOutdoorFtp]         = useState('')
  const [ftpCalibSaving,     setFtpCalibSaving]     = useState(false)
  const [ftpCalibResult,     setFtpCalibResult]     = useState(null)

  // Strava
  const [stravaConnected,  setStravaConnected]  = useState(false)
  const [stravaAthleteId,  setStravaAthleteId]  = useState(null)
  const [stravaLastSync,   setStravaLastSync]   = useState(null)
  const [stravaSyncing,    setStravaSyncing]    = useState(false)
  const [stravaConnecting, setStravaConnecting] = useState(false)
  const [stravaMsg,        setStravaMsg]        = useState('')
  const [stravaMsgType,    setStravaMsgType]    = useState('')

  useEffect(() => {
    let upgradePoll = null

    getHeatProfile().then(r => setHeatProfile(r.data)).catch(() => {})
    getIndoorOutdoorProfile().then(r => setIndoorProfile(r.data)).catch(() => {})
    Promise.all([getSettings(), getMe(), stravaStatus().catch(() => ({ data: { connected: false } }))])
      .then(([s, u, sv]) => {
        setMaxHr(s.data.max_hr ?? '')
        setAge(s.data.age ?? '')
        setRestingHr(s.data.resting_hr ?? '')
        setWeightKg(s.data.weight_kg ?? '')
        setFtp(s.data.ftp ?? '')
        setExperienceLevel(s.data.experience_level ?? '')
        setBikeType(s.data.bike_type ?? '')
        setBikeWeightKg(s.data.bike_weight_kg ?? '')
        setCalibSource(s.data.calibration_source ?? null)
        setCalibCda(s.data.calibrated_cda ?? null)
        setUser(u.data)
        setStravaConnected(sv.data.connected)
        setStravaAthleteId(sv.data.athlete_id || null)
        setStravaLastSync(sv.data.last_sync_at || null)

        if (justUpgraded && (u.data.membership || 'free') === 'free') {
          let attempts = 0
          upgradePoll = setInterval(async () => {
            attempts++
            try {
              const fresh = await getMe()
              if ((fresh.data.membership || 'free') !== 'free' || attempts >= 8) {
                clearInterval(upgradePoll)
                setUser(fresh.data)
              }
            } catch { clearInterval(upgradePoll) }
          }, 2000)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))

    return () => { if (upgradePoll) clearInterval(upgradePoll) }
  }, [])

  const handleSweatTest = async () => {
    setSweatMsg('')
    const before = parseFloat(sweatBefore), after = parseFloat(sweatAfter)
    const intake = parseInt(sweatIntake, 10), dur = parseFloat(sweatDuration)
    if (isNaN(before) || before <= 0) { setSweatMsg('Enter a valid pre-ride weight.'); setSweatMsgType('error'); return }
    if (isNaN(after)  || after  <= 0) { setSweatMsg('Enter a valid post-ride weight.'); setSweatMsgType('error'); return }
    if (isNaN(intake) || intake < 0)  { setSweatMsg('Enter fluid intake (0 if none).'); setSweatMsgType('error'); return }
    if (isNaN(dur)    || dur   <= 0)  { setSweatMsg('Enter a valid duration in hours.'); setSweatMsgType('error'); return }
    setSweatSaving(true)
    try {
      const res = await recordSweatTest({ weight_before_kg: before, weight_after_kg: after, intake_ml_during: intake, duration_h: dur })
      setHeatProfile(res.data)
      setSweatMsg(`Calibrated: ${Math.round(res.data.sweat_rate_ml_per_hour)} ml/h saved.`)
      setSweatMsgType('success')
      setSweatBefore(''); setSweatAfter(''); setSweatIntake(''); setSweatDuration('')
    } catch (e) {
      setSweatMsg(e.response?.data?.detail || 'Calculation failed. Check your inputs.')
      setSweatMsgType('error')
    } finally { setSweatSaving(false) }
  }

  const handleDirectSweatRate = async () => {
    const ml_h = parseInt(directSweatRate, 10)
    if (isNaN(ml_h) || ml_h < 100 || ml_h > 4000) {
      setDirectSweatMsg('Enter a value between 100 and 4000 ml/h.')
      setDirectSweatMsgType('error')
      return
    }
    setDirectSweatSaving(true); setDirectSweatMsg('')
    try {
      const res = await setSweatRateDirect(ml_h)
      setHeatProfile(res.data)
      setDirectSweatMsg(`Saved: ${Math.round(res.data.sweat_rate_ml_per_hour)} ml/h.`)
      setDirectSweatMsgType('success')
      setDirectSweatRate('')
    } catch (e) {
      setDirectSweatMsg(e.response?.data?.detail || 'Failed to save.')
      setDirectSweatMsgType('error')
    } finally { setDirectSweatSaving(false) }
  }


  const handleResetSweatRate = async () => {
    setResetSweatSaving(true); setResetSweatMsg('')
    try {
      const res = await resetSweatRate()
      setHeatProfile(res.data)
      setResetSweatMsg('Sweat rate cleared. Analysis will now use the population model.')
    } catch (e) {
      setResetSweatMsg(e.response?.data?.detail || 'Failed to reset.')
    } finally { setResetSweatSaving(false) }
  }

  const handleRecalculateIndoor = async () => {
    setRecalculating(true); setIndoorMsg('')
    try {
      const res = await recalculateIndoorOutdoor()
      setIndoorProfile(res.data)
      setIndoorMsg('Profile recalculated.')
      setIndoorMsgType('success')
    } catch (e) {
      setIndoorMsg(e.response?.data?.detail || 'Recalculation failed.')
      setIndoorMsgType('error')
    } finally { setRecalculating(false) }
  }

  const handleFtpCalib = async () => {
    setIndoorMsg('')
    const iF = parseFloat(indoorFtp), oF = parseFloat(outdoorFtp)
    if (isNaN(iF) || iF <= 0) { setIndoorMsg('Enter a valid indoor FTP.'); setIndoorMsgType('error'); return }
    if (isNaN(oF) || oF <= 0) { setIndoorMsg('Enter a valid outdoor FTP.'); setIndoorMsgType('error'); return }
    setFtpCalibSaving(true)
    try {
      const res = await calibrateIndoorOutdoor({ method: 'ftp_comparison', indoor_ftp: iF, outdoor_ftp: oF })
      setFtpCalibResult(res.data)
      const freshProfile = await getIndoorOutdoorProfile()
      setIndoorProfile(freshProfile.data)
      setIndoorMsg('Calibration saved.')
      setIndoorMsgType('success')
    } catch (e) {
      setIndoorMsg(e.response?.data?.detail || 'Calibration failed.')
      setIndoorMsgType('error')
    } finally { setFtpCalibSaving(false) }
  }

  const handleSaveHr = async () => {
    const val = parseInt(maxHr, 10)
    if (maxHr !== '' && (isNaN(val) || val < 100 || val > 250)) {
      setHrError('Max HR must be between 100 and 250 bpm'); return
    }
    setSaving(true); setHrError('')
    try {
      await updateSettings({ max_hr: maxHr === '' ? null : val })
      setSaved(true); setTimeout(() => setSaved(false), 2500)
    } catch { setHrError('Failed to save') }
    finally { setSaving(false) }
  }

  const handleSaveFitness = async () => {
    setFitnessError('')
    const payload = {}
    if (age !== '') {
      const v = parseInt(age, 10)
      if (isNaN(v) || v < 10 || v > 100) { setFitnessError('Age must be between 10 and 100.'); return }
      payload.age = v
    }
    if (restingHr !== '') {
      const v = parseInt(restingHr, 10)
      if (isNaN(v) || v < 30 || v > 100) { setFitnessError('Resting HR must be between 30 and 100 bpm.'); return }
      payload.resting_hr = v
    }
    if (weightKg !== '') {
      const v = parseFloat(weightKg)
      if (isNaN(v) || v < 30 || v > 250) { setFitnessError('Weight must be between 30 and 250 kg.'); return }
      payload.weight_kg = v
    }
    if (ftp !== '') {
      const v = parseInt(ftp, 10)
      if (isNaN(v) || v < 50 || v > 600) { setFitnessError('FTP must be between 50 and 600 W.'); return }
      payload.ftp = v
    }
    if (experienceLevel) payload.experience_level = experienceLevel
    if (bikeType)        payload.bike_type        = bikeType
    if (bikeWeightKg !== '') {
      const v = parseFloat(bikeWeightKg)
      if (isNaN(v) || v < 3 || v > 50) { setFitnessError('Bike weight must be between 3 and 50 kg.'); return }
      payload.bike_weight_kg = v
    }
    setFitnessSaving(true)
    try {
      await updateSettings(payload)
      setFitnessSaved(true); setTimeout(() => setFitnessSaved(false), 2500)
    } catch (e) {
      setFitnessError(e.response?.data?.detail || 'Failed to save.')
    } finally { setFitnessSaving(false) }
  }

  const handleCalibratePower = async (method) => {
    setCalibMsg(''); setCalibSaving(true)
    try {
      const payload = { method }
      if (method === 'ftp') {
        const v = parseInt(calibFtp, 10)
        if (isNaN(v) || v < 50 || v > 600) { setCalibMsg('FTP must be between 50 and 600 W.'); setCalibMsgType('error'); setCalibSaving(false); return }
        payload.value = v
      } else {
        const v = parseFloat(calibPower)
        const cid = parseInt(calibClimbId, 10)
        if (isNaN(v) || v < 50) { setCalibMsg('Enter a valid power value (W).'); setCalibMsgType('error'); setCalibSaving(false); return }
        if (isNaN(cid)) { setCalibMsg('Enter a valid climb ID.'); setCalibMsgType('error'); setCalibSaving(false); return }
        payload.value = v
        payload.climb_id = cid
      }
      const res = await calibratePower(payload)
      setCalibSource(method === 'ftp' ? 'manual_ftp' : 'known_climb')
      setCalibCda(res.data.calibrated_cda)
      setCalibMsg(`Calibration applied. ${res.data.climbs_recalculated} climb(s) recalculated.`)
      setCalibMsgType('success')
    } catch (e) {
      setCalibMsg(e.response?.data?.detail || 'Calibration failed.')
      setCalibMsgType('error')
    } finally { setCalibSaving(false) }
  }

  const handleResetCalibration = async () => {
    setCalibSaving(true)
    try {
      await resetPowerCalibration()
      setCalibSource(null); setCalibCda(null)
      setCalibMsg('Calibration reset to defaults.')
      setCalibMsgType('success')
    } catch { setCalibMsg('Reset failed.'); setCalibMsgType('error') }
    finally { setCalibSaving(false) }
  }

  const handleUpgrade = async (tier) => {
    setChecking(tier)
    setCheckoutError('')
    try {
      const res = await createCheckout(tier)
      window.location.href = res.data.url
    } catch (e) {
      setCheckoutError(e.response?.data?.detail || 'Could not start checkout.')
      setChecking(null)
    }
  }

  const handleRequestEmailChange = async () => {
    setEmailError('')
    if (!newEmail.includes('@')) { setEmailError('Enter a valid email address.'); return }
    setEmailSending(true)
    try {
      await requestEmailChange(newEmail); setEmailSent(true)
    } catch (e) {
      setEmailError(e.response?.data?.detail || 'Failed to send verification email.')
    } finally { setEmailSending(false) }
  }

  const handleChangePassword = async () => {
    setPwError('')
    if (!oldPw || !newPw) { setPwError('Fill in both fields.'); return }
    if (newPw.length < 6)  { setPwError('New password must be at least 6 characters.'); return }
    setPwSaving(true)
    try {
      await changePassword(oldPw, newPw)
      setPwSaved(true); setOldPw(''); setNewPw('')
      setTimeout(() => { setPwSaved(false); setPwOpen(false) }, 2000)
    } catch (e) {
      setPwError(e.response?.data?.detail || 'Failed to change password.')
    } finally { setPwSaving(false) }
  }

  const handleStravaConnect = async () => {
    setStravaConnecting(true)
    try {
      const res = await stravaAuthUrl()
      window.location.href = res.data.url
    } catch (e) {
      setStravaMsg(e.response?.data?.detail || 'Strava is not configured on this server.')
      setStravaMsgType('error')
      setStravaConnecting(false)
    }
  }

  const handleStravaDisconnect = async () => {
    try {
      await stravaDisconnect()
      setStravaConnected(false)
      setStravaAthleteId(null)
      setStravaLastSync(null)
      setStravaMsg('Strava disconnected.')
      setStravaMsgType('success')
    } catch {
      setStravaMsg('Failed to disconnect.')
      setStravaMsgType('error')
    }
  }

  const handleStravaSync = async () => {
    setStravaSyncing(true)
    setStravaMsg('')
    try {
      const res = await stravaSync()
      const { imported, skipped, backfilled, capped, detail } = res.data
      let msg = `Sync complete: ${imported} ride${imported !== 1 ? 's' : ''} imported`
      if (backfilled > 0) msg += `, ${backfilled} updated with GPS data`
      if (skipped > 0) msg += `, ${skipped} skipped`
      msg += '.'
      if (capped) msg = detail
      setStravaMsg(msg)
      setStravaMsgType(capped ? 'error' : 'success')
      setStravaLastSync(new Date().toISOString())
    } catch (e) {
      setStravaMsg(e.response?.data?.detail || 'Sync failed.')
      setStravaMsgType('error')
    } finally {
      setStravaSyncing(false)
    }
  }

  const handleExportData = async () => {
    setExporting(true); setExportError('')
    try {
      const res = await exportMyData()
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `cobbra-data-${user?.username || 'export'}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setExportError('Export failed. Please try again.')
    } finally { setExporting(false) }
  }

  const handleDeleteAccount = async () => {
    if (deleteConfirm !== 'DELETE') { setDeleteError('Type DELETE to confirm.'); return }
    if (!deletePw) { setDeleteError('Enter your password.'); return }
    setDeleting(true); setDeleteError('')
    try {
      await deleteAccount(deletePw)
      markLoggedOut()
      window.location.href = '/'
    } catch (e) {
      setDeleteError(e.response?.data?.detail || 'Failed to delete account.')
      setDeleting(false)
    }
  }

  if (loading) return <div className="loading-center"><div className="spinner" /></div>

  const membership  = user?.membership || 'free'
  const ts          = TIER_STYLE[membership] || TIER_STYLE.free
  const currentRank = TIER_RANK[membership] ?? 0
  const subEnd      = user?.subscription_end ? new Date(user.subscription_end) : null
  const hrVal       = parseInt(maxHr, 10)
  const upgradable  = UPGRADE_PLANS.filter(p => TIER_RANK[p.tier] > currentRank)
  const aColor      = avatarColor(user?.username)

  // â"€â"€ Karvonen zones preview (mirrors backend logic for display) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
  const maxHrNum     = parseInt(maxHr, 10)
  const restingHrNum = parseInt(restingHr, 10)
  const zonesReady   = maxHr !== '' && !isNaN(maxHrNum) && maxHrNum >= 100
  const useKarvonen  = zonesReady && restingHr !== '' && !isNaN(restingHrNum) && restingHrNum >= 30

  function zoneBpm(lo, hi) {
    if (!zonesReady) return null
    if (useKarvonen) {
      const hrr = maxHrNum - restingHrNum
      return { lo: Math.round(restingHrNum + hrr * lo), hi: Math.round(restingHrNum + hrr * hi) }
    }
    return { lo: Math.round(maxHrNum * lo), hi: Math.round(maxHrNum * hi) }
  }

  const TABS = [
    { id: 'account',      label: 'Account' },
    { id: 'training',     label: 'Training' },
    { id: 'calibration',  label: 'Calibration' },
    { id: 'data',         label: 'Data' },
    { id: 'integrations', label: 'Integrations' },
  ]

  return (
    <div style={{ maxWidth: 1140 }}>
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
      </div>

      <div className="imp-tab-bar" role="tablist">
        {TABS.map(tab => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tab-panel-${tab.id}`}
            className={`imp-tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Account ──────────────────────────────────────────── */}
      {activeTab === 'account' && (
        <div id="tab-panel-account" role="tabpanel">
          {justUpgraded && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 18px', borderRadius: 10, background: 'color-mix(in srgb, var(--accent) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--accent) 25%, transparent)', color: 'var(--accent)', marginBottom: 20, fontWeight: 600 }}>
              <CheckCircle size={16} />
              Welcome to {membership.charAt(0).toUpperCase() + membership.slice(1)}! Your plan has been upgraded.
            </div>
          )}
          <div className="settings-layout-top">
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 4 }}>
                <div style={{ width: 64, height: 64, borderRadius: '50%', flexShrink: 0, background: aColor, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, fontWeight: 800, color: 'oklch(8% 0.005 142)', boxShadow: `0 0 0 3px oklch(8% 0.005 142), 0 0 0 5px color-mix(in srgb, ${aColor} 33%, transparent)` }}>
                  {(user?.username || '?')[0].toUpperCase()}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{user?.username}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {user?.email || <span style={{ opacity: 0.4 }}>No email on file</span>}
                  </div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: ts.bg, border: `1px solid ${ts.border}`, color: ts.color, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                    {membership === 'lifetime' && <Star size={9} />}
                    {membership}
                  </span>
                </div>
              </div>
              <CollapsibleRow icon={Mail} label="Change Email" open={emailOpen} onToggle={() => { setEmailOpen(o => !o); setEmailError(''); setEmailSent(false); setNewEmail('') }}>
                {emailSent ? (
                  <div style={{ padding: '14px 16px', borderRadius: 10, background: 'color-mix(in srgb, var(--accent) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--accent) 19%, transparent)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--accent)', marginBottom: 6, fontSize: 13 }}>
                      <CheckCircle size={14} /> Verification email sent
                    </div>
                    <p style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                      Sent to <strong style={{ color: 'var(--text-primary)' }}>{newEmail}</strong>. Link expires in 24 h.
                    </p>
                    <button onClick={() => { setEmailSent(false); setNewEmail('') }} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-muted)', padding: 0, textDecoration: 'underline' }}>
                      Use a different address
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Current: <strong style={{ color: 'var(--text-secondary)' }}>{user?.email || '—'}</strong>
                    </div>
                    <input id="settings-new-email" aria-label="New email address" type="email" className="filter-input" style={{ width: '100%' }} value={newEmail} onChange={e => { setNewEmail(e.target.value); setEmailError('') }} placeholder="new@email.com" onKeyDown={e => e.key === 'Enter' && handleRequestEmailChange()} />
                    {emailError && <Alert variant="error" style={{ fontSize: 12 }}>{emailError}</Alert>}
                    <button className="btn btn-primary" onClick={handleRequestEmailChange} disabled={emailSending}>
                      <Send size={12} />{emailSending ? 'Sending…' : 'Send verification'}
                    </button>
                  </div>
                )}
              </CollapsibleRow>
              <CollapsibleRow icon={Lock} label="Change Password" open={pwOpen} onToggle={() => { setPwOpen(o => !o); setPwError(''); setPwSaved(false) }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[
                    { id: 'settings-current-pw', label: 'Current password', val: oldPw, set: setOldPw, show: showOld, toggle: () => setShowOld(s => !s) },
                    { id: 'settings-new-pw',     label: 'New password',     val: newPw, set: setNewPw, show: showNew, toggle: () => setShowNew(s => !s), hint: 'Min. 6 characters' },
                  ].map(({ id, label, val, set, show, toggle, hint }) => (
                    <div key={label}>
                      <label htmlFor={id} style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 5 }}>{label}</label>
                      <div style={{ position: 'relative' }}>
                        <input id={id} type={show ? 'text' : 'password'} className="filter-input" style={{ width: '100%', paddingRight: 36 }} value={val} onChange={e => set(e.target.value)} placeholder={hint || '••••••••'} />
                        <button onClick={toggle} aria-label={show ? 'Hide password' : 'Show password'} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 0 }}>
                          {show ? <EyeOff size={13} /> : <Eye size={13} />}
                        </button>
                      </div>
                    </div>
                  ))}
                  {pwError && <Alert variant="error" style={{ fontSize: 12 }}>{pwError}</Alert>}
                  {pwSaved && <Alert variant="success" style={{ fontSize: 12 }}><Shield size={12} /> Password updated. Other sessions signed out.</Alert>}
                  <button className="btn btn-primary" onClick={handleChangePassword} disabled={pwSaving}>
                    <Lock size={12} />{pwSaving ? 'Updating…' : 'Update Password'}
                  </button>
                </div>
              </CollapsibleRow>
            </Card>

            <Card>
              <CardTitle icon={CreditCard}>Plan & Billing</CardTitle>
              <div style={{ border: `1px solid ${ts.border}`, borderRadius: 12, background: ts.bg, padding: '18px 20px', marginBottom: upgradable.length ? 16 : 0 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: ts.color, marginBottom: 4 }}>Current plan</div>
                    <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                      {membership === 'lifetime' && <Star size={18} style={{ color: ts.color }} />}
                      {membership.charAt(0).toUpperCase() + membership.slice(1)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
                    {membership === 'free'     && <span>15 activities max</span>}
                    {membership === 'lifetime' && <span style={{ color: ts.color, fontWeight: 600 }}>Never expires</span>}
                    {(membership === 'pro' || membership === 'annual') && subEnd && (
                      <span>Renews {format(subEnd, 'dd MMM yyyy')}</span>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 20px' }}>
                  {TIER_FEATURES[membership]?.map(f => (
                    <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, color: 'var(--text-secondary)' }}>
                      <CheckCircle size={12} style={{ color: ts.color, flexShrink: 0 }} />{f}
                    </div>
                  ))}
                </div>
              </div>
              {upgradable.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${upgradable.length}, 1fr)`, gap: 12 }}>
                  {upgradable.map(plan => {
                    const ps = TIER_STYLE[plan.tier]
                    return (
                      <div key={plan.tier} style={{ border: `1px solid ${ps.border}`, borderRadius: 10, padding: '16px 18px', background: ps.bg }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <span style={{ fontWeight: 700, fontSize: 15, color: ps.color }}>{plan.label}</span>
                          {plan.sub && <span style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-secondary)', borderRadius: 4, padding: '2px 7px' }}>{plan.sub}</span>}
                        </div>
                        <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 12 }}>{plan.price}</div>
                        <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {plan.features.map(f => (
                            <li key={f} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--text-muted)' }}>
                              <Zap size={10} style={{ color: ps.color, flexShrink: 0 }} />{f}
                            </li>
                          ))}
                        </ul>
                        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', background: ps.color, color: 'oklch(8% 0.005 142)', fontWeight: 700 }} onClick={() => handleUpgrade(plan.tier)} disabled={checking === plan.tier}>
                          {checking === plan.tier
                            ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, borderColor: 'oklch(8% 0.005 142 / 0.25)', borderTopColor: 'oklch(8% 0.005 142)' }} />
                            : `Upgrade to ${plan.label}`}
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
              {checkoutError && <Alert variant="error" style={{ marginTop: 12, fontSize: 12 }}>{checkoutError}</Alert>}
              {membership === 'lifetime' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderRadius: 8, background: 'color-mix(in srgb, var(--tier-lifetime) 3%, transparent)', border: '1px solid color-mix(in srgb, var(--tier-lifetime) 13%, transparent)', fontSize: 13, color: 'var(--text-muted)' }}>
                  <Star size={13} style={{ color: 'var(--tier-lifetime)' }} />
                  You have lifetime access. Nothing left to upgrade.
                </div>
              )}
            </Card>
          </div>
        </div>
      )}

      {/* ── Training ─────────────────────────────────────────── */}
      {activeTab === 'training' && (
        <div id="tab-panel-training" role="tabpanel">
          <div className="settings-layout-bottom">
            <Card>
              <CardTitle icon={Bike}>Fitness Profile</CardTitle>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 20, lineHeight: 1.5 }}>
                Used to personalise AI training plans. More data = more accurate sessions.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, marginBottom: 16 }}>
                {[
                  { id: 'profile-age',        label: 'Age',        unit: 'years', val: age,       set: setAge,       placeholder: '32',  min: 10, max: 100, step: 1 },
                  { id: 'profile-weight',     label: 'Weight',     unit: 'kg',    val: weightKg,  set: setWeightKg,  placeholder: '72',  min: 30, max: 250, step: 0.1 },
                  { id: 'profile-resting-hr', label: 'Resting HR', unit: 'bpm',   val: restingHr, set: setRestingHr, placeholder: '52',  min: 30, max: 100, step: 1,   hint: 'Morning, before getting up' },
                  { id: 'profile-ftp',        label: 'FTP',        unit: 'W',     val: ftp,       set: setFtp,       placeholder: '220', min: 50, max: 600, step: 1,   hint: 'Only needed with a power meter' },
                ].map(({ id, label, unit, val, set, placeholder, min, max, step, hint }) => (
                  <div key={label}>
                    <label htmlFor={id} style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>{label}</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <input id={id} type="number" className="filter-input" style={{ flex: 1, minWidth: 0 }} value={val} onChange={e => { set(e.target.value); setFitnessError('') }} placeholder={placeholder} min={min} max={max} step={step} />
                      <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{unit}</span>
                    </div>
                    {hint && <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.4 }}>{hint}</div>}
                  </div>
                ))}
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>Bike Type</label>
                <div role="group" aria-label="Bike type" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: 8 }}>
                  {[
                    { value: 'road', label: 'Road' }, { value: 'gravel', label: 'Gravel' },
                    { value: 'mtb',  label: 'MTB' },  { value: 'tt',     label: 'TT' },
                    { value: 'ebike', label: 'E-Bike' }, { value: 'other', label: 'Other' },
                  ].map(opt => (
                    <button key={opt.value} onClick={() => { setBikeType(opt.value); setFitnessError('') }} aria-pressed={bikeType === opt.value} style={{ padding: '8px 4px', borderRadius: 8, cursor: 'pointer', textAlign: 'center', fontSize: 12, fontWeight: 600, border: bikeType === opt.value ? '1px solid color-mix(in srgb, var(--accent) 30%, transparent)' : '1px solid var(--border)', background: bikeType === opt.value ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'var(--bg-secondary)', color: bikeType === opt.value ? 'var(--accent)' : 'var(--text-muted)', transition: 'border-color 150ms cubic-bezier(0.23, 1, 0.32, 1), background-color 150ms cubic-bezier(0.23, 1, 0.32, 1), color 150ms cubic-bezier(0.23, 1, 0.32, 1)' }}>{opt.label}</button>
                  ))}
                </div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>
                  Bike Weight <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(for climb power estimates)</span>
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="number" className="filter-input" style={{ width: 90 }} value={bikeWeightKg} onChange={e => { setBikeWeightKg(e.target.value); setFitnessError('') }} placeholder={bikeType === 'mtb' ? '13' : bikeType === 'ebike' ? '22' : bikeType === 'gravel' ? '10' : '9'} min={3} max={50} step={0.1} />
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>kg</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Leave blank to use default for bike type</span>
                </div>
              </div>
              <div style={{ marginBottom: 18 }}>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Experience Level</label>
                <div role="group" aria-label="Experience level" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {[
                    { value: 'beginner',     label: 'Beginner',     desc: 'Riding less than 1 year' },
                    { value: 'intermediate', label: 'Intermediate', desc: '1–4 years of regular riding' },
                    { value: 'advanced',     label: 'Advanced',     desc: '4+ years, structured training or racing' },
                  ].map(opt => (
                    <button key={opt.value} onClick={() => { setExperienceLevel(opt.value); setFitnessError('') }} aria-pressed={experienceLevel === opt.value} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 8, cursor: 'pointer', textAlign: 'left', border: experienceLevel === opt.value ? '1px solid color-mix(in srgb, var(--accent) 25%, transparent)' : '1px solid var(--border)', background: experienceLevel === opt.value ? 'color-mix(in srgb, var(--accent) 6%, transparent)' : 'var(--bg-secondary)', transition: 'border-color 150ms cubic-bezier(0.23, 1, 0.32, 1), background-color 150ms cubic-bezier(0.23, 1, 0.32, 1)' }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: experienceLevel === opt.value ? 'var(--accent)' : 'var(--border)', boxShadow: experienceLevel === opt.value ? '0 0 6px color-mix(in srgb, var(--accent) 60%, transparent)' : 'none', transition: 'background-color 150ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 150ms cubic-bezier(0.23, 1, 0.32, 1)' }} />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: experienceLevel === opt.value ? 'var(--accent)' : 'var(--text-primary)', marginBottom: 1 }}>{opt.label}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{opt.desc}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              {fitnessError && <Alert variant="error" style={{ marginBottom: 12, fontSize: 12 }}>{fitnessError}</Alert>}
              {fitnessSaved && <Alert variant="success" style={{ marginBottom: 12, fontSize: 12 }}>Fitness profile saved.</Alert>}
              <button className="btn btn-primary" onClick={handleSaveFitness} disabled={fitnessSaving}>
                <Save size={13} />{fitnessSaving ? 'Saving…' : 'Save Profile'}
              </button>
              <div style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                  Power Calibration <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>(optional)</span>
                </div>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.5 }}>
                  Fine-tune estimated climb power using a known FTP or a climb where you know your actual power output.
                </p>
                {calibSource && (
                  <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 8, background: 'color-mix(in srgb, var(--status-good) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--status-good) 20%, transparent)', fontSize: 12, color: 'var(--status-good)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Calibrated from {calibSource === 'manual_ftp' ? 'FTP' : 'known climb'}, CdA: {calibCda?.toFixed(3)}</span>
                    <button className="btn" style={{ fontSize: 11, padding: '4px 10px', minHeight: 32, color: 'var(--text-muted)' }} onClick={handleResetCalibration} disabled={calibSaving}>Reset</button>
                  </div>
                )}
                {!calibSource && <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--text-muted)' }}>Current: Default parameters for bike type</div>}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600 }}>Option 1: Calibrate from FTP</div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input type="number" className="filter-input" style={{ width: 90 }} value={calibFtp} onChange={e => setCalibFtp(e.target.value)} placeholder="280" min={50} max={600} />
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>W</span>
                      <button className="btn" style={{ fontSize: 12, padding: '5px 12px', minHeight: 36 }} onClick={() => handleCalibratePower('ftp')} disabled={calibSaving}>Calibrate</button>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600 }}>Option 2: Known power on a specific climb</div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <input type="number" className="filter-input" style={{ width: 90 }} value={calibClimbId} onChange={e => setCalibClimbId(e.target.value)} placeholder="Climb ID" min={1} />
                      <input type="number" className="filter-input" style={{ width: 90 }} value={calibPower} onChange={e => setCalibPower(e.target.value)} placeholder="Watts" min={50} />
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>W</span>
                      <button className="btn" style={{ fontSize: 12, padding: '5px 12px', minHeight: 36 }} onClick={() => handleCalibratePower('climb')} disabled={calibSaving}>Calibrate</button>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>Find Climb ID in the activity detail page (expand a climb card).</div>
                  </div>
                </div>
                {calibMsg && <Alert variant={calibMsgType === 'error' ? 'error' : 'success'} style={{ marginTop: 10, fontSize: 12 }}>{calibMsg}</Alert>}
              </div>
            </Card>

            <Card>
              <CardTitle icon={Heart} color="var(--heart)">Heart Rate Zones</CardTitle>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.5 }}>
                Set your max HR to unlock zone tracking and Suffer Score.
                Add resting HR too for more precise Karvonen zones, used in AI training plans.
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>Max Heart Rate</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="number" className="filter-input" style={{ width: 90 }} value={maxHr} onChange={e => { setMaxHr(e.target.value); setHrError(''); setSaved(false) }} placeholder="e.g. 185" min={100} max={250} />
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>bpm</span>
                  </div>
                </div>
                {zonesReady && (
                  <div style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, background: useKarvonen ? 'color-mix(in srgb, var(--status-good) 8%, transparent)' : 'color-mix(in srgb, var(--text-secondary) 8%, transparent)', border: useKarvonen ? '1px solid color-mix(in srgb, var(--status-good) 20%, transparent)' : '1px solid color-mix(in srgb, var(--text-secondary) 20%, transparent)', color: useKarvonen ? 'var(--status-good)' : 'var(--text-secondary)', whiteSpace: 'nowrap', marginTop: 18 }}>
                    {useKarvonen ? 'Karvonen zones' : '% of max HR'}
                  </div>
                )}
              </div>
              {zonesReady && (
                <>
                  <div style={{ display: 'flex', height: 8, borderRadius: 6, overflow: 'hidden', marginBottom: 5 }}>
                    {HR_ZONES.map(z => <div key={z.label} style={{ flex: z.range[1] - z.range[0], background: z.color }} title={z.name} />)}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', marginBottom: 16, fontFamily: 'var(--font-mono)' }}>
                    {HR_ZONES.map((z, i) => { const bpm = zoneBpm(z.range[0], z.range[1]); return <span key={z.label}>{i === 0 ? bpm?.lo : bpm?.hi}</span> })}
                    <span>{zoneBpm(HR_ZONES[4].range[0], HR_ZONES[4].range[1])?.hi}+</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {HR_ZONES.map(z => {
                      const bpm = zoneBpm(z.range[0], z.range[1])
                      const hiStr = z.range[1] === 1 ? `${bpm?.lo}+` : bpm?.hi
                      return (
                        <div key={z.label} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 8, background: `color-mix(in srgb, ${z.color} 4%, transparent)`, border: `1px solid color-mix(in srgb, ${z.color} 12%, transparent)` }}>
                          <div style={{ width: 26, height: 26, borderRadius: 7, background: `color-mix(in srgb, ${z.color} 12%, transparent)`, border: `1px solid color-mix(in srgb, ${z.color} 25%, transparent)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 800, color: z.color, flexShrink: 0 }}>{z.label}</div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: z.color }}>{z.name}</div>
                            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>{z.desc}</div>
                          </div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                            {bpm?.lo}–{hiStr} <span style={{ fontSize: 10, fontWeight: 400, color: 'var(--text-muted)' }}>bpm</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
              {!zonesReady && (
                <div style={{ padding: '20px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', textAlign: 'center' }}>
                  <Heart size={24} style={{ color: 'var(--text-muted)', opacity: 0.4, marginBottom: 8 }} />
                  <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Enter your max HR to see your zones</div>
                </div>
              )}
              {hrError && <Alert variant="error" style={{ marginTop: 14, fontSize: 12 }}>{hrError}</Alert>}
              {saved   && <Alert variant="success" style={{ marginTop: 14, fontSize: 12 }}>Heart rate saved.</Alert>}
              <div style={{ marginTop: 16 }}>
                <button className="btn btn-primary" onClick={handleSaveHr} disabled={saving}><Save size={13} />{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* ── Calibration ──────────────────────────────────────── */}
      {activeTab === 'calibration' && (
        <div id="tab-panel-calibration" role="tabpanel" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* ── Accuracy Overview ── */}
          <Card>
            <CardTitle icon={CheckCircle}>Accuracy Overview</CardTitle>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.5 }}>
              Every physiological input below sharpens a specific calculation. Missing values fall back to population estimates.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
              {[
                {
                  label: 'Body Weight',
                  value: weightKg !== '' ? `${weightKg} kg` : null,
                  affects: 'Sweat-loss %, calorie burn, W/kg power',
                  critical: true,
                },
                {
                  label: 'FTP',
                  value: ftp !== '' ? `${ftp} W` : null,
                  affects: 'TSS, training load, intensity factor for hydration',
                  critical: false,
                },
                {
                  label: 'Max Heart Rate',
                  value: maxHr !== '' ? `${maxHr} bpm` : null,
                  affects: 'HR-based TSS, zone boundaries, effort calibration',
                  critical: false,
                },
                {
                  label: 'Resting HR',
                  value: restingHr !== '' ? `${restingHr} bpm` : null,
                  affects: 'TRIMP heart rate reserve (more accurate training load)',
                  critical: false,
                },
                {
                  label: 'Sweat Rate',
                  value: heatProfile?.has_calibrated_rate ? `${Math.round(heatProfile.sweat_rate_ml_per_hour)} ml/h` : null,
                  missing: 'Population avg (~700 ml/h base)',
                  affects: 'Estimated sweat loss, hydration deficit, risk level',
                  critical: true,
                },
                {
                  label: 'Heat Adaptation',
                  value: heatProfile?.heat_adaptation_level && heatProfile.heat_adaptation_level !== 'none'
                    ? heatProfile.heat_adaptation_level.charAt(0).toUpperCase() + heatProfile.heat_adaptation_level.slice(1)
                    : null,
                  missing: 'Auto-computed from hot-ride history',
                  affects: 'Sweat efficiency multiplier (adapted athletes sweat more efficiently)',
                  critical: false,
                  auto: true,
                },
              ].map(({ label, value, missing, affects, critical, auto }) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'var(--bg-card)' }}>
                  <div style={{
                    width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                    background: value
                      ? 'var(--status-good)'
                      : critical ? 'var(--status-alert)' : 'var(--border)',
                  }} />
                  <div style={{ minWidth: 110, fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
                  <div style={{ flex: 1, fontSize: 11, color: 'var(--text-muted)' }}>{affects}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, fontFamily: 'var(--font-mono)', color: value ? 'var(--text-primary)' : 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                    {value || <span style={{ fontStyle: 'italic', fontFamily: 'inherit', fontWeight: 400 }}>{missing || (auto ? 'Auto' : 'Not set')}</span>}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardTitle icon={Droplets}>Heat &amp; Hydration</CardTitle>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 18, lineHeight: 1.5 }}>
              Your personal sweat rate calibrates sweat-loss estimates. When set, it anchors the calculation to your physiology;
              only temperature and humidity <em>above</em> typical test conditions (20°C / 55% RH) are added on top.
              If estimates seem too high or too low, reset below and re-run a sweat test.
            </p>
            {heatProfile && (
              <div style={{ display: 'flex', gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', marginBottom: 12 }}>
                <div style={{ flex: 1, padding: '11px 16px', background: 'var(--bg-card)' }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Sweat Rate</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: heatProfile.has_calibrated_rate ? 'var(--text-primary)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 2 }}>
                    {heatProfile.has_calibrated_rate ? `${Math.round(heatProfile.sweat_rate_ml_per_hour)} ml/h` : 'Population avg'}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    {heatProfile.has_calibrated_rate ? 'Personal calibration — used in all analyses' : 'No calibration set — using generic model'}
                  </div>
                </div>
                <div style={{ flex: 1, padding: '11px 16px', background: 'var(--bg-card)' }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Heat Adaptation</div>
                  <div style={{ fontSize: 15, fontWeight: 700, fontFamily: 'var(--font-mono)', marginBottom: 2, color: heatProfile.heat_adaptation_level === 'high' ? 'var(--status-good)' : heatProfile.heat_adaptation_level === 'moderate' ? 'var(--status-warn)' : 'var(--text-muted)' }}>
                    {heatProfile.heat_adaptation_level ? heatProfile.heat_adaptation_level.charAt(0).toUpperCase() + heatProfile.heat_adaptation_level.slice(1) : 'Low'}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{heatProfile.heat_rides_last_14d} hot rides (≥27°C) in last 14 days</div>
                </div>
              </div>
            )}
            {heatProfile?.has_calibrated_rate && (
              <div style={{ marginBottom: 14 }}>
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 12, color: 'var(--status-alert)', borderColor: 'color-mix(in srgb, var(--status-alert) 30%, transparent)' }}
                  onClick={handleResetSweatRate}
                  disabled={resetSweatSaving}
                >
                  <RefreshCw size={12} /> {resetSweatSaving ? 'Resetting…' : 'Reset to population model'}
                </button>
                {resetSweatMsg && (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>{resetSweatMsg}</div>
                )}
              </div>
            )}
            <CollapsibleRow icon={Thermometer} label="Run a Sweat Test" open={sweatTestOpen} onToggle={() => { setSweatTestOpen(o => !o); setSweatMsg('') }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.6 }}>
                Ride at a steady effort for exactly 1 hour with no fluid intake, or log any intake below. Weigh yourself (dry, no kit) immediately before and after.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12, marginBottom: 12 }}>
                {[
                  { id: 'sweat-before', label: 'Weight before', unit: 'kg', val: sweatBefore, set: setSweatBefore, placeholder: '72.4', step: '0.1' },
                  { id: 'sweat-after',  label: 'Weight after',  unit: 'kg', val: sweatAfter,  set: setSweatAfter,  placeholder: '71.1', step: '0.1' },
                  { id: 'sweat-intake', label: 'Fluid intake',  unit: 'ml', val: sweatIntake, set: setSweatIntake, placeholder: '500',  step: '50' },
                  { id: 'sweat-dur',    label: 'Duration',      unit: 'h',  val: sweatDuration, set: setSweatDuration, placeholder: '1.0', step: '0.25' },
                ].map(({ id, label, unit, val, set, placeholder, step }) => (
                  <div key={id}>
                    <label htmlFor={id} style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 5 }}>{label}</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <input id={id} type="number" className="filter-input" style={{ flex: 1 }} value={val} onChange={e => { set(e.target.value); setSweatMsg('') }} placeholder={placeholder} step={step} min="0" />
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{unit}</span>
                    </div>
                  </div>
                ))}
              </div>
              {sweatMsg && <Alert variant={sweatMsgType === 'error' ? 'error' : 'success'} style={{ marginBottom: 10, fontSize: 12 }}>{sweatMsg}</Alert>}
              <button className="btn btn-primary" onClick={handleSweatTest} disabled={sweatSaving}>
                <Droplets size={12} />{sweatSaving ? 'Calculating…' : 'Calculate & Save'}
              </button>
            </CollapsibleRow>
            <div style={{ marginTop: 14, padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>Already know your sweat rate?</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10, lineHeight: 1.5 }}>Enter it directly (e.g. from a lab test or a previous calibration). Typical range: 500–2000 ml/h.</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input type="number" min={100} max={4000} step={50} value={directSweatRate} onChange={e => { setDirectSweatRate(e.target.value); setDirectSweatMsg('') }} placeholder="e.g. 900" className="filter-input" style={{ width: 100 }} />
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>ml/h</span>
                <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 12, minHeight: 36 }} onClick={handleDirectSweatRate} disabled={directSweatSaving}>
                  {directSweatSaving ? 'Saving…' : 'Set Rate'}
                </button>
                {directSweatMsg && <span style={{ fontSize: 12, color: directSweatMsgType === 'error' ? 'var(--status-alert)' : 'var(--status-good)' }}>{directSweatMsg}</span>}
              </div>
            </div>
          </Card>

          <Card>
            <CardTitle icon={Home}>Indoor / Outdoor Profile</CardTitle>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 18, lineHeight: 1.5 }}>
              Cobbra automatically detects whether each ride was indoor or outdoor and calculates your personal power gap,
              the difference in sustainable power between environments. This corrects your TSS and CTL/ATL/TSB for more accurate fitness tracking.
            </p>
            {indoorProfile && (
              <>
                <div style={{ display: 'flex', gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', marginBottom: 14 }}>
                  {[
                    { label: 'Power Gap', value: indoorProfile.effective_power_gap_pct != null ? `${indoorProfile.effective_power_gap_pct.toFixed(1)}%` : '—', color: 'var(--text-primary)', hint: indoorProfile.manual_power_gap_pct != null ? 'manual' : 'auto-calculated' },
                    { label: 'Confidence', value: indoorProfile.power_gap_confidence ? indoorProfile.power_gap_confidence.replace('_', ' ') : '—', color: indoorProfile.power_gap_confidence === 'high' ? 'var(--status-good)' : indoorProfile.power_gap_confidence === 'medium' ? 'var(--status-warn)' : indoorProfile.power_gap_confidence === 'low' ? 'var(--status-alert)' : 'var(--text-muted)', hint: indoorProfile.last_calculated ? `Updated ${new Date(indoorProfile.last_calculated).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}` : '' },
                    { label: 'Indoor',  value: indoorProfile.indoor_rides_analyzed,  color: 'var(--text-secondary)', hint: 'rides analysed' },
                    { label: 'Outdoor', value: indoorProfile.outdoor_rides_analyzed, color: 'var(--text-secondary)', hint: 'rides analysed' },
                  ].map(({ label, value, color, hint }) => (
                    <div key={label} style={{ flex: 1, minWidth: 80, padding: '11px 14px', background: 'var(--bg-card)' }}>
                      <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color, fontFamily: 'var(--font-mono)', marginBottom: 2 }}>{value}</div>
                      {hint && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{hint}</div>}
                    </div>
                  ))}
                </div>
                {(indoorProfile.indoor_rides_analyzed < 3 || indoorProfile.outdoor_rides_analyzed < 3) && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '10px 14px', borderRadius: 8, background: 'color-mix(in srgb, var(--status-warn) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--status-warn) 20%, transparent)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.5 }}>
                    <Home size={13} style={{ color: 'var(--status-warn)', flexShrink: 0, marginTop: 1 }} />
                    Need at least 3 indoor and 3 outdoor rides with power data (at Z3 intensity) for automatic gap calculation. Use the FTP calibration below as a shortcut.
                  </div>
                )}
              </>
            )}
            <div style={{ display: 'flex', gap: 8, marginBottom: indoorMsg ? 12 : 0 }}>
              <button className="btn btn-ghost" onClick={handleRecalculateIndoor} disabled={recalculating} style={{ fontSize: 13 }}>
                <RefreshCw size={13} style={recalculating ? { animation: 'spin 1s linear infinite' } : {}} />
                {recalculating ? 'Recalculating…' : 'Recalculate Gap'}
              </button>
            </div>
            {indoorMsg && <Alert variant={indoorMsgType === 'error' ? 'error' : 'success'} style={{ marginBottom: 12, fontSize: 12 }}>{indoorMsg}</Alert>}
            <CollapsibleRow icon={Zap} label="Calibrate via FTP Comparison" open={ftpCalibOpen} onToggle={() => { setFtpCalibOpen(o => !o); setFtpCalibResult(null); setIndoorMsg('') }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.6 }}>
                If you know your indoor and outdoor FTP values (e.g. from separate 20-min tests), enter them to manually calibrate your power gap. The calibrated gap overrides the auto-calculated one.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 12, marginBottom: 12 }}>
                {[
                  { id: 'indoor-ftp',  label: 'Indoor FTP',  val: indoorFtp,  set: setIndoorFtp,  placeholder: '200' },
                  { id: 'outdoor-ftp', label: 'Outdoor FTP', val: outdoorFtp, set: setOutdoorFtp, placeholder: '230' },
                ].map(({ id, label, val, set, placeholder }) => (
                  <div key={id}>
                    <label htmlFor={id} style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 5 }}>{label}</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <input id={id} type="number" className="filter-input" style={{ flex: 1 }} value={val} onChange={e => { set(e.target.value); setIndoorMsg('') }} placeholder={placeholder} min={50} max={600} />
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>W</span>
                    </div>
                  </div>
                ))}
              </div>
              {ftpCalibResult && (
                <div style={{ padding: '12px 14px', borderRadius: 8, background: 'color-mix(in srgb, var(--status-good) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--status-good) 20%, transparent)', marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--status-good)', marginBottom: 4 }}>Gap: {ftpCalibResult.power_gap_pct?.toFixed(1)}%</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>{ftpCalibResult.interpretation}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontStyle: 'italic' }}>{ftpCalibResult.recommendation}</div>
                </div>
              )}
              <button className="btn btn-primary" onClick={handleFtpCalib} disabled={ftpCalibSaving}>
                <Zap size={12} />{ftpCalibSaving ? 'Calibrating…' : 'Calibrate & Save'}
              </button>
            </CollapsibleRow>
          </Card>
        </div>
      )}

      {/* ── Data ─────────────────────────────────────────────── */}
      {activeTab === 'data' && (
        <div id="tab-panel-data" role="tabpanel">
          <Card>
            <CardTitle icon={Shield}>Privacy &amp; Data</CardTitle>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 20, lineHeight: 1.6 }}>
              Under GDPR you have the right to export all your data or permanently delete your account.
              {' '}<a href="/privacy" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Privacy Policy</a>
              {' · '}<a href="/terms" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Terms of Service</a>
            </p>
            <div style={{ padding: '14px 16px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>Export My Data</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>
                Download a JSON file containing your profile, all activity metadata, goals, segments, and training plans. Raw GPS track data can be exported per-activity via the CSV / GPX buttons.
              </div>
              <button className="btn btn-ghost" onClick={handleExportData} disabled={exporting} style={{ fontSize: 13 }}>
                <Download size={13} />{exporting ? 'Preparing…' : 'Download My Data'}
              </button>
              {exportError && <Alert variant="error" style={{ marginTop: 10, fontSize: 12 }}>{exportError}</Alert>}
            </div>
            <div style={{ padding: '14px 16px', borderRadius: 10, background: 'color-mix(in srgb, var(--status-critical) 5%, transparent)', border: '1px solid color-mix(in srgb, var(--status-critical) 13%, transparent)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--status-critical)', marginBottom: 2 }}>Delete Account</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Permanently removes your account and all associated data. This cannot be undone.</div>
                </div>
                <button className="btn" style={{ fontSize: 12, color: 'var(--status-critical)', borderColor: 'color-mix(in srgb, var(--status-critical) 25%, transparent)', marginLeft: 16, flexShrink: 0 }} onClick={() => { setDeleteOpen(o => !o); setDeleteError(''); setDeletePw(''); setDeleteConfirm('') }}>
                  <Trash2 size={13} /> {deleteOpen ? 'Cancel' : 'Delete…'}
                </button>
              </div>
              {deleteOpen && (
                <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 8, background: 'color-mix(in srgb, var(--status-critical) 7%, transparent)', border: '1px solid color-mix(in srgb, var(--status-critical) 19%, transparent)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    <AlertTriangle size={13} />
                    All activities, track data, goals, segments, and personal records will be permanently erased.
                  </div>
                  <div>
                    <label htmlFor="delete-pw" style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 5 }}>Your password</label>
                    <input id="delete-pw" type="password" className="filter-input" style={{ width: '100%' }} value={deletePw} onChange={e => { setDeletePw(e.target.value); setDeleteError('') }} placeholder="Enter your password" />
                  </div>
                  <div>
                    <label htmlFor="delete-confirm" style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 5 }}>
                      Type <strong style={{ color: 'var(--status-critical)' }}>DELETE</strong> to confirm
                    </label>
                    <input id="delete-confirm" type="text" className="filter-input" style={{ width: '100%' }} value={deleteConfirm} onChange={e => { setDeleteConfirm(e.target.value); setDeleteError('') }} placeholder="DELETE" />
                  </div>
                  {deleteError && <Alert variant="error" style={{ fontSize: 12 }}>{deleteError}</Alert>}
                  <button className="btn btn-danger" onClick={handleDeleteAccount} disabled={deleting || deleteConfirm !== 'DELETE'}>
                    <Trash2 size={13} />{deleting ? 'Deleting…' : 'Permanently Delete My Account'}
                  </button>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* ── Integrations ─────────────────────────────────────── */}
      {activeTab === 'integrations' && (
        <div id="tab-panel-integrations" role="tabpanel">
          <Card>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: `color-mix(in srgb, ${STRAVA_COLOR} 8%, transparent)`, border: `1px solid color-mix(in srgb, ${STRAVA_COLOR} 19%, transparent)`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill={STRAVA_COLOR}>
                    <path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0 5 13.828h4.172" />
                  </svg>
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>Strava</div>
                  {stravaConnected ? (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Connected{stravaAthleteId && <span style={{ opacity: 0.6 }}> · athlete #{stravaAthleteId}</span>}
                      {stravaLastSync && <span> · last synced {new Date(stravaLastSync).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Import your cycling activities from Strava</div>
                  )}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {stravaConnected ? (
                  <>
                    <button className="btn btn-primary" style={{ background: STRAVA_COLOR, color: 'oklch(98% 0.005 120)', fontWeight: 700, gap: 6 }} onClick={handleStravaSync} disabled={stravaSyncing}>
                      {stravaSyncing ? <><span className="spinner" style={{ width: 13, height: 13, borderWidth: 2, borderColor: 'oklch(98% 0.005 120 / 0.25)', borderTopColor: 'oklch(98% 0.005 120)' }} /> Syncing…</> : <><RefreshCw size={13} /> Sync Rides</>}
                    </button>
                    <button className="btn" style={{ fontSize: 12, color: 'var(--text-muted)', borderColor: 'var(--border)', gap: 6 }} onClick={handleStravaDisconnect}>
                      <Link2Off size={13} /> Disconnect
                    </button>
                  </>
                ) : (
                  <button className="btn btn-primary" style={{ background: STRAVA_COLOR, color: 'oklch(98% 0.005 120)', fontWeight: 700, gap: 6 }} onClick={handleStravaConnect} disabled={stravaConnecting}>
                    {stravaConnecting ? <><span className="spinner" style={{ width: 13, height: 13, borderWidth: 2, borderColor: 'oklch(98% 0.005 120 / 0.25)', borderTopColor: 'oklch(98% 0.005 120)' }} /> Redirecting…</> : <><Link2 size={13} /> Connect Strava</>}
                  </button>
                )}
              </div>
            </div>
            {stravaMsg && <Alert variant={stravaMsgType === 'error' ? 'error' : 'success'} style={{ marginTop: 12, fontSize: 12 }}>{stravaMsg}</Alert>}
            {stravaConnected && (
              <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Only cycling activities (Ride, Virtual Ride, Gravel, MTB) are imported.
                {membership === 'free' && ' Free plan: up to 15 activities total.'}
                {' '}GPS track data is not available; activities imported from Strava won't generate personal records.
              </div>
            )}
          </Card>
        </div>
      )}

    </div>
  )
}
