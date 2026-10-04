#!/usr/bin/env python3
"""
Check given acronyms against an availability provider.

The provider name corresponds to a module under src/availability/.
For example:
    python check.py github ABC XYZ
    python check.py pypi ABC XYZ

Results are cached independently for each provider under .cache/.
Cached results are reused until they are expired with --ttl-days.

A provider returns:
    available    -> the name is available
    unavailable  -> the name is already in use
    unknown      -> the provider could not determine the result

Only successful availability checks are written to the cache.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import timedelta
from types import ModuleType

from acronym_finder.availability import get_provider
from acronym_finder.cache import (
    cache_get,
    cache_set,
    load_cache,
    purge_cache,
    save_cache,
)


@dataclass(frozen=True)
class Arguments:
    provider: ModuleType
    acronyms: list[str]
    ttl_days: float | None


def load_candidates(path):
    try:
        with path.open("r", encoding="utf-8") as f:
            session = json.load(f)

    except FileNotFoundError:
        raise ValueError(f"file not found: {path}")

    if not isinstance(session, dict):
        raise TypeError(f"invalid session file: {path}")

    results = session.get("results")

    if not isinstance(results, list):
        raise TypeError(f"'{path}' does not contain a valid results list")

    if not all(isinstance(result, str) for result in results):
        raise ValueError(f"results in '{path}' must all be strings")

    return results


def parse_args() -> Arguments:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    ap.add_argument(
        "provider",
        help="provider name; must match a file under src/availability",
    )

    ap.add_argument(
        "acronyms",
        nargs="+",
        metavar="ACRONYM",
        help="acronyms to check",
    )

    ap.add_argument(
        "--ttl-days",
        type=float,
        default=None,
        help="ignore cached checks older than this many days",
    )

    a = ap.parse_args()

    if a.ttl_days is not None and a.ttl_days < 0:
        ap.error("--ttl-days cannot be negative")

    try:
        provider = get_provider(a.provider)
    except ValueError as e:
        ap.error(str(e))

    return Arguments(
        provider=provider,
        acronyms=a.acronyms,
        ttl_days=a.ttl_days,
    )


def main():
    args = parse_args()
    provider_name = args.provider.__name__

    candidates = list(dict.fromkeys(name.lower() for name in args.acronyms))

    cache = load_cache(provider_name)

    ttl = timedelta(days=args.ttl_days) if args.ttl_days is not None else None

    purged_count = purge_cache(cache, ttl)

    if purged_count:
        print(
            f"Purged {purged_count} invalid or expired "
            f"{provider_name} cache entr"
            f"{'ies' if purged_count != 1 else 'y'}."
        )

        save_cache(provider_name, cache)

    cached_count = 0
    checked_count = 0
    free_count = 0
    unavailable_count = 0
    unknown_count = 0

    try:
        for name in candidates:
            result = cache_get(cache, name)

            if result is not None:
                cached_count += 1

                print(f"{name}: {'available' if result else 'unavailable'} (cached)")

                if result:
                    free_count += 1
                else:
                    unavailable_count += 1

                continue

            result = args.provider.check(name)
            checked_count += 1

            if result is None:
                unknown_count += 1
                print(f"{name}: unknown")
                continue

            cache_set(cache, name, result)
            save_cache(provider_name, cache)

            if result:
                free_count += 1
                print(f"{name}: available")
            else:
                unavailable_count += 1
                print(f"{name}: unavailable")

    except KeyboardInterrupt:
        save_cache(provider_name, cache)

        print(
            "\nInterrupted; cache saved.",
            file=sys.stderr,
        )

        return 130

    save_cache(provider_name, cache)

    print()
    print(
        f"{len(candidates)} acronym"
        f"{'s' if len(candidates) != 1 else ''}: "
        f"{checked_count} checked, {cached_count} cached"
    )
    print(
        f"{free_count} available, "
        f"{unavailable_count} unavailable, "
        f"{unknown_count} unknown"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
