"""Checks package names and versions before any network request."""

import re

from registry_connectors.errors import InvalidPackageError

NPM_NAME = re.compile(r"^(?:@[a-z0-9-]{1,64}/)?[a-z0-9][a-z0-9._-]{0,213}$")
PYPI_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")

MAX_NAME_LENGTH = 214


def validate_request(ecosystem, package_name, version):
    """Return cleaned values, or raise InvalidPackageError."""

    if not isinstance(ecosystem, str) or not isinstance(package_name, str) or not isinstance(version, str):
        raise InvalidPackageError("Invalid package name or version.")

    clean_ecosystem = ecosystem.strip().lower()
    clean_name = package_name.strip()
    clean_version = version.strip()

    if clean_ecosystem not in {"npm", "pypi"}:
        raise InvalidPackageError("Invalid package name or version: choose npm or pypi.")

    if clean_ecosystem == "npm":
        name_is_valid = NPM_NAME.fullmatch(clean_name) and len(clean_name) <= MAX_NAME_LENGTH
    else:
        name_is_valid = PYPI_NAME.fullmatch(clean_name) and len(clean_name) <= MAX_NAME_LENGTH

    version_is_valid = VERSION.fullmatch(clean_version) is not None
    if ".." in clean_name or ".." in clean_version:
        name_is_valid = False
        version_is_valid = False

    if not name_is_valid or not version_is_valid:
        raise InvalidPackageError(
            "Invalid package name or version: use a plain package name and version, without spaces or file paths."
        )

    return clean_ecosystem, clean_name, clean_version
