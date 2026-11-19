"""The file chosen from registry metadata, before it is downloaded."""

from dataclasses import dataclass
from urllib.parse import urlparse
import re

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,180}$")
_FALLBACK_NAMES = {
    "tarball": "package.tgz",
    "sdist": "package.tar.gz",
    "wheel": "package.whl",
}


@dataclass(frozen=True)
class SelectedArtifact:
    ecosystem: str
    package_name: str
    version: str
    download_url: str
    artifact_type: str
    display_filename: str
    npm_integrity: str | None = None
    npm_shasum: str | None = None
    expected_sha256: str | None = None
    declared_size: int | None = None


def display_filename(raw_name, artifact_type):
    """Keep a registry filename for display only when it cannot be a path."""

    fallback = _FALLBACK_NAMES[artifact_type]
    if not isinstance(raw_name, str):
        return fallback
    if "/" in raw_name or "\\" in raw_name or ".." in raw_name:
        return fallback

    name = raw_name.strip()
    if not _SAFE_FILENAME.fullmatch(name):
        return fallback
    return name


def filename_from_url(url, artifact_type):
    path = urlparse(url).path
    raw_name = path.rsplit("/", 1)[-1]
    return display_filename(raw_name, artifact_type)
