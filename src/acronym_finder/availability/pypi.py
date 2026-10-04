import urllib.error
import urllib.parse
import urllib.request


def check(name):
    name = name.lower()

    url = "https://pypi.org/pypi/" + urllib.parse.quote(name, safe="") + "/json"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "acronym-finder",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=8):
            return True

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False

        return None

    except (urllib.error.URLError, TimeoutError):
        return None
