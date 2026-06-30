import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { LayoutDashboard, List, Upload, Bike, Trophy, Map, Target, LogOut, Flag, GitCompare, Settings, Brain, User, Shield, Menu, X } from 'lucide-react'
import { markLoggedOut } from '../services/auth'
import { logout } from '../services/api'
import { useMe, useSettings, useAdminCheck } from '../services/queries'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/activities', icon: List,           label: 'Activities' },
  { to: '/records',   icon: Trophy,          label: 'Records' },
  { to: '/segments',  icon: Flag,            label: 'Segments' },
  { to: '/compare',   icon: GitCompare,      label: 'Compare' },
  { to: '/heatmap',   icon: Map,             label: 'Heatmap' },
  { to: '/goals',     icon: Target,          label: 'Goals' },
  { to: '/training',  icon: Brain,           label: 'Training Plan' },
  { to: '/upload',    icon: Upload,          label: 'Upload Ride' },
  { to: '/settings',  icon: Settings,        label: 'Settings' },
]

export default function Layout() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Shared, cached resources — fetched once and reused across the app instead
  // of re-requested on every navigation.
  const { data: me } = useMe()
  const { data: isAdmin = false } = useAdminCheck()
  const { data: settings } = useSettings()
  const username = me?.username ?? ''

  // Gate access until the essential fitness profile is filled in. The settings
  // query is cached, so this no longer hits the backend on every route change —
  // it reads the shared cache and only refetches when stale.
  useEffect(() => {
    if (!settings) return
    const incomplete = settings.age == null || settings.weight_kg == null || !settings.experience_level || !settings.bike_type
    if (incomplete) navigate('/onboarding', { replace: true })
  }, [settings, location.pathname, navigate])

  // Close drawer on route change
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  // Per-route document title (WCAG 2.4.2)
  useEffect(() => {
    const match = navItems.find(({ to }) => location.pathname === to || location.pathname.startsWith(to + '/'))
    const label = match?.label ?? (location.pathname.startsWith('/admin') ? 'Admin' : null)
    document.title = label ? `${label} — Cobbra` : 'Cobbra'
  }, [location.pathname])

  const handleLogout = async () => {
    try { await logout() } catch (_) {}
    markLoggedOut()
    navigate('/login')
  }

  const close = () => setMobileOpen(false)

  return (
    <>
      <a href="#main-content" className="skip-to-content">Skip to content</a>

      {/* Mobile hamburger toggle */}
      <button
        className="mobile-nav-toggle"
        onClick={() => setMobileOpen(o => !o)}
        aria-label="Toggle menu"
      >
        {mobileOpen ? <X size={18} /> : <Menu size={18} />}
      </button>

      {/* Overlay (mobile only) */}
      <div
        className={`mobile-overlay${mobileOpen ? ' open' : ''}`}
        onClick={close}
        aria-hidden="true"
      />

      <div className="app">
        <aside className={`sidebar${mobileOpen ? ' open' : ''}`} aria-label="Primary navigation">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">
              <Bike size={18} strokeWidth={2.5} />
            </div>
            <span className="sidebar-logo-text">COBBRA</span>
          </div>

          <nav className="sidebar-nav" aria-label="Main navigation">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                <Icon size={16} />
                <span className="nav-label">{label}</span>
              </NavLink>
            ))}
            {isAdmin && (
              <NavLink
                to="/admin"
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                style={{ color: 'var(--accent)' }}
              >
                <Shield size={16} />
                <span className="nav-label">Admin</span>
              </NavLink>
            )}
          </nav>

          <div style={{ marginTop: 'auto', padding: '0 10px 16px', flexShrink: 0 }}>
            {username && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', marginBottom: 4, color: 'var(--text-muted)', fontSize: 12 }}>
                <User size={13} />
                <span className="nav-label" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{username}</span>
              </div>
            )}
            <button
              className="nav-item"
              style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
              onClick={handleLogout}
            >
              <LogOut size={16} />
              <span className="nav-label">Logout</span>
            </button>
          </div>
        </aside>

        <main id="main-content" className="main">
          <div key={location.pathname} className="page-enter">
            <Outlet />
          </div>
        </main>
      </div>
    </>
  )
}
