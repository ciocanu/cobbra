import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

const field = {
  width: '100%',
  background: 'var(--bg-card, #0f0f1a)',
  border: '1px solid var(--border, #1e1e38)',
  borderRadius: 8,
  padding: '12px 14px',
  fontSize: 14,
  color: 'var(--text-primary, #f0f0ff)',
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
}

export default function Contact() {
  const renderedAt = useRef(Date.now() / 1000)
  const [form, setForm] = useState({ name: '', email: '', subject: '', message: '', website: '' })
  const [state, setState] = useState('idle') // idle | loading | success | error
  const [errorMsg, setErrorMsg] = useState('')

  function set(k) {
    return e => setForm(f => ({ ...f, [k]: e.target.value }))
  }

  async function submit(e) {
    e.preventDefault()
    setState('loading')
    setErrorMsg('')
    try {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, rendered_at: renderedAt.current }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Something went wrong. Please try again.')
      }
      setState('success')
    } catch (err) {
      setErrorMsg(err.message)
      setState('error')
    }
  }

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: '48px 24px' }}>
      <Link to="/" style={{ color: 'var(--text-muted, #8888aa)', fontSize: 13, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 32 }}>
        ← Back
      </Link>

      <h1 style={{ fontSize: 28, fontWeight: 900, color: 'var(--text-primary, #f0f0ff)', marginBottom: 6 }}>Contact</h1>
      <p style={{ color: 'var(--text-muted, #8888aa)', fontSize: 14, marginBottom: 36 }}>
        Send us a message and we'll get back to you.
      </p>

      {state === 'success' ? (
        <div style={{ background: 'var(--bg-card, #0f0f1a)', border: '1px solid #1e1e38', borderRadius: 12, padding: '32px 28px', textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>✓</div>
          <p style={{ color: 'var(--text-primary, #f0f0ff)', fontWeight: 700, marginBottom: 8 }}>Message sent</p>
          <p style={{ color: 'var(--text-muted, #8888aa)', fontSize: 14 }}>We'll get back to you as soon as possible.</p>
          <Link to="/" style={{ display: 'inline-block', marginTop: 24, color: 'var(--text-muted, #8888aa)', fontSize: 13, textDecoration: 'none' }}>← Back to home</Link>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Honeypot — hidden from humans, bots fill it */}
          <input
            type="text"
            name="website"
            value={form.website}
            onChange={set('website')}
            tabIndex={-1}
            autoComplete="off"
            style={{ position: 'absolute', left: -9999, width: 1, height: 1, overflow: 'hidden' }}
            aria-hidden="true"
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted, #8888aa)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Name *</label>
              <input required value={form.name} onChange={set('name')} placeholder="Your name" style={field} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted, #8888aa)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Email *</label>
              <input required type="email" value={form.email} onChange={set('email')} placeholder="your@email.com" style={field} />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted, #8888aa)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Subject</label>
            <input value={form.subject} onChange={set('subject')} placeholder="What's this about?" style={field} />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted, #8888aa)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Message *</label>
            <textarea
              required
              value={form.message}
              onChange={set('message')}
              placeholder="Your message..."
              rows={6}
              maxLength={5000}
              style={{ ...field, resize: 'vertical', minHeight: 120 }}
            />
            <p style={{ textAlign: 'right', fontSize: 11, color: 'var(--text-muted, #8888aa)', marginTop: 4 }}>{form.message.length}/5000</p>
          </div>

          {state === 'error' && (
            <div style={{ background: '#ff4d6d18', border: '1px solid #ff4d6d40', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#ff4d6d' }}>
              {errorMsg}
            </div>
          )}

          <button
            type="submit"
            disabled={state === 'loading'}
            style={{
              padding: '13px 24px',
              background: state === 'loading' ? '#1e1e38' : 'var(--accent, #4ade80)',
              color: state === 'loading' ? 'var(--text-muted, #8888aa)' : '#09090f',
              border: 'none',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 700,
              cursor: state === 'loading' ? 'not-allowed' : 'pointer',
              transition: 'opacity 0.15s',
              alignSelf: 'flex-start',
            }}
          >
            {state === 'loading' ? 'Sending…' : 'Send message'}
          </button>
        </form>
      )}
    </div>
  )
}
