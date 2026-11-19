"""Find and download a package's likely matching GitHub source release.

All network content is treated as data. No project code is executed.
"""
from __future__ import annotations
import json
import re
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from registry_connectors.errors import RegistryError
from registry_connectors.service import STORAGE_DIR

ROOT = STORAGE_DIR.parent
SOURCE_DIR = ROOT / "sources"
META_DIR = ROOT / "metadata"
MAX_SOURCE_BYTES = 100 * 1024 * 1024
TIMEOUT = 15
GITHUB_HOSTS = {"github.com", "www.github.com"}

class SourceDiscoveryError(RegistryError):
    status_code = 502

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"PackSleuthY/1.0", "Accept":"application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read(5 * 1024 * 1024 + 1)
            if len(raw) > 5 * 1024 * 1024:
                raise SourceDiscoveryError("Source metadata response exceeded the size limit.")
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise SourceDiscoveryError(f"Source provider returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, ValueError, UnicodeError) as exc:
        raise SourceDiscoveryError("Could not retrieve source repository metadata.") from exc

def _download_github_archive(url, destination):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"codeload.github.com"}:
        raise SourceDiscoveryError("Refusing an unexpected source archive host.")
    req = urllib.request.Request(url, headers={"User-Agent":"PackSleuthY/1.0"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response, destination.open("wb") as out:
            final_url = urllib.parse.urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.hostname != "codeload.github.com":
                raise SourceDiscoveryError("Source archive redirected to an unexpected host.")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise SourceDiscoveryError("Source archive exceeds the 100 MB download limit.")
                out.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return total

def _repo_slug(url):
    if not isinstance(url, str):
        return None
    raw = url.strip()
    if raw.startswith("git+"):
        raw = raw[4:]
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("https", "http") or parsed.hostname not in GITHUB_HOSTS:
        return None
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], re.sub(r"\.git$", "", parts[1])
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo):
        return None
    return f"{owner}/{repo}"

def _metadata_for(ecosystem, name, version):
    from urllib.parse import quote
    if ecosystem == "npm":
        url = f"https://registry.npmjs.org/{quote(name, safe='@')}/{quote(version, safe='')}"
        data = _get_json(url)
        if not isinstance(data, dict):
            return None, []
        repo = data.get("repository")
        urls = [repo.get("url")] if isinstance(repo, dict) else ([repo] if isinstance(repo, str) else [])
        return data, urls
    url = f"https://pypi.org/pypi/{quote(name)}/{quote(version)}/json"
    data = _get_json(url)
    if not isinstance(data, dict):
        return None, []
    info = data.get("info") or {}
    urls = []
    if isinstance(info, dict):
        urls.extend([info.get("home_page")])
        project_urls = info.get("project_urls") or {}
        if isinstance(project_urls, dict):
            urls.extend(project_urls.values())
    return data, urls

def discover_source(ecosystem, package_name, version, saved_artifact_id):
    from registry_connectors.validation import validate_request
    ecosystem, package_name, version = validate_request(ecosystem, package_name, version)
    if not re.fullmatch(r"[a-f0-9]{32}", str(saved_artifact_id or "")):
        raise SourceDiscoveryError("Invalid saved package artifact identifier.")
    artifact_dir = STORAGE_DIR.resolve()
    artifact_files = list(artifact_dir.glob(saved_artifact_id + ".*"))
    if not artifact_files or not any(p.is_file() for p in artifact_files):
        raise SourceDiscoveryError("The downloaded package artifact was not found. Download it again first.")
    data, urls = _metadata_for(ecosystem, package_name, version)
    candidates = []
    for url in urls:
        slug = _repo_slug(url)
        if slug and slug not in candidates:
            candidates.append(slug)
    if not candidates:
        result = {
            "ecosystem":ecosystem,"package_name":package_name,"version":version,
            "repository_url":None,"matching_tag":None,"commit_sha":None,
            "source_archive_id":None,"match_status":"unavailable","confidence":"none",
            "explanation":"The exact registry version did not provide a valid GitHub repository URL."
        }
        _save_metadata(saved_artifact_id, result)
        return result
    # Prefer the first valid repository URL declared by the exact published version.
    slug = candidates[0]
    tags = _get_json(f"https://api.github.com/repos/{slug}/tags?per_page=100")
    releases = _get_json(f"https://api.github.com/repos/{slug}/releases?per_page=100")
    tag_items = tags if isinstance(tags, list) else []
    release_items = releases if isinstance(releases, list) else []
    tag_map = {t.get("name"):t for t in tag_items if isinstance(t,dict) and isinstance(t.get("name"),str)}
    expected = [version, "v"+version, "version-"+version, "release-"+version]
    selected = next((tag_map[t] for t in expected if t in tag_map), None)
    if selected is None:
        selected = next((r for r in release_items if isinstance(r,dict) and r.get("tag_name") in expected), None)
    if selected is None:
        result = {
            "ecosystem":ecosystem,"package_name":package_name,"version":version,
            "repository_url":f"https://github.com/{slug}","matching_tag":None,
            "commit_sha":None,"source_archive_id":None,"match_status":"uncertain",
            "confidence":"low","explanation":"A GitHub repository was declared, but no exact version tag or release tag was found. The default branch was not substituted."
        }
        _save_metadata(saved_artifact_id, result)
        return result
    tag = selected.get("name") or selected.get("tag_name")
    commit = (selected.get("commit") or {}).get("sha") if isinstance(selected.get("commit"),dict) else None
    if not commit:
        ref = _get_json(f"https://api.github.com/repos/{slug}/git/ref/tags/{urllib.parse.quote(tag, safe='')}")
        obj = ref.get("object",{}) if isinstance(ref,dict) else {}
        commit = obj.get("sha") if isinstance(obj,dict) else None
        if isinstance(obj,dict) and obj.get("type") == "tag" and commit:
            tag_obj = _get_json(f"https://api.github.com/repos/{slug}/git/tags/{commit}")
            commit = (tag_obj.get("object") or {}).get("sha") if isinstance(tag_obj,dict) else commit
    if not isinstance(commit,str) or not re.fullmatch(r"[a-f0-9]{40}",commit):
        commit = None
    source_id = uuid.uuid4().hex
    archive = SOURCE_DIR / f"{source_id}.zip"
    ref = commit or tag
    size = _download_github_archive(f"https://codeload.github.com/{slug}/zip/{urllib.parse.quote(ref, safe='')}", archive)
    result = {
        "ecosystem":ecosystem,"package_name":package_name,"version":version,
        "repository_url":f"https://github.com/{slug}","matching_tag":tag,
        "commit_sha":commit,"source_archive_id":source_id,"source_archive_size_bytes":size,
        "match_status":"confirmed" if commit else "uncertain",
        "confidence":"high" if commit else "medium",
        "explanation":f"Selected the exact published-version repository metadata and matched GitHub tag '{tag}'."
    }
    _save_metadata(saved_artifact_id,result)
    return result

def _save_metadata(artifact_id, result):
    META_DIR.mkdir(parents=True,exist_ok=True)
    (META_DIR/f"{artifact_id}.source.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
