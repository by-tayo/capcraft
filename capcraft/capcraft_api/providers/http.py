"""One small place that talks to the network, so tests can replace it and every
caller gets the same errors and caching."""
import json
import os
import time
import urllib.error
import urllib.request
from typing import Dict, Optional, Tuple


class DataError(Exception):
    """An outside source failed or has no answer. The message is safe to show the user."""


class Unavailable(DataError):
    """The source could not be reached or answered with a server error. A saved
    snapshot may stand in; a bad ticker or an unsuitable company may not."""


class NotFound(DataError):
    """The source has no such company or series."""


class NotConfigured(DataError):
    """A key or contact string this feature needs has not been set."""


_cache: Dict[str, Tuple[float, object]] = {}


def env(name: str) -> Optional[str]:
    v = os.environ.get(name, "").strip()
    return v or None


def get_json(url: str, headers: Optional[Dict[str, str]] = None, ttl: float = 0, timeout: float = 12):
    """GET a URL and parse JSON. Results are kept in memory for `ttl` seconds.
    Never put a secret in an error message: the URL may contain an API key."""
    now = time.time()
    hit = _cache.get(url)
    if ttl and hit and now - hit[0] < ttl:
        return hit[1]
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise Unavailable(f"The data source answered with an error ({e.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Unavailable("Could not reach the data source. Try again in a moment.") from None
    except ValueError:
        raise DataError("The data source sent something unreadable.") from None
    if ttl:
        _cache[url] = (now, data)
    return data


def clear_cache():
    _cache.clear()
