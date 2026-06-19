import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getActivities } from '../services/api'
import { format } from 'date-fns'
import { Route, Search, X, RefreshCw } from 'lucide-react'
import Alert from './Alert'

function fmtDuration(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export default function ActivityList() {
  const { t } = useTranslation()
  const [activities, setActivities] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
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
    setError(null)
    getActivities(params)
      .then(r => setActivities(r.data))
      .catch(e => { console.error(e); setError(e) })
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
          <h1 className="page-title">{t('activityList.title')}</h1>
          <p className="page-subtitle">
            {hasFilters
              ? t('activityList.countFiltered', { count: activities.length })
              : t('activityList.countRecorded', { count: activities.length })}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-search">
          <Search size={14} className="filter-search-icon" />
          <input
            className="filter-input filter-input-search"
            placeholder={t('activityList.searchPlaceholder')}
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <input
          type="date"
          className="filter-input"
          value={dateFrom}
          onChange={e => setDateFrom(e.target.value)}
          title={t('activityList.fromDate')}
        />
        <input
          type="date"
          className="filter-input"
          value={dateTo}
          onChange={e => setDateTo(e.target.value)}
          title={t('activityList.toDate')}
        />
        <input
          type="number"
          className="filter-input filter-input-dist"
          placeholder={t('activityList.minKm')}
          value={minDist}
          onChange={e => setMinDist(e.target.value)}
          min="0"
        />
        <input
          type="number"
          className="filter-input filter-input-dist"
          placeholder={t('activityList.maxKm')}
          value={maxDist}
          onChange={e => setMaxDist(e.target.value)}
          min="0"
        />
        {hasFilters && (
          <button className="btn btn-ghost" onClick={clearFilters} style={{ padding: '6px 10px' }}>
            <X size={14} /> {t('common.clear')}
          </button>
        )}
      </div>

      {error ? (
        <div className="empty-state">
          <Alert variant="error" style={{ marginBottom: 16 }}>{t('common.errorLoad')}</Alert>
          <button className="btn btn-ghost" onClick={fetchActivities}>
            <RefreshCw size={14} /> {t('common.retry')}
          </button>
        </div>
      ) : loading ? (
        <div className="loading-center"><div className="spinner" /></div>
      ) : activities.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Route size={48} /></div>
          <h3>{hasFilters ? t('activityList.emptyFilteredTitle') : t('activityList.emptyTitle')}</h3>
          <p>{hasFilters ? t('activityList.emptyFilteredDesc') : t('activityList.emptyDesc')}</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t('activityList.col.name')}</th>
                <th scope="col">{t('activityList.col.date')}</th>
                <th scope="col">{t('activityList.col.distance')}</th>
                <th scope="col">{t('activityList.col.time')}</th>
                <th scope="col">{t('activityList.col.avgSpeed')}</th>
                <th scope="col">{t('activityList.col.maxSpeed')}</th>
                <th scope="col">{t('activityList.col.avgHr')}</th>
                <th scope="col">{t('activityList.col.cadence')}</th>
                <th scope="col">{t('activityList.col.avgPower')}</th>
                <th scope="col">{t('activityList.col.suffer')}</th>
                <th scope="col">{t('activityList.col.elevation')}</th>
                <th scope="col">{t('activityList.col.type')}</th>
              </tr>
            </thead>
            <tbody>
              {activities.map((a, i) => (
                <tr
                  key={a.id}
                  className="act-row"
                  style={{ '--row-delay': `${Math.min(i, 15) * 22}ms` }}
                  onClick={() => navigate(`/activities/${a.id}`)}
                  onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && navigate(`/activities/${a.id}`)}
                  tabIndex={0}
                  role="button"
                  aria-label={t('activityList.openAria', { name: a.name })}
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
