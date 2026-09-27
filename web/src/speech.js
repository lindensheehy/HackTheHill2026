// Speech output: ElevenLabs audio from our API when configured, otherwise the browser's own speechSynthesis.
// Speech input: the browser's SpeechRecognition where available (Chrome/Edge). Both are optional extras;
// every spoken text is also shown on screen.

let current = null

export function stopSpeaking() {
  if (current?.audio) { current.audio.pause(); URL.revokeObjectURL(current.url) }
  if (window.speechSynthesis) window.speechSynthesis.cancel()
  current = null
}

/**
 * Speak `text`. Returns { engine: 'elevenlabs' | 'browser' | 'none', error? }.
 * provider 'elevenlabs' + fetchAudio (a Blob from our API) tries ElevenLabs first. If that fails, `error` says why,
 * and the browser voice is used only when `fallback` is true (VOICE_BROWSER_FALLBACK on the server).
 */
export async function speak(text, { provider, fetchAudio, onEnd, fallback = true } = {}) {
  stopSpeaking()
  let error
  if (provider === 'elevenlabs' && fetchAudio) {
    try {
      const blob = await fetchAudio()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      current = { audio, url }
      audio.onended = () => { URL.revokeObjectURL(url); current = null; onEnd?.() }
      await audio.play()
      return { engine: 'elevenlabs' }
    } catch (e) {
      error = e.message || String(e)
      console.warn('ElevenLabs audio failed:', error)
      if (!fallback) { onEnd?.(); return { engine: 'none', error } }
    }
  }
  if (!window.speechSynthesis) { onEnd?.(); return { engine: 'none', error } }
  const u = new SpeechSynthesisUtterance(text)
  u.lang = 'en-GB'
  u.rate = 1
  u.onend = () => onEnd?.()
  window.speechSynthesis.speak(u)
  current = {}
  return { engine: 'browser', error }
}

export const canListen = () => !!(window.SpeechRecognition || window.webkitSpeechRecognition)

export function listen({ onResult, onEnd }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) return null
  const rec = new SR()
  rec.lang = 'en-GB'
  rec.interimResults = false
  rec.maxAlternatives = 1
  rec.onresult = (e) => onResult(e.results[0][0].transcript)
  rec.onend = () => onEnd?.()
  rec.onerror = () => onEnd?.()
  rec.start()
  return rec
}
