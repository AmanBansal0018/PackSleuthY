"""Safe archive extraction, deterministic file comparison and heuristic review."""
from __future__ import annotations
import difflib, hashlib, json, os, re, stat, tarfile, uuid, zipfile
from pathlib import Path, PurePosixPath
from registry_connectors.service import STORAGE_DIR
from source_discovery.service import SOURCE_DIR

ROOT = STORAGE_DIR.parent
EXTRACT_DIR = ROOT / "extracted"
MAX_FILES = 10000
MAX_TOTAL = 200 * 1024 * 1024
MAX_FILE = 25 * 1024 * 1024
TEXT_LIMIT = 1024 * 1024

class InspectionError(Exception): pass

def _safe_rel(name):
    if not isinstance(name,str) or not name or "\x00" in name or "\\" in name:
        return None
    p=PurePosixPath(name)
    if p.is_absolute() or any(part in ("..","") for part in p.parts):
        return None
    if p.parts and re.match(r"^[A-Za-z]:",p.parts[0]):
        return None
    return p

def _write_member(root, rel, stream, size, count_state):
    if size < 0 or size > MAX_FILE: raise InspectionError("Archive contains a file larger than 25 MB.")
    count_state[0]+=1; count_state[1]+=size
    if count_state[0]>MAX_FILES: raise InspectionError("Archive contains more than 10,000 files.")
    if count_state[1]>MAX_TOTAL: raise InspectionError("Archive expands beyond 200 MB.")
    target=(root/Path(*rel.parts)).resolve()
    if not target.is_relative_to(root.resolve()): raise InspectionError("Archive path escaped extraction directory.")
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb") as out:
        remaining=size
        while remaining:
            chunk=stream.read(min(1024*1024,remaining))
            if not chunk: raise InspectionError("Archive member ended unexpectedly.")
            out.write(chunk); remaining-=len(chunk)

def _extract_zip(archive, dest, state, rejected):
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            rel = _safe_rel(info.filename)
            if rel is None:
                rejected.append({"path": info.filename[:500], "reason": "Unsafe or invalid archive path"})
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode) or (file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR)):
                rejected.append({"path": info.filename[:500], "reason": "Symbolic link or special file is not extracted"})
                continue
            with z.open(info) as stream:
                _write_member(dest, rel, stream, info.file_size, state)

def _extract_tar(archive, dest, state, rejected):
    with tarfile.open(archive, "r:*") as tf:
        for member in tf:
            if member.isdir():
                continue
            if not member.isfile():
                rejected.append({"path": member.name[:500], "reason": "Link or special file is not extracted"})
                continue
            rel = _safe_rel(member.name)
            if rel is None:
                rejected.append({"path": member.name[:500], "reason": "Unsafe or invalid archive path"})
                continue
            stream = tf.extractfile(member)
            if stream is None:
                rejected.append({"path": member.name[:500], "reason": "Archive member could not be read"})
                continue
            with stream:
                _write_member(dest, rel, stream, member.size, state)

def safe_extract(archive_path, label):
    archive=Path(archive_path)
    if not archive.is_file(): raise InspectionError("Archive was not found.")
    EXTRACT_DIR.mkdir(parents=True,exist_ok=True)
    ident=uuid.uuid4().hex; dest=EXTRACT_DIR/ident; dest.mkdir()
    state=[0,0]
    rejected=[]
    try:
        if zipfile.is_zipfile(archive): _extract_zip(archive,dest,state,rejected)
        elif tarfile.is_tarfile(archive): _extract_tar(archive,dest,state,rejected)
        else: raise InspectionError("Unsupported or invalid archive format.")
        files=[]
        top_items=list(dest.iterdir())
        common_root=top_items[0] if len(top_items)==1 and top_items[0].is_dir() else None
        for path in dest.rglob("*"):
            if path.is_file():
                rel=path.relative_to(common_root if common_root else dest).as_posix()
                h=hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
                files.append({"path":rel,"size":path.stat().st_size,"sha256":h.hexdigest()})
        return {"extraction_id":ident,"label":label,"file_count":len(files),"total_size_bytes":state[1],
                "rejected_file_count":len(rejected),"rejected_files":rejected,"files":files}
    except Exception:
        import shutil; shutil.rmtree(dest,ignore_errors=True); raise

def _directory(extraction_id):
    if not re.fullmatch(r"[a-f0-9]{32}",str(extraction_id or "")): raise InspectionError("Invalid extraction identifier.")
    p=(EXTRACT_DIR/extraction_id).resolve()
    if not p.is_relative_to(EXTRACT_DIR.resolve()) or not p.is_dir(): raise InspectionError("Extraction was not found.")
    return p

def _file_map(root):
    out={}
    top_items=list(root.iterdir())
    common_root=top_items[0] if len(top_items)==1 and top_items[0].is_dir() else None
    for p in root.rglob("*"):
        if p.is_file():
            rel=p.relative_to(common_root if common_root else root).as_posix()
            if rel not in out: out[rel]=p
    return out

def compare_extractions(package_extraction_id, source_extraction_id):
    a=_file_map(_directory(package_extraction_id)); b=_file_map(_directory(source_extraction_id))
    added=sorted(a.keys()-b.keys()); deleted=sorted(b.keys()-a.keys())
    added_details=[]
    for name in added:
        path=a[name]
        detail={"path":name,"size":path.stat().st_size,
                "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
        if detail["size"]<=TEXT_LIMIT:
            try:
                content=path.read_text(encoding="utf-8")
                if "\\x00" not in content:
                    detail["text"]=content[:200000]
            except (UnicodeError,OSError): pass
        added_details.append(detail)
    modified=[]; identical=[]
    for name in sorted(a.keys()&b.keys()):
        ha=hashlib.sha256(a[name].read_bytes()).hexdigest()
        hb=hashlib.sha256(b[name].read_bytes()).hexdigest()
        if ha==hb: identical.append(name); continue
        item={"path":name,"package_sha256":ha,"source_sha256":hb,
              "package_size":a[name].stat().st_size,"source_size":b[name].stat().st_size}
        try:
            if max(item["package_size"],item["source_size"])<=TEXT_LIMIT:
                old=b[name].read_text(encoding="utf-8"); new=a[name].read_text(encoding="utf-8")
                if "\x00" not in old+new:
                    item["diff"]="".join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile="source/"+name,tofile="package/"+name))[:30000]
        except (UnicodeError,OSError): pass
        modified.append(item)
    return {"package_extraction_id":package_extraction_id,"source_extraction_id":source_extraction_id,
            "summary":{"identical":len(identical),"added":len(added),"deleted":len(deleted),"modified":len(modified)},
            "identical_files":identical,"added_files":added,"added_file_details":added_details,
            "deleted_files":deleted,"modified_files":modified}

RULES=[
 ("high",r"\b(?:child_process.{0,40}(?:exec|execSync|spawn)|subprocess\.(?:Popen|run|call))\b","Process or shell execution API"),
 ("medium",r"\b(?:eval|new Function)\s*\(","Dynamic code evaluation"),
 ("medium",r"\b(?:fetch|axios\.(?:get|post)|https?\.request)\s*\(","Network request API"),
 ("medium",r"\b(?:preinstall|postinstall|install)\b","Install lifecycle behavior"),
 ("medium",r"\b(?:base64|atob|btoa)\b","Encoding primitive that may merit review"),
 ("medium",r"String\.fromCharCode\s*\(|\bcharCodeAt\s*\(","Character-code based string construction"),
 ("high",r"\b(?:powershell(?:\.exe)?|/bin/(?:sh|bash)|cmd\.exe)\b","Shell interpreter reference"),
]
def analyze_differences(comparison, source_status="confirmed"):
    findings=[]
    if source_status != "confirmed":
        findings.append({
            "title": "Source release match is not confirmed",
            "severity": "medium",
            "confidence": "low",
            "file": "Source discovery",
            "evidence": f"Source match status: {source_status}",
            "why_it_matters": "File differences are only meaningful when the selected source release corresponds to the published package version.",
            "recommendation": "Verify the repository and release tag manually before relying on this comparison."
        })
    for item in comparison["modified_files"]:
        path=item["path"]; diff=item.get("diff","")
        combined=path+"\n"+diff
        for severity,pattern,title in RULES:
            m=re.search(pattern,combined,re.I)
            if m:
                findings.append({"title":title,"severity":severity,"confidence":"medium",
                    "file":path,"evidence":combined[max(0,m.start()-100):m.end()+100][:500],
                    "why_it_matters":"This behavior can be legitimate, but its appearance or change in the published artifact deserves review.",
                    "recommendation":"Inspect the surrounding code and verify whether the behavior is expected for this release."})
    for detail in comparison.get("added_file_details", []):
        path=detail["path"]
        combined=path+"\n"+detail.get("text","")
        for severity,pattern,title in RULES:
            m=re.search(pattern,combined,re.I)
            if m:
                findings.append({"title":title,"severity":severity,"confidence":"medium",
                    "file":path,"evidence":combined[max(0,m.start()-100):m.end()+100][:500],
                    "why_it_matters":"This behavior can be legitimate, but its appearance in the published artifact deserves review.",
                    "recommendation":"Inspect the surrounding code and verify whether the behavior is expected for this release."})
        if re.search(r"\.(?:exe|dll|so|dylib|bin)$",path,re.I):
            findings.append({"title":"Unexpected executable or binary file added","severity":"high","confidence":"medium",
                "file":path,"evidence":"Added file: "+path,"why_it_matters":"An added executable may materially change package behavior.",
                "recommendation":"Verify its purpose and provenance against the release process."})
        if re.search(r"(?:^|/)(?:preinstall|postinstall|install)\.(?:js|cjs|mjs|py)$",path,re.I):
            findings.append({"title":"New install-related script","severity":"high","confidence":"medium",
                "file":path,"evidence":"Added file: "+path,"why_it_matters":"Install-time scripts can run automatically when users install a package.",
                "recommendation":"Review the complete script; PackSleuthY does not execute it."})
    return findings
