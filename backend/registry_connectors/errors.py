"""Errors the package downloader can show to the user."""


class RegistryError(Exception):
    """Base error for a download that did not succeed."""

    status_code = 400


class InvalidPackageError(RegistryError):
    """The ecosystem, package name, or version is not acceptable."""

    status_code = 400


class PackageNotFoundError(RegistryError):
    """The registry does not have this package."""

    status_code = 404

    def __init__(self, package_name):
        super().__init__(f"Package not found: {package_name}")


class VersionNotFoundError(RegistryError):
    """The package exists, but this exact version does not."""

    status_code = 404

    def __init__(self, package_name, version):
        super().__init__(f"Version not found: {package_name} {version}")


class NetworkError(RegistryError):
    """The registry could not be reached or returned an unexpected response."""

    status_code = 502


class DownloadTooLargeError(RegistryError):
    """The published file is larger than the size limit."""

    status_code = 413

    def __init__(self):
        super().__init__("Download too large: packages over 50 MB are refused.")


class IntegrityError(RegistryError):
    """The downloaded bytes do not match the hash published by the registry."""

    status_code = 422


class NoDistributionError(RegistryError):
    """PyPI published this version without an sdist or a wheel."""

    status_code = 404

    def __init__(self):
        super().__init__(
            "No source distribution or wheel was published for this version."
        )
