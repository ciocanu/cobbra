import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { validateOffer, claimLifetimeOffer } from '../services/api'
import { isLoggedIn } from '../services/auth'
import { Star, Clock, Zap, AlertCircle } from 'lucide-react'

function Countdown({ expiresAt }) {
  const [remaining, setRemaining] = useState('')

  useEffect(() => {
    const tick = () => {
      const diff = new Date(expiresAt) - Date.now()
      if (diff <= 0) { setRemaining('Expired'); return }
      const h = Math.floor(diff / 3600000)
      const m = Math.floor((diff % 3600000) / 60000)
      const s = Math.floor((diff % 60000) / 1000)
      setRemaining(`${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [expiresAt])

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px', borderRadius: 8, background: 'color-mix(in srgb, var(--heart) 7%, transparent)', border: '1px solid color-mix(in srgb, var(--heart) 19%, transparent)' }}>
      <Clock size={14} style={{ color: 'var(--heart)', flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Offer expires in </span>
      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--heart)', fontFamily: 'var(--font-display)' }}>{remaining}</span>
    </div>
  )
}

export default function LifetimeOffer() {
  const [searchParams] = useSearchParams()
  const navigate        = useNavigate()
  const token           = searchParams.get('token') || ''

  const [state,    setState]    = useState('loading') // loading | valid | expired | invalid | buying
  const [offer,    setOffer]    = useState(null)
  const [error,    setError]    = useState('')

  useEffect(() => {
    if (!token) { setState('invalid'); return }
    validateOffer(token)
      .then(r => { setOffer(r.data); setState('valid') })
      .catch(e => {
        if (e.response?.status === 410) setState('expired')
        else setState('invalid')
      })
  }, [token])

  const handleClaim = async () => {
    if (!isLoggedIn()) {
      navigate(`/login?next=/lifetime-offer?token=${token}`)
      return
    }
    setState('buying')
    try {
      const res = await claimLifetimeOffer(token)
      window.location.href = res.data.url
    } catch (e) {
      setError(e.response?.data?.detail || 'Something went wrong. Please try again.')
      setState('valid')
    }
  }

  if (state === 'loading') {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="spinner" />
      </div>
    )
  }

  const centerBox = (children) => (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ maxWidth: 480, width: '100%', textAlign: 'center' }}>
        {children}
      </div>
    </div>
  )

  if (state === 'expired') return centerBox(
    <>
      <AlertCircle size={48} style={{ color: 'var(--heart)', marginBottom: 16 }} />
      <h2 style={{ color: 'var(--text-primary)', marginBottom: 8 }}>This offer has expired</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>The link you followed is no longer valid. Contact the Cobbra team if you believe this is a mistake.</p>
      <a href="/" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>← Back to Cobbra</a>
    </>
  )

  if (state === 'invalid') return centerBox(
    <>
      <AlertCircle size={48} style={{ color: 'var(--heart)', marginBottom: 16 }} />
      <h2 style={{ color: 'var(--text-primary)', marginBottom: 8 }}>Invalid offer link</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>This link is not valid. Make sure you copied the full link from your email.</p>
      <a href="/" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>← Back to Cobbra</a>
    </>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ maxWidth: 520, width: '100%' }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>COBBRA</span>
        </div>

        {/* Card */}
        <div style={{ background: 'var(--bg-secondary)', border: '1px solid color-mix(in srgb, var(--tier-lifetime) 19%, transparent)', borderRadius: 16, overflow: 'hidden' }}>

          {/* Header strip */}
          <div style={{ background: 'linear-gradient(135deg, color-mix(in srgb, var(--tier-lifetime) 9%, transparent), color-mix(in srgb, var(--tier-lifetime) 3%, transparent))', borderBottom: '1px solid color-mix(in srgb, var(--tier-lifetime) 12%, transparent)', padding: '28px 32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <Star size={18} style={{ color: 'var(--tier-lifetime)' }} />
              <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--tier-lifetime)' }}>Exclusive invitation</span>
            </div>
            <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.2 }}>
              Lifetime access,<br />just for you.
            </h1>
            {offer?.username && (
              <p style={{ margin: '10px 0 0', fontSize: 14, color: 'var(--text-muted)' }}>
                Hi <strong style={{ color: 'var(--text-primary)' }}>{offer.username}</strong>, this offer was sent personally.
              </p>
            )}
          </div>

          {/* Body */}
          <div style={{ padding: '28px 32px' }}>

            {/* Price */}
            <div style={{ textAlign: 'center', margin: '0 0 28px' }}>
              <div style={{ fontSize: 48, fontWeight: 800, color: 'var(--tier-lifetime)', lineHeight: 1 }}>€79</div>
              <div style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 4 }}>one-time · never pay again</div>
            </div>

            {/* Features */}
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                'Unlimited activities forever',
                'AI ride analysis on every ride',
                '3 AI training plans per month',
                'Activity export (CSV and GPX)',
                'Early access to new features',
              ].map(f => (
                <li key={f} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 14, color: 'var(--text-secondary)' }}>
                  <Zap size={13} style={{ color: 'var(--tier-lifetime)', flexShrink: 0 }} />
                  {f}
                </li>
              ))}
            </ul>

            {/* Countdown */}
            {offer?.expires_at && (
              <div style={{ marginBottom: 24 }}>
                <Countdown expiresAt={offer.expires_at} />
              </div>
            )}

            {error && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 8, background: 'color-mix(in srgb, var(--heart) 7%, transparent)', border: '1px solid color-mix(in srgb, var(--heart) 19%, transparent)', color: 'var(--heart)', fontSize: 13, marginBottom: 16 }}>
                <AlertCircle size={14} />
                {error}
              </div>
            )}

            {/* CTA */}
            <button
              onClick={handleClaim}
              disabled={state === 'buying'}
              style={{
                width: '100%', padding: '14px 0', borderRadius: 10,
                background: state === 'buying' ? 'color-mix(in srgb, var(--tier-lifetime) 50%, transparent)' : 'var(--tier-lifetime)',
                color: 'oklch(8% 0.015 120)', fontWeight: 700, fontSize: 15,
                border: 'none', cursor: state === 'buying' ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {state === 'buying'
                ? <><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2, borderColor: 'oklch(8% 0.015 120 / 0.25)', borderTopColor: 'oklch(8% 0.015 120)' }} /> Processing…</>
                : isLoggedIn() ? 'Claim Lifetime Access →' : 'Log in to claim your offer →'
              }
            </button>

            {!isLoggedIn() && (
              <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-muted)', marginTop: 12 }}>
                You need to be logged in to complete your purchase.
              </p>
            )}
          </div>
        </div>

        <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-muted)', marginTop: 20 }}>
          This offer is exclusive to you and is not available publicly.
        </p>
      </div>
    </div>
  )
}
