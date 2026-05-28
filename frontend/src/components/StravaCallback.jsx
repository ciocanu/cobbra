import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { stravaCallback } from '../services/api'

export default function StravaCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    const error = searchParams.get('error')
    if (error) {
      setError('Strava access was denied. You can try connecting again from Settings.')
      return
    }

    const code = searchParams.get('code')
    if (!code) {
      setError('Invalid callback — no authorization code received.')
      return
    }

    stravaCallback(code)
      .then(() => navigate('/settings', { replace: true }))
      .catch(e => setError(e.response?.data?.detail || 'Failed to connect Strava. Please try again.'))
  }, [])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-primary)' }}>
      <div style={{ textAlign: 'center', maxWidth: 400, padding: '0 24px' }}>
        {error ? (
          <>
            <div style={{ fontSize: 32, marginBottom: 16 }}>⚠️</div>
            <div style={{ fontSize: 15, color: 'var(--text-primary)', fontWeight: 600, marginBottom: 8 }}>Connection failed</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 20, lineHeight: 1.6 }}>{error}</div>
            <button
              className="btn btn-primary"
              onClick={() => navigate('/settings', { replace: true })}
            >
              Back to Settings
            </button>
          </>
        ) : (
          <>
            <div className="spinner" style={{ width: 32, height: 32, margin: '0 auto 16px', borderWidth: 3 }} />
            <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>Connecting your Strava account…</div>
          </>
        )}
      </div>
    </div>
  )
}
