# PackSleuthY

Static package supply-chain inspection for exact **npm** and **PyPI** releases.

Downloads the registry artifact, verifies the published digest, tries to locate a matching GitHub release tag, safely extracts both archives, compares files, and surfaces heuristic security indicators.

> Prototype only — not a malware scanner. A clean result does **not** prove a package is safe.

---

## One-command local run

Requirements: **Node.js 18+**, **Python 3.10+**, `npm`.

```bash
# 1. Install everything (frontend + backend + concurrent runner)
npm install

# 2. Start both servers together
npm run dev
```

- Frontend (Vite): http://localhost:5173  
- Backend (FastAPI): http://127.0.0.1:8000  
- API docs: http://127.0.0.1:8000/docs  

Vite proxies `/api/*` to the backend, so the UI works out of the box.

### Alternative: run servers separately

```bash
# Terminal 1 – backend
npm run backend

# Terminal 2 – frontend
npm run frontend
```

### Production-style local run (single process)

```bash
npm run build          # builds frontend into frontend/dist
npm start              # FastAPI serves both API + the built UI on port 8000
```

Open http://localhost:8000

---

## Deploy once on Render.com

You only need **one** Web Service.

### Option A – Blueprint (recommended)

1. Push the `PackSleuthY` project folder to a GitHub repo (or set it as the Render Root Directory).
2. On Render → **New** → **Blueprint**.
3. Connect the repo. Render reads `render.yaml`; the build installs dependencies and builds the React frontend, then the start command runs FastAPI, which serves both the API and the built UI.

### Option B – Manual Web Service

| Setting        | Value |
|----------------|-------|
| Runtime        | Python 3 |
| Build Command  | `npm install && npm run build` |
| Start Command  | `npm start` |
| Health Check   | `/api/health` |

Add env var (optional):

```
ALLOW_ALL_ORIGINS=1
```

That’s it — one URL serves both the UI and the API.

---

## Project layout

```
PackSleuthY/
├── package.json          # root scripts: npm run dev / build / start
├── render.yaml           # single-service Render Blueprint
├── frontend/             # React + Vite
│   ├── src/
│   └── package.json
├── backend/
│   ├── main.py           # FastAPI + static file serving
│   ├── requirements.txt
│   ├── registry_connectors/
│   ├── source_discovery/
│   ├── analysis_engine/
│   ├── storage/          # runtime data (gitignored)
│   └── tests/
└── docs/
```

---

## API workflow

1. `POST /api/packages/download` – download exact package version  
2. `POST /api/source/discover` – find matching GitHub source  
3. `POST /api/artifacts/extract` – safe extract both archives  
4. `POST /api/comparison/run` – compare + heuristic findings  
5. `GET  /api/scans/history` – past scans  

Interactive docs: `/docs`

### Demo packages

- npm: `express` @ `4.18.2`
- PyPI: `requests` @ `2.31.0`

---

## Security model (summary)

- Downloaded code is never installed, imported, or executed.
- Archives are extracted as data only (path traversal / symlinks rejected).
- Limits: 10k files, 200 MB expanded, 25 MB per file, 50–100 MB download.
- Findings are indicators for human review, not automatic verdicts.

---

## Tests

```bash
npm test
# or
cd backend && python -m unittest discover -s tests -t .
```

Tests are offline and use synthetic fixtures.
