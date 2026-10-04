import csv
from pathlib import Path

CACHE_FILE = Path(__file__).with_name("names.csv")


def load_cache():
    try:
        with CACHE_FILE.open("r", newline="", encoding="utf-8") as f:
            result = {}

            for row in csv.DictReader(f):
                name = row["name"].lower()

                def parse(value):
                    if value == "?":
                        return None
                    return value == "true"

                result[name] = {
                    "github": parse(row["github_taken"]),
                    "github_checked_at": row.get("github_checked_at") or None,
                    "pypi": parse(row["pypi_taken"]),
                    "pypi_checked_at": row.get("pypi_checked_at") or None,
                }

            return result

    except FileNotFoundError:
        return {}


def save_cache(cache):
    with CACHE_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(
            [
                "name",
                "github_taken",
                "pypi_taken",
                "github_checked_at",
                "pypi_checked_at",
            ]
        )

        for name, data in sorted(cache.items()):
            writer.writerow(
                [
                    name,
                    "?" if data["github"] is None else str(data["github"]).lower(),
                    "?" if data["pypi"] is None else str(data["pypi"]).lower(),
                    data["github_checked_at"] or "",
                    data["pypi_checked_at"] or "",
                ]
            )
