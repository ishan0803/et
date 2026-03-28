import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import frameUrls from 'virtual:frame-list'
import './LandingPage.css'

/* ── Section content config ── */
const SECTIONS = [
  {
    headline: 'AI-Native News Experience',
    description:
      "Business news shouldn't feel like 2005. Welcome to the future of intelligent journalism.",
    start: 0.02,
    end: 0.19,
    align: 'center',
    isHero: true,
  },
  {
    label: '01',
    headline: 'My ET — Personalized Newsroom',
    description:
      'Every reader gets a fundamentally different newsroom tailored to their interests.',
    start: 0.16,
    end: 0.34,
    align: 'left',
  },
  {
    label: '02',
    headline: 'News Navigator — Interactive Intelligence Briefings',
    description:
      'Turn multiple articles into one interactive AI briefing.',
    start: 0.31,
    end: 0.50,
    align: 'right',
  },
  {
    label: '03',
    headline: 'AI News Video Studio',
    description:
      'Transform any article into broadcast-quality AI videos.',
    start: 0.47,
    end: 0.65,
    align: 'left',
  },
  {
    label: '04',
    headline: 'Story Arc Tracker',
    description:
      'Track evolving business stories with AI-generated timelines.',
    start: 0.62,
    end: 0.81,
    align: 'right',
  },
  {
    label: '05',
    headline: 'Vernacular Business News Engine',
    description: 'Real-time business news in regional languages.',
    start: 0.78,
    end: 0.98,
    align: 'center',
  },
]

const SCROLL_VH = 500

/* ── App Component ── */
export default function LandingPage() {
  const navigate = useNavigate()
  const canvasRef = useRef(null)
  const wrapRef = useRef(null)
  const imgsRef = useRef([])
  const curFrameRef = useRef(-1)
  const [progress, setProgress] = useState(0)
  const [loadPct, setLoadPct] = useState(0)
  const [ready, setReady] = useState(false)

  /* Draw one frame on the canvas (cover-fit) */
  const draw = useCallback((idx) => {
    const cvs = canvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')
    const img = imgsRef.current[idx]
    if (!img || !img.complete) return

    const dpr = window.devicePixelRatio || 1
    const { width: w, height: h } = cvs.getBoundingClientRect()
    cvs.width = w * dpr
    cvs.height = h * dpr
    ctx.scale(dpr, dpr)

    const iw = img.naturalWidth || img.width
    const ih = img.naturalHeight || img.height
    const s = Math.max(w / iw, h / ih)
    const dw = iw * s
    const dh = ih * s
    ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh)
  }, [])

  /* Preload all frames */
  useEffect(() => {
    let count = 0
    const total = frameUrls.length
    const imgs = new Array(total)

    frameUrls.forEach((url, i) => {
      const img = new Image()
      img.src = url
      img.onload = img.onerror = () => {
        count++
        setLoadPct(count / total)
        if (count === total) {
          setReady(true)
          draw(0)
          curFrameRef.current = 0
        }
      }
      imgs[i] = img
    })
    imgsRef.current = imgs
  }, [draw])

  /* Scroll → frame + progress */
  useEffect(() => {
    let ticking = false
    const onScroll = () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(() => {
        const el = wrapRef.current
        if (!el) { ticking = false; return }
        const top = -el.getBoundingClientRect().top
        const scrollable = el.offsetHeight - window.innerHeight
        const p = Math.max(0, Math.min(1, top / scrollable))
        setProgress(p)

        const fi = Math.min(
          frameUrls.length - 1,
          Math.max(0, Math.floor(p * (frameUrls.length - 1)))
        )
        if (fi !== curFrameRef.current) {
          curFrameRef.current = fi
          draw(fi)
        }
        ticking = false
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [draw])

  /* Resize → redraw */
  useEffect(() => {
    const onResize = () => {
      if (curFrameRef.current >= 0) draw(curFrameRef.current)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [draw])

  /*
   * Improved section opacity + y-offset.
   * Overlapping ranges so the next card FADES IN before the previous one fully fades out.
   * Fade-out uses a "push up" translateY so cards slide up when leaving.
   */
  const vis = useCallback(
    (sec) => {
      const { start: s, end: e } = sec
      const r = e - s
      const fi = s + r * 0.12   // fade-in ends at 12% into range
      const fo = e - r * 0.18   // fade-out starts at 82% into range
      let op = 0, y = 40

      if (progress >= s && progress <= e) {
        if (progress < fi) {
          // Fade in: slide up from below
          const t = (progress - s) / (fi - s)
          op = t
          y = 40 * (1 - t)
        } else if (progress > fo) {
          // Fade out: push up and become nearly invisible
          const t = (progress - fo) / (e - fo)
          op = 1 - t * 0.95     // fade to near-zero
          y = -40 * t            // slide up more aggressively
        } else {
          op = 1
          y = 0
        }
      }
      return {
        opacity: Math.max(0, Math.min(1, op)),
        transform: `translateY(${y}px)`,
      }
    },
    [progress],
  )

  /* Determine active section index for the indicator dots */
  const activeSection = useMemo(() => {
    for (let i = SECTIONS.length - 1; i >= 0; i--) {
      const sec = SECTIONS[i]
      const mid = (sec.start + sec.end) / 2
      if (progress >= sec.start && progress <= sec.end) {
        // Return the one where we're closest to mid
        return i
      }
    }
    return 0
  }, [progress])

  /* ── Render ── */
  return (
    <div className="landing" ref={wrapRef} style={{ height: `${SCROLL_VH}vh` }}>
      {/* Loader */}
      <div className={`loader${ready ? ' loader--done' : ''}`}>
        <div className="loader__inner">
          <div className="loader__brand">THE ECONOMIC TIMES</div>
          <div className="loader__sub">AI-Native News Experience</div>
          <div className="loader__track">
            <div
              className="loader__fill"
              style={{ transform: `scaleX(${loadPct})` }}
            />
          </div>
          <div className="loader__pct">{Math.round(loadPct * 100)}%</div>
        </div>
      </div>

      {/* Sticky viewport */}
      <div className="viewport">
        <canvas ref={canvasRef} className="viewport__canvas" />
        <div className="viewport__vignette" />

        {/* Ambient floating particles */}
        <div className="ambient-particles">
          <div className="ambient-particles__dot" />
          <div className="ambient-particles__dot" />
          <div className="ambient-particles__dot" />
          <div className="ambient-particles__dot" />
          <div className="ambient-particles__dot" />
          <div className="ambient-particles__dot" />
        </div>

        {/* Masthead */}
        <header
          className="masthead"
          style={{ opacity: ready && progress > 0.01 ? 1 : 0 }}
        >
          <div className="masthead__rule" />
          <span className="masthead__title">THE ECONOMIC TIMES</span>
          <div className="masthead__rule" />
          <button 
            className="masthead__login-btn"
            onClick={() => navigate('/dashboard')}
          >
            Enter Newsroom
          </button>
        </header>

        {/* Section indicator dots (right side) */}
        {ready && progress > 0.01 && (
          <div className="section-indicator" style={{ opacity: progress > 0.02 ? 1 : 0 }}>
            {SECTIONS.map((_, i) => (
              <div
                key={i}
                className={`section-indicator__dot${i === activeSection ? ' section-indicator__dot--active' : ''}`}
              />
            ))}
          </div>
        )}

        {/* Content sections */}
        {SECTIONS.map((sec, i) => {
          const style = vis(sec)
          return (
            <div
              key={i}
              className={`section section--${sec.align}${sec.isHero ? ' section--hero' : ''}`}
              aria-hidden={style.opacity < 0.05}
            >
              <div className="section__inner" style={style}>
                {sec.label && <span className="section__label">{sec.label}</span>}
                <div className="section__accent" />
                <h2 className="section__headline">{sec.headline}</h2>
                <p className="section__desc">{sec.description}</p>
              </div>
            </div>
          )
        })}

        {/* Scroll cue */}
        {ready && (
          <div className="scroll-cue" style={{ opacity: progress < 0.03 ? 1 : 0 }}>
            <div className="scroll-cue__line" />
            <div className="scroll-cue__chevron">
              <span /><span /><span />
            </div>
            <span className="scroll-cue__text">Scroll to explore</span>
          </div>
        )}

        {/* Bottom frosted bar — hides veo watermark & shows team credit (Click to enter) */}
        <div
          className="bottom-bar"
          onClick={() => navigate('/dashboard')}
          style={{ opacity: ready ? 1 : 0, cursor: 'pointer' }}
        >
          <div className="bottom-bar__line" />
          <span className="bottom-bar__credit">
            Brewing Smarter News with <span className="team-name">Chai &amp; Code</span> — <span style={{color: 'rgba(245,240,232,0.85)'}}>Enter Newsroom &rarr;</span>
          </span>
          <div className="bottom-bar__line" />
        </div>

        {/* Progress bar (sits above bottom bar) */}
        <div className="progress" style={{ opacity: ready && progress > 0.01 ? 1 : 0 }}>
          <div className="progress__fill" style={{ transform: `scaleX(${progress})` }} />
        </div>
      </div>
    </div>
  )
}
