import type { ReactNode } from 'react'
import { Reveal, NumberTicker } from '@/components/motion'
import type { ModelId } from '@/lib/contract'
import { MODELS } from '@/lib/models'
import { cn } from '@/lib/utils'
import { Matrix } from './Landing'

/**
 * Data & Models. Every row is a fact from WORKFLOW_AND_DECK_81.md §B4, §B4.2,
 * §C10 and §C12 (store metadata checked 28 Sep 2026). Nothing here is synthetic.
 */

const SOURCES: { name: string; m?: ModelId; family: string; years: string; leads: string; rain: string; other: string; store: string }[] = [
  { name: 'IFS HRES', m: 'hres', family: 'Physics NWP', years: '2016–2022', leads: '0–240 h, 6 h (41)', rain: 'yes', other: 'yes', store: 'hres/2016-2022-0012-240x121_equiangular_with_poles_conservative.zarr' },
  { name: 'GraphCast', m: 'graphcast', family: 'AI', years: '2018, 2020, 2022', leads: '6–240 h (40)', rain: 'yes', other: 'yes', store: 'graphcast_v2/{2018,2020,2022}-240x121_…_conservative.zarr' },
  { name: 'Pangu-Weather', m: 'pangu', family: 'AI', years: '2018–2022', leads: '6–240 h (40)', rain: 'no', other: 'yes', store: 'pangu/2018-2022_0012_240x121_…_conservative.zarr' },
  { name: 'FuXi', m: 'fuxi', family: 'AI', years: '2020', leads: 'to 15 d (60)', rain: 'yes, 24 h from 6 h', other: 'yes', store: 'fuxi/2020-240x121_…_conservative.zarr' },
  { name: 'GenCast (mean)', m: 'gencast', family: 'AI ensemble', years: '2020', leads: '12 h–15 d (30)', rain: 'yes', other: 'yes', store: 'gencast/2020-240x121_…_conservative_mean.zarr' },
  { name: 'Aurora', family: 'AI', years: '2022', leads: '40', rain: 'no', other: 'yes', store: 'aurora/2022-240x121_… (not in the blend yet)' },
  { name: 'NeuralGCM', family: 'Hybrid AI–physics', years: '2020', leads: '31', rain: 'no (P − E only)', other: 'pressure levels only', store: 'not used' },
]

const SETS = [
  { id: 'S1', models: 'HRES + GraphCast + Pangu', vars: 'T2m, wind, MSLP', years: '2018, 2020, 2022', val: 'Leave-one-year-out (3 folds)', role: 'Headline number' },
  { id: 'S2', models: 'HRES + GraphCast', vars: 'rain + T2m + wind', years: '2018, 2020, 2022', val: 'Leave-one-year-out', role: 'Rain headline' },
  { id: 'S3', models: 'HRES + GraphCast + Pangu + FuXi + GenCast', vars: 'T2m, wind, MSLP', years: '2020', val: 'Blocked months', role: 'Weight maps; do more models help?' },
  { id: 'S4', models: 'HRES + GraphCast + FuXi + GenCast', vars: 'rain', years: '2020', val: 'Blocked months', role: 'Rain weight maps, extremes' },
]

const LIVE: { m: ModelId; counterpart: string; start: string }[] = [
  { m: 'ifs', counterpart: 'HRES (same system)', start: 'HRES skill and seasonal bias carry over; then online update (B4)' },
  { m: 'aifs', counterpart: 'GraphCast (AI, trained on ERA5)', start: 'GraphCast skill as prior; no bias correction; then online update (B4)' },
  { m: 'gfs', counterpart: 'none in WeatherBench 2', start: 'HRES skill with 1.5x error: near-zero weight until its own verified days accumulate' },
  { m: 'ncum', counterpart: 'none (not public)', start: 'Only when NCMRWF shares GRIB2: HRES skill with 1.5x error, then its own verified days (B4)' },
  { m: 'nepsg', counterpart: 'none (not public)', start: 'Only when NCMRWF shares GRIB2: members averaged, HRES skill with 1.5x error, then B4' },
]

const TRUTH = [
  { name: 'ERA5', use: 'Truth for T2m, wind, MSLP; regime labels', access: 'WeatherBench 2, 1959–2022', note: 'Rain is in metres: convert' },
  { name: 'CHIRPS 2.0, 0.25° daily', use: 'Rain truth over land', access: 'Open HTTPS (UCSB CHC)', note: 'Verifying rain on ERA5 rewards models that look like ERA5' },
  { name: 'IMD gridded rain, 0.25°', use: 'Better rain truth', access: 'Unconfirmed from our network', note: 'Try from the team network' },
]

function Head({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <Reveal><div className="label text-ink-2">{eyebrow}</div></Reveal>
      <Reveal><h2 className="t-section">{title}</h2></Reveal>
      {children && <Reveal delay={0.08}><div className="max-w-[44rem] text-[15.5px] leading-relaxed text-ink-2">{children}</div></Reveal>}
    </div>
  )
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="frame overflow-x-auto bg-surface scroll-thin">
      <table className="w-full min-w-[720px] text-[13px]">
        <thead>
          <tr className="border-b border-ink text-left text-[11px] text-ink-3">
            {head.map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}
const td = 'border-b border-rule/70 px-3 py-2.5 align-top'

export default function Data() {
  return (
    <div className="flex flex-col gap-16 px-4 py-10 sm:px-8">
      <section className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          <Reveal><div className="label text-ink-2">Data &amp; models</div></Reveal>
          <Reveal><h1 className="t-hero text-[clamp(40px,5.5vw,80px)]">Public data, checked before promised.</h1></Reveal>
          <Reveal delay={0.1}>
            <p className="max-w-[34rem] text-[16px] leading-relaxed text-ink-2">
              Every source below was probed in the public WeatherBench 2 bucket on 28 Sep 2026, with no login. What each store
              actually holds decides what can be blended, for which variable, in which year.
            </p>
          </Reveal>
        </div>
        <Reveal delay={0.1}>
          <dl className="grid grid-cols-2 gap-px border border-ink bg-ink">
            {[
              { v: 5, l: 'models in the blend', s: '1 physics, 4 AI' },
              { v: 4, l: 'can blend rain', s: 'Pangu has no precipitation' },
              { v: 3, l: 'years, each left out in turn', s: '2018 · 2020 · 2022' },
              { v: 10, l: 'common lead days', s: 'Day 1–10 at 24 h' },
            ].map((x, k) => (
              <div key={x.l} className="bg-paper p-5">
                <dd><NumberTicker value={x.v} delay={k * 0.08} className="text-[56px] font-medium leading-none tracking-tight" /></dd>
                <dt className="mt-2 text-[14px] font-medium">{x.l}</dt>
                <div className="text-[12.5px] text-ink-3">{x.s}</div>
              </div>
            ))}
          </dl>
        </Reveal>
      </section>

      <section className="flex flex-col gap-6">
        <Head eyebrow="Forecast sources" title="What each store holds">
          All used on the 1.5° development grid (240 × 121, conservative regridding), India box 5–40° N, 65–100° E, 00 UTC inits.
          Path prefix <span className="mono text-[13px]">gs://weatherbench2/datasets/</span>.
        </Head>
        <Table head={['Source', 'Family', 'Years', 'Leads', '24 h rain', 'T2m · wind · MSLP', 'Store']}>
          {SOURCES.map((s) => (
            <tr key={s.name} className={cn(!s.m && 'text-ink-3')}>
              <td className={td}><span className="mr-2 inline-block size-2.5 align-middle" style={{ background: s.m ? MODELS[s.m].colour : '#b6b1a9' }} />{s.name}</td>
              <td className={td}>{s.family}</td>
              <td className={cn(td, 'mono text-[12px]')}>{s.years}</td>
              <td className={cn(td, 'mono text-[12px]')}>{s.leads}</td>
              <td className={cn(td, s.rain.startsWith('no') && s.m && 'text-bad font-medium')}>{s.rain}</td>
              <td className={td}>{s.other}</td>
              <td className={cn(td, 'mono text-[11px] text-ink-2 break-all')}>{s.store}</td>
            </tr>
          ))}
        </Table>
      </section>

      <section className="grid gap-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Head eyebrow="Model sets" title="Which models blend what, when">
          2020 is the only year where every AI model overlaps. The three-model trio has three years, so it carries the headline
          number with a true leave-one-year-out test. The five-model set is tested inside 2020 on held-out months, never on random days.
        </Head>
        <Reveal className="frame bg-paper p-4 sm:p-5"><Matrix /></Reveal>
      </section>

      <section>
        <Table head={['Set', 'Models', 'Variables', 'Years', 'Validation', 'Role']}>
          {SETS.map((s) => (
            <tr key={s.id}>
              <td className={cn(td, 'mono font-medium')}>{s.id}</td>
              <td className={td}>{s.models}</td>
              <td className={td}>{s.vars}</td>
              <td className={cn(td, 'mono text-[12px]')}>{s.years}</td>
              <td className={td}>{s.val}</td>
              <td className={cn(td, 'font-medium')}>{s.role}</td>
            </tr>
          ))}
        </Table>
      </section>

      <section className="grid gap-8 lg:grid-cols-2">
        <div className="flex flex-col gap-6">
          <Head eyebrow="The daily run" title="Live models are not the training models">
            The weights are learned on WeatherBench 2 hindcasts; the daily 15:00 IST run uses what is openly served every day. Stated
            plainly, because a judge will ask.
          </Head>
          <Table head={['Live source', 'Training counterpart', 'Weight at start']}>
            {LIVE.map((l) => (
              <tr key={l.m}>
                <td className={td}><span className="mr-2 inline-block size-2.5 align-middle" style={{ background: MODELS[l.m].colour }} />{MODELS[l.m].name}</td>
                <td className={td}>{l.counterpart}</td>
                <td className={td}>{l.start}</td>
              </tr>
            ))}
          </Table>
          <p className="text-[13px] text-ink-3">GraphCast and Pangu are not openly served daily, so they are excluded from the live run unless run on our own GPU.</p>
        </div>
        <div className="flex flex-col gap-6">
          <Head eyebrow="Truth" title="What the forecasts are scored against" />
          <Table head={['Source', 'Use', 'Access', 'Note']}>
            {TRUTH.map((t) => (
              <tr key={t.name}>
                <td className={cn(td, 'font-medium')}>{t.name}</td>
                <td className={td}>{t.use}</td>
                <td className={td}>{t.access}</td>
                <td className={cn(td, 'text-ink-2')}>{t.note}</td>
              </tr>
            ))}
          </Table>
        </div>
      </section>

      <section className="frame grid gap-6 bg-surface p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Head eyebrow="India's own models" title="NCUM and NEPS-G plug in through an adapter">
          NCUM (12 km deterministic) and NEPS-G (23 members) are not public. The adapter reads their GRIB2 by field name, whatever
          the file layout, averages the NEPS-G members, and feeds the daily run like GFS:
          <span className="mono text-[13px]"> python -m blend.live run --ncum DIR --nepsg DIR</span>. It is tested on generated GRIB2
          files, not on NCMRWF output.
        </Head>
        <div className="flex flex-col justify-center gap-4">
          <div className="border-l-4 border-good bg-good-bg px-4 py-3">
            <div className="label text-good">We say</div>
            <div className="t-display mt-1 text-[22px]">“Adapter ready; needs NCMRWF data to learn its weights.”</div>
          </div>
          <div className="border-l-4 border-bad bg-bad-bg px-4 py-3">
            <div className="label text-bad">We never say</div>
            <div className="t-display mt-1 text-[22px] line-through decoration-bad">“Tested on NCUM.”</div>
          </div>
        </div>
      </section>
    </div>
  )
}
