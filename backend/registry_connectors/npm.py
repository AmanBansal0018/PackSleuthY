"""Read one exact version from the official npm registry."""

from urllib.parse import quote

from registry_connectors.artifacts import SelectedArtifact, filename_from_url
from registry_connectors.errors import NetworkError, PackageNotFoundError, VersionNotFoundError
from registry_connectors.http_client import ensure_allowed_url, get_json

NPM_HOSTS = {"registry.npmjs.org"}


def fetch_npm_artifact(package_name, version, opener=None):
    """Return the published tarball chosen for this exact npm version."""

    url = f"https://registry.npmjs.org/{quote(package_name, safe='@')}/{quote(version, safe='')}"
    status, payload = get_json(url, NPM_HOSTS, opener)
    if status == 404:
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("error", ""))
        if "version not found" in message.lower():
            raise VersionNotFoundError(package_name, version)
        raise PackageNotFoundError(package_name)

    if not isinstance(payload, dict):
        raise NetworkError("Network failure: the npm registry returned an unexpected response.")
    return parse_npm_metadata(payload, package_name, version)


def parse_npm_metadata(payload, package_name, version):
    dist = payload.get("dist")
    if not isinstance(dist, dict):
        raise NetworkError("Network failure: the npm registry response did not include download details.")

    tarball = dist.get("tarball")
    if not isinstance(tarball, str):
        raise NetworkError("Network failure: the npm registry response did not include a tarball URL.")
    ensure_allowed_url(tarball, NPM_HOSTS)

    integrity = dist.get("integrity")
    shasum = dist.get("shasum")
    if integrity is not None and not isinstance(integrity, str):
        raise NetworkError("Network failure: the npm registry returned an unexpected integrity value.")
    if shasum is not None and not isinstance(shasum, str):
        raise NetworkError("Network failure: the npm registry returned an unexpected shasum.")

    return SelectedArtifact(
        ecosystem="npm",
        package_name=package_name,
        version=version,
        download_url=tarball,
        artifact_type="tarball",
        display_filename=filename_from_url(tarball, "tarball"),
        npm_integrity=integrity,
        npm_shasum=shasum,
    )
