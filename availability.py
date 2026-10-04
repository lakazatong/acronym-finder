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

# Don't hammer GitHub if it tells us we're rate-limited.
github_pause_until = 0.0

# Minimum spacing between GitHub requests.
# This is deliberately conservative; the actual delay is adjusted
# using the rate-limit headers returned by GitHub.
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
        if delay > 10:
            print(
                f"Sleeping for {delay} seconds because of github rate limiting\n"
                + "You can safely CTRL+C, cache will be saved before aborting\n"
                + "If you so wish to reduce that cooldown, set the GITHUB_TOKEN env variable with your PAT"
            )
        time.sleep(delay)


def update_github_rate_limit(headers):
    """
    Update the delay before the next GitHub request based on the
    rate-limit headers returned by GitHub.

    We don't try to hit the limit exactly. We leave a small amount
    of headroom and spread the remaining requests across the
    remaining time window.
    """
    global github_next_request_at

    try:
        remaining = int(headers.get("X-RateLimit-Remaining", ""))
        # limit = int(headers.get("X-RateLimit-Limit", ""))
        reset = int(headers.get("X-RateLimit-Reset", ""))
    except ValueError:
        return

    if remaining <= 0:
        return

    seconds_until_reset = max(1, reset - int(time.time()))

    # Spread the remaining requests over the remaining window.
    # Leave one request in reserve.
    requests_left = max(1, remaining - 1)

    interval = seconds_until_reset / requests_left

    # Never go faster than 100 ms between requests.
    # This also helps avoid secondary rate limits.
    interval = max(0.10, interval)

    github_next_request_at = max(
        github_next_request_at,
        time.time() + interval,
    )


def github_rate_limit_delay(error):
    """
    Determine how long GitHub says we should wait.

    Returns:
        seconds, or None if no usable server-provided delay exists.
    """
    headers = error.headers

    # Secondary rate limits may explicitly tell us how long to wait.
    retry_after = headers.get("Retry-After")

    if retry_after:
        try:
            return max(0, int(float(retry_after)))
        except ValueError:
            pass

    # Primary rate limit: wait until X-RateLimit-Reset.
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
    global github_pause_until

    if time.time() < github_pause_until:
        return None

    github_wait_before_request()

    url = f"https://api.github.com/users/{name}"

    try:
        req = urllib.request.Request(
            url,
            headers=github_headers(),
        )

        with urllib.request.urlopen(req, timeout=8) as response:
            update_github_rate_limit(response.headers)
            return True

    except urllib.error.HTTPError as e:
        # Always process rate-limit headers when GitHub gives us them.
        update_github_rate_limit(e.headers)

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

        if e.code in (403, 429):
            delay = github_rate_limit_delay(e)

            if delay is None:
                delay = SECONDARY_LIMIT_WAIT

            github_pause_until = time.time() + delay

            print(
                f"GitHub rate limited; skipping GitHub checks for this run "
                f"(retry in {delay}s).",
                file=sys.stderr,
            )

            # IMPORTANT:
            # Do not sleep here. A reset could be 50+ minutes away.
            return None

        return None

    except (urllib.error.URLError, TimeoutError):
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

    if data["github"] is None:
        result = check_github(name)

        if result is not None:
            data["github"] = result
            data["github_checked_at"] = utc_now()

    if data["pypi"] is None:
        result = check_pypi(name)

        if result is not None:
            data["pypi"] = result
            data["pypi_checked_at"] = utc_now()

    def fmt(value):
        return "?" if value is None else ("taken" if value else "free")

    return fmt(data["github"]), fmt(data["pypi"])
