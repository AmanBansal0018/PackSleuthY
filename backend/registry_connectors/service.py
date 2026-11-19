"""Download one published package file and check its registry hash.

The saved file is never extracted, installed, or executed.
"""

import uuid
from pathlib import Path

from registry_connectors.errors import RegistryError
from registry_connectors.http_client import stream_to_file
from registry_connectors.integrity import safety_note, verify_npm, verify_pypi
from registry_connectors.npm import NPM_HOSTS, fetch_npm_artifact
from registry_connectors.pypi import PYPI_DOWNLOAD_HOSTS, fetch_pypi_artifact
from registry_connectors.validation import validate_request

STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage" / "packages"
_EXTENSIONS = {
    "tarball": ".tgz",
    "sdist": ".tar.gz",
    "wheel": ".whl",
}


def download_package(ecosystem, package_name, version, opener=None, storage_dir=None):
    """Validate the request, download the selected file, and return result JSON."""

    clean_ecosystem, clean_name, clean_version = validate_request(ecosystem, package_name, version)
    if clean_ecosystem == "npm":
        artifact = fetch_npm_artifact(clean_name, clean_version, opener)
        allowed_hosts = NPM_HOSTS
    else:
        artifact = fetch_pypi_artifact(clean_name, clean_version, opener)
        allowed_hosts = PYPI_DOWNLOAD_HOSTS

    destination_dir = Path(storage_dir) if storage_dir is not None else STORAGE_DIR
    return _save_artifact(artifact, allowed_hosts, destination_dir, opener)


def _save_artifact(artifact, allowed_hosts, storage_dir, opener):
    storage_root = storage_dir.resolve()
    storage_root.mkdir(parents=True, exist_ok=True)

    artifact_id = uuid.uuid4().hex
    extension = _EXTENSIONS[artifact.artifact_type]
    partial_path = _path_inside(storage_root, f"{artifact_id}.partial")
    final_path = _path_inside(storage_root, f"{artifact_id}{extension}")

    try:
        hashes = stream_to_file(
            artifact.download_url,
            allowed_hosts,
            partial_path,
            opener,
            artifact.declared_size,
        )
        status = _verify(artifact, hashes)
        partial_path.replace(final_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    return {
        "ecosystem": artifact.ecosystem,
        "package_name": artifact.package_name,
        "version": artifact.version,
        "artifact_filename": artifact.display_filename,
        "artifact_type": artifact.artifact_type,
        "file_size_bytes": hashes["size"],
        "sha256": hashes["sha256"].hexdigest(),
        "integrity_verification_status": status,
        "registry_download_url": artifact.download_url,
        "saved_artifact_id": artifact_id,
        "safety_note": safety_note(status),
    }


def _verify(artifact, hashes):
    if artifact.ecosystem == "npm":
        return verify_npm(hashes, artifact.npm_integrity, artifact.npm_shasum)
    return verify_pypi(hashes, artifact.expected_sha256)


def _path_inside(storage_root, filename):
    path = (storage_root / filename).resolve()
    if not path.is_relative_to(storage_root):
        raise RegistryError("Refusing to save a file outside package storage.")
    return path
