import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

function getConversations() {
  try {
    return JSON.parse(localStorage.getItem('et_conversations') || '[]')
  } catch { return [] }
}

function saveConversations(conversations) {
  localStorage.setItem('et_conversations', JSON.stringify(conversations))
}

export default function AISidebar({ open, onClose }) {
  const navigate = useNavigate()
  const [conversations, setConversations] = useState(getConversations)
  const [tool, setTool] = useState('navigator')
  const [editingId, setEditingId] = useState(null)
  const [editTitle, setEditTitle] = useState('')

  // Allow sidebar to dynamically update if conversations changed in HubPage
  useEffect(() => {
    if (open) {
      setConversations(getConversations())
    }
  }, [open])

  const selectConversation = useCallback((convo) => {
    navigate(`/hub?id=${convo.id}`)
    onClose()
  }, [navigate, onClose])

  const deleteConversation = useCallback((id, e) => {
    e.stopPropagation()
    const updated = conversations.filter(c => c.id !== id)
    setConversations(updated)
    saveConversations(updated)
  }, [conversations])

  const startRename = useCallback((id, title, e) => {
    e.stopPropagation()
    setEditingId(id)
    setEditTitle(title)
  }, [])

  const saveRename = useCallback(() => {
    const updated = conversations.map(c =>
      c.id === editingId ? { ...c, title: editTitle } : c
    )
    setConversations(updated)
    saveConversations(updated)
    setEditingId(null)
  }, [conversations, editingId, editTitle])

  return (
    <div className={`sidebar ${!open ? 'sidebar--hidden' : ''}`}>
      <div className="sidebar__header">
        <div className="sidebar__title">📖 History</div>
        <button className="sidebar__close" onClick={onClose}>✕</button>
      </div>

      {/* Tool Selector */}
      <div className="tool-selector">
        <button
          className={`tool-btn ${tool === 'navigator' ? 'active' : ''}`}
          onClick={() => setTool('navigator')}
        >
          📰 News Navigator
        </button>
        <button
          className={`tool-btn ${tool === 'storyarc' ? 'active' : ''}`}
          onClick={() => setTool('storyarc')}
        >
          🧬 Story Arc
        </button>
      </div>

      {/* Chat History */}
      <div className="sidebar__history" style={{ flex: 1 }}>
        {conversations.filter(c => c.tool === tool).length === 0 && (
          <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 14 }}>
            No history for {tool === 'navigator' ? 'News Navigator' : 'Story Arc'} yet.
          </div>
        )}
        
        {conversations.filter(c => c.tool === tool).map(convo => (
          <div
            key={convo.id}
            className={`history-item`}
            onClick={() => selectConversation(convo)}
          >
            {editingId === convo.id ? (
              <input
                className="form-input"
                style={{ fontSize: 12, padding: '4px 8px' }}
                value={editTitle}
                onChange={e => setEditTitle(e.target.value)}
                onBlur={saveRename}
                onKeyDown={e => e.key === 'Enter' && saveRename()}
                autoFocus
                onClick={e => e.stopPropagation()}
              />
            ) : (
              <span className="history-item__title">{convo.title}</span>
            )}
            <div className="history-item__actions">
              <button
                className="history-action"
                onClick={e => startRename(convo.id, convo.title, e)}
                title="Rename"
              >✏️</button>
              <button
                className="history-action"
                onClick={e => deleteConversation(convo.id, e)}
                title="Delete"
              >🗑️</button>
            </div>
          </div>
        ))}
        <button 
          className="btn-new-chat" 
          onClick={() => {
            navigate('/hub')
            onClose()
          }}
          style={{ marginTop: 20 }}
        >
          + New Search
        </button>
      </div>
    </div>
  )
}
