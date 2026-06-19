import { useEffect, useRef, useState } from 'react'
import { format } from 'date-fns'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { MapContainer, TileLayer, Polyline, CircleMarker } from 'react-leaflet'
import { Shield, Users, Activity, Zap, Mountain, Database, Clock, Trash2, Pencil, Check, X, ArrowRightLeft, Eye, Star, Mail } from 'lucide-react'
import {
  adminGetStats, adminGetSystem,
  adminGetUsers, adminUpdateMembership, adminSendOffer, adminDeleteUser,
  adminGetSegments, adminRenameSegment, adminTransferSegment, adminDeleteSegment,
} from '../services/api'
import { useTranslation } from 'react-i18next'

function fmtUptime(secs) {
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function fmtBytes(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="card" style={{ padding: '18px 22px', display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{
        width: 42, height: 42, borderRadius: 10, flexShrink: 0,
        background: `${color}18`, border: `1px solid ${color}30`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.1 }}>{value}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
      </div>
    </div>
  )
}

const MEMBERSHIP_STYLES = {
  free:     { background: '#ffffff14', color: '#aaa',    border: '1px solid #ffffff20' },
  pro:      { background: '#4da6ff20', color: '#4da6ff', border: '1px solid #4da6ff40' },
  annual:   { background: '#ffd93d20', color: '#ffd93d', border: '1px solid #ffd93d40' },
  lifetime: { background: '#c084fc20', color: '#c084fc', border: '1px solid #c084fc40' },
}

function MembershipBadge({ tier }) {
  const s = MEMBERSHIP_STYLES[tier] || MEMBERSHIP_STYLES.free
  return (
    <span style={{ ...s, fontSize: 10, fontWeight: 700, borderRadius: 4, padding: '2px 7px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
      {tier}
    </span>
  )
}

const btnStyle = (variant = 'ghost') => ({
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 500,
  border: `1px solid ${variant === 'danger' ? '#ff4d4d40' : variant === 'accent' ? 'var(--border)' : 'var(--border)'}`,
  background: variant === 'danger' ? '#ff4d4d12' : 'transparent',
  color: variant === 'danger' ? '#ff6b6b' : 'var(--text-secondary)',
  cursor: 'pointer',
})

export default function Admin() {
  const { t } = useTranslation()
  const [stats,    setStats]    = useState(null)
  const [system,   setSystem]   = useState(null)
  const [users,    setUsers]    = useState([])
  const [segments, setSegments] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState('')

  // Inline rename state
  const [editingId,   setEditingId]   = useState(null)
  const [editingName, setEditingName] = useState('')

  // Inline transfer state
  const [transferId,     setTransferId]     = useState(null)
  const [transferUserId, setTransferUserId] = useState('')

  // Membership editing state
  const [membershipEditId,  setMembershipEditId]  = useState(null)
  const [membershipDraft,   setMembershipDraft]   = useState('free')

  // Map preview state
  const [viewSegment, setViewSegment] = useState(null)

  const load = () => {
    setLoading(true)
    Promise.all([adminGetStats(), adminGetSystem(), adminGetUsers(), adminGetSegments()])
      .then(([s, sys, u, seg]) => {
        setStats(s.data); setSystem(sys.data)
        setUsers(u.data); setSegments(seg.data)
      })
      .catch(err => setError(
        err.response?.status === 403 ? t('admin.errorAccessDenied') : t('admin.errorLoadFailed')
      ))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const modalRef     = useRef(null)
  const prevFocusRef = useRef(null)

  useEffect(() => {
    if (viewSegment) {
      prevFocusRef.current = document.activeElement
      const focusable = modalRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (focusable?.length) focusable[0].focus()
    } else {
      prevFocusRef.current?.focus()
    }
  }, [viewSegment])

  const handleModalKeyDown = (e) => {
    if (e.key === 'Escape') { setViewSegment(null); return }
    if (e.key !== 'Tab') return
    const focusable = Array.from(
      modalRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      ) ?? []
    ).filter(el => !el.disabled)
    if (!focusable.length) return
    const first = focusable[0]
    const last  = focusable[focusable.length - 1]
    if (e.shiftKey) {
      if (document.activeElement === first) { last.focus(); e.preventDefault() }
    } else {
      if (document.activeElement === last) { first.focus(); e.preventDefault() }
    }
  }

  const saveMembership = async (id) => {
    try {
      await adminUpdateMembership(id, membershipDraft)
      setUsers(u => u.map(x => x.id === id ? { ...x, membership: membershipDraft } : x))
      setMembershipEditId(null)
    } catch (e) { alert(e.response?.data?.detail || t('admin.alertUpdateFailed')) }
  }

  const [offerSentIds, setOfferSentIds] = useState(new Set())

  const handleSendOffer = async (u) => {
    if (!window.confirm(t('admin.confirmSendOffer', { username: u.username, email: u.email }))) return
    try {
      await adminSendOffer(u.id)
      setOfferSentIds(s => new Set([...s, u.id]))
    } catch (e) { alert(e.response?.data?.detail || t('admin.alertSendEmailFailed')) }
  }

  const handleGrantLifetime = async (u) => {
    const isLifetime = u.membership === 'lifetime'
    const msg = isLifetime
      ? t('admin.confirmRevokeLifetime', { username: u.username })
      : t('admin.confirmGrantLifetime', { username: u.username })
    if (!window.confirm(msg)) return
    const next = isLifetime ? 'free' : 'lifetime'
    try {
      await adminUpdateMembership(u.id, next)
      setUsers(us => us.map(x => x.id === u.id ? { ...x, membership: next } : x))
    } catch (e) { alert(e.response?.data?.detail || t('admin.alertUpdateFailed')) }
  }

  const handleDeleteUser = async (id, username) => {
    if (!window.confirm(t('admin.confirmDeleteUser', { username }))) return
    try {
      await adminDeleteUser(id)
      setUsers(u => u.filter(x => x.id !== id))
    } catch (e) { alert(e.response?.data?.detail || t('admin.alertDeleteFailed')) }
  }

  const startEdit = (seg) => { cancelTransfer(); setEditingId(seg.id); setEditingName(seg.name) }
  const cancelEdit = () => { setEditingId(null); setEditingName('') }

  const startTransfer = (seg) => { cancelEdit(); setTransferId(seg.id); setTransferUserId('') }
  const cancelTransfer = () => { setTransferId(null); setTransferUserId('') }

  const getPositions = (seg) => {
    try {
      const pts = JSON.parse(seg.waypoints_json || '[]')
      if (pts.length >= 2) return pts
    } catch {}
    return [[seg.start_lat, seg.start_lon], [seg.end_lat, seg.end_lon]]
  }

  const saveTransfer = async (segId, segName) => {
    if (!transferUserId) return
    const newOwner = users.find(u => u.id === parseInt(transferUserId))
    if (!window.confirm(t('admin.confirmTransfer', { segName, ownerName: newOwner?.username }))) return
    try {
      const res = await adminTransferSegment(segId, parseInt(transferUserId))
      setSegments(s => s.map(x => x.id === segId ? { ...x, created_by: res.data.created_by } : x))
      cancelTransfer()
    } catch (e) { alert(e.response?.data?.detail || t('admin.alertTransferFailed')) }
  }

  const saveEdit = async (id) => {
    if (!editingName.trim()) return
    try {
      await adminRenameSegment(id, editingName.trim())
      setSegments(s => s.map(x => x.id === id ? { ...x, name: editingName.trim() } : x))
      cancelEdit()
    } catch (e) { alert(e.response?.data?.detail || t('admin.alertRenameFailed')) }
  }

  const handleDeleteSegment = async (id, name) => {
    if (!window.confirm(t('admin.confirmDeleteSegment', { name }))) return
    try {
      await adminDeleteSegment(id)
      setSegments(s => s.filter(x => x.id !== id))
    } catch (e) { alert(e.response?.data?.detail || t('admin.alertDeleteFailed')) }
  }

  if (loading) return <div className="loading-center"><div className="spinner" /></div>

  if (error) return (
    <div className="empty-state">
      <div className="empty-state-icon"><Shield size={48} /></div>
      <h3>{error}</h3>
    </div>
  )

  const thStyle = { padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }
  const tdStyle = { padding: '11px 16px', borderBottom: '1px solid var(--border)' }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          <Shield size={20} style={{ display: 'inline', marginRight: 8, color: 'var(--accent)' }} />
          {t('admin.title')}
        </h1>
        <p className="page-subtitle">{t('admin.subtitle')}</p>
      </div>

      {/* ── Stats ────────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14, marginBottom: 24 }}>
        <StatCard icon={Users}    label={t('admin.statTotalUsers')}      value={stats.total_users}      color="var(--accent)" />
        <StatCard icon={Activity} label={t('admin.statTotalActivities')} value={stats.total_activities}  color="var(--speed)" />
        <StatCard icon={Zap}      label={t('admin.statTotalDistance')}   value={`${stats.total_distance_km.toLocaleString()} km`} color="var(--cadence)" />
        <StatCard icon={Mountain} label={t('admin.statTotalElevation')}  value={`${stats.total_elevation_m.toLocaleString()} m`}  color="var(--heart)" />
      </div>

      {/* ── Chart + System ───────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 260px', gap: 14, marginBottom: 24 }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px 10px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-secondary)' }}>
            {t('admin.weeklySignupsChartTitle')}
          </div>
          <div style={{ padding: '16px 8px 8px' }}>
            <ResponsiveContainer width="100%" height={140}>
              <BarChart data={stats.weekly_signups} barSize={18}>
                <XAxis dataKey="week" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} width={24} />
                <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} cursor={{ fill: 'var(--border)' }} />
                <Bar dataKey="signups" radius={[4, 4, 0, 0]}>
                  {stats.weekly_signups.map((_, i) => (
                    <Cell key={i} fill={i === stats.weekly_signups.length - 1 ? 'var(--accent)' : 'var(--border)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card" style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-secondary)' }}>{t('admin.systemTitle')}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Clock size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('admin.systemUptime')}</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{fmtUptime(system.uptime_seconds)}</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Database size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('admin.systemDatabase')}</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{fmtBytes(system.db_size_bytes)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Users ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 8, fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
        {t('admin.usersSection', { count: users.length })}
      </div>
      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 28 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={thStyle}>{t('admin.colUsername')}</th>
              <th style={thStyle}>{t('admin.colEmail')}</th>
              <th style={thStyle}>{t('admin.colJoined')}</th>
              <th style={thStyle}>{t('admin.colActivities')}</th>
              <th style={thStyle}>{t('admin.colSubscription')}</th>
              <th style={thStyle}>{t('admin.colMembership')}</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>{t('admin.colActions')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td style={{ ...tdStyle, color: 'var(--text-primary)', fontWeight: u.is_admin ? 700 : 400 }}>
                  {u.username}
                  {u.is_admin && (
                    <span style={{ marginLeft: 8, fontSize: 10, background: 'var(--accent)', color: 'oklch(8% 0.015 120)', borderRadius: 4, padding: '1px 6px', fontWeight: 700 }}>
                      {t('admin.adminBadge')}
                    </span>
                  )}
                </td>
                <td style={{ ...tdStyle, color: 'var(--text-muted)', fontSize: 12 }}>
                  {u.email || <span style={{ opacity: 0.4 }}>—</span>}
                </td>
                <td style={{ ...tdStyle, color: 'var(--text-muted)' }}>
                  {u.created_at ? format(new Date(u.created_at), 'dd MMM yyyy') : '—'}
                </td>
                <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>{u.activity_count}</td>
                <td style={{ ...tdStyle, fontSize: 12, color: 'var(--text-muted)' }}>
                  {u.subscription_start || u.subscription_end ? (
                    <div style={{ lineHeight: 1.6 }}>
                      {u.subscription_start && (
                        <div><span style={{ opacity: 0.55 }}>{t('admin.subscriptionFrom')} </span>{format(new Date(u.subscription_start), 'dd MMM yyyy')}</div>
                      )}
                      {u.subscription_end && u.membership !== 'lifetime' && (
                        <div><span style={{ opacity: 0.55 }}>{t('admin.subscriptionTo')} </span>{format(new Date(u.subscription_end), 'dd MMM yyyy')}</div>
                      )}
                      {u.membership === 'lifetime' && (
                        <div style={{ color: 'var(--tier-lifetime)' }}>{t('admin.subscriptionNeverExpires')}</div>
                      )}
                    </div>
                  ) : (
                    <span style={{ opacity: 0.35 }}>—</span>
                  )}
                </td>
                <td style={tdStyle}>
                  {membershipEditId === u.id ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <select
                        value={membershipDraft}
                        onChange={e => setMembershipDraft(e.target.value)}
                        autoFocus
                        style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12 }}
                      >
                        <option value="free">{t('admin.membershipFree')}</option>
                        <option value="pro">{t('admin.membershipPro')}</option>
                        <option value="annual">{t('admin.membershipAnnual')}</option>
                        <option value="lifetime">{t('admin.membershipLifetime')}</option>
                      </select>
                      <button style={{ ...btnStyle('accent'), color: 'var(--accent)', borderColor: 'var(--accent)' }} onClick={() => saveMembership(u.id)}>
                        <Check size={12} />
                      </button>
                      <button style={btnStyle()} onClick={() => setMembershipEditId(null)}>
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <div
                      style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
                      onClick={() => { setMembershipEditId(u.id); setMembershipDraft(u.membership || 'free') }}
                      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (setMembershipEditId(u.id), setMembershipDraft(u.membership || 'free'))}
                      tabIndex={0}
                      role="button"
                      aria-label={t('admin.editMembershipAriaLabel', { username: u.username })}
                    >
                      <MembershipBadge tier={u.membership || 'free'} />
                      <Pencil size={11} style={{ color: 'var(--text-muted)', opacity: 0.5 }} />
                    </div>
                  )}
                </td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>
                  {!u.is_admin && (
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', alignItems: 'center' }}>
                      {u.email && u.membership !== 'lifetime' && (
                        <button
                          onClick={() => handleSendOffer(u)}
                          title={t('admin.sendOfferTitle')}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 5,
                            padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                            cursor: 'pointer',
                            background: offerSentIds.has(u.id) ? 'color-mix(in srgb, var(--accent) 9%, transparent)' : 'transparent',
                            border: offerSentIds.has(u.id) ? '1px solid color-mix(in srgb, var(--accent) 31%, transparent)' : '1px solid color-mix(in srgb, var(--accent) 19%, transparent)',
                            color: offerSentIds.has(u.id) ? 'var(--accent)' : 'color-mix(in srgb, var(--accent) 44%, transparent)',
                          }}
                        >
                          <Mail size={11} />
                          {offerSentIds.has(u.id) ? t('admin.offerSentBtn') : t('admin.sendOfferBtn')}
                        </button>
                      )}
                      <button style={btnStyle('danger')} onClick={() => handleDeleteUser(u.id, u.username)}>
                        <Trash2 size={12} /> {t('admin.deleteUserBtn')}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>{t('admin.noUsersYet')}</div>}
      </div>

      {/* ── Segments ─────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 8, fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
        {t('admin.segmentsSection', { count: segments.length })}
      </div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={thStyle}>{t('admin.colName')}</th>
              <th style={thStyle}>{t('admin.colCreatedBy')}</th>
              <th style={thStyle}>{t('admin.colCreated')}</th>
              <th style={thStyle}>{t('admin.colEfforts')}</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>{t('admin.colActions')}</th>
            </tr>
          </thead>
          <tbody>
            {segments.map(s => (
              <tr key={s.id}>
                <td style={{ ...tdStyle, color: 'var(--text-primary)', fontWeight: 500 }}>
                  {editingId === s.id ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <input
                        value={editingName}
                        onChange={e => setEditingName(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') saveEdit(s.id); if (e.key === 'Escape') cancelEdit() }}
                        autoFocus
                        style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid var(--accent)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 13, width: 200 }}
                      />
                      <button style={{ ...btnStyle('accent'), color: 'var(--accent)', borderColor: 'var(--accent)' }} onClick={() => saveEdit(s.id)}>
                        <Check size={12} /> {t('admin.saveBtnLabel')}
                      </button>
                      <button style={btnStyle()} onClick={cancelEdit}>
                        <X size={12} /> {t('admin.cancelBtnLabel')}
                      </button>
                    </div>
                  ) : s.name}
                </td>
                <td style={{ ...tdStyle, color: 'var(--text-muted)' }}>{s.created_by}</td>
                <td style={{ ...tdStyle, color: 'var(--text-muted)' }}>
                  {s.created_at ? format(new Date(s.created_at), 'dd MMM yyyy') : '—'}
                </td>
                <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>{s.effort_count}</td>
                <td style={{ ...tdStyle }}>
                  {transferId === s.id ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                      <select
                        value={transferUserId}
                        onChange={e => setTransferUserId(e.target.value)}
                        autoFocus
                        style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12 }}
                      >
                        <option value="">{t('admin.pickOwnerPlaceholder')}</option>
                        {users.filter(u => u.username !== s.created_by).map(u => (
                          <option key={u.id} value={u.id}>{u.username}</option>
                        ))}
                      </select>
                      <button style={{ ...btnStyle('accent'), color: 'var(--accent)', borderColor: 'var(--accent)' }} onClick={() => saveTransfer(s.id, s.name)} disabled={!transferUserId}>
                        <Check size={12} /> {t('admin.confirmBtnLabel')}
                      </button>
                      <button style={btnStyle()} onClick={cancelTransfer}>
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      {editingId !== s.id && (
                        <>
                          <button style={btnStyle()} onClick={() => setViewSegment(s)}>
                            <Eye size={12} /> {t('admin.viewBtnLabel')}
                          </button>
                          <button style={btnStyle()} onClick={() => startEdit(s)}>
                            <Pencil size={12} /> {t('admin.renameBtnLabel')}
                          </button>
                          <button style={btnStyle()} onClick={() => startTransfer(s)}>
                            <ArrowRightLeft size={12} /> {t('admin.transferBtnLabel')}
                          </button>
                        </>
                      )}
                      <button style={btnStyle('danger')} onClick={() => handleDeleteSegment(s.id, s.name)}>
                        <Trash2 size={12} /> {t('admin.deleteBtnLabel')}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {segments.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>{t('admin.noSegmentsYet')}</div>}
      </div>

      {/* ── Segment map modal ─────────────────────────────────────────── */}
      {viewSegment && (() => {
        const positions = getPositions(viewSegment)
        const start = positions[0]
        const end   = positions[positions.length - 1]
        return (
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 2000, background: 'oklch(4% 0.006 142 / 0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            onClick={() => setViewSegment(null)}
          >
            <div
              ref={modalRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="segment-modal-title"
              onKeyDown={handleModalKeyDown}
              style={{ width: 'min(640px, calc(100vw - 32px))', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 64px oklch(4% 0.006 142 / 0.6)', position: 'relative' }}
              onClick={e => e.stopPropagation()}
            >
              {/* Header */}
              <div style={{ background: 'var(--surface)', padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)' }}>
                <div>
                  <div id="segment-modal-title" style={{ fontWeight: 700, fontSize: 14 }}>{viewSegment.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                    {t('admin.segmentModalBy', { creator: viewSegment.created_by, count: viewSegment.effort_count })}
                  </div>
                </div>
                <button onClick={() => setViewSegment(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
                  <X size={18} />
                </button>
              </div>

              {/* Map */}
              <MapContainer
                key={viewSegment.id}
                bounds={positions}
                boundsOptions={{ padding: [40, 40] }}
                style={{ height: 380, width: '100%', background: '#0d0d1a' }}
                zoomControl={true}
                scrollWheelZoom={true}
              >
                <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="" />
                <Polyline positions={positions} color="var(--accent)" weight={3} />
                <CircleMarker center={start} radius={6} pathOptions={{ color: '#4dff91', fillColor: '#4dff91', fillOpacity: 1 }} />
                <CircleMarker center={end}   radius={6} pathOptions={{ color: '#ff4d4d', fillColor: '#ff4d4d', fillOpacity: 1 }} />
              </MapContainer>

              {/* Legend */}
              <div style={{ background: 'var(--surface)', padding: '8px 16px', display: 'flex', gap: 20, fontSize: 12, color: 'var(--text-muted)' }}>
                <span><span style={{ color: '#4dff91', fontWeight: 700 }}>●</span> {t('admin.segmentModalStart')}</span>
                <span><span style={{ color: '#ff4d4d', fontWeight: 700 }}>●</span> {t('admin.segmentModalEnd')}</span>
                <span style={{ marginLeft: 'auto' }}>{t('admin.segmentModalClickToClose')}</span>
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}
