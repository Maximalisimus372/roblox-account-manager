"""The bits of the Roblox web API this manager needs.

Everything here is done with the account's own `.ROBLOSECURITY` cookie, the
same way the website does it when you press Play:

  1. ask auth.roblox.com for a one-shot authentication ticket,
  2. hand that ticket to the Roblox player through its URL protocol.

Only stdlib, so there is nothing to install.
"""

import json
import random
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 20


class RobloxError(Exception):
    """A request to Roblox failed, or the cookie is no longer valid."""


def _request(method, url, cookie=None, csrf=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(url, method=method,
                                 data=data if method != "GET" else None)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    req.add_header("Referer", "https://www.roblox.com/")
    req.add_header("Origin", "https://www.roblox.com")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", ".ROBLOSECURITY=" + cookie)
    if csrf:
        req.add_header("X-CSRF-TOKEN", csrf)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except urllib.error.URLError as exc:
        raise RobloxError("network error: %s" % exc.reason) from exc


def _json(payload):
    try:
        return json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


def clean_cookie(raw: str) -> str:
    """Accept a pasted cookie in any of the shapes people paste it in."""
    value = raw.strip().strip('"').strip()
    if value.startswith(".ROBLOSECURITY="):
        value = value[len(".ROBLOSECURITY="):]
    return value.split(";")[0].strip()


def authenticated_user(cookie: str) -> dict:
    """Return {'id', 'name', 'displayName'} for the cookie's owner."""
    status, _, payload = _request(
        "GET", "https://users.roblox.com/v1/users/authenticated", cookie=cookie)
    if status == 401:
        raise RobloxError("cookie is invalid or expired")
    if status != 200:
        raise RobloxError("users.roblox.com returned HTTP %s" % status)
    return _json(payload)


def robux(cookie: str, user_id: int):
    """Robux balance, or None when Roblox will not tell us."""
    status, _, payload = _request(
        "GET", "https://economy.roblox.com/v1/users/%d/currency" % user_id,
        cookie=cookie)
    if status != 200:
        return None
    return _json(payload).get("robux")


_SERVER_CACHE = {}
SERVER_CACHE_SECONDS = 120


def public_servers(place_id, limit=100, exclude_full=True, max_age=None):
    """The public servers of a place, nearest (lowest ping) first.

    Used to send each account to a different server: the launcher URL takes a
    server's job ID, and this is where those come from. No cookie needed.

    The endpoint answers 429 to anything but occasional calls, so the answer
    is cached for a couple of minutes; launching accounts one at a time would
    otherwise get a rate-limit instead of a server list.
    """
    import time
    max_age = SERVER_CACHE_SECONDS if max_age is None else max_age
    cached = _SERVER_CACHE.get(place_id)
    if cached and time.time() - cached[0] < max_age:
        return cached[1]
    query = urllib.parse.urlencode({
        "sortOrder": "Asc",
        "excludeFullGames": "true" if exclude_full else "false",
        "limit": min(int(limit), 100)})
    status, _, payload = _request(
        "GET", "https://games.roblox.com/v1/games/%s/servers/Public?%s"
        % (place_id, query))
    if status != 200:
        if cached:  # stale is better than nothing when rate-limited
            return cached[1]
        raise RobloxError("could not list the servers of place %s (HTTP %s)"
                          % (place_id, status))
    servers = [s for s in _json(payload).get("data", [])
               if s.get("id") and s.get("playing", 0) < s.get("maxPlayers", 0)]
    servers.sort(key=lambda s: s.get("ping") or 9999)
    _SERVER_CACHE[place_id] = (time.time(), servers)
    return servers


def csrf_token(cookie: str) -> str:
    """Roblox hands out its CSRF token in the 403 it sends to a bare POST."""
    status, headers, _ = _request(
        "POST", "https://auth.roblox.com/v1/authentication-ticket",
        cookie=cookie)
    token = headers.get("x-csrf-token") or headers.get("X-CSRF-TOKEN")
    if not token:
        if status == 401:
            raise RobloxError("cookie is invalid or expired")
        raise RobloxError("Roblox did not return a CSRF token (HTTP %s)" % status)
    return token


def authentication_ticket(cookie: str) -> str:
    """A single-use ticket the Roblox player exchanges for a session."""
    token = csrf_token(cookie)
    status, headers, payload = _request(
        "POST", "https://auth.roblox.com/v1/authentication-ticket",
        cookie=cookie, csrf=token)
    ticket = headers.get("rbx-authentication-ticket")
    if not ticket:
        if status == 401:
            raise RobloxError("cookie is invalid or expired")
        message = _json(payload).get("errors", [{}])[0].get("message", "")
        raise RobloxError(("no authentication ticket (HTTP %s) %s"
                           % (status, message)).strip())
    return ticket


def browser_tracker_id() -> int:
    return random.randint(10_000_000_000, 99_999_999_999)


def place_launcher_url(place_id, *, job_id=None, access_code=None,
                       follow_user_id=None, tracker_id=None) -> str:
    """The PlaceLauncher URL describing which server to join."""
    params = {"browserTrackerId": tracker_id or browser_tracker_id(),
              "placeId": place_id,
              "isPlayTogetherGame": "false"}
    if follow_user_id:
        params = {"request": "RequestFollowUser",
                  "browserTrackerId": params["browserTrackerId"],
                  "userId": follow_user_id}
    elif access_code:
        params["request"] = "RequestPrivateGame"
        params["accessCode"] = access_code
    elif job_id:
        params["request"] = "RequestGameJob"
        params["gameId"] = job_id
    else:
        params["request"] = "RequestGame"
    ordered = ["request"] + [k for k in params if k != "request"]
    query = urllib.parse.urlencode([(k, params[k]) for k in ordered])
    return "https://assetgame.roblox.com/game/PlaceLauncher.ashx?" + query


def launch_uri(ticket: str, launcher_url: str, *, tracker_id=None,
               launch_time_ms=None, locale="en_us") -> str:
    """The `roblox-player:` URI that starts the client on a given server."""
    import time
    tracker_id = tracker_id or browser_tracker_id()
    launch_time_ms = launch_time_ms or int(time.time() * 1000)
    return ("roblox-player:1"
            "+launchmode:play"
            "+gameinfo:{ticket}"
            "+launchtime:{time}"
            "+placelauncherurl:{url}"
            "+browsertrackerid:{tracker}"
            "+robloxLocale:{locale}"
            "+gameLocale:{locale}"
            "+channel:").format(ticket=ticket, time=launch_time_ms,
                                url=urllib.parse.quote(launcher_url, safe=""),
                                tracker=tracker_id, locale=locale)
