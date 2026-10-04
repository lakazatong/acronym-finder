import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Primary GitHub REST API budget:
#
#   unauthenticated: 60 requests / hour
#   authenticated PAT: 5,000 requests / hour
#
# Add a small safety margin rather than subtracting one.
GITHUB_REQUESTS_PER_HOUR = 5000 if GITHUB_TOKEN else 60
GITHUB_REQUEST_INTERVAL = (3600 / GITHUB_REQUESTS_PER_HOUR) + 0.01

SECONDARY_LIMIT_WAIT = 60

_next_request_at = 0.0


def _headers():
    headers = {
        "User-Agent": "acronym-finder",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def _schedule_request():
    global _next_request_at

    now = time.monotonic()
    delay = _next_request_at - now

    if delay > 0:
        time.sleep(delay)

        now = time.monotonic()

    # Schedule from the request start, not the response.
    # Therefore network latency does not get added to our interval.
    _next_request_at = max(_next_request_at, now) + GITHUB_REQUEST_INTERVAL


def _server_delay(headers):
    retry_after = headers.get("Retry-After")

    if retry_after:
        try:
            return max(0, float(retry_after))
        except ValueError:
            pass

    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")

    if remaining == "0" and reset:
        try:
            return max(
                0,
                int(reset) - int(time.time()),
            )
        except ValueError:
            pass

    return None


def _respect_success_headers(headers):
    global _next_request_at

    delay = _server_delay(headers)

    if delay is None:
        return

    _next_request_at = max(
        _next_request_at,
        time.monotonic() + delay,
    )


def check(name):
    name = name.lower()

    _schedule_request()

    url = "https://api.github.com/users/" + urllib.parse.quote(name, safe="")

    req = urllib.request.Request(
        url,
        headers=_headers(),
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            _respect_success_headers(response.headers)
            return True

    except urllib.error.HTTPError as e:
        delay = _server_delay(e.headers)

        if delay is not None:
            global _next_request_at

            _next_request_at = max(
                _next_request_at,
                time.monotonic() + delay,
            )

        if e.code == 404:
            return False

        if e.code == 401:
            print(
                "GitHub authentication failed.",
                file=sys.stderr,
            )
            return None

        if e.code in (403, 429):
            if delay is None:
                delay = SECONDARY_LIMIT_WAIT

                _next_request_at = max(
                    _next_request_at,
                    time.monotonic() + delay,
                )

            print(
                f"GitHub rate limited; waiting {delay:g}s "
                "before the next GitHub request.",
                file=sys.stderr,
            )

            return None

        return None

    except (urllib.error.URLError, TimeoutError):
        return None
