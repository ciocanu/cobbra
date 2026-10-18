import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { demoLogin } from '../services/api'
import { markLoggedIn } from '../services/auth'
import { useConfig } from '../services/queries'

// Signs into the shared read-only demo account. Renders nothing when the
// instance has no demo (see backend/scripts/seed_demo.py).
export default function DemoButton({ className, style, children }) {
  const { data: config } = useConfig()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!config?.demo_available) return null

  const start = async () => {
    setBusy(true)
    setError('')
    try {
      await demoLogin()
      markLoggedIn()
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'The demo is unavailable right now.')
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className={className} style={style} onClick={start} disabled={busy}>
        {children}
      </button>
      {error && <span role="alert" style={{ fontSize: 12, color: 'var(--danger, #f87171)' }}>{error}</span>}
    </>
  )
}
