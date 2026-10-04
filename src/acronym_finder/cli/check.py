#!/usr/bin/env python3
"""
Check given acronyms against an availability provider.

Currently available providers are github and pypi.

Results are cached independently for each provider.
Cached results are reused until they are expired with --ttl-days.

A provider returns:
    available    -> the name is available
    unavailable  -> the name is already in use
    unknown      -> the provider could not determine the result

Only successful availability checks are written to the cache.

For GitHub, you can set the GITHUB_TOKEN env variable with a PAT (might require the read:user scope).
This will increase the hourly request budget from 60 to 5000.

Examples:
    acronyms check github NASA IEEE
    acronyms check pypi DEAD BEEF
"""

import argparse
import sys
from datetime import timedelta

from acronym_finder.availability import get_provider
from acronym_finder.cache import (
    cache_get,
    cache_set,
    load_cache,
    purge_cache,
    save_cache,
)


def register_parser(subparsers):
    parser = subparsers.add_parser(
        "check",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "provider",
        help="provider name; must match a file under src/availability",
    )

    parser.add_argument(
        "acronyms",
        nargs="+",
        metavar="ACRONYM",
        help="acronyms to check",
    )

    parser.add_argument(
        "--ttl-days",
        type=float,
        default=12 * 30,
        help="ignore cached checks older than this many days (default: 1 year)",
    )

    parser.set_defaults(func=main)


def main(args):
    if args.ttl_days is not None and args.ttl_days < 0:
        print("--ttl-days cannot be negative", file=sys.stderr)
        return 2

    try:
        provider = get_provider(args.provider)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    provider_name = args.provider.lower()

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

            result = provider.check(name)
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
