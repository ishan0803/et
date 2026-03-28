import { useState, useEffect, useCallback } from 'react'
import { useUser, useAuth, SignInButton, UserButton } from '@clerk/clerk-react'
import Navbar from '../components/Navbar'
import NewsFeed from '../components/NewsFeed'
import AISidebar from '../components/AISidebar'
import VideoModal from '../components/VideoModal'
import ProfileSetup from '../components/ProfileSetup'

const API = '/api'

export default function DashboardPage() {
  const clerkAvailable = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
  let user = null, isSignedIn = false, isLoaded = true

  let getTokenFn = async () => null

  if (clerkAvailable) {
    try {
      const clerkUser = useUser()
      const clerkAuth = useAuth()
      user = clerkUser.user
      isSignedIn = clerkUser.isSignedIn
      isLoaded = clerkUser.isLoaded
      getTokenFn = clerkAuth.getToken
    } catch {
      // Graceful fallback if Clerk fails to initialize at runtime
      isLoaded = true
      isSignedIn = true
      user = { id: 'demo_user_001', firstName: 'Demo', primaryEmailAddress: { emailAddress: 'demo@et.com' } }
    }
  } else {
    isSignedIn = true
    user = { id: 'demo_user_001', firstName: 'Demo', primaryEmailAddress: { emailAddress: 'demo@et.com' } }
  }

  const [profile, setProfile] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [videoJob, setVideoJob] = useState(null)
  const [showSetup, setShowSetup] = useState(false)

  const getAuthHeaders = useCallback(async () => {
    const headers = { 'Content-Type': 'application/json' }
    if (clerkAvailable && isSignedIn) {
      const token = await getTokenFn()
      if (token) headers['Authorization'] = `Bearer ${token}`
    } else if (!clerkAvailable) {
      headers['X-User-Id'] = 'demo_user_001'
    }
    return headers
  }, [clerkAvailable, isSignedIn, getTokenFn])

  // Load user profile
  useEffect(() => {
    if (!isSignedIn) return

    const loadProfile = async () => {
      try {
        const headers = await getAuthHeaders()
        const res = await fetch(`${API}/auth/profile`, { headers })
        if (res.ok) {
          const data = await res.json()
          setProfile(data)
          if (data.needs_setup) setShowSetup(true)
        } else {
          // If 401 or 404, we must require setup or wait for token propagation
          if (res.status === 404) setShowSetup(true)
        }
      } catch (e) {
        console.error('Failed to load profile:', e)
        if (!clerkAvailable) {
          setProfile({ role: 'student', interests: ['AI', 'startups'], level: 'beginner' })
        }
      }
    }
    loadProfile()
  }, [isSignedIn, getAuthHeaders])

  const handleProfileSetup = async (setupData) => {
    try {
      const headers = await getAuthHeaders()
      await fetch(`${API}/auth/profile/setup`, {
        method: 'POST',
        headers,
        body: JSON.stringify(setupData),
      })
      setProfile({ ...profile, ...setupData, needs_setup: false })
      setShowSetup(false)
    } catch (e) {
      console.error('Profile setup failed:', e)
    }
  }

  const handleVideoGenerate = async (topic, sourceUrl) => {
    try {
      const headers = await getAuthHeaders()
      const res = await fetch(`${API}/video/generate`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ topic, source_url: sourceUrl }),
      })
      const data = await res.json()
      setVideoJob(data)
    } catch (e) {
      console.error('Video generation failed:', e)
    }
  }

  if (!isLoaded) {
    return (
      <div className="dashboard">
        <div className="feed-loading">
          <div className="spinner" />
          <div>Loading...</div>
        </div>
      </div>
    )
  }

  if (!isSignedIn && clerkAvailable) {
    return (
      <div className="dashboard">
        <div className="feed-loading" style={{ gap: 24 }}>
          <div style={{ fontFamily: 'var(--font-editorial)', fontSize: 32, fontWeight: 800 }}>
            ET Intelligence Platform
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 16 }}>
            Sign in to access your personalized newsroom
          </div>
          <SignInButton mode="modal">
            <button className="landing-cta">Sign In →</button>
          </SignInButton>
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <Navbar
        user={user}
        profile={profile}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        clerkAvailable={clerkAvailable}
      />

      <div className="dashboard-body">
        <div className="dashboard-main">
          <NewsFeed
            profile={profile}
            getAuthHeaders={getAuthHeaders}
            onVideoGenerate={handleVideoGenerate}
          />
        </div>

        <AISidebar
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          getAuthHeaders={getAuthHeaders}
        />
      </div>

      {videoJob && (
        <VideoModal
          job={videoJob}
          onClose={() => setVideoJob(null)}
        />
      )}

      {showSetup && (
        <ProfileSetup
          onComplete={handleProfileSetup}
        />
      )}
    </div>
  )
}
