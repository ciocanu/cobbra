import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { verifyEmailChange } from '../services/api'
import { CheckCircle, AlertCircle, Mail } from 'lucide-react'

export default function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  const [state, setState] = useState('loading') // loading | success | expired | invalid
  const [email, setEmail] = useState('')

  useEffect(() => {
    if (!token) { setState('invalid'); return }
    verifyEmailChange(token)
      .then(r => { setEmail(r.data.email); setState('success') })
      .catch(e => {
        if (e.response?.status === 410) setState('expired')
        else setState('invalid')
      })
  }, [token])

  const center = (children) => (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ maxWidth: 420, width: '100%', textAlign: 'center' }}>
        <div style={{ marginBottom: 32 }}>
          <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: '0.1em', color: 'var(--accent)' }}>COBBRA</span>
        </div>
        {children}
      </div>
    </div>
  )

  if (state === 'loading') return center(<div className="spinner" style={{ margin: '0 auto' }} />)

  if (state === 'success') return center(
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid color-mix(in srgb, var(--accent) 19%, transparent)', borderRadius: 16, padding: '36px 32px' }}>
      <CheckCircle size={44} style={{ color: 'var(--accent)', marginBottom: 16 }} />
      <h2 style={{ color: 'var(--text-primary)', margin: '0 0 10px', fontSize: 22 }}>Email verified!</h2>
      <p style={{ color: 'var(--text-muted)', margin: '0 0 24px', fontSize: 14, lineHeight: 1.6 }}>
        Your email has been updated to<br />
        <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>
      </p>
      <Link
        to="/settings"
        style={{ display: 'inline-block', padding: '10px 24px', background: 'var(--accent)', color: 'oklch(8% 0.015 120)', borderRadius: 8, fontWeight: 700, fontSize: 14, textDecoration: 'none' }}
      >
        Back to Settings
      </Link>
    </div>
  )

  if (state === 'expired') return center(
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid color-mix(in srgb, var(--heart) 19%, transparent)', borderRadius: 16, padding: '36px 32px' }}>
      <AlertCircle size={44} style={{ color: 'var(--heart)', marginBottom: 16 }} />
      <h2 style={{ color: 'var(--text-primary)', margin: '0 0 10px', fontSize: 22 }}>Link expired</h2>
      <p style={{ color: 'var(--text-muted)', margin: '0 0 24px', fontSize: 14, lineHeight: 1.6 }}>
        This verification link has expired (valid for 24 hours).<br />
        Go to Settings and request a new one.
      </p>
      <Link
        to="/settings"
        style={{ display: 'inline-block', padding: '10px 24px', background: 'var(--bg-card)', color: 'var(--text-primary)', borderRadius: 8, fontWeight: 600, fontSize: 14, textDecoration: 'none', border: '1px solid var(--border)' }}
      >
        Back to Settings
      </Link>
    </div>
  )

  return center(
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 16, padding: '36px 32px' }}>
      <Mail size={44} style={{ color: 'var(--text-muted)', marginBottom: 16 }} />
      <h2 style={{ color: 'var(--text-primary)', margin: '0 0 10px', fontSize: 22 }}>Invalid link</h2>
      <p style={{ color: 'var(--text-muted)', margin: '0 0 24px', fontSize: 14, lineHeight: 1.6 }}>
        This verification link is not valid. Make sure you copied the full link from your email.
      </p>
      <Link
        to="/settings"
        style={{ display: 'inline-block', padding: '10px 24px', background: 'var(--bg-card)', color: 'var(--text-primary)', borderRadius: 8, fontWeight: 600, fontSize: 14, textDecoration: 'none', border: '1px solid var(--border)' }}
      >
        Back to Settings
      </Link>
    </div>
  )
}
