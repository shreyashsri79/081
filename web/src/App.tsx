import { useEffect } from 'react'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import { Disclosure, Masthead, RunStrip } from '@/components/Chrome'
import Forecast from '@/screens/Forecast'
import Weights from '@/screens/Weights'
import Skill from '@/screens/Skill'
import Extremes from '@/screens/Extremes'
import RunLog from '@/screens/RunLog'
import Landing from '@/screens/Landing'
import Data from '@/screens/Data'
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
  return (
    <div className={full ? 'flex h-dvh flex-col pb-8' : 'flex min-h-dvh flex-col pb-8'}>
      <Masthead desk={desk} />
      {desk && <div className={full ? 'hidden md:block' : undefined}><RunStrip /></div>}
      <main className={full ? 'relative min-h-0 flex-1' : 'flex-1'}>
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
