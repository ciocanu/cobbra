import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { MapContainer, TileLayer, Polyline, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useHeatmap } from '../services/queries'
import { Map, RefreshCw } from 'lucide-react'
import { colors } from '../tokens'
import Alert from './Alert'

export default function Heatmap() {
  const { t } = useTranslation()
  const { data: routes = [], isPending: loading, isError: error, refetch } = useHeatmap()

  const center = useMemo(() => {
    const allPts = routes.flatMap(r => r.points)
    if (!allPts.length) return [38.5, -9.0]
    const lat = allPts.reduce((s, p) => s + p[0], 0) / allPts.length
    const lon = allPts.reduce((s, p) => s + p[1], 0) / allPts.length
    return [lat, lon]
  }, [routes])

  if (loading) return <div className="loading-center"><div className="spinner" /></div>
  if (error) return (
    <div className="empty-state">
      <Alert variant="error" style={{ marginBottom: 16 }}>{t('common.errorLoad')}</Alert>
      <button className="btn btn-ghost" onClick={() => refetch()}>
        <RefreshCw size={14} /> {t('common.retry')}
      </button>
    </div>
  )

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('heatmap.title')}</h1>
        <p className="page-subtitle">{t('heatmap.subtitle', { count: routes.length })}</p>
      </div>

      {routes.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Map size={48} /></div>
          <h3>{t('heatmap.emptyTitle')}</h3>
          <p>{t('heatmap.emptyDesc')}</p>
        </div>
      ) : (
        <div className="map-container" style={{ height: 600 }}>
          <MapContainer
            center={center}
            zoom={11}
            style={{ height: '100%', width: '100%', background: '#0d0d1a' }}
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://carto.com/">CARTO</a>'
            />
            {routes.map(route => (
              <Polyline
                key={route.id}
                positions={route.points}
                pathOptions={{ color: colors.accent, weight: 2, opacity: 0.5 }}
              >
                <Tooltip sticky>
                  <span style={{ fontSize: 12 }}>
                    {route.name} · {route.distance_km.toFixed(1)} km
                  </span>
                </Tooltip>
              </Polyline>
            ))}
          </MapContainer>
        </div>
      )}
    </div>
  )
}
