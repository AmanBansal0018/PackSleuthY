"""PackSleuthY API: download, discover source, safely inspect and compare."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from registry_connectors.errors import RegistryError
from registry_connectors.service import download_package, STORAGE_DIR
from source_discovery.service import discover_source, SourceDiscoveryError, SOURCE_DIR
from analysis_engine.service import safe_extract, compare_extractions, analyze_differences, InspectionError, EXTRACT_DIR
import json, os, re, sqlite3, time

app = FastAPI(title="PackSleuthY", version="0.2.0")

# Allow local Vite dev server and any origin in production (single-service deploy)
_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if os.getenv("ALLOW_ALL_ORIGINS", "1") == "1":
    _origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

DB_PATH = STORAGE_DIR.parent / "packsleuthy.sqlite3"
def _db():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL,
            ecosystem TEXT, package_name TEXT, version TEXT, artifact_id TEXT,
            source_status TEXT, comparison_json TEXT, findings_json TEXT)""")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(scans)")}
        if "source_status" not in columns:
            conn.execute("ALTER TABLE scans ADD COLUMN source_status TEXT")
        conn.commit()

class DownloadRequest(BaseModel):
    ecosystem: str
    package_name: str
    version: str

class SourceRequest(BaseModel):
    ecosystem: str
    package_name: str
    version: str
    saved_artifact_id: str

class ExtractRequest(BaseModel):
    saved_artifact_id: str
    source_archive_id: str

class CompareRequest(BaseModel):
    package_extraction_id: str
    source_extraction_id: str
    ecosystem: str = "unknown"
    package_name: str = "unknown"
    version: str = "unknown"
    saved_artifact_id: str = ""
    source_status: str = "unknown"

@app.get("/api/health")
def health():
    return {"status":"ok","service":"PackSleuthY","message":"Backend is running","version":"0.2.0"}

@app.post("/api/packages/download")
def download_package_endpoint(body: DownloadRequest):
    try: return download_package(body.ecosystem,body.package_name,body.version)
    except RegistryError as exc: raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc

@app.post("/api/source/discover")
def source_discover_endpoint(body: SourceRequest):
    try: return discover_source(body.ecosystem,body.package_name,body.version,body.saved_artifact_id)
    except (RegistryError,SourceDiscoveryError) as exc: raise HTTPException(status_code=getattr(exc,"status_code",502),detail=str(exc)) from exc

@app.post("/api/artifacts/extract")
def extract_endpoint(body: ExtractRequest):
    try:
        if not re.fullmatch(r"[a-f0-9]{32}",body.saved_artifact_id or "") or not re.fullmatch(r"[a-f0-9]{32}",body.source_archive_id or ""):
            raise InspectionError("Invalid artifact identifier.")
        package_files=list(STORAGE_DIR.glob(body.saved_artifact_id+".*"))
        source_file=SOURCE_DIR/(body.source_archive_id+".zip")
        if not package_files or not source_file.is_file(): raise InspectionError("Package or source archive was not found.")
        package_result=safe_extract(package_files[0],"published_package")
        source_result=safe_extract(source_file,"source_repository")
        return {"package":package_result,"source":source_result}
    except InspectionError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=400,detail=f"Could not safely extract archive: {type(exc).__name__}") from exc

@app.post("/api/comparison/run")
def comparison_endpoint(body: CompareRequest):
    try:
        comparison=compare_extractions(body.package_extraction_id,body.source_extraction_id)
        findings=analyze_differences(comparison, body.source_status)
        _db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO scans(created_at,ecosystem,package_name,version,artifact_id,source_status,comparison_json,findings_json) VALUES(?,?,?,?,?,?,?,?)",
                (int(time.time()),body.ecosystem,body.package_name,body.version,body.saved_artifact_id,body.source_status,json.dumps(comparison),json.dumps(findings)))
            conn.commit()
        return {"comparison":comparison,"findings":findings,
            "assessment": (
                "Investigation incomplete: source release not confirmed"
                if body.source_status != "confirmed"
                else ("Suspicious differences found" if findings else (
                    "No significant anomalies detected by current rules"
                    if comparison["summary"]["added"] + comparison["summary"]["deleted"] + comparison["summary"]["modified"] == 0
                    else "Differences found; manual review recommended"
                ))
            ),
            "limitations":["Heuristic findings are indicators, not proof of malicious behavior.","A clean result does not prove a package is safe.","Build-generated files and platform-specific artifacts may legitimately differ.","Source tag matching confidence affects comparison reliability."]}
    except InspectionError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc

@app.get("/api/scans/history")
def scan_history():
    _db()
    with sqlite3.connect(DB_PATH) as conn:
        rows=conn.execute("SELECT id,created_at,ecosystem,package_name,version,artifact_id,source_status FROM scans ORDER BY id DESC LIMIT 100").fetchall()
    return {"scans":[{"id":r[0],"created_at":r[1],"ecosystem":r[2],"package_name":r[3],"version":r[4],"artifact_id":r[5],"source_status":r[6]} for r in rows]}


# ---------------------------------------------------------------------------
# Serve the built React frontend from a single process (production / Render)
# Frontend build output is expected at ../frontend/dist relative to this file.
# ---------------------------------------------------------------------------
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Never intercept API routes (they are already registered above)
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")
