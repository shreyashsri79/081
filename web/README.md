# Samanvay web (PS26081 dashboard)

Frontend MVP for the blending system. Screens follow C11 of `../WORKFLOW_AND_DECK_81.md`;
layout borrows meteoblue MultiModel (meteogram per cell) and the WeatherBench 2 scorecard.

```
npm install
npm run dev        # http://localhost:5181
npm run build
```

## Data

`src/lib/api.ts` probes `/api/runs` (proxied to `127.0.0.1:8081`). If `blend/server.py` is not
running, every call is served by `src/lib/synthetic.ts` and the bottom bar reads **SYNTHETIC DATA**.
Synthetic numbers are invented; never screenshot them for the deck.

The API contract is `src/lib/contract.ts`. The server must return exactly those shapes.

| Screen | Route | Endpoints |
|---|---|---|
| Forecast + meteogram | `/` | `field`, `meteogram` |
| Weights + "why" card | `/weights` | `weights`, `cell`, `meteogram` |
| Skill scorecard | `/skill` | `scorecard` |
| Extremes | `/extremes` | `extremes` |
| Run log | `/runs` | `runs`, `runs/:id` |

## Map

`src/geo/india.json` is baked by `tools/make_geo.py` from datameet/maps (Survey of India
boundary, 35 states). No tiles, no network at demo time.

Product name is a placeholder: change `BRAND` in `src/components/Chrome.tsx` and the `<title>`.
