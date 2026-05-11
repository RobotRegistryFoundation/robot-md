"""robot-md — parse, validate, and render ROBOT.md files."""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

try:
    __version__ = _pkg_version("robot-md")
except PackageNotFoundError:
    # Editable install before egg-info is registered, or running from source tree.
    __version__ = "0.0.0+source"
