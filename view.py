#!/usr/bin/env python3
"""
View, filter, and sort the results of an acronym generation session.

Runtime result fields:
    a.acr
        The acronym.

    a.mask
        The mask producing this result, with one mask string per source word.

    a.syllables
        The syllables of the acronym.

Expression passed to --filter must return a boolean.

Expressions passed to --sort compare two results and must return a boolean.

    compare(a, b) == True
        a should appear before b.

    compare(a, b) == False and compare(b, a) == True
        b should appear before a.

    compare(a, b) == False and compare(b, a) == False
        The results are considered equal for this comparator, so the next
        sort expression is evaluated.

    compare(a, b) == True and compare(b, a) == True
        The comparator is contradictory and is invalid.

Examples:
    python view.py SESSION --sort "len(a.syllables)<len(b.syllables);len(a.acr)<len(b.acr)"
    -> sorts first by syllable count, then by acronym length.

    python view.py SESSION --filter "len(a.syllables)<=3"

    python view.py SESSION \
        --filter "a.mask[0].count('1')==1" \
        --sort "a.mask[0]<b.mask[0];a.acr<b.acr" \
        --top 20
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path

from acronym_finder.session import Session, load_session

SAFE_BUILTINS = {
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "any": any,
    "all": all,
}


@dataclass(frozen=True)
class Result:
    acr: str
    mask: list[str]
    syllables: list[str]


@dataclass(frozen=True)
class Arguments:
    session: Session
    filter: Callable[[Result], bool] | None
    sort: list[Callable[[Result, Result], bool]]
    top: int
    unique: bool


def syllables(word: str) -> list[str]:
    """Return the vowel groups used as syllable approximations."""
    vowels = set("aeiouy")
    result = []
    i = 0

    while i < len(word):
        if word[i] in vowels:
            start = i

            while i < len(word) and word[i] in vowels:
                i += 1

            result.append(word[start:i])
        else:
            i += 1

    if (
        len(word) >= 3
        and word[-1] == "e"
        and word[-2] not in vowels
        and word[-3] in vowels
        and len(result) > 1
    ):
        result.pop()

    return result


def enrich_result(
    acr: str,
    mask: list[str],
) -> Result:
    return Result(
        acr=acr,
        mask=mask,
        syllables=syllables(acr.lower()),
    )


def enrich_session(session: Session) -> list[Result]:
    return [
        enrich_result(result.acronym, mask)
        for result in session.results
        for mask in result.masks
    ]


def split_expressions(value: str) -> list[str]:
    expressions = [expression.strip() for expression in value.split(";")]

    if not all(expressions):
        raise ValueError("empty expression in expression list")

    return expressions


def evaluate_filter(
    expression: str,
    result: Result,
) -> bool:
    value = eval(
        expression,
        {"__builtins__": {}},
        {
            "a": result,
            **SAFE_BUILTINS,
        },
    )

    if not isinstance(value, bool):
        raise TypeError(
            f"--filter expression must return bool, got {type(value).__name__}"
        )

    return value


def make_filter(
    expression: str,
) -> Callable[[Result], bool]:
    def filter_result(result: Result) -> bool:
        return evaluate_filter(expression, result)

    return filter_result


def parse_filter(
    expression: str | None,
) -> Callable[[Result], bool] | None:
    if expression is None:
        return None

    expression = expression.strip()

    if not expression:
        raise ValueError("--filter cannot be empty")

    return make_filter(expression)


def evaluate_comparator(
    expression: str,
    a: Result,
    b: Result,
) -> bool:
    value = eval(
        expression,
        {"__builtins__": {}},
        {
            "a": a,
            "b": b,
            **SAFE_BUILTINS,
        },
    )

    if not isinstance(value, bool):
        raise TypeError(f"--sort expression must return bool: {expression}")

    return value


def make_comparator(
    expression: str,
) -> Callable[[Result, Result], bool]:
    def compare(a: Result, b: Result) -> bool:
        return evaluate_comparator(expression, a, b)

    return compare


def parse_sort(
    expression: str | None,
) -> list[Callable[[Result, Result], bool]]:
    if expression is None:
        return []

    return [make_comparator(expression) for expression in split_expressions(expression)]


def compare_results(
    a: Result,
    b: Result,
    comparators: list[Callable[[Result, Result], bool]],
) -> int:
    for compare in comparators:
        a_before_b = compare(a, b)
        b_before_a = compare(b, a)

        if a_before_b and not b_before_a:
            return -1

        if b_before_a and not a_before_b:
            return 1

    return 0


def sort_results(
    results: list[Result],
    comparators: list[Callable[[Result, Result], bool]],
) -> list[Result]:
    if not comparators:
        return results

    return sorted(
        results,
        key=cmp_to_key(lambda a, b: compare_results(a, b, comparators)),
    )


def apply_mask(word: str, mask: str) -> str:
    return "".join(
        char.upper() if selected == "1" else char
        for char, selected in zip(word, mask, strict=True)
    )


def format_selection(
    result: Result,
    words: list[str],
) -> str:
    return " ".join(
        apply_mask(word, mask) for word, mask in zip(words, result.mask, strict=True)
    )


def print_metadata(
    session: Session,
    displayed_results: int,
) -> None:
    total_acronyms = len(session.results)
    total_masks = sum(len(result.masks) for result in session.results)

    if total_acronyms:
        mask_counts = [len(result.masks) for result in session.results]
        average_masks = total_masks / total_acronyms

        sorted_mask_counts = sorted(mask_counts)
        middle = total_acronyms // 2

        if total_acronyms % 2:
            median_masks = sorted_mask_counts[middle]
        else:
            median_masks = (
                sorted_mask_counts[middle - 1] + sorted_mask_counts[middle]
            ) / 2
    else:
        average_masks = 0
        median_masks = 0

    print("Session")
    print(f"  Words:            {' '.join(session.request.words)}")
    print(f"  Length:           {session.request.min_len}-{session.request.max_len}")
    print()
    print("Results")
    print(f"  Acronyms:         {total_acronyms:,}")
    print(f"  Masks:            {total_masks:,}")
    print(f"  Displayed:        {displayed_results:,}")
    print(f"  Average masks:    {average_masks:.2f}")
    print(f"  Median masks:     {median_masks:g}")
    print()


def print_results(
    results: list[Result],
    words: list[str],
    mask_counts: dict[str, int] | None = None,
) -> None:
    if not results:
        print("No results.")
        return

    if mask_counts is None:
        headers = (
            "ACRONYM",
            "SYLLABLES",
            "LENGTH",
            "SELECTION",
        )

        rows = [
            (
                result.acr,
                len(result.syllables),
                len(result.acr),
                format_selection(result, words),
            )
            for result in results
        ]
    else:
        headers = (
            "ACRONYM",
            "MASKS",
            "SYLLABLES",
            "LENGTH",
            "SELECTION",
        )

        rows = [
            (
                result.acr,
                mask_counts[result.acr],
                len(result.syllables),
                len(result.acr),
                format_selection(result, words),
            )
            for result in results
        ]

    widths = [
        max(
            len(header),
            *(len(str(row[i])) for row in rows),
        )
        for i, header in enumerate(headers)
    ]

    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))

    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)))


def parse_args() -> Arguments:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    ap.add_argument(
        "session",
        type=Path,
        help="session JSON file produced by acronym.py",
    )

    ap.add_argument(
        "--filter",
        dest="filter_expression",
        default=None,
        help="Python boolean expression applied to each result",
    )

    ap.add_argument(
        "--sort",
        dest="sort_expression",
        default=None,
        help="semicolon-separated Python comparison expressions",
    )

    ap.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="show only the first N results after filtering and sorting (default: 10)",
    )

    ap.add_argument(
        "-u",
        "--unique",
        action="store_true",
        help="keep only the first result for each acronym",
    )

    args = ap.parse_args()

    if args.top < 1:
        ap.error("--top must be at least 1")

    try:
        session = load_session(args.session)

        if session is None:
            raise FileNotFoundError(f"session not found: {args.session}")

        filter_function = parse_filter(args.filter_expression)
        sort_functions = parse_sort(args.sort_expression)

    except (ValueError, TypeError, SyntaxError, FileNotFoundError) as e:
        ap.error(str(e))

    return Arguments(
        session=session,
        filter=filter_function,
        sort=sort_functions,
        top=args.top,
        unique=args.unique,
    )


def unique_results(results: list[Result]) -> list[Result]:
    seen: set[str] = set()
    unique = []

    for result in results:
        if result.acr in seen:
            continue

        seen.add(result.acr)
        unique.append(result)

    return unique


def main() -> int:
    args = parse_args()

    results = enrich_session(args.session)

    if args.filter is not None:
        results = [result for result in results if args.filter(result)]

    results = sort_results(results, args.sort)

    if args.unique:
        results = unique_results(results)

    if args.top is not None:
        results = results[: args.top]

    print_metadata(
        args.session,
        len(results),
    )

    mask_counts = {result.acronym: len(result.masks) for result in args.session.results}

    print_results(
        results,
        args.session.request.words,
        mask_counts if args.unique else None,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
