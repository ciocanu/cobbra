import { useEffect, useState } from 'react'
import { getTrainingPlan, generateTrainingPlan } from '../services/api'
import { Brain, Calendar, RefreshCw, Zap } from 'lucide-react'
import { format, parseISO } from 'date-fns'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const OBJECTIVES = [
  { value: 'Build base endurance',        desc: 'Long Z2 rides, raise weekly volume steadily' },
  { value: 'Improve speed and power',     desc: 'Intervals, tempo work, sprint sessions' },
  { value: 'Prepare for a specific event',desc: 'Structured build toward your target race or sportive' },
  { value: 'Weight loss / general fitness',desc: 'Consistent riding, calorie burn, habit building' },
  { value: 'Recovery / maintain fitness', desc: 'Low load, keep legs moving without accumulating fatigue' },
]

function PlanText({ text }) {
  return (
    <div className="plan-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="plan-h1">{children}</h1>,
          h2: ({ children }) => <h2 className="plan-h2">{children}</h2>,
          h3: ({ children }) => <h3 className="plan-h3">{children}</h3>,
          h4: ({ children }) => <h4 className="plan-h4">{children}</h4>,
          p:  ({ children }) => <p  className="plan-p">{children}</p>,
          ul: ({ children }) => <ul className="plan-ul">{children}</ul>,
          ol: ({ children }) => <ol className="plan-ol">{children}</ol>,
          li: ({ children }) => <li className="plan-li">{children}</li>,
          strong: ({ children }) => <strong className="plan-strong">{children}</strong>,
          em: ({ children }) => <em style={{ color: 'var(--text-secondary)' }}>{children}</em>,
          hr: () => <hr className="plan-hr" />,
          blockquote: ({ children }) => <blockquote className="plan-blockquote">{children}</blockquote>,
          table: ({ children }) => (
            <div className="plan-table-wrap">
              <table className="plan-table">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="plan-th">{children}</th>,
          td: ({ children }) => <td className="plan-td">{children}</td>,
          code: ({ children }) => <code className="plan-code">{children}</code>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

export default function Training() {
  const [data, setData] = useState(null)       // { plan, can_generate, next_generation_date }
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)

  const ALL_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

  // Form state
  const [objective, setObjective] = useState(OBJECTIVES[0].value)
  const [trainingDays, setTrainingDays] = useState(['Tuesday', 'Thursday', 'Saturday'])
  const [eventDate, setEventDate] = useState('')
  const [extraNotes, setExtraNotes] = useState('')

  const toggleDay = (day) => {
    setTrainingDays(prev =>
      prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day]
    )
  }

  useEffect(() => {
    getTrainingPlan()
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleGenerate = async () => {
    setGenerating(true)
    setError('')
    try {
      if (trainingDays.length === 0) {
        setError('Please select at least one training day.')
        setGenerating(false)
        return
      }
      const res = await generateTrainingPlan({
        objective,
        training_days: trainingDays,
        event_date: eventDate || null,
        extra_notes: extraNotes || null,
      })
      setData(res.data)
      setShowForm(false)
    } catch (e) {
      const detail = e.response?.data?.detail
      if (Array.isArray(detail)) {
        setError('Validation error: ' + detail.map(d => d.msg).join(', '))
      } else {
        setError(detail || e.message || 'Failed to generate plan')
      }
    } finally {
      setGenerating(false)
    }
  }

  if (loading) return <div className="loading-center"><div className="spinner" /></div>

  const { plan, can_generate, next_generation_date, plans_used, plans_limit, is_free } = data || { plan: null, can_generate: true, next_generation_date: null, plans_used: 0, plans_limit: 3, is_free: false }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">
            <Brain size={22} style={{ display: 'inline', marginRight: 8, color: 'var(--accent)' }} />
            Training Plan
          </h1>
          <p className="page-subtitle">AI-generated plan based on your ride history and goals</p>
        </div>
        {plan && can_generate && !showForm && (
          <button className="btn btn-primary" onClick={() => setShowForm(true)}>
            <RefreshCw size={13} /> New Plan
          </button>
        )}
      </div>

      {/* Free plan gate */}
      {is_free && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px', borderRadius: 10, background: '#4da6ff12', border: '1px solid #4da6ff30', marginBottom: 24 }}>
          <Zap size={16} style={{ color: '#4da6ff', flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>AI training plans are a Pro feature.</span>
            <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>Upgrade to generate personalised 4-week plans based on your ride history.</span>
          </div>
          <a href="/settings" style={{ fontSize: 12, fontWeight: 700, color: '#4da6ff', textDecoration: 'none', whiteSpace: 'nowrap' }}>Upgrade →</a>
        </div>
      )}

      {/* Monthly quota */}
      {!is_free && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, fontSize: 13, color: 'var(--text-muted)' }}>
          <Calendar size={13} />
          <span>{plans_used} of {plans_limit} plans used this month</span>
        </div>
      )}

      {/* Rate limit notice */}
      {plan && !can_generate && !is_free && (
        <div className="alert" style={{
          background: 'color-mix(in srgb, var(--accent) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--accent) 15%, transparent)',
          color: 'var(--text-secondary)', marginBottom: 20
        }}>
          <Calendar size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
          Plan generated on {format(parseISO(plan.created_at), 'dd MMM yyyy')} ·
          Next plan available on <strong style={{ color: 'var(--accent)' }}>
            {next_generation_date ? format(parseISO(next_generation_date), 'dd MMM yyyy') : '—'}
          </strong>
        </div>
      )}

      {/* Form */}
      {!is_free && (showForm || (!plan && can_generate)) && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 18 }}>
            {plan ? 'Generate New Plan' : 'Set Your Goal'}
          </div>

          {/* Objective */}
          <div className="training-field">
            <label className="training-label">What is your main objective?</label>
            <div className="objective-grid">
              {OBJECTIVES.map(o => (
                <button
                  key={o.value}
                  className={`objective-card${objective === o.value ? ' selected' : ''}`}
                  onClick={() => setObjective(o.value)}
                >
                  <div className="objective-title">{o.value}</div>
                  <div className="objective-desc">{o.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Available days */}
          <div className="training-field">
            <label className="training-label">
              Which days can you train?
              <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: 8 }}>
                {trainingDays.length === 0 ? 'None selected' : `${trainingDays.length} day${trainingDays.length !== 1 ? 's' : ''} selected`}
              </span>
            </label>
            <div className="day-picker">
              {ALL_DAYS.map(d => (
                <button
                  key={d}
                  className={`day-pill${trainingDays.includes(d) ? ' selected' : ''}`}
                  onClick={() => toggleDay(d)}
                >
                  <span className="day-pill-short">{d.slice(0, 3)}</span>
                  <span className="day-pill-full">{d}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Event date */}
          <div className="training-field">
            <label className="training-label">Target event date <span style={{ color: 'var(--text-muted)' }}>(optional)</span></label>
            <input
              type="date"
              className="filter-input"
              style={{ width: 180 }}
              value={eventDate}
              onChange={e => setEventDate(e.target.value)}
            />
          </div>

          {/* Notes */}
          <div className="training-field">
            <label className="training-label">Anything else the coach should know? <span style={{ color: 'var(--text-muted)' }}>(optional)</span></label>
            <textarea
              className="notes-textarea"
              rows={3}
              placeholder='e.g. "I have a knee injury", "I can only ride indoors", "I want to focus on climbing"'
              value={extraNotes}
              onChange={e => setExtraNotes(e.target.value)}
            />
          </div>

          {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}

          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
              {generating
                ? <><div className="spinner" style={{ width: 14, height: 14 }} /> Generating…</>
                : <><Brain size={14} /> Generate 4-Week Plan</>
              }
            </button>
            {plan && (
              <button className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            )}
          </div>

          {generating && (
            <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 10 }}>
              This takes 10–20 seconds — Sonnet is building your personalised plan…
            </p>
          )}
        </div>
      )}

      {/* Plan display */}
      {plan && !showForm && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, fontWeight: 600, marginBottom: 4 }}>
                Objective
              </div>
              <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 2 }}>{plan.objective}</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                {plan.training_days?.length > 0
                  ? plan.training_days.map(d => d.slice(0, 3)).join(' · ')
                  : `${plan.available_days} days/week`}
                {plan.event_date && ` · Target: ${format(parseISO(plan.event_date), 'dd MMM yyyy')}`}
              </div>
            </div>
            {can_generate && (
              <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setShowForm(true)}>
                <RefreshCw size={12} /> New Plan
              </button>
            )}
          </div>

          <PlanText text={plan.plan_text} />
        </div>
      )}

      {/* Empty state — paid user, no plan yet */}
      {!plan && !showForm && !is_free && can_generate && (
        <div className="empty-state">
          <div className="empty-state-icon"><Brain size={48} /></div>
          <h3>No plan yet</h3>
          <p>Fill in your goal above to generate your first training plan.</p>
        </div>
      )}
    </div>
  )
}
