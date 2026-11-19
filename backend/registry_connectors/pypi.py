"""Read one exact version from the official PyPI JSON API."""

from urllib.parse import quote

from registry_connectors.artifacts import SelectedArtifact, display_filename
from registry_connectors.errors import (
    NetworkError,
    NoDistributionError,
    PackageNotFoundError,
    VersionNotFoundError,
)
from registry_connectors.http_client import ensure_allowed_url, get_json

PYPI_METADATA_HOSTS = {"pypi.org"}
PYPI_DOWNLOAD_HOSTS = {"files.pythonhosted.org"}


def fetch_pypi_artifact(package_name, version, opener=None):
    """Return an sdist when PyPI published one, otherwise a wheel."""

    version_url = f"https://pypi.org/pypi/{quote(package_name)}/{quote(version)}/json"
    status, payload = get_json(version_url, PYPI_METADATA_HOSTS, opener)
    if status == 404:
        package_url = f"https://pypi.org/pypi/{quote(package_name)}/json"
        package_status, _package_payload = get_json(package_url, PYPI_METADATA_HOSTS, opener)
        if package_status == 404:
            raise PackageNotFoundError(package_name)
        raise VersionNotFoundError(package_name, version)

    if not isinstance(payload, dict):
        raise NetworkError("Network failure: the PyPI registry returned an unexpected response.")
    return parse_pypi_metadata(payload, package_name, version)


def parse_pypi_metadata(payload, package_name, version):
    files = payload.get("urls")
    if not isinstance(files, list):
        raise NetworkError("Network failure: the PyPI registry response did not include files.")

    sdists = [item for item in files if _packagetype(item) == "sdist"]
    wheels = [item for item in files if _packagetype(item) == "bdist_wheel"]
    candidates = sdists or wheels
    if not candidates:
        raise NoDistributionError()

    selected = next((item for item in candidates if _sha256(item)), candidates[0])
    artifact_type = "sdist" if selected in sdists else "wheel"
    download_url = selected.get("url")
    if not isinstance(download_url, str):
        raise NetworkError("Network failure: the PyPI registry response did not include a file URL.")
    ensure_allowed_url(download_url, PYPI_DOWNLOAD_HOSTS)

    size = selected.get("size")
    declared_size = size if isinstance(size, int) and size >= 0 else None

    return SelectedArtifact(
        ecosystem="pypi",
        package_name=package_name,
        version=version,
        download_url=download_url,
        artifact_type=artifact_type,
        display_filename=display_filename(selected.get("filename"), artifact_type),
        expected_sha256=_sha256(selected),
        declared_size=declared_size,
    )


def _packagetype(item):
    if not isinstance(item, dict):
        return ""
    value = item.get("packagetype")
    return value if isinstance(value, str) else ""


def _sha256(item):
    digests = item.get("digests")
    if not isinstance(digests, dict):
        return None
    digest = digests.get("sha256")
    if not isinstance(digest, str) or not digest.strip():
        return None
    return digest
