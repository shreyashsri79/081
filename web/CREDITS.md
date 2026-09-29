# Credits

Patterns borrowed, rewritten on `motion/react` and restyled to our tokens. No library source copied verbatim.

| Pattern | From | Where |
|---|---|---|
| Number Ticker | Magic UI (magicui.design) | `src/components/motion.tsx` `NumberTicker` |
| Marquee | Magic UI | `motion.tsx` `Marquee` |
| Blur Fade / in-view reveal | Magic UI, Motion Primitives | `motion.tsx` `Reveal` |
| Line-mask text reveal | Motion Primitives / React Bits | `motion.tsx` `LineReveal` |
| Sticky scroll narrative | Aceternity UI "Sticky Scroll Reveal" | `src/screens/Landing.tsx` |
| MultiModel meteogram layout | meteoblue | `src/components/Meteogram.tsx` |
| Full-screen map explorer: floating layer list, model picker, day timeline, city values, point drawer | Ventusky, meteoblue maps | `src/screens/Forecast.tsx` |
| Wind particle flow | Ventusky, earth.nullschool.net (Cameron Beccario) | `src/components/WeatherMap.tsx` |
| Scorecard grid | WeatherBench 2 (Google Research) | `src/screens/Skill.tsx` |
| Design system "Field Atlas" | SIH/167 (our own) | `src/index.css` |

Data: India outline and state boundaries from datameet/maps (Survey of India boundary), simplified by `tools/make_geo.py`.
Basemap tiles © OpenStreetMap contributors (ODbL), from tile.openstreetmap.org, loaded live and never cached for offline use (OSM tile usage policy). Without network the map falls back to plain ground plus the baked outlines.
Neighbouring coastlines and borders from Natural Earth 1:50m (public domain); lines overlapping the Survey of India outline are removed.
Fonts: Source Serif 4, Geist, IBM Plex Mono (SIL OFL) via Fontsource.
Model colours: Okabe & Ito colour-blind-safe palette.
