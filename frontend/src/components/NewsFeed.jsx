import { useState, useEffect } from 'react'
import ArticleCard from './ArticleCard'

const API = '/api'

export default function NewsFeed({ profile, getAuthHeaders, onVideoGenerate }) {
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchFeed = async () => {
    setLoading(true)
    setError(null)
    try {
      const headers = await getAuthHeaders()
      const res = await fetch(`${API}/news/feed`, { headers })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setArticles(data.articles || [])
    } catch (e) {
      console.error('Feed error:', e)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { 
    if (profile) fetchFeed() 
  }, [profile?.role])

  if (loading) {
    return (
      <>
        <div className="feed-header">
          <div>
            <h1 className="feed-title">Your Briefing</h1>
            <div className="feed-count">Loading personalized articles...</div>
          </div>
        </div>
        {[1, 2, 3].map(i => (
          <div key={i} className="skeleton-card">
            <div className="skeleton skeleton--sm" />
            <div className="skeleton skeleton--lg" />
            <div className="skeleton skeleton--md" />
            <div className="skeleton skeleton--block" />
          </div>
        ))}
      </>
    )
  }

  if (error) {
    return (
      <>
        <div className="feed-header">
          <div>
            <h1 className="feed-title">Your Briefing</h1>
          </div>
        </div>
        <div style={{
          padding: 40,
          textAlign: 'center',
          color: 'var(--text-secondary)',
        }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📰</div>
          <div style={{ marginBottom: 8 }}>Unable to load your feed</div>
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 20 }}>{error}</div>
          <button className="btn-refresh" onClick={fetchFeed}>↻ Try Again</button>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="feed-header">
        <div>
          <h1 className="feed-title">Your Briefing</h1>
          <div className="feed-count">
            {articles.length} articles personalized for {profile?.role || 'you'}
          </div>
        </div>
        <button className="btn-refresh" onClick={fetchFeed}>
          ↻ Refresh
        </button>
      </div>

      {articles.length === 0 ? (
        <div style={{
          padding: 60,
          textAlign: 'center',
          color: 'var(--text-secondary)',
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🗞️</div>
          <div>No articles yet — the system is crunching the latest news.</div>
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginTop: 8 }}>
            Articles refresh every 15 minutes.
          </div>
        </div>
      ) : (
        articles.map((article, i) => (
          <ArticleCard
            key={i}
            article={article}
            onVideoGenerate={onVideoGenerate}
          />
        ))
      )}
    </>
  )
}
