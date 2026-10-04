import argparse

from acronym_finder.cli import check, generate, view


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="acronyms",
        description="Generate, check, and view acronyms.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    generate.register_parser(subparsers)
    view.register_parser(subparsers)
    check.register_parser(subparsers)

    args = parser.parse_args()

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
