import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useSession } from '../session.js'
import { Provenance } from './common.jsx'
import { speak, stopSpeaking, canListen, listen } from '../speech.js'

const SUGGEST = {
  dashboard: ['What is the main problem, in one sentence?', 'Why are transfers the cause?', 'What should Northwind do about smart meters?'],
  intake: ['How does the router decide the owner?', 'What does "non-transferred history" mean?'],
  replay: ['Is the Replay saving guaranteed?', 'Where do the per-transfer numbers come from?'],
  queue: ['Why is the top case ranked first?', 'Why not trust the stored breach flag?', 'What should I do next with this case?'],
}
const KIND = { OBSERVED: 'observed', POLICY: 'policy', ASSUMPTION: 'assumption', SIMULATED: 'simulated' }

export default function Assistant({ page }) {
  const { config, can, focus } = useSession()
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const endRef = useRef()
  const inputRef = useRef()

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [msgs, open])
  useEffect(() => { if (open) inputRef.current?.focus() }, [open])
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && open) { setOpen(false); stopSpeaking() } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!config || !can('assistant:use')) return null
  const ai = config.ai?.gemini
  const voiceProvider = config.voice?.elevenlabs ? 'elevenlabs' : 'browser'

  const send = async (q = text) => {
    q = q.trim()
    if (!q || busy) return
    const history = msgs.map((m) => ({ role: m.role, text: m.text })).slice(-6)
    setMsgs((m) => [...m, { role: 'user', text: q }])
    setText('')
    setBusy(true)
    try {
      const r = await api.ask({ question: q, history, page, case_id: focus.case_id, alert_id: focus.alert_id })
      setMsgs((m) => [...m, { role: 'assistant', text: r.answer, mode: r.mode, evidence: r.evidence, note: r.note }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', text: `Sorry, that failed: ${e.message}`, mode: 'error', evidence: [] }])
    }
    setBusy(false)
  }

  const mic = () => {
    if (listening) return
    setListening(true)
    listen({ onResult: (t) => { setText(t); send(t) }, onEnd: () => setListening(false) })
  }

  const context = focus.case_id ? `Case ${focus.case_id}` : focus.alert_id ? `Alert ${focus.alert_id}` : null

  return (
    <>
      <button className="assistant-fab" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="assistant-panel">
        {open ? 'Close' : 'Ask Northwind'}
      </button>
      {open && (
        <section id="assistant-panel" className="assistant" role="dialog" aria-label="Ask Northwind assistant">
          <header className="row between">
            <div>
              <b>Ask Northwind</b>
              <div className="small muted">
                {ai ? `Gemini (${config.ai.model}), answers only from the app's evidence` : 'AI off: answers are looked up from the app’s evidence'}
              </div>
            </div>
            <button className="btn sm" onClick={() => { setOpen(false); stopSpeaking() }} aria-label="Close assistant">✕</button>
          </header>
          {context && <div className="chip" style={{ alignSelf: 'flex-start' }}>Context: {context}</div>}
          <div className="assistant-msgs" aria-live="polite">
            {msgs.length === 0 && (
              <div className="stack" style={{ gap: 6 }}>
                <div className="small ink2">Ask about the problem, the numbers or how to use this page. Answers cite the evidence they use.</div>
                {(SUGGEST[page] || SUGGEST.dashboard).map((s) => (
                  <button key={s} className="btn sm" style={{ textAlign: 'left', whiteSpace: 'normal' }} onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            )}
            {msgs.map((m, i) => <Message key={i} m={m} voiceProvider={voiceProvider} fallback={config.voice?.browser_fallback !== false} />)}
            {busy && <div className="small muted">Thinking…</div>}
            <div ref={endRef} />
          </div>
          <form className="row" style={{ flexWrap: 'nowrap' }} onSubmit={(e) => { e.preventDefault(); send() }}>
            <input ref={inputRef} type="text" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a question" style={{ flex: 1 }} aria-label="Question" />
            {canListen() && (
              <button type="button" className="btn sm" onClick={mic} aria-label="Ask by voice" title="Ask by voice (browser speech recognition)">
                {listening ? '●' : '🎤'}
              </button>
            )}
            <button className="btn sm primary" disabled={busy || !text.trim()}>Send</button>
          </form>
        </section>
      )}
    </>
  )
}

function Message({ m, voiceProvider, fallback }) {
  const [openEv, setOpenEv] = useState(null)
  const [voiceErr, setVoiceErr] = useState(null)
  if (m.role === 'user') return <div className="msg user">{m.text}</div>
  const clean = m.text.replace(/\s*\[([ECA]\d+)\]/g, ' [$1]')
  const read = () => {
    const plain = m.text.replace(/\[[ECA]\d+\]/g, '').replace(/[-*]\s/g, '')
    const provider = plain.length <= 600 ? voiceProvider : 'browser'
    setVoiceErr(null)
    speak(plain, { provider, fetchAudio: () => api.tts(plain), fallback }).then((r) => setVoiceErr(r.error || null))
  }
  return (
    <div className="msg bot">
      <div className="row between" style={{ marginBottom: 4 }}>
        {m.mode === 'gemini' ? <Provenance kind="ai" /> : m.mode === 'offline' ? <Provenance kind="template" text="Evidence lookup (AI off)" /> : <span />}
        {m.mode !== 'error' && <button className="btn sm" onClick={read} aria-label="Read answer aloud" title="Read aloud">🔊</button>}
      </div>
      <div style={{ whiteSpace: 'pre-wrap' }}>{clean}</div>
      {m.note && <div className="small muted" style={{ marginTop: 4 }}>{m.note}</div>}
      {voiceErr && <div className="small" style={{ marginTop: 4, color: 'var(--critical)' }}>ElevenLabs didn’t play: {voiceErr}</div>}
      {m.evidence?.length > 0 && (
        <div className="row" style={{ marginTop: 6, gap: 4 }}>
          {m.evidence.map((e) => (
            <button key={e.id} className={`chip cite ${openEv === e.id ? 'on' : ''}`} onClick={() => setOpenEv(openEv === e.id ? null : e.id)}>{e.id}</button>
          ))}
        </div>
      )}
      {openEv && (() => {
        const e = m.evidence.find((x) => x.id === openEv)
        return <div className="evidence"><Provenance kind={KIND[e.kind] || 'observed'} /> {e.text}</div>
      })()}
    </div>
  )
}
