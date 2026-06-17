import { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, Polyline, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { getHeatmap } from '../services/api'
import { Map } from 'lucide-react'
import { colors } from '../tokens'

export default function Heatmap() {
  const [routes, setRoutes] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getHeatmap()
      .then(r => setRoutes(r.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const center = useMemo(() => {
    const allPts = routes.flatMap(r => r.points)
    if (!allPts.length) return [38.5, -9.0]
    const lat = allPts.reduce((s, p) => s + p[0], 0) / allPts.length
    const lon = allPts.reduce((s, p) => s + p[1], 0) / allPts.length
    return [lat, lon]
  }, [routes])

  if (loading) return <div className="loading-center"><div className="spinner" /></div>

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Heatmap</h1>
        <p className="page-subtitle">{routes.length} rides on the map</p>
      </div>

      {routes.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Map size={48} /></div>
          <h3>No GPS data yet</h3>
          <p>Upload rides with GPS to see them here</p>
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
