import { useState, useRef, useEffect, useCallback } from 'react'
import { marked } from 'marked'
import { useAuth } from '@clerk/clerk-react'
import { useSearchParams } from 'react-router-dom'
import Navbar from '../components/Navbar'
import './HubPage.css'

const API = '/api'

function getConversations() {
  try {
    return JSON.parse(localStorage.getItem('et_conversations') || '[]')
  } catch { return [] }
}

function saveConversations(conversations) {
  localStorage.setItem('et_conversations', JSON.stringify(conversations))
}

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 5)
}

export default function HubPage({ profile }) {
  const { getToken, isSignedIn } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlId = searchParams.get('id')
  
  const [input, setInput] = useState('')
  const [tool, setTool] = useState(null) 
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [activeId, setActiveId] = useState(null)
  
  const bottomRef = useRef(null)

  // Load conversation from URL ID
  useEffect(() => {
    if (urlId && urlId !== activeId) {
      const convos = getConversations()
      const convo = convos.find(c => c.id === urlId)
      if (convo) {
        setMessages(convo.messages || [])
        setTool(convo.tool || 'navigator')
        setActiveId(urlId)
      } else {
        // ID not found, reset url
        setSearchParams({})
      }
    }
  }, [urlId, activeId, setSearchParams])

  const getAuthHeaders = useCallback(async () => {
    const headers = { 'Content-Type': 'application/json' }
    if (isSignedIn) {
      const token = await getToken()
      if (token) headers['Authorization'] = `Bearer ${token}`
    } else {
      headers['X-User-Id'] = 'demo_user_001'
    }
    return headers
  }, [isSignedIn, getToken])

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const startTopic = async (selectedTool) => {
    if (!input.trim() || loading) return
    
    setTool(selectedTool)
    const userMessage = { role: 'user', content: `Analyze: ${input.trim()}` }
    setMessages([userMessage])
    setLoading(true)

    try {
      const endpoint = selectedTool === 'navigator' ? '/intel/generate' : '/intel/generate-arc'
      const headers = await getAuthHeaders()
      
      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ topic: input.trim() }),
      })

      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()

      let assistantContent = ''
      
      if (selectedTool === 'navigator') {
        const briefing = data.briefing
        if (typeof briefing === 'string') {
          assistantContent = briefing
        } else {
          let md = ''
          for (const key in briefing) {
            md += `## ${key}\n`
            if (Array.isArray(briefing[key])) {
              md += briefing[key].map(item => `- ${item}`).join('\n') + '\n'
            } else {
              md += `${briefing[key]}\n`
            }
            md += '\n'
          }
          if (data.followups?.length > 0) {
            md += `\n---\n\n**Suggested follow-ups:**\n`
            md += data.followups.map(q => `- ${q}`).join('\n')
          }
          assistantContent = md
        }
      } else {
        // Story arc
        let md = `## Story Summary\n${data.story_summary}\n\n`
        if (data.timeline?.length > 0) {
          md += `## Timeline\n`
          data.timeline.forEach(evt => {
            md += `**[${evt.date}]** ${evt.title}\n> ${evt.summary}\n\n`
          })
        }
        if (data.key_players?.length > 0) {
          md += `## Key Players\n`
          md += data.key_players.map(p => `- **${p.name}** — ${p.role}`).join('\n') + '\n\n'
        }
        if (data.sentiment_overview) {
          md += `## Sentiment\nOverall: **${data.sentiment_overview.overall}**\n\n`
        }
        if (data.contrarian_insights) {
          md += `## Contrarian Insights\n**Mainstream:** ${data.contrarian_insights.mainstream}\n`
          if (data.contrarian_insights.contrarian?.length > 0) {
            md += data.contrarian_insights.contrarian.map(c => `- ${c}`).join('\n') + '\n\n'
          }
        }
        if (data.what_to_watch?.length > 0) {
          md += `## What to Watch\n`
          md += data.what_to_watch.map(p => `- ${p}`).join('\n')
        }
        assistantContent = md
      }

      const updatedMessages = [userMessage, { role: 'assistant', content: assistantContent }]
      setMessages(updatedMessages)
      setInput('')
      
      // Save
      const convos = getConversations()
      let cId = activeId
      if (!cId) {
        cId = generateId()
        setActiveId(cId)
        setSearchParams({ id: cId })
        convos.unshift({
          id: cId,
          title: input.trim().substring(0, 40) + '...',
          tool: selectedTool,
          messages: updatedMessages,
          createdAt: new Date().toISOString()
        })
      } else {
        const idx = convos.findIndex(c => c.id === cId)
        if (idx !== -1) convos[idx].messages = updatedMessages
      }
      saveConversations(convos)
      
    } catch (e) {
      setMessages([userMessage, { role: 'assistant', content: `⚠️ Error: ${e.message}. Please try again.` }])
    } finally {
      setLoading(false)
    }
  }

  const askFollowup = async (questionText) => {
    if (!questionText.trim() || loading) return
    
    setInput('')
    const userMessage = { role: 'user', content: questionText.trim() }
    setMessages(prev => [...prev, userMessage])
    setLoading(true)

    try {
      const headers = await getAuthHeaders()
      const res = await fetch(`${API}/intel/ask`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ question: questionText.trim() }),
      })

      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      
      const assistantMessage = { role: 'assistant', content: data.answer || 'No response received.' }
      const newMsgs = [...messages, userMessage, assistantMessage]
      setMessages(newMsgs)
      
      // Save
      if (activeId) {
        const convos = getConversations()
        const idx = convos.findIndex(c => c.id === activeId)
        if (idx !== -1) {
          convos[idx].messages = newMsgs
          saveConversations(convos)
        }
      }
      
    } catch (e) {
      setMessages([...messages, userMessage, { role: 'assistant', content: `⚠️ Error: ${e.message}. Please try again.` }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e, isFollowup = false) => {
    if (e.key === 'Enter') {
      if (isFollowup) {
        askFollowup(input)
      } else {
        // Default to navigator on enter if initially empty
        startTopic('navigator')
      }
    }
  }

  const resetHub = () => {
    setMessages([])
    setTool(null)
    setInput('')
    setActiveId(null)
    setSearchParams({})
  }

  return (
    <div className="hub-page">
      <Navbar profile={profile} />
      
      <main className="hub-main">
        {messages.length === 0 ? (
          <>
            <div className="hub-header">
              <div className="hub-title">
                <span className="hub-icon-et">⚡</span>
                ET Intelligence Hub
              </div>
              <p className="hub-tagline">AI-Powered News Analysis & Story Arc Tracking</p>
            </div>
            
            <section className="hub-input-section">
              <div className="hub-input-card">
                <label className="hub-input-label">What topic do you want to explore?</label>
                <input
                  type="text"
                  className="hub-topic-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => handleKeyDown(e, false)}
                  placeholder="e.g. RBI rate cuts, Adani Hindenburg, EV market India..."
                  autoComplete="off"
                />
                <div className="hub-button-group">
                  <button 
                    className="btn-hub-tool primary" 
                    onClick={() => startTopic('navigator')}
                    disabled={!input.trim()}
                  >
                    <span className="hub-btn-icon">📰</span>
                    Generate News Briefing
                  </button>
                  <button 
                    className="btn-hub-tool" 
                    onClick={() => startTopic('storyarc')}
                    disabled={!input.trim()}
                  >
                    <span className="hub-btn-icon">🧬</span>
                    Generate Story Arc
                  </button>
                </div>
              </div>
            </section>
          </>
        ) : (
          <section className="hub-results-section">
            <div className="hub-section-header">
              <h2>
                {tool === 'navigator' ? '📰 News Navigator Briefing' : '🧬 Story Arc Analysis'}
              </h2>
              <button className="btn-hub-reset" onClick={resetHub}>← New Topic</button>
            </div>
            
            <div className="hub-chat-history">
              {messages.map((msg, i) => (
                <div key={i} className={`hub-chat-message ${msg.role}`}>
                  {msg.role === 'assistant' ? (
                    <div className="hub-result-card">
                      <div dangerouslySetInnerHTML={{ __html: marked.parse(msg.content) }} />
                    </div>
                  ) : (
                    <div className="msg-bubble">
                      <strong>{msg.content}</strong>
                    </div>
                  )}
                </div>
              ))}
            </div>
            
            {loading && (
              <div className="hub-loading-card">
                <div className="hub-spinner"></div>
                <div className="hub-loading-title">Agent is processing...</div>
                <div className="hub-loading-sub">Collecting intel, generating insights.</div>
              </div>
            )}
            
            {!loading && (
              <div className="hub-qa-section">
                <h3>💬 Ask a Follow-up Question</h3>
                <div className="hub-qa-row">
                  <input
                    type="text"
                    className="hub-qa-input"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => handleKeyDown(e, true)}
                    placeholder="Ask anything about the report..."
                  />
                  <button 
                    className="btn-hub-ask" 
                    onClick={() => askFollowup(input)}
                    disabled={!input.trim()}
                  >
                    Ask
                  </button>
                </div>
              </div>
            )}
            
            <div ref={bottomRef} />
          </section>
        )}
      </main>
    </div>
  )
}
