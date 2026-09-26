import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card } from './common.jsx'
import { useSession } from '../session.js'
import { speak, stopSpeaking } from '../speech.js'

// What the customer would hear and read. The text is a fixed template filled from the live case state,
// so it changes as soon as an agent changes the status. No model writes it.
export default function CustomerUpdate({ id, version, onHelp }) {
  const { can } = useSession()
  const [u, setU] = useState(null)
  const [playing, setPlaying] = useState(false)
  const [used, setUsed] = useState(null)
  useEffect(() => { api.customerUpdate(id).then(setU).catch(() => setU(false)); return stopSpeaking }, [id, version])
  if (u === false) return null

  const play = async () => {
    if (playing) { stopSpeaking(); setPlaying(false); return }
    setPlaying(true)
    const how = await speak(u.text, { provider: u.provider, fetchAudio: () => api.customerUpdateAudio(id), onEnd: () => setPlaying(false) })
    setUsed(how)
    if (how === 'none') setPlaying(false)
  }

  return (
    <Card title="Customer update" sub="What the customer hears and reads. Generated from the current case state; it changes when the status does.">
      {!u ? <div className="muted small">Loading…</div> : (
        <>
          <div className="row" style={{ marginBottom: 8 }}>
            <button className="btn sm primary" onClick={play} aria-pressed={playing}>{playing ? '■ Stop' : '▶ Play update'}</button>
            <button className="btn sm" disabled={!can('cases:write')} title={can('cases:write') ? '' : 'Needs the cases:write permission'}
              onClick={onHelp}>I still need help</button>
            <span className="small muted">
              Voice: {u.provider === 'elevenlabs' ? 'ElevenLabs' : 'browser (ElevenLabs not configured)'}
              {used && used !== u.provider ? ` · played with ${used}` : ''}
            </span>
          </div>
          <blockquote className="transcript">{u.text}</blockquote>
          <div className="small muted">Never promises repair dates or says a case is resolved unless an agent resolved it.</div>
        </>
      )}
    </Card>
  )
}
