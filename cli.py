#!/usr/bin/env python3
"""
Acronym finder: picks letters from each word (in order), keeps the ones that
look pronounceable, and ranks them by:
  1. fewer syllables
  2. closer to 1 letter per word
  3. letters closer to the start of their word

Words are positional arguments. Each word can optionally carry a maximum
number of letters it may contribute, as word:N.

Every word contributes at least one letter. If N is omitted, its maximum
is determined by --min-len and --max-len. If neither is provided, both
default to the number of words, so every word contributes exactly one letter.

For k words:
  --min-len L implies N <= L - k + 1
  --max-len V implies N >= V - k + 1

When both are provided, every N must satisfy:
  V - k + 1 <= N <= L - k + 1

Pinning letters: a one-letter "word" can only contribute that exact letter,
so it acts as a fixed letter at that position. Use it to force part of the
acronym without any extra option.

Examples:
  python acronym_finder.py my awesome words
  python acronym_finder.py my:2 awesome:3 words
  python acronym_finder.py m awesome words
  python acronym_finder.py m awesome w
"""

import argparse
import sys
from datetime import timedelta

from availability import check_free
from cache import load_cache, purge_cache, save_cache
from generator import generator_init, generator_next, generator_words


def format_selected_words(words, selections):
    result = []

    for word, selected in zip(words, selections):
        formatted = "".join(
            char.upper() if selected[i] else char.lower() for i, char in enumerate(word)
        )

        result.append(formatted)

    return " ".join(result)


def add_best(best, row):
    """Keep the best row seen for each acronym."""
    _syl, _extra, _cost, acr, _selections = row
    old = best.get(acr)

    if old is None or row[:3] < old[:3]:
        best[acr] = row


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    ap.add_argument(
        "words",
        nargs="+",
        metavar="WORD[:N]",
        help="a word, optionally with the max letters it may contribute",
    )

    ap.add_argument(
        "--top",
        type=int,
        default=10,
        help="top results to show (default 10)",
    )

    ap.add_argument(
        "--min-len",
        type=int,
        default=None,
        help="min acronym length (default: number of words)",
    )

    ap.add_argument(
        "--max-len",
        type=int,
        default=None,
        help="max acronym length (default: sum of the per-word maxima)",
    )

    ap.add_argument(
        "--check",
        action="store_true",
        help="Check GitHub and PyPI for each candidate (requires network access and takes a long time). Set the GITHUB_TOKEN environment variable to a GitHub personal access token to increase GitHub API rate limits.",
    )

    a = ap.parse_args()

    if a.top < 1:
        ap.error("--top must be at least 1")

    if a.min_len is not None and a.max_len is not None and a.max_len <= a.min_len:
        ap.error("--max-len must be strictly greater than --min-len")

    generator_init(
        a.words,
        min_len=a.min_len,
        max_len=a.max_len,
    )

    best = {}

    cache = load_cache() if a.check else None
    ttl = timedelta(days=30 * 12)
    purged_count = purge_cache(cache, ttl)
    if purged_count > 0:
        print(
            f"Purged {purged_count} from the cache: either invalid (missing fields) or older than {ttl}"
        )
    save_cache(cache)
    checked = set()
    free_acronyms = set()

    batch_size = 32 if a.check else 1024

    try:
        while True:
            batch = generator_next(batch_size)

            if not batch:
                break

            if not a.check:
                for row in batch:
                    add_best(best, row)

                continue

            checks = 0

            for row in batch:
                _syl, _extra, _cost, acr, _selections = row

                if acr in checked:
                    if acr in free_acronyms:
                        add_best(best, row)
                    continue

                checked.add(acr)

                try:
                    gh, py, performed_check = check_free(acr, cache)
                except KeyboardInterrupt:
                    save_cache(cache)
                    raise

                if performed_check:
                    checks += 1

                if gh == "free" and py == "free":
                    free_acronyms.add(acr)
                    add_best(best, row)

            save_cache(cache)

            if checks:
                print(f"{checks} check{'s' if checks > 1 else ''} down, cache saved")

    except KeyboardInterrupt:
        if a.check:
            save_cache(cache)
        raise

    rows = sorted(best.values())[: a.top]

    if not rows:
        print("no free candidates found" if a.check else "no candidates found")
        return 1

    print(f"top {len(rows)} ({'best free' if a.check else 'best'} first)\n")
    print(f"{'acronym':<12}{'syll':>5}{'extra':>7}{'dist':>6}  words")

    for syl, extra, cost, acr, selections in rows:
        source = format_selected_words(generator_words(), selections)
        print(f"{acr.upper():<12}{syl:>5}{extra:>7}{cost:>6}  {source}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
