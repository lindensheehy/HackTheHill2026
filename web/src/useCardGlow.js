import { useEffect } from 'react'

const CARD_SELECTOR = '.card, .region-card, .region-item, .glow-card'

export default function useCardGlow() {
  useEffect(() => {
    const allowed = window.matchMedia(
      '(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)'
    )

    let frame = null
    let mouseX = 0
    let mouseY = 0
    let illuminated = new Set()

    function clear() {
      if (frame !== null) cancelAnimationFrame(frame)
      frame = null

      for (const card of illuminated) {
        card.style.removeProperty('--nw-glow')
        card.style.removeProperty('--nw-x')
        card.style.removeProperty('--nw-y')
      }

      illuminated.clear()
    }

    function paint() {
      frame = null
      if (!allowed.matches) return

      // Read positions first, then update styles.
      const measurements = Array.from(
        document.querySelectorAll(CARD_SELECTOR),
        card => ({ card, rect: card.getBoundingClientRect() })
      )

      const next = new Set()

      for (const { card, rect } of measurements) {
        if (
          rect.width === 0 || rect.height === 0 ||
          rect.bottom < 0 || rect.top > window.innerHeight ||
          rect.right < 0 || rect.left > window.innerWidth
        ) continue

        const dx = Math.max(rect.left - mouseX, 0, mouseX - rect.right)
        const dy = Math.max(rect.top - mouseY, 0, mouseY - rect.bottom)

        // Nearby cards share the same spotlight.
        if (Math.hypot(dx, dy) > 320) continue

        card.style.setProperty('--nw-x', `${mouseX - rect.left}px`)
        card.style.setProperty('--nw-y', `${mouseY - rect.top}px`)
        card.style.setProperty('--nw-glow', '1')
        next.add(card)
      }

      for (const card of illuminated) {
        if (!next.has(card)) {
          card.style.removeProperty('--nw-glow')
          card.style.removeProperty('--nw-x')
          card.style.removeProperty('--nw-y')
        }
      }

      illuminated = next
    }

    function move(event) {
      if (!allowed.matches || event.pointerType === 'touch') return

      mouseX = event.clientX
      mouseY = event.clientY

      if (frame === null) frame = requestAnimationFrame(paint)
    }

    document.addEventListener('pointermove', move, { passive: true })
    document.documentElement.addEventListener('pointerleave', clear)
    window.addEventListener('blur', clear)
    window.addEventListener('scroll', clear, true)
    window.addEventListener('resize', clear)
    window.addEventListener('hashchange', clear)
    allowed.addEventListener('change', clear)

    return () => {
      document.removeEventListener('pointermove', move)
      document.documentElement.removeEventListener('pointerleave', clear)
      window.removeEventListener('blur', clear)
      window.removeEventListener('scroll', clear, true)
      window.removeEventListener('resize', clear)
      window.removeEventListener('hashchange', clear)
      allowed.removeEventListener('change', clear)
      clear()
    }
  }, [])
}