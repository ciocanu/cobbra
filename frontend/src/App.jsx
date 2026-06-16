import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { isLoggedIn } from './services/auth'

// Critical path — always eager
import Landing from './components/Landing'
import Login   from './components/Login'
import Layout  from './components/Layout'

// Public pages — lazy
const LifetimeOffer  = lazy(() => import('./components/LifetimeOffer'))
const VerifyEmail    = lazy(() => import('./components/VerifyEmail'))
const StravaCallback = lazy(() => import('./components/StravaCallback'))
const PrivacyPolicy  = lazy(() => import('./components/PrivacyPolicy'))
const TermsOfService = lazy(() => import('./components/TermsOfService'))
const CobbraLanding  = lazy(() => import('./brand/CobbraLanding'))

// App routes — lazy (all behind auth or heavy deps like Leaflet/Recharts)
const Onboarding      = lazy(() => import('./components/Onboarding'))
const Dashboard       = lazy(() => import('./components/Dashboard'))
const ActivityList    = lazy(() => import('./components/ActivityList'))
const ActivityDetail  = lazy(() => import('./components/ActivityDetail'))
const Upload          = lazy(() => import('./components/Upload'))
const PersonalRecords = lazy(() => import('./components/PersonalRecords'))
const Heatmap         = lazy(() => import('./components/Heatmap'))
const Goals           = lazy(() => import('./components/Goals'))
const Segments        = lazy(() => import('./components/Segments'))
const Compare         = lazy(() => import('./components/Compare'))
const Settings        = lazy(() => import('./components/Settings'))
const Training        = lazy(() => import('./components/Training'))
const Admin           = lazy(() => import('./components/Admin'))

function RequireAuth({ children }) {
  if (!isLoggedIn()) return <Navigate to="/login" replace />
  return children
}

function PageFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: 200 }}>
      <div className="spinner" />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          {/* Public routes */}
          <Route path="/"               element={<Landing />} />
          <Route path="/login"          element={<Login />} />
          <Route path="/lifetime-offer" element={<LifetimeOffer />} />
          <Route path="/verify-email"   element={<VerifyEmail />} />
          <Route path="/strava/callback" element={<StravaCallback />} />
          <Route path="/privacy"        element={<PrivacyPolicy />} />
          <Route path="/terms"          element={<TermsOfService />} />
          <Route path="/brand"          element={<CobbraLanding />} />
          <Route path="/onboarding"     element={<RequireAuth><Onboarding /></RequireAuth>} />

          {/* Authenticated app */}
          <Route
            path="/"
            element={<RequireAuth><Layout /></RequireAuth>}
          >
            <Route path="dashboard"      element={<Dashboard />} />
            <Route path="activities"     element={<ActivityList />} />
            <Route path="activities/:id" element={<ActivityDetail />} />
            <Route path="upload"         element={<Upload />} />
            <Route path="records"        element={<PersonalRecords />} />
            <Route path="heatmap"        element={<Heatmap />} />
            <Route path="goals"          element={<Goals />} />
            <Route path="segments"       element={<Segments />} />
            <Route path="compare"        element={<Compare />} />
            <Route path="settings"       element={<Settings />} />
            <Route path="training"       element={<Training />} />
            <Route path="admin"          element={<Admin />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
