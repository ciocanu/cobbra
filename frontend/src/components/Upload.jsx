import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadActivity } from '../services/api'
import { Upload as UploadIcon, CheckCircle, AlertCircle } from 'lucide-react'
import Alert from './Alert'

export default function Upload() {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [success, setSuccess] = useState(null)
  const [error, setError] = useState('')
  const inputRef = useRef()
  const navigate = useNavigate()

  const handleFile = async (file) => {
    if (!file) return
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['gpx', 'fit'].includes(ext)) {
      setError('Only .gpx and .fit files are supported')
      return
    }

    setError('')
    setSuccess(null)
    setUploading(true)

    try {
      const res = await uploadActivity(file)
      setSuccess(res.data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Upload failed. Check the file and try again.')
    } finally {
      setUploading(false)
    }
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Upload Ride</h1>
        <p className="page-subtitle">Supports .gpx and .fit files exported from Cycplus, Garmin, Wahoo, etc.</p>
      </div>

      {error && (
        <Alert variant="error">
          <AlertCircle size={15} /> {error}
        </Alert>
      )}

      {success ? (
        <div style={{ textAlign: 'center', padding: '60px 40px' }}>
          <CheckCircle size={52} color="var(--accent)" style={{ margin: '0 auto 20px' }} />
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
            {success.name}
          </div>
          <div style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>
            {success.distance_km.toFixed(2)} km · {success.avg_speed_kmh.toFixed(1)} km/h avg
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 24 }}>
            <button className="btn btn-primary" onClick={() => navigate(`/activities/${success.id}`)}>
              View Activity
            </button>
            <button className="btn btn-ghost" onClick={() => setSuccess(null)}>
              Upload Another
            </button>
          </div>
        </div>
      ) : (
        <div
          className={`upload-zone${dragging ? ' drag-over' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && inputRef.current.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".gpx,.fit"
            style={{ display: 'none' }}
            onChange={e => handleFile(e.target.files[0])}
          />

          <div className="upload-zone-icon">
            {uploading ? (
              <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
            ) : (
              <UploadIcon size={48} />
            )}
          </div>

          <div className="upload-zone-title">
            {uploading ? 'Processing...' : 'Drop your file here'}
          </div>
          <div className="upload-zone-sub">
            {uploading
              ? 'Parsing GPS data and calculating metrics'
              : 'or click to browse · .gpx and .fit supported'
            }
          </div>
        </div>
      )}

      <div style={{ marginTop: 32 }}>
        <div className="section-title">How to export from Cycplus</div>
        <div className="card" style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7 }}>
          <p>1. Open the <strong style={{ color: 'var(--text-primary)' }}>Cycplus app</strong> on your phone</p>
          <p>2. Go to <strong style={{ color: 'var(--text-primary)' }}>My → Activities</strong> and select a ride</p>
          <p>3. Tap the share icon → <strong style={{ color: 'var(--text-primary)' }}>Export GPX or FIT</strong></p>
          <p>4. Save the file and upload it here</p>
        </div>
      </div>
    </div>
  )
}
