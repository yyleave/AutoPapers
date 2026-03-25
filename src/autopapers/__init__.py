__all__ = ["__version__"]

try:
    from importlib.metadata import version as _distribution_version

    __version__ = _distribution_version("autopapers")
except (ImportError, LookupError, OSError, TypeError, ValueError):
    __version__ = "0.0.1"

