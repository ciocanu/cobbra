import { useState, useId, useEffect, useRef } from 'react'

export default function InfoTip({ text, width = 260 }) {
  const [open, setOpen] = useState(false)
  const uid = useId()
  const tooltipId = `infotip-${uid}`
  const buttonRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', marginLeft: 6, verticalAlign: 'middle' }}>
      <button
        ref={buttonRef}
        aria-label="More information"
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={e => { e.stopPropagation(); setOpen(v => !v) }}
        style={{
          background: 'none', border: 'none', borderRadius: '50%',
          width: 32, height: 32, padding: 0,
          color: 'var(--text-muted)', cursor: 'pointer',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <span aria-hidden="true" style={{
          width: 15, height: 15,
          border: '1px solid var(--border-bright)', borderRadius: '50%',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 9, fontWeight: 700,
          fontFamily: 'var(--font-body)', fontStyle: 'italic',
          lineHeight: 1, pointerEvents: 'none', userSelect: 'none',
        }}>i</span>
      </button>
      {open && (
        <div
          id={tooltipId}
          role="tooltip"
          style={{
            position: 'absolute', top: 34, left: '50%', transform: 'translateX(-50%)',
            zIndex: 300,
            background: 'var(--bg-card)', border: '1px solid var(--border-bright)',
            borderRadius: 8, padding: '10px 13px',
            fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.55,
            width, boxShadow: '0 6px 24px oklch(4% 0.006 142 / 0.6)',
            pointerEvents: 'none',
          }}
        >
          {text}
        </div>
      )}
    </span>
  )
}
