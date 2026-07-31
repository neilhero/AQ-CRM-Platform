"""Read the CRM release version from the repository-level VERSION file."""

from pathlib import Path


def get_app_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        value = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-dev"
    return value or "0.0.0-dev"


APP_VERSION = get_app_version()
