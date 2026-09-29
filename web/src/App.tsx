import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import { Disclosure, Masthead, RunStrip } from '@/components/Chrome'
import Landing from '@/screens/Landing'

// The landing ships in the first bundle; every desk screen loads on first visit (and is prefetched on idle).
const load = {
  forecast: () => import('@/screens/Forecast'),
  weights: () => import('@/screens/Weights'),
  skill: () => import('@/screens/Skill'),
  extremes: () => import('@/screens/Extremes'),
  runs: () => import('@/screens/RunLog'),
  data: () => import('@/screens/Data'),
}
const Forecast = lazy(load.forecast)
const Weights = lazy(load.weights)
const Skill = lazy(load.skill)
const Extremes = lazy(load.extremes)
const RunLog = lazy(load.runs)
const Data = lazy(load.data)
import { useDeskSync } from '@/lib/sync'

const DESK = ['/forecast', '/weights', '/skill', '/extremes', '/runs']

/** Run strip on desk screens only; story pages start at the top on navigation. */
function Shell() {
  const { pathname } = useLocation()
  const desk = DESK.includes(pathname)
  // The map explorer owns the whole viewport, as on Ventusky: no page scroll.
  const full = pathname === '/forecast'
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  useDeskSync()
  useEffect(() => {
    const idle = (window as { requestIdleCallback?: (f: () => void) => number }).requestIdleCallback ?? ((f: () => void) => setTimeout(f, 1500))
    idle(() => Object.values(load).forEach((f) => f()))
  }, [])
  return (
    <div className={full ? 'flex h-dvh flex-col pb-8' : 'flex min-h-dvh flex-col pb-8'}>
      <Masthead desk={desk} />
      {desk && <div className={full ? 'hidden md:block' : undefined}><RunStrip /></div>}
      <main className={full ? 'relative min-h-0 flex-1' : 'flex-1'}>
        <Suspense fallback={<div className="h-full min-h-[50vh]" />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/forecast" element={<Forecast />} />
          <Route path="/weights" element={<Weights />} />
          <Route path="/skill" element={<Skill />} />
          <Route path="/extremes" element={<Extremes />} />
          <Route path="/runs" element={<RunLog />} />
          <Route path="/data" element={<Data />} />
          <Route path="*" element={<Landing />} />
        </Routes>
        </Suspense>
      </main>
      <Disclosure />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      {/* "user": every Motion animation honours prefers-reduced-motion. */}
      <MotionConfig reducedMotion="user">
        <Shell />
      </MotionConfig>
    </BrowserRouter>
  )
}
