import axios from 'axios'
import { markLoggedOut } from './auth'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 30000,
  withCredentials: true,  // send the httpOnly auth cookie on every request
})

// Redirect to login on 401 (expired or missing cookie)
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      markLoggedOut()
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// Auth
export const checkSetup    = () => api.get('/auth/setup')
export const register      = (username, email, password, website = '') => api.post('/auth/register', { username, email, password, website })
export const login         = (username, password) => api.post('/auth/login', { username, password })
export const logout        = () => api.post('/auth/logout')
export const getMe         = () => api.get('/auth/me')

// Activities
export const getActivities = (params = {}) => api.get('/activities/', { params })
export const getActivity   = (id) => api.get(`/activities/${id}`)
export const deleteActivity= (id) => api.delete(`/activities/${id}`)
export const renameActivity= (id, name) => api.patch(`/activities/${id}/rename`, { name })
export const updateNotes   = (id, notes) => api.patch(`/activities/${id}/notes`, { notes })
export const getAnalysis   = (id) => api.get(`/activities/${id}/analysis`)
export const clearAnalysis = (id) => api.delete(`/activities/${id}/analysis`)
export const exportCsv     = (id) => api.get(`/activities/${id}/export/csv`, { responseType: 'blob' })
export const exportGpx     = (id) => api.get(`/activities/${id}/export/gpx`, { responseType: 'blob' })
export const uploadActivity= (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/activities/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
}

// Stats
export const getStats             = () => api.get('/stats/summary')
export const getMonthlyStats      = () => api.get('/stats/monthly')
export const getFitnessStats      = (days = 90)  => api.get('/stats/fitness',     { params: { days } })
export const getWeeklyStats       = (weeks = 16) => api.get('/stats/weekly',      { params: { weeks } })
export const getYearStats         = () => api.get('/stats/year')
export const getConsistencyStats  = (weeks = 12) => api.get('/stats/consistency', { params: { weeks } })
export const getEfficiencyStats   = ()           => api.get('/stats/efficiency')

// Records, Heatmap, Goals
export const getRecords  = () => api.get('/records/')
export const getHeatmap  = () => api.get('/heatmap/')
export const getGoals    = () => api.get('/goals/')
export const setGoal     = (goal_type, target) => api.post('/goals/', { goal_type, target })
export const deleteGoal  = (id) => api.delete(`/goals/${id}`)

// Segments
export const getSegments          = () => api.get('/segments/')
export const createSegment        = (data) => api.post('/segments/', data)
export const deleteSegment        = (id) => api.delete(`/segments/${id}`)
export const getSegmentEfforts    = (id) => api.get(`/segments/${id}/efforts`)
export const getSegmentTrend      = (id) => api.get(`/segments/${id}/my-trend`)
export const getActivitySegments  = (activityId) => api.get(`/segments/activity/${activityId}`)

// Settings
export const getSettings    = () => api.get('/settings/')
export const updateSettings = (data) => api.patch('/settings/', data)
export const changePassword    = (old_password, new_password) => api.patch('/settings/password', { old_password, new_password })
export const requestEmailChange = (email) => api.post('/settings/email', { email })
export const verifyEmailChange  = (token) => api.post('/settings/verify-email', { token })
export const exportMyData   = () => api.get('/settings/export', { responseType: 'blob' })
export const deleteAccount  = (password) => api.delete('/settings/account', { data: { password } })

// Training plan
export const getTrainingPlan      = () => api.get('/training/plan')
export const generateTrainingPlan = (data) => api.post('/training/plan', data, { timeout: 90000 })

// Payments
export const createCheckout     = (tier)  => api.post('/payments/create-checkout', { tier })
export const validateOffer      = (token) => api.get('/payments/validate-offer', { params: { token } })
export const claimLifetimeOffer = (token) => api.post('/payments/lifetime-checkout', { token })

// Strava
export const stravaAuthUrl    = ()     => api.get('/strava/auth-url')
export const stravaCallback   = (code) => api.post('/strava/callback', { code })
export const stravaStatus     = ()     => api.get('/strava/status')
export const stravaDisconnect = ()     => api.post('/strava/disconnect')
export const stravaSync       = ()     => api.post('/strava/sync', {}, { timeout: 60000 })

// Durability
export const getDurabilityAnalysis  = (id)           => api.get(`/activities/${id}/durability`)
export const getDurabilityTrend     = (weeks = 12)   => api.get('/stats/durability-trend', { params: { weeks } })
export const compareDurability      = (activity_ids) => api.post('/stats/durability-compare', { activity_ids })

// Hydration
export const getHydrationAnalysis  = (id)        => api.get(`/activities/${id}/hydration`)
export const updateHydrationIntake = (id, intake_ml) => api.patch(`/activities/${id}/hydration`, { intake_ml })
export const getHeatProfile        = ()           => api.get('/user/heat-profile')
export const recordSweatTest       = (data)       => api.post('/user/sweat-test', data)

// Dashboard AI insights
export const getDashboardRideInsight    = (data) => api.post('/dashboard/ride-insight', data)
export const getDashboardFitnessInsight = (data) => api.post('/dashboard/fitness-insight', data)

// Admin
export const adminCheck         = () => api.get('/admin/check')
export const adminGetStats      = () => api.get('/admin/stats')
export const adminGetSystem     = () => api.get('/admin/system')
export const adminGetUsers          = () => api.get('/admin/users')
export const adminUpdateMembership  = (id, membership) => api.patch(`/admin/users/${id}`, { membership })
export const adminSendOffer         = (id) => api.post(`/admin/users/${id}/offer`)
export const adminDeleteUser        = (id) => api.delete(`/admin/users/${id}`)
export const adminGetSegments    = () => api.get('/admin/segments')
export const adminRenameSegment   = (id, name) => api.patch(`/admin/segments/${id}`, { name })
export const adminTransferSegment = (id, user_id) => api.patch(`/admin/segments/${id}`, { user_id })
export const adminDeleteSegment  = (id) => api.delete(`/admin/segments/${id}`)

export default api
