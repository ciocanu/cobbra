import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, Polyline, CircleMarker, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { createSegment, deleteSegment, getSegmentEfforts, getSegmentTrend } from '../services/api'
import { useSegments, useHeatmap, useMe, useInvalidate } from '../services/queries'
import { format } from 'date-fns'
import { Flag, Trash2, ChevronDown, ChevronUp, Plus, X, MapPin, Trophy, User, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { colors } from '../tokens'

function fmtTime(s) {
  const sec = Math.round(s)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const ss = sec % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
    : `${m}:${String(ss).padStart(2, '0')}`
}

function MapClickHandler({ active, onPoint }) {
  useMapEvents({
    click(e) {
      if (active) onPoint([e.latlng.lat, e.latlng.lng])
    },
  })
  return null
}

function wpColor(i, total) {
  if (i === 0) return '#6dffb8'
  if (i === total - 1) return '#ff4d6d'
  return '#ffd93d'
}

const MEDAL = ['🥇', '🥈', '🥉']

export default function Segments() {
  const segmentsQuery = useSegments()
  const heatmapQuery = useHeatmap()
  useMe()
  const invalidate = useInvalidate()
  const segments = segmentsQuery.data ?? []
  const routes = heatmapQuery.data ?? []
  const loading = segmentsQuery.isPending || heatmapQuery.isPending
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [waypoints, setWaypoints] = useState([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [leaderboard, setLeaderboard] = useState({})
  const [trend, setTrend] = useState({})
  const navigate = useNavigate()

  const handleMapPoint = useCallback((pt) => {
    setWaypoints(prev => [...prev, pt])
    setSaveError('')
  }, [])

  const removeWaypoint = (idx) => setWaypoints(prev => prev.filter((_, i) => i !== idx))

  const cancelCreating = () => {
    setCreating(false)
    setNewName('')
    setWaypoints([])
    setSaveError('')
  }

  const handleSave = async () => {
    if (!newName.trim() || waypoints.length < 2) return
    setSaving(true)
    setSaveError('')
    try {
      await createSegment({ name: newName.trim(), waypoints })
      invalidate.segments()
      cancelCreating()
    } catch (e) {
      setSaveError(e.response?.data?.detail || 'Failed to save segment')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id, e) => {
    e.stopPropagation()
    if (!confirm('Delete this segment?')) return
    await deleteSegment(id)
    invalidate.segments()
    if (expanded === id) setExpanded(null)
  }

  const toggleExpand = async (seg) => {
    if (expanded === seg.id) { setExpanded(null); return }
    setExpanded(seg.id)
    if (!leaderboard[seg.id]) {
      const [lbRes, trendRes] = await Promise.all([
        getSegmentEfforts(seg.id),
        getSegmentTrend(seg.id),
      ])
      setLeaderboard(prev => ({ ...prev, [seg.id]: lbRes.data }))
      setTrend(prev => ({ ...prev, [seg.id]: trendRes.data }))
    }
  }

  const mapCenter = routes.length > 0
    ? (() => {
        const all = routes.flatMap(r => r.points)
        if (!all.length) return [38.5, -9.0]
        return [
          all.reduce((s, p) => s + p[0], 0) / all.length,
          all.reduce((s, p) => s + p[1], 0) / all.length,
        ]
      })()
    : [38.5, -9.0]

  const stepLabel = waypoints.length === 0
    ? 'Click on the map to add the start point'
    : waypoints.length === 1
      ? 'Add more points along the route (minimum 1 more to finish)'
      : `${waypoints.length} points set — add more or save`

  if (loading) return <div className="loading-center"><div className="spinner" /></div>

  const uniqueRiders = (seg) => {
    const lb = leaderboard[seg.id]
    if (lb) return lb.length
    return null
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="page-title">
            <Flag size={22} style={{ display: 'inline', marginRight: 8, color: 'var(--accent)' }} />
            Segments
          </h1>
          <p className="page-subtitle">{segments.length} public segment{segments.length !== 1 ? 's' : ''} · ride through one to appear on the leaderboard</p>
        </div>
        {!creating && (
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> New Segment
          </button>
        )}
      </div>

      {/* Creation panel */}
      {creating && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontWeight: 600 }}>New Segment</span>
            <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={cancelCreating}>
              <X size={14} />
            </button>
          </div>

          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>{stepLabel}</p>

          {waypoints.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
              {waypoints.map((wp, i) => (
                <div key={i} className="segment-point-badge" style={{
                  background: `${wpColor(i, waypoints.length)}18`,
                  borderColor: wpColor(i, waypoints.length),
                  fontSize: 12,
                }}>
                  <MapPin size={10} style={{ color: wpColor(i, waypoints.length) }} />
                  <span style={{ color: wpColor(i, waypoints.length) }}>
                    {i === 0 ? 'Start' : i === waypoints.length - 1 ? 'End' : `P${i + 1}`}
                    {' '}{wp[0].toFixed(4)}, {wp[1].toFixed(4)}
                  </span>
                  <button
                    onClick={() => removeWaypoint(i)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '0 2px', lineHeight: 1 }}
                  >✕</button>
                </div>
              ))}
            </div>
          )}

          {waypoints.length >= 2 && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                className="filter-input"
                placeholder="Segment name"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSave()}
                style={{ width: 220 }}
                autoFocus
              />
              <button className="btn btn-primary" onClick={handleSave} disabled={saving || !newName.trim()}>
                {saving ? 'Saving…' : `Save Segment (${waypoints.length} pts)`}
              </button>
              <button className="btn btn-ghost" onClick={() => setWaypoints([])}>Clear All</button>
            </div>
          )}

          {saveError && (
            <div className="alert alert-error" style={{ marginTop: 10 }}>{saveError}</div>
          )}
        </div>
      )}

      {/* Map */}
      <div className="map-container" style={{ height: 420, marginBottom: 24, cursor: creating ? 'crosshair' : 'default' }}>
        <MapContainer center={mapCenter} zoom={11} style={{ height: '100%', width: '100%', background: '#0d0d1a' }}>
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          />
          <MapClickHandler active={creating} onPoint={handleMapPoint} />

          {routes.map(r => (
            <Polyline key={r.id} positions={r.points}
              pathOptions={{ color: colors.accent, weight: 1.5, opacity: 0.2 }} />
          ))}

          {segments.map(seg => (
            <Polyline key={`path-${seg.id}`} positions={seg.waypoints}
              pathOptions={{ color: '#ffffff', weight: 2.5, opacity: 0.55 }} />
          ))}
          {segments.map(seg => (
            <CircleMarker key={`s-${seg.id}`} center={seg.waypoints[0]} radius={6}
              pathOptions={{ color: '#6dffb8', fillColor: '#6dffb8', fillOpacity: 0.9 }} />
          ))}
          {segments.map(seg => (
            <CircleMarker key={`e-${seg.id}`} center={seg.waypoints[seg.waypoints.length - 1]} radius={6}
              pathOptions={{ color: '#ff4d6d', fillColor: '#ff4d6d', fillOpacity: 0.9 }} />
          ))}

          {waypoints.length >= 2 && (
            <Polyline positions={waypoints}
              pathOptions={{ color: colors.accent, weight: 2.5, opacity: 0.9 }} />
          )}
          {waypoints.map((wp, i) => (
            <CircleMarker key={`new-${i}`} center={wp} radius={i === 0 || i === waypoints.length - 1 ? 8 : 5}
              pathOptions={{ color: wpColor(i, waypoints.length), fillColor: wpColor(i, waypoints.length), fillOpacity: 1 }}
            />
          ))}
        </MapContainer>
      </div>

      {creating && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 12, color: 'var(--text-muted)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#6dffb8', display: 'inline-block' }} /> Start
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ffd93d', display: 'inline-block' }} /> Intermediate
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff4d6d', display: 'inline-block' }} /> End
          </span>
        </div>
      )}

      {/* Segments list */}
      {segments.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Flag size={48} /></div>
          <h3>No segments yet</h3>
          <p>Click "New Segment" and trace your route on the map — it becomes public for all riders</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {segments.map(seg => {
            const lb = leaderboard[seg.id]
            const myEffort = lb?.find(e => e.is_me)
            const myRank = lb ? lb.findIndex(e => e.is_me) + 1 : null

            return (
              <div key={seg.id} className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div
                  className="segment-row"
                  onClick={() => toggleExpand(seg)}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpand(seg) } }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${seg.name} segment details`}
                  aria-expanded={expanded === seg.id}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3, flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 600 }}>{seg.name}</span>
                      <span className="segment-creator-badge">
                        <User size={10} /> {seg.created_by}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                      <span>{seg.waypoints.length} pts</span>
                      <span>{seg.effort_count} effort{seg.effort_count !== 1 ? 's' : ''}</span>
                      {seg.best_time && (
                        <span>
                          KOM: <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-display)' }}>{fmtTime(seg.best_time)}</span>
                          {seg.best_speed && <span> @ {seg.best_speed} km/h</span>}
                        </span>
                      )}
                      {myRank > 0 && (
                        <span style={{ color: myRank === 1 ? 'var(--accent)' : 'var(--text-secondary)' }}>
                          {myRank <= 3 ? MEDAL[myRank - 1] : `#${myRank}`} You
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                    {seg.is_mine && (
                      <button className="btn btn-ghost" style={{ padding: '4px 8px' }}
                        aria-label={`Delete ${seg.name} segment`}
                        onClick={(e) => handleDelete(seg.id, e)}>
                        <Trash2 size={13} />
                      </button>
                    )}
                    {expanded === seg.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </div>
                </div>

                {expanded === seg.id && (() => {
                  const lb = leaderboard[seg.id]
                  const myTrend = trend[seg.id]
                  const hrTrend = myTrend?.filter(e => e.avg_hr != null) ?? []
                  const hasTrend = hrTrend.length >= 2

                  // EF = speed / HR × 100. Compute first vs last to show direction
                  const efFirst = hrTrend.length >= 2 && hrTrend[0].avg_speed_kmh
                    ? (hrTrend[0].avg_speed_kmh / hrTrend[0].avg_hr) * 100 : null
                  const efLast = hrTrend.length >= 2 && hrTrend[hrTrend.length - 1].avg_speed_kmh
                    ? (hrTrend[hrTrend.length - 1].avg_speed_kmh / hrTrend[hrTrend.length - 1].avg_hr) * 100 : null
                  const efDelta = efFirst && efLast ? ((efLast - efFirst) / efFirst) * 100 : null
                  const efImproving = efDelta !== null && efDelta > 2
                  const efDeclining = efDelta !== null && efDelta < -2

                  const chartData = hrTrend.map((e, i) => ({
                    n: i + 1,
                    label: format(new Date(e.date), 'dd MMM'),
                    hr: e.avg_hr ? Math.round(e.avg_hr) : null,
                    ef: e.avg_speed_kmh && e.avg_hr
                      ? Math.round((e.avg_speed_kmh / e.avg_hr) * 1000) / 10
                      : null,
                  }))

                  return (
                    <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px' }}>
                      {!lb ? (
                        <div className="loading-center" style={{ padding: 20 }}><div className="spinner" /></div>
                      ) : lb.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                          No efforts yet — upload a ride that passes through this segment.
                        </p>
                      ) : (
                        <>
                          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Trophy size={11} style={{ color: 'var(--accent)' }} /> Leaderboard
                          </div>
                          <table className="table" style={{ marginBottom: 0 }}>
                            <thead>
                              <tr>
                                <th scope="col">#</th>
                                <th scope="col">Rider</th>
                                <th scope="col">Time</th>
                                <th scope="col">Speed</th>
                                <th scope="col">Avg HR</th>
                                <th scope="col">Date</th>
                              </tr>
                            </thead>
                            <tbody>
                              {lb.map((e, i) => (
                                <tr
                                  key={e.id}
                                  onClick={() => e.is_me && navigate(`/activities/${e.activity_id}`)}
                                  tabIndex={e.is_me ? 0 : undefined}
                                  role={e.is_me ? 'button' : undefined}
                                  aria-label={e.is_me ? `View your effort: ${fmtTime(e.elapsed_seconds)}${e.avg_speed_kmh ? ` at ${e.avg_speed_kmh} km/h` : ''} · ${format(new Date(e.set_at), 'dd MMM yyyy')}` : undefined}
                                  onKeyDown={e.is_me ? (ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); navigate(`/activities/${e.activity_id}`) } }) : undefined}
                                  style={{
                                    cursor: e.is_me ? 'pointer' : 'default',
                                    background: e.is_me ? 'color-mix(in srgb, var(--accent) 4%, transparent)' : undefined,
                                  }}
                                >
                                  <td>
                                    {i < 3
                                      ? <span style={{ fontSize: 14 }}>{MEDAL[i]}</span>
                                      : <span style={{ color: 'var(--text-muted)' }}>{i + 1}</span>
                                    }
                                  </td>
                                  <td>
                                    <span style={{ fontWeight: e.is_me ? 700 : 400, color: e.is_me ? 'var(--accent)' : 'var(--text-primary)' }}>
                                      {e.username}
                                      {e.is_me && <span style={{ fontSize: 10, marginLeft: 5, color: 'var(--text-muted)', fontWeight: 400 }}>you</span>}
                                    </span>
                                  </td>
                                  <td style={{ fontFamily: 'var(--font-display)', color: i === 0 ? 'var(--accent)' : 'var(--text-primary)' }}>
                                    {fmtTime(e.elapsed_seconds)}
                                  </td>
                                  <td>{e.avg_speed_kmh ? `${e.avg_speed_kmh} km/h` : '—'}</td>
                                  <td>{e.avg_hr ? <span style={{ color: 'var(--heart)' }}>{Math.round(e.avg_hr)} bpm</span> : '—'}</td>
                                  <td style={{ color: 'var(--text-muted)' }}>{format(new Date(e.set_at), 'dd MMM yyyy')}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </>
                      )}

                      {/* Personal HR efficiency trend */}
                      {hasTrend && (
                        <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                              Your HR Efficiency Trend
                              <span style={{ fontSize: 10, fontWeight: 400, color: 'var(--text-muted)', textTransform: 'none', letterSpacing: 0 }}>
                                ({hrTrend.length} efforts with HR data)
                              </span>
                            </div>
                            {efDelta !== null && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12,
                                color: efImproving ? '#6dffb8' : efDeclining ? '#ff8c42' : 'var(--text-muted)' }}>
                                {efImproving
                                  ? <TrendingUp size={14} />
                                  : efDeclining
                                    ? <TrendingDown size={14} />
                                    : <Minus size={14} />}
                                EF {efImproving ? '+' : ''}{Math.round(efDelta * 10) / 10}%
                                <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
                                  {efImproving ? '— aerobic fitness improving'
                                    : efDeclining ? '— worth investigating'
                                    : '— stable'}
                                </span>
                              </div>
                            )}
                          </div>

                          <ResponsiveContainer width="100%" height={130}>
                            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                              <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                              <YAxis yAxisId="hr"  tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} unit=" bpm" width={52} />
                              <YAxis yAxisId="ef"  orientation="right" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
                              <Tooltip
                                contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-bright)', borderRadius: 6, fontSize: 12 }}
                                formatter={(v, name) => name === 'HR' ? [`${v} bpm`, 'HR'] : [`${v}`, 'EF']}
                                labelFormatter={l => `Effort ${chartData.findIndex(d => d.label === l) + 1} · ${l}`}
                              />
                              <Line yAxisId="hr" type="monotone" dataKey="hr" stroke="var(--heart)" strokeWidth={2} dot={{ r: 4, fill: 'var(--heart)' }} name="HR" connectNulls />
                              <Line yAxisId="ef" type="monotone" dataKey="ef" stroke="#6dffb8" strokeWidth={1.5} dot={false} strokeDasharray="4 2" name="EF" connectNulls />
                            </LineChart>
                          </ResponsiveContainer>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
                            HR (solid) · EF = speed/HR×10 (dashed) · Falling HR or rising EF = aerobic adaptation. Min 8–10 efforts for a reliable trend.
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })()}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
