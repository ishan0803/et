import { UserButton } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'

export default function Navbar({ user, profile, sidebarOpen, onToggleSidebar, clerkAvailable }) {
  const role = profile?.role || 'reader'
  const displayName = user?.firstName || user?.primaryEmailAddress?.emailAddress?.split('@')[0] || 'User'

  const roleEmoji = { student: '🎓', investor: '💼', founder: '🚀', journalist: '📝', analyst: '📊' }

  return (
    <nav className="navbar">
      <div className="nav-brand">
        <div className="nav-logo">ET</div>
        <div>
          <div className="nav-title">ET Intelligence</div>
          <div className="nav-subtitle">AI-Native News Platform</div>
        </div>
      </div>

      <div className="nav-spacer" />

      {profile && (
        <div className="nav-role">
          <span>{roleEmoji[role] || '📰'}</span>
          <span>{role.charAt(0).toUpperCase() + role.slice(1)}</span>
        </div>
      )}

      <div className="nav-user">
        <span className="nav-avatar">{displayName[0]?.toUpperCase()}</span>
        <span>{displayName}</span>
      </div>

      {clerkAvailable && (
        <div style={{ marginLeft: 4 }}>
          <UserButton afterSignOutUrl="/" />
        </div>
      )}

      <div className="nav-actions">
        <Link to="/dashboard" className="btn-sidebar-toggle" style={{ textDecoration: 'none', marginRight: 8, whiteSpace: 'nowrap' }}>
          🏠 Dashboard
        </Link>
        <Link to="/hub" className="btn-sidebar-toggle active" style={{ textDecoration: 'none', marginRight: 8, whiteSpace: 'nowrap' }}>
          ⚡ AI Hub
        </Link>
        {onToggleSidebar && (
          <button
            className={`btn-sidebar-toggle ${sidebarOpen ? 'active' : ''}`}
            onClick={onToggleSidebar}
            id="btn-toggle-ai-sidebar"
            style={{ whiteSpace: 'nowrap' }}
          >
            {sidebarOpen ? '✕' : '📖'} History
          </button>
        )}
      </div>
    </nav>
  )
}
