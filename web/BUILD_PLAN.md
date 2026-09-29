# Frontend Build Plan — PS26081

**Owner: Shreyash.** Scope: the web application: landing, forecast desk (five screens plus the cell inspector), data and models, method and results, daily bulletin.

Requirements come from `../WORKFLOW_AND_DECK_81.md` §B1 (R1–R12), §B2 (outcomes 1–5), §C9–C12, §C13, and `../PPT_TEAM_GUIDE_81.md` §4.8, §4.11, §5, §7. Adapted from `SIH/167/web/BUILD_PLAN.md`. Keep what 167 learned, drop what was specific to imagery.

> **Direction note (29 Sep).** The 167 plan's first theme, "Editorial Instrument" (Bricolage Grotesque, Zara-scale type), was dropped by 167 itself on 19 Sep because it read as a fashion lookbook (`SIH/167/docs/06_Design_System.md` §1). This app uses the theme 167 ended with, **Field Atlas**: stone ground, a serif for headlines, one-pixel ink frames, and mono type for every value. The motion rules and component sourcing from the 167 plan carry over unchanged. Layout for the desk comes from **meteoblue MultiModel** (the meteogram for one cell) and the **WeatherBench 2 scorecard** (chosen 29 Sep).

---

## 1. The brief, stated plainly

**Be unique. Do not build a boring weather site.** No weather-app card grid, no dark navy with animated wind particles, no purple gradient. Judges from NCMRWF look at Windy, ECMWF charts and IMD maps every day. A copy of those loses. A tool that shows **why** each forecast is trusted wins.

**Light theme.** Maps of rain and temperature read truer on stone than on black, and every competing weather demo will be dark.

**Bold where it counts.** Big serif headlines. The numbers that matter are set at display scale in mono: RMSE, weight, probability, lead. Nobody else gives a weight of `0.62` the same typographic weight as a slogan.

**Animate a lot, but only what is real.** Every animation shows something the system actually does: weights shifting across Day 1–10, a map filling cell by cell as a field arrives, a scorecard cell counting to its value, a run's steps landing one by one. Motion that means nothing reads as a template.

**Don't hand-build solved components.** Take the patterns from the libraries in §4 and restyle them to our tokens.

**Honesty is a feature.** Until the engine produces output, every number is synthetic and says so on screen (§5.0). The "what we will not claim" list is part of the product, not a footnote.

---

## 2. Theme: "Field Atlas, forecast desk"

### 2.1 The signature move

**The model colours are the only colours.** The chrome is ink on stone. Every hue on screen belongs to a model (Okabe–Ito, PPT guide §7.1), and the blend is ink. After ten seconds a judge reads orange as GraphCast without a legend. The dominant-model map, where each cell takes the colour of the model it trusts, is the hero image of the product. It is the "weight map" deliverable (outcome 2) doubling as identity.

### 2.2 Tokens (in `src/index.css`)

| Token | Hex | Use |
|---|---|---|
| `--paper` / `--surface` / `--surface-2` | `#EFEEEC` / `#F8F7F5` / `#E4E2DE` | ground / cards / table under maps |
| `--ink` / `--ink-2` / `--ink-3` | `#0E2129` / `#45565D` / `#7A878C` | text; the blend line |
| `--hres` | `#0072B2` | IFS HRES, and ECMWF IFS open data (same system) |
| `--graphcast` | `#E69F00` | GraphCast |
| `--pangu` | `#009E73` | Pangu-Weather |
| `--fuxi` | `#CC79A7` | FuXi |
| `--gencast` | `#D55E00` | GenCast |
| `--aifs` / `--gfs` | `#56B4E9` / `#6B5B45` | live-only sources |
| `--good` / `--warn` / `--bad` | `#2F7D5A` / `#9C700C` / `#C4342A` | verdicts and run status only |

Rules: no action colour, since interaction is ink (filled or outlined). Model hues are never used for anything but models. Red means worse, failed or synthetic, nothing else. Rain uses IMD category bins (64.5 / 115.6 / 204.5 mm).

### 2.3 Type

| Role | Face | Setting |
|---|---|---|
| Display | **Source Serif 4** (variable, optical size) 700 | hero `clamp(44px, 7vw, 104px)`, −0.025em |
| Body / UI | **Geist** | 15 px / 1.5 |
| Data | **IBM Plex Mono**, `tabular-nums` | every value; at display scale for the signature numbers |

All fonts self-hosted through Fontsource. Nothing is fetched at runtime.

### 2.4 Layout

Editorial grid for the story pages (landing, method): big type, asymmetric columns, the map bleeding off the edge. **Desk grid** for the forecast screens: the map is the largest region, and the meteogram or "why" panel is always visible beside it, never hidden behind a tab. The lead slider sits under the map because lead is the axis of the whole product.

---

## 3. Motion plan: heavy, and every piece earns it

| Moment | Motion | Source |
|---|---|---|
| Landing hero | The dominant-model map **plays Day 1 → 10** on loop; cells change colour as trust moves from GraphCast (early) to GenCast (late) | Motion + canvas |
| Headline entrance | Line-mask reveal of the serif headline | React Bits / Motion Primitives text reveal pattern |
| Telemetry | System facts count up: models, variables, leads, cells, thresholds | Magic UI *Number Ticker* pattern |
| Vocabulary strip | Marquee of real terms: model names, `64.5 mm`, `LOYO 2018/20/22`, `λ = 0.95`, `k = 20` | Magic UI *Marquee* pattern |
| Landing scroll | Pinned pipeline narrative: line up → track record → weights → blend → extremes → scorecard. Each step swaps its own live visual | Motion `useScroll` / IntersectionObserver |
| Five friends disagree | Five model lines draw in one after another, then the blend line draws through them | Motion path length |
| Map field arrives | New lead or variable: cells **develop** in a diagonal sweep (like data arriving), not a crossfade | canvas |
| Weight change | Stacked weight bars tween between leads | Motion layout |
| Scorecard | Cells fill in lead order and their % counts to its value. Grey (no claim) cells never animate | Motion stagger |
| Run log | Steps land one by one with their timings; a failed step turns red and shows its note | `AnimatePresence` stagger |
| Hover | Map readout follows the cursor; meteogram crosshair reads every model at a lead | built |

**Non-negotiable:** `prefers-reduced-motion` makes everything instant and stops the hero loop. No animation blocks input. Play/pause on every autoplaying thing.

---

## 4. Component sourcing: search, take, restyle

| Library | Take |
|---|---|
| **[React Bits](https://reactbits.dev)** | text reveals, scroll reveals, animated lists |
| **[Magic UI](https://magicui.design)** | Number Ticker, Marquee, Animated Beam (pipeline arrows), Blur Fade |
| **[Motion Primitives](https://motion-primitives.com)** | in-view reveals, text effects, sliding number |
| **[Aceternity UI](https://ui.aceternity.com)** | sticky-scroll reveal (pipeline narrative) |
| **[21st.dev](https://21st.dev)** / **shadcn/ui** | command palette (jump to a place, a lead, a run), tabs, dialog, toast |
| **Motion** (`motion/react`) | all tweening |

Rules:
1. Restyle to the tokens. Square corners, ink frames, no library default left visible.
2. Skip fingerprinted shader backgrounds (Silk, Iridescence, LiquidChrome) and particle wind fields.
3. Record every borrowed pattern in `CREDITS.md`.
4. Everything bundled locally; nothing from a CDN at runtime.

---

## 5. Pages

### 5.0 Global
- **Disclosure bar**, permanent: SYNTHETIC DATA until `/api` answers, then ENGINE CONNECTED. Every map and chart built from synthetic data carries a stamp. (PPT guide §5.2: never present staged output as a result.)
- Masthead with run picker; run strip giving init time, season, regime (with basis: init-day label), rung, models and grid.

### 5.1 Landing: the thesis (`/`)
- **Hero:** headline "Right model, right place, right weather." with the dominant-model map playing Day 1–10 beside it. Telemetry row: `5 models · 4 variables · Day 1–10 · 64.5 mm · 0.5°`.
- **Five friends:** one cell, five model forecasts drawn in, the blend drawn through them (PPT guide §1.1), labelled illustrative.
- **Pipeline narrative**, pinned scroll, six steps, each with its real visual from the desk components.
- **Which models can blend what:** the B4.2 matrix as a grid. Rain uses four models; Pangu has no precipitation.
- **What makes this different:** the six points of PPT guide §4.11, no "first" or "novel".
- **What we will not claim:** the red list of PPT guide §5.2, stated as a feature.
- **Ink CTA band:** "Open the forecast desk".

### 5.2 Forecast desk (built)
**Forecast (`/forecast`) is a full-screen map explorer after Ventusky and meteoblue** (chosen 29 Sep): the map is the page; search and a layer list (blended rain / temperature / wind / pressure, most-trusted model, extremes) float top-left; the model picker and overlay toggles (wind flow, isobars with H/L, city values, smooth vs raw grid) top-right; legend and a weekday/date timeline along the bottom; clicking a point opens the meteogram drawer (bottom sheet on phones). Drag to pan, scroll or pinch to zoom, search flies to a city. Neighbouring coastlines from Natural Earth, India's boundary from the Survey of India only. Weights and Extremes use the same map engine (`src/components/WeatherMap.tsx`) beside their analysis panels. Skill and Run log as in `README.md`. Remaining: field-arrival sweep, animated scorecard, run-log stagger, command palette.

### 5.3 Data & Models (`/data`)
Sources table (B4) with family, years, leads, rain yes/no, and store path. Model-set matrix S1–S4 with validation and role. Live sources and their training counterparts (C10 table). Truth sources (ERA5, CHIRPS, IMD) and why rain is verified against CHIRPS (C13). The NCUM / NEPS-G adapter stated as "adapter ready, needs NCMRWF data". Big numbers: `4` rain models, `3` years LOYO, `10` leads.

### 5.4 Method & Results (`/method`)
The weight ladder B0 → B5, each rung with its formula and the rule that it ships only if it beats the rung below out of sample. Shrinkage and smoothing (C5). Leakage rule for regimes (C4). Validation protocol (LOYO, blocked months, block bootstrap, CI). Traps and guards (C13). Results slot: the one measured line from the model team, set at display scale. It shows `—` until measured.

### 5.5 Bulletin (`/bulletin`)
Print-styled daily page: date, regime, blended maps for Day 1/3/5, extremes by state, weights summary, run status, and "what this cannot establish". Browser print to PDF.

---

## 6. Engineering

- **Stack:** React 19 + TypeScript, Vite, Tailwind 4 tokens, Motion, TanStack Query, zustand, lucide. No map library: a canvas grid plus an SVG India outline, fully offline.
- **API:** contract in `src/lib/contract.ts`, served by `blend/server.py` (FastAPI). Synthetic fallback in `src/lib/synthetic.ts`, same shapes.
- **Budget:** under 1.5 MB before compression. Code-split landing and desk.
- **Quality floor:** zero console errors apart from the `/api` probe; WCAG AA text; visible focus rings; keyboard-reachable map (arrow keys move the cell); model never encoded by colour alone (legend text on every chart).
- **Headless checks** (Playwright, `data-testid`): each route loads, lead slider changes the map, a cell click updates the inspector, the run picker switches, rain weights never include Pangu, the disclosure bar reads SYNTHETIC with no backend.

---

## 7. Calendar

| When | Deliverable |
|---|---|
| 29 Sep | This plan; routing; landing; Data & Models — **done** |
| 30 Sep | **Deck upload** (Shreyash). No app screenshot on a slide unless it comes from engine output (PPT guide §7.5, §9) |
| Week 1 after upload | Method & Results; desk motion (sweep, scorecard, run log); `blend/server.py` stub on the contract |
| Week 2 | Wire real S1 output (T2m, wind) from the model team; bulletin |
| Week 3 | Daily job on IFS / AIFS / GFS feeding the run log |
| Week 4 | Accessibility pass, offline bundle, venue-laptop test, NCUM adapter page |
| Finale hours 16–24 | Desk polish against real data (E3) |

---

## 8. Definition of done: frontend

- [ ] Light theme, Field Atlas tokens, model hues only for models
- [ ] Landing with the Day 1–10 dominant-model hero and the pinned pipeline story
- [ ] Motion throughout, all tied to real state; reduced motion honoured; play/pause on loops
- [ ] Borrowed patterns restyled and listed in `CREDITS.md`
- [ ] Desk: map → cell → meteogram → weights → scorecard, all working from one click
- [ ] Data & Models and Method pages that match the docs, with no invented number
- [ ] Synthetic disclosure everywhere until the engine is connected; real numbers only from `/api`
- [ ] Zero console errors; bundle budget met; works offline
- [ ] A first-time judge answers "who does the blend trust in Kerala at Day 7, and why?" unaided
