#!/usr/bin/env python3
"""
Generate pronounceable acronyms from a sequence of words.

Words are positional arguments and are case-insensitive. Each word contributes
at least one letter, and the generated acronym must have a length between
--min and --max.

By default, both --min and --max are set to the number of words, so every
word contributes exactly one letter.

The maximum number of letters each word may contribute is derived automatically
from --max. For k words, no word can contribute more than:

    --max - k + 1

or more than the number of letters in the word itself.

A one-letter word contributes only that letter, so it can be used to pin a
specific position in the acronym.

Generation is resumable. Running the same request again continues from the
previously saved generator state and appends new candidates to its session.

Examples:
    acronyms generate my awesome words
    acronyms generate my awesome words --min 3 --max 5
    acronyms generate m awesome words
    acronyms generate m awesome w --max 4
"""

import argparse
import sys

from acronym_finder.generator import GenerationRequest, Generator
from acronym_finder.session import (
    GenerationResult,
    Session,
    load_session,
    make_session_path,
    save_session,
)

SAVE_INTERVAL = 1024


def parse_words(tokens: list[str]) -> list[str]:
    words = []

    for token in tokens:
        if not token.isascii() or not token.isalpha():
            raise ValueError(f"invalid word '{token}': use only A-Z/a-z")

        words.append(token.lower())

    return words


def register_parser(subparsers):
    parser = subparsers.add_parser(
        "generate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "words",
        nargs="+",
        metavar="WORD",
        help="a word",
    )

    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="number of new acronyms to generate (default: 10)",
    )

    parser.add_argument(
        "--min",
        type=int,
        default=None,
        help="minimum acronym length (default: number of words)",
    )

    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="maximum acronym length (default: --min)",
    )

    parser.set_defaults(func=main)


def main(args) -> int:
    if args.count < 1:
        print("--count must be at least 1", file=sys.stderr)
        return 2

    try:
        words = parse_words(args.words)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    n = len(words)

    min_len = args.min if args.min is not None else n
    max_len = args.max if args.max is not None else min_len

    if min_len < n:
        print(
            f"error: --min must be at least {n} "
            "because every word contributes at least one letter",
            file=sys.stderr,
        )
        return 2

    if max_len < min_len:
        print(
            f"error: --max ({max_len}) must be at least --min ({min_len})",
            file=sys.stderr,
        )
        return 2

    cap_limit = max_len - n + 1
    caps = [min(len(word), cap_limit) for word in words]

    if min_len > sum(caps):
        print(
            f"error: --min {min_len} is unreachable; "
            f"the words allow at most {sum(caps)} letters",
            file=sys.stderr,
        )
        return 2

    request = GenerationRequest(
        words=words,
        caps=caps,
        min_len=min_len,
        max_len=max_len,
    )

    session_path = make_session_path(request)

    try:
        generator = Generator.create(request)

        session = load_session(session_path)

        if session is None:
            session = Session(
                request=request,
                generator_stack=generator.get_stack(),
                results=[],
            )
        else:
            if session.request != request:
                raise ValueError(
                    f"session '{session_path}' belongs to a different request"
                )

            if not session.generator_stack:
                print("Session's generator exhausted")
                return 0

            generator.set_stack(session.generator_stack)

        generated = 0
        processed_since_save = 0

        results_by_acronym = {result.acronym: result for result in session.results}

        while generated < args.count:
            acronym, mask = generator.next()

            result = results_by_acronym.get(acronym)

            if result is None:
                result = GenerationResult(
                    acronym=acronym,
                    masks=[],
                )
                results_by_acronym[acronym] = result
                session.results.append(result)
                generated += 1

            if mask not in result.masks:
                result.masks.append(mask)

            processed_since_save += 1

            if processed_since_save >= SAVE_INTERVAL:
                session.generator_stack = generator.get_stack()
                save_session(session_path, session)
                processed_since_save = 0

            if not generator.stack:
                break

        session.generator_stack = generator.get_stack()
        save_session(session_path, session)

        print(f"Generated {generated} new acronym{'s' if generated != 1 else ''}.")
        print(f"Session: {session_path}")
        return 0

    except (ValueError, RuntimeError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print(
            "\nInterrupted; the last completed candidate is saved.",
            file=sys.stderr,
        )
        return 130
