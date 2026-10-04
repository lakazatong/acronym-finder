import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .config import USER_CACHE_DIR

CACHE_DIR = USER_CACHE_DIR / "acronym-finder"
CACHE_FIELDS = (
    "name",
    "available",
    "checked_at",
)

_PROVIDER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class CacheEntry:
    available: bool
    checked_at: str


type Cache = dict[str, CacheEntry]


def _cache_path(provider):
    if not isinstance(provider, str) or not _PROVIDER_RE.fullmatch(provider):
        raise ValueError(f"invalid provider name: {provider!r}")

    return CACHE_DIR / f"{provider}.csv"


def _parse_available(value: object) -> bool | None:
    if value == "true":
        return True

    if value == "false":
        return False

    return None


def _parse_checked_at(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    value = value.strip()

    return value or None


def _parse_timestamp(value: str):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _utc_now():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_cache(provider) -> Cache:
    path = _cache_path(provider)

    try:
        with path.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as f:
            reader = csv.DictReader(f)

            if reader.fieldnames != list(CACHE_FIELDS):
                raise ValueError(f"invalid cache header in '{path}'")

            cache: Cache = {}

            for row in reader:
                name = (row.get("name") or "").strip().lower()

                if not name:
                    continue

                available = _parse_available(row.get("available"))
                checked_at = _parse_checked_at(row.get("checked_at"))

                if available is not None and checked_at is not None:
                    cache[name] = CacheEntry(
                        available=available,
                        checked_at=checked_at,
                    )

            return cache

    except FileNotFoundError:
        return {}


def save_cache(provider: str, cache: Cache):
    path = _cache_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".csv.tmp")

    with temporary.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.writer(f)
        writer.writerow(CACHE_FIELDS)

        for name, entry in sorted(cache.items()):
            available = entry.available
            checked_at = entry.checked_at

            if not isinstance(available, bool):
                raise TypeError(f"invalid cached availability for '{name}'")

            if not checked_at:
                raise ValueError(f"missing checked_at for '{name}'")

            writer.writerow(
                [
                    name,
                    str(available).lower(),
                    checked_at,
                ]
            )

    temporary.replace(path)


def cache_get(cache: Cache, name: str):
    name = name.lower()
    entry = cache.get(name)

    if entry is None:
        return None

    available = entry.available

    return available if isinstance(available, bool) else None


def cache_set(cache: Cache, name, available):
    if not isinstance(available, bool):
        raise TypeError("cached availability must be a boolean")

    cache[name.lower()] = CacheEntry(
        available=available,
        checked_at=_utc_now(),
    )


def purge_cache(cache: Cache, ttl=None):
    if ttl is not None and ttl < timedelta(0):
        raise ValueError("cache TTL cannot be negative")

    now = datetime.now(UTC)
    cutoff = now - ttl if ttl is not None else None

    invalid = []

    for name, entry in cache.items():
        available = entry.available
        checked_at = entry.checked_at

        if not isinstance(available, bool):
            invalid.append(name)
            continue

        if not checked_at:
            invalid.append(name)
            continue

        if cutoff is not None:
            timestamp = _parse_timestamp(checked_at)

            if timestamp is None or timestamp < cutoff:
                invalid.append(name)

    for name in invalid:
        del cache[name]

    return len(invalid)
