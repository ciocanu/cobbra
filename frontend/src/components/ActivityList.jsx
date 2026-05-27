import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getActivities } from '../services/api'
import { format } from 'date-fns'
import { Route, Search, X } from 'lucide-react'

function fmtDuration(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export default function ActivityList() {
  const [activities, setActivities] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [minDist, setMinDist] = useState('')
  const [maxDist, setMaxDist] = useState('')
  const navigate = useNavigate()

  const fetchActivities = useCallback(() => {
    const params = {}
    if (search) params.search = search
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    if (minDist) params.min_distance_km = minDist
    if (maxDist) params.max_distance_km = maxDist

    setLoading(true)
    getActivities(params)
      .then(r => setActivities(r.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [search, dateFrom, dateTo, minDist, maxDist])

  useEffect(() => {
    fetchActivities()
  }, [fetchActivities])

  const hasFilters = search || dateFrom || dateTo || minDist || maxDist
  const clearFilters = () => {
    setSearch('')
    setDateFrom('')
    setDateTo('')
    setMinDist('')
    setMaxDist('')
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="page-title">Activities</h1>
          <p className="page-subtitle">{activities.length} rides{hasFilters ? ' (filtered)' : ' recorded'}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-search">
          <Search size={14} className="filter-search-icon" />
          <input
            className="filter-input filter-input-search"
            placeholder="Search by name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <input
          type="date"
          className="filter-input"
          value={dateFrom}
          onChange={e => setDateFrom(e.target.value)}
          title="From date"
        />
        <input
          type="date"
          className="filter-input"
          value={dateTo}
          onChange={e => setDateTo(e.target.value)}
          title="To date"
        />
        <input
          type="number"
          className="filter-input filter-input-dist"
          placeholder="Min km"
          value={minDist}
          onChange={e => setMinDist(e.target.value)}
          min="0"
        />
        <input
          type="number"
          className="filter-input filter-input-dist"
          placeholder="Max km"
          value={maxDist}
          onChange={e => setMaxDist(e.target.value)}
          min="0"
        />
        {hasFilters && (
          <button className="btn btn-ghost" onClick={clearFilters} style={{ padding: '6px 10px' }}>
            <X size={14} /> Clear
          </button>
        )}
      </div>

      {loading ? (
        <div className="loading-center"><div className="spinner" /></div>
      ) : activities.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Route size={48} /></div>
          <h3>{hasFilters ? 'No rides match your filters' : 'No activities yet'}</h3>
          <p>{hasFilters ? 'Try adjusting or clearing the filters' : 'Upload a .gpx or .fit file to see your rides here'}</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Date</th>
                <th scope="col">Distance</th>
                <th scope="col">Time</th>
                <th scope="col">Avg Speed</th>
                <th scope="col">Max Speed</th>
                <th scope="col">Avg HR</th>
                <th scope="col">Cadence</th>
                <th scope="col">Avg Power</th>
                <th scope="col">Suffer</th>
                <th scope="col">Elevation</th>
                <th scope="col">Type</th>
              </tr>
            </thead>
            <tbody>
              {activities.map(a => (
                <tr
                  key={a.id}
                  onClick={() => navigate(`/activities/${a.id}`)}
                  onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && navigate(`/activities/${a.id}`)}
                  tabIndex={0}
                  role="button"
                  aria-label={`Open ${a.name}`}
                >
                  <td className="name">{a.name}</td>
                  <td>{format(new Date(a.date), 'dd MMM yy')}</td>
                  <td className="accent">{a.distance_km.toFixed(2)} km</td>
                  <td>{fmtDuration(a.duration_seconds)}</td>
                  <td style={{ color: 'var(--speed)' }}>{a.avg_speed_kmh.toFixed(1)} km/h</td>
                  <td>{a.max_speed_kmh.toFixed(1)} km/h</td>
                  <td>
                    {a.avg_heart_rate_bpm
                      ? <span style={{ color: 'var(--heart)' }}>{Math.round(a.avg_heart_rate_bpm)} bpm</span>
                      : <span style={{ color: 'var(--text-muted)' }}>—</span>
                    }
                  </td>
                  <td>
                    {a.avg_cadence_rpm
                      ? <span style={{ color: 'var(--cadence)' }}>{Math.round(a.avg_cadence_rpm)} rpm</span>
                      : <span style={{ color: 'var(--text-muted)' }}>—</span>
                    }
                  </td>
                  <td>
                    {a.avg_power_w
                      ? <span style={{ color: 'var(--power)' }}>{Math.round(a.avg_power_w)} W</span>
                      : <span style={{ color: 'var(--text-muted)' }}>—</span>
                    }
                  </td>
                  <td>
                    {a.suffer_score != null
                      ? <span style={{ color: 'var(--heart)' }}>{a.suffer_score}</span>
                      : <span style={{ color: 'var(--text-muted)' }}>—</span>
                    }
                  </td>
                  <td style={{ color: 'var(--elevation)' }}>↑ {a.elevation_gain_m.toFixed(0)} m</td>
                  <td>
                    <span className={`badge badge-${a.file_type}`}>{a.file_type.toUpperCase()}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
