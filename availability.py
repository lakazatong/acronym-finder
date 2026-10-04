import os
import sys
import time
import urllib
import urllib.error
import urllib.request

# Optional GitHub authentication.
# Set this in PowerShell:
#
#   $env:GITHUB_TOKEN = "github_pat_..."
#
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# GitHub's primary REST API budget.
#
# Unauthenticated:
#   60 requests / hour
#
# Authenticated with a PAT:
#   5,000 requests / hour
#
# Keep a small safety margin so clock/network overhead does not
# accumulate enough to push us over the nominal hourly budget.
GITHUB_REQUESTS_PER_HOUR = 5000 if GITHUB_TOKEN else 60
GITHUB_REQUEST_INTERVAL = (3600 / GITHUB_REQUESTS_PER_HOUR) - 0.01

github_next_request_at = 0.0

# If GitHub gives us a secondary-rate-limit response without
# Retry-After or a usable reset time, GitHub recommends waiting
# at least one minute.
SECONDARY_LIMIT_WAIT = 60


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def github_headers():
    headers = {
        "User-Agent": "acronym-finder",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def github_wait_before_request():
    delay = github_next_request_at - time.time()

    if delay > 0:
        time.sleep(delay)


def github_mark_request():
    global github_next_request_at

    github_next_request_at = time.time() + GITHUB_REQUEST_INTERVAL


def github_rate_limit_delay(error):
    """
    Determine how long GitHub says we should wait.

    Returns:
        seconds, or None if no usable server-provided delay exists.
    """
    headers = error.headers

    retry_after = headers.get("Retry-After")

    if retry_after:
        try:
            return max(0, int(float(retry_after)))
        except ValueError:
            pass

    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")

    if remaining == "0" and reset:
        try:
            return max(0, int(reset) - int(time.time()))
        except ValueError:
            pass

    return None


def check_github(name):
    """
    Returns:
        True  -> GitHub user exists / taken
        False -> GitHub user does not exist / free
        None  -> couldn't determine
    """
    github_wait_before_request()

    url = f"https://api.github.com/users/{name}"

    try:
        req = urllib.request.Request(
            url,
            headers=github_headers(),
        )

        with urllib.request.urlopen(req, timeout=8):
            github_mark_request()
            return True

    except urllib.error.HTTPError as e:
        # The request was sent, so keep the normal pacing regardless
        # of whether GitHub returned a successful response or an error.
        github_mark_request()

        # 404 is the one response that means "this username doesn't exist".
        if e.code == 404:
            return False

        # Authentication problem: don't confuse this with "taken".
        if e.code == 401:
            print(
                "GitHub authentication failed; ignoring the token.",
                file=sys.stderr,
            )
            return None

        # Primary or secondary rate limit.
        if e.code in (403, 429):
            delay = github_rate_limit_delay(e)

            if delay is None:
                delay = SECONDARY_LIMIT_WAIT

            # Do not sleep here. The next request will honor the
            # server-provided delay if we need to retry.
            global github_next_request_at
            github_next_request_at = max(
                github_next_request_at,
                time.time() + delay,
            )

            print(
                f"GitHub rate limited; waiting {delay}s before the next "
                "GitHub request.",
                file=sys.stderr,
            )

            return None

        return None

    except (urllib.error.URLError, TimeoutError):
        github_mark_request()
        return None


def check_pypi(name):
    """
    Returns:
        True  -> package exists / taken
        False -> package doesn't exist / free
        None  -> couldn't determine
    """
    url = f"https://pypi.org/pypi/{name}/json"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "acronym-finder"},
        )

        with urllib.request.urlopen(req, timeout=8):
            return True

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False

        # Never interpret a rate limit or server error as "taken".
        return None

    except (urllib.error.URLError, TimeoutError):
        return None


def check_free(name, cache):
    name = name.lower()

    data = cache.setdefault(
        name,
        {
            "github": None,
            "github_checked_at": None,
            "pypi": None,
            "pypi_checked_at": None,
        },
    )

    performed_check = False

    if data["github"] is None:
        performed_check = True
        result = check_github(name)

        if result is not None:
            data["github"] = result
            data["github_checked_at"] = utc_now()

    if data["pypi"] is None:
        performed_check = True
        result = check_pypi(name)

        if result is not None:
            data["pypi"] = result
            data["pypi_checked_at"] = utc_now()

    def fmt(value):
        return "?" if value is None else ("taken" if value else "free")

    return fmt(data["github"]), fmt(data["pypi"]), performed_check
