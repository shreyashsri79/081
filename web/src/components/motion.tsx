import { useEffect, useRef, useState, type ReactNode } from 'react'
import { animate, motion, useInView, useReducedMotion } from 'motion/react'
import { cn } from '@/lib/utils'

/**
 * Motion primitives. Patterns after Magic UI (Number Ticker, Marquee, Blur
 * Fade) and Motion Primitives (text reveal), rewritten on `motion/react` and
 * restyled to the tokens. See CREDITS.md.
 */

const EASE = [0.2, 0.7, 0.3, 1] as const

/** Counts from 0 to `value` when scrolled into view. The end value is the measured one. */
export function NumberTicker({ value, digits = 0, className, delay = 0 }: { value: number; digits?: number; className?: string; delay?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const seen = useInView(ref, { once: true, margin: '0px 0px -10% 0px' })
  const reduce = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el || !seen) return
    if (reduce) { el.textContent = value.toFixed(digits); return }
    const c = animate(0, value, {
      duration: 1.1,
      delay,
      ease: EASE,
      onUpdate: (v) => { el.textContent = v.toFixed(digits) },
    })
    return () => c.stop()
  }, [seen, value, digits, delay, reduce])
  return <span ref={ref} className={cn('mono', className)}>{(0).toFixed(digits)}</span>
}

/** Fade + rise on entering the viewport, once. */
export function Reveal({ children, delay = 0, className, y = 10 }: { children: ReactNode; delay?: number; className?: string; y?: number }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '0px 0px -8% 0px' }}
      transition={{ duration: 0.5, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  )
}

/** Headline set line by line behind a mask. */
export function LineReveal({ lines, className, delay = 0 }: { lines: ReactNode[]; className?: string; delay?: number }) {
  return (
    <span className={className}>
      {lines.map((l, k) => (
        <span key={k} className="block overflow-hidden pb-[0.06em]">
          <motion.span
            className="block"
            initial={{ y: '105%' }}
            animate={{ y: 0 }}
            transition={{ duration: 0.7, delay: delay + k * 0.09, ease: EASE }}
          >
            {l}
          </motion.span>
        </span>
      ))}
    </span>
  )
}

/** Continuous strip of real vocabulary. Pauses on hover; static under reduced motion. */
export function Marquee({ items, className }: { items: ReactNode[]; className?: string }) {
  const [paused, setPaused] = useState(false)
  const row = (
    <div className="flex shrink-0 items-center gap-8 pr-8" aria-hidden>
      {items.map((it, k) => <span key={k} className="flex shrink-0 items-center gap-8">{it}<span className="text-ink-3">·</span></span>)}
    </div>
  )
  return (
    <div className={cn('flex overflow-hidden', className)} onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="marquee flex" style={{ animationPlayState: paused ? 'paused' : 'running' }}>
        {row}
        {row}
      </div>
    </div>
  )
}
