const CATEGORY_BADGE_CLASS = {
  markets: 'badge--markets',
  technology: 'badge--tech',
  tech: 'badge--tech',
  startups: 'badge--startups',
  finance: 'badge--finance',
  economy: 'badge--finance',
}

export default function ArticleCard({ article, onVideoGenerate }) {
  const {
    title,
    url,
    source,
    category,
    tags,
    relevance_score,
    personalized,
    ai_generated,
    published,
  } = article

  const badgeClass = CATEGORY_BADGE_CLASS[category?.toLowerCase()] || 'badge--general'
  const score = relevance_score ? Math.round(relevance_score * 100) / 100 : null

  const handleVideoClick = (e) => {
    e.stopPropagation()
    onVideoGenerate(title, url)
  }

  return (
    <div className="article-card" id={`article-${title?.substring(0, 20)?.replace(/\s/g, '-')}`}>
      <div className="article-card__header">
        {source && <span className="badge badge--source">{source}</span>}
        {category && <span className={`badge ${badgeClass}`}>{category}</span>}
        {tags?.slice(0, 2).map((tag, i) => (
          <span key={i} className="badge badge--source">{tag}</span>
        ))}
        {score !== null && (
          <span className="badge badge--relevance">{score.toFixed(1)}</span>
        )}
      </div>

      <h2 className="article-card__title">{title}</h2>

      {published && (
        <div className="article-card__time">{published}</div>
      )}

      {personalized && Object.keys(personalized).length > 0 && (
        <div className="article-card__insights">
          {personalized.summary && (
            <div className="insight insight--summary">
              <span className="insight__icon">📋</span>
              <div className="insight__content">
                <div className="insight__label">AI Summary</div>
                <div className="insight__text">{personalized.summary}</div>
              </div>
            </div>
          )}
          {personalized.key_insight && (
            <div className="insight insight--highlight">
              <span className="insight__icon">💡</span>
              <div className="insight__content">
                <div className="insight__label">Key Insight</div>
                <div className="insight__text">{personalized.key_insight}</div>
              </div>
            </div>
          )}
          {personalized.action_item && (
            <div className="insight insight--action">
              <span className="insight__icon">🎯</span>
              <div className="insight__content">
                <div className="insight__label">For You</div>
                <div className="insight__text">{personalized.action_item}</div>
              </div>
            </div>
          )}
          {personalized.market_impact && (
            <div className="insight insight--market">
              <span className="insight__icon">📊</span>
              <div className="insight__content">
                <div className="insight__label">Market Impact</div>
                <div className="insight__text">{personalized.market_impact}</div>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="article-card__footer">
        {ai_generated && (
          <div className="ai-indicator">
            <div className="ai-dot" />
            AI Personalized
          </div>
        )}
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="read-more">
            Read full article →
          </a>
        )}
      </div>

      <button className="video-trigger" onClick={handleVideoClick}>
        🎬 Create Video Summary
      </button>
    </div>
  )
}
