# PackSleuthY — Final audit and demo guide

## What is implemented

- Exact-version npm and PyPI package metadata retrieval and artifact download.
- Registry digest verification where the registry publishes a supported digest.
- GitHub repository discovery from the exact package version's metadata.
- Exact version tag matching; the default branch is never silently substituted.
- GitHub source archive download with host and redirect checks.
- ZIP and TAR safe extraction with path validation, symlink/special-file rejection, and file/count/expanded-size limits.
- File manifest hashing, identical/added/deleted/modified classification, and unified text diffs.
- Deterministic heuristic indicators for selected process execution, shell, network, dynamic evaluation, encoding and install-script patterns.
- SQLite scan history and JSON/HTML report export in the frontend.
- Explicit warning in the report when the source release match is not confirmed.

## Validation performed for this handoff

- Backend unit tests: **29 passed, 0 failed** (`python -m unittest discover -s tests -t . -v`).
- Python compilation: passed (`python -m compileall -q backend`).
- FastAPI runtime smoke test: `/api/health` returned HTTP 200.
- API integration test with harmless synthetic archives: download artifacts were represented by local fixtures; extraction, comparison, source-confidence warning and SQLite history endpoints passed. This is not a live npm/PyPI end-to-end test.
- Frontend JSX syntax parse: passed for `src/App.jsx` and `src/main.jsx`.
- Frontend production build: **not verified in this environment**. The uploaded `node_modules` lacked the Linux Rollup optional native package, and a clean npm install could not complete because registry access timed out. On Windows, run `npm ci` and then `npm run build` as part of final local verification.

## Important limitations — do not overclaim

- This is static inspection and heuristic triage, not a malware verdict or proof of safety.
- A registry digest match proves bytes match the registry's advertised digest; it does not prove the publisher or package is trustworthy.
- A matching Git tag is evidence of a likely source version, not proof the published artifact was built from that source.
- GitHub tags/releases beyond the first API page may not be discovered; GitHub rate limits and incomplete metadata can cause uncertain/unavailable outcomes.
- Heuristic patterns are intentionally small and can produce false positives and false negatives.
- The current tool does not reproduce build systems, inspect runtime behavior, or execute package code.
- Release monitoring/alerts, AI explanation, containerized rebuilds, semantic AST diffing, authentication and multi-user deployment are not implemented.
- Scan history lists past comparisons but does not yet provide a full historical report re-open endpoint.

## Windows setup

Open two terminals in the project folder.

### Terminal 1 — backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

### Terminal 2 — frontend

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`). Keep both terminals running. The frontend proxies `/api` requests to `http://127.0.0.1:8000`.

### Automated backend tests

```powershell
cd backend
python -m unittest discover -s tests -t . -v
```

## Suggested live demo

1. Start both servers and open the frontend.
2. Select npm and scan `express` version `4.18.2`.
3. Show the artifact filename, size, SHA-256 and registry integrity result.
4. Run source discovery and explain the exact-tag status honestly.
5. If an exact source archive is available, extract and compare it.
6. Show the file counts, added/deleted/modified files and a text diff.
7. Use a harmless synthetic test fixture to demonstrate a newly added install script being flagged. Clearly label it as synthetic; do not imply a real package is compromised.
8. Export the JSON and HTML reports.

If a source tag is missing or uncertain, show the incomplete status rather than choosing the default branch or fabricating a result.
