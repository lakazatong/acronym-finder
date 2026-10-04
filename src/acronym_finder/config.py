import os
from pathlib import Path


def _get_user_cache_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base)

        return Path.home() / "AppData" / "Local"

    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base)

    return Path.home() / ".cache"


WORKING_DIR = Path.cwd()
USER_CACHE_DIR = _get_user_cache_dir()
