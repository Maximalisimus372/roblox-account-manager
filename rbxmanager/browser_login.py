"""Signing in without copying cookies by hand.

The manager opens a browser window on Roblox's own login (or sign-up) page,
using a profile directory of its own, and then watches that profile for a
`.ROBLOSECURITY` cookie. You log in in the window exactly as you normally
would - password, captcha, 2FA and all of it stay between you and Roblox - and
the moment the cookie appears the account is added.

A separate profile per account is what makes several accounts possible at all:
browsers keep one Roblox session per profile, so logging into a second account
in your everyday window would sign the first one out.

Two families of browser are supported:

* Firefox keeps cookie values in plain text in `cookies.sqlite`, so the cookie
  is read straight out of the profile with sqlite3.
* Chrome/Edge/Brave encrypt theirs, so instead of decrypting anything the
  browser is started with `--remote-debugging-port` on its own profile and
  asked for the cookie over the DevTools protocol.

Nothing here fills in forms, and nothing here touches your normal browser
profile.
"""

import base64
import glob
import json
import os
import shutil
import socket
import sqlite3
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .storage import data_dir

LOGIN_URL = "https://www.roblox.com/login"
SIGNUP_URL = "https://www.roblox.com/CreateAccount"
COOKIE_NAME = ".ROBLOSECURITY"


class LoginError(Exception):
    pass


# --------------------------------------------------------------- browsers

@dataclass(frozen=True)
class Browser:
    name: str
    path: str
    family: str  # "firefox" or "chromium"


_CANDIDATES = (
    ("Firefox", "firefox", [
        r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
        r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
    ]),
    ("Chrome", "chromium", [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ]),
    ("Edge", "chromium", [
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    ]),
    ("Brave", "chromium", [
        r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]),
)


def available_browsers():
    """Every supported browser installed on this machine."""
    found = []
    for name, family, patterns in _CANDIDATES:
        for pattern in patterns:
            path = os.path.expandvars(pattern)
            if "%" not in path and os.path.exists(path):
                found.append(Browser(name, path, family))
                break
    return found


def profiles_dir() -> str:
    path = os.path.join(data_dir(), "profiles")
    os.makedirs(path, exist_ok=True)
    return path


def new_profile_path(prefix="login") -> str:
    path = os.path.join(profiles_dir(), "%s-%d" % (prefix, int(time.time())))
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------- minimal websocket

class _WebSocket:
    """Just enough RFC 6455 to talk to the DevTools endpoint."""

    def __init__(self, url, timeout=10):
        parsed = urllib.parse.urlparse(url)
        port = parsed.port or 80
        self.sock = socket.create_connection((parsed.hostname, port), timeout)
        self.sock.settimeout(timeout)
        self._buffer = b""
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = ("GET {path} HTTP/1.1\r\n"
                     "Host: {host}:{port}\r\n"
                     "Upgrade: websocket\r\n"
                     "Connection: Upgrade\r\n"
                     "Sec-WebSocket-Key: {key}\r\n"
                     "Sec-WebSocket-Version: 13\r\n\r\n").format(
                         path=path, host=parsed.hostname, port=port, key=key)
        self.sock.sendall(handshake.encode("ascii"))
        status = self._read_until(b"\r\n\r\n").split(b"\r\n", 1)[0]
        if b"101" not in status:
            raise LoginError("DevTools refused the websocket: %s"
                             % status.decode("latin-1", "replace"))

    def _read_until(self, marker):
        while marker not in self._buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise LoginError("DevTools closed the connection")
            self._buffer += chunk
        head, self._buffer = self._buffer.split(marker, 1)
        return head + marker

    def _read_exact(self, count):
        while len(self._buffer) < count:
            chunk = self.sock.recv(max(4096, count - len(self._buffer)))
            if not chunk:
                raise LoginError("DevTools closed the connection")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def send(self, text):
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv(self):
        """Next text message; control frames are handled and skipped."""
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            if second & 0x80:  # a server should never mask, but be safe
                mask = self._read_exact(4)
                payload = bytes(b ^ mask[i % 4]
                                for i, b in enumerate(self._read_exact(length)))
            else:
                payload = self._read_exact(length)
            if opcode == 0x8:
                raise LoginError("DevTools closed the connection")
            if opcode == 0x9:  # ping -> pong
                self.sock.sendall(b"\x8a\x80" + os.urandom(4))
                continue
            if opcode in (0x1, 0x2):
                return payload.decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ------------------------------------------------------------- sessions

class _Session:
    """A browser window opened on a Roblox page, watched for the cookie."""

    LOCK_FILES = ()

    def __init__(self, browser: Browser, profile: str, url: str):
        self.browser = browser
        self.profile = profile
        self.url = url
        self.process = None
        self._checked_at = 0.0
        self._was_running = True

    def start(self):
        raise NotImplementedError

    def cookie(self):
        """The cookie if the login has gone through, else None."""
        raise NotImplementedError

    def alive(self):
        """Whether a browser is still open on this profile.

        The process we started is not a reliable answer: Firefox's launcher
        hands over to another process and exits within a second, which used to
        look exactly like "the user closed the window". So each family also
        points at the file its browser keeps while a profile is in use.
        """
        if self.process is not None and self.process.poll() is None:
            return True
        if not any(os.path.exists(os.path.join(self.profile, marker))
                   for marker in self.LOCK_FILES):
            return False
        # A lock file left behind by a browser that was killed would otherwise
        # look like a window that is still open, so confirm with the process
        # list - but rarely, since that costs a subprocess.
        now = time.time()
        if now - self._checked_at > 10:
            self._checked_at = now
            self._was_running = self._browser_processes() > 0
        return self._was_running

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self._close_by_profile()

    def _powershell(self, script):
        try:
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    def _profile_query(self):
        """Processes of this browser started on this profile.

        Filtered by the browser's own executable name, so the shell running
        the command - whose command line also mentions the profile - cannot
        match itself.
        """
        return ("Get-CimInstance Win32_Process -Filter \"Name='%s'\" | "
                "Where-Object { $_.CommandLine -like '*%s*' }"
                % (os.path.basename(self.browser.path),
                   os.path.basename(self.profile)))

    def _browser_processes(self):
        if os.name != "nt":
            return 0
        out = self._powershell("@(%s).Count" % self._profile_query())
        try:
            return int(out.strip() or 0)
        except ValueError:
            return 0

    def _close_by_profile(self):
        """Close a browser that outlived the process we started.

        Firefox in particular is a different process by now, so it is found by
        the profile path on its command line - nothing else is touched.
        """
        if os.name != "nt" or not os.path.isdir(self.profile):
            return
        self._powershell("%s | ForEach-Object { Stop-Process -Id "
                         "$_.ProcessId -Force -ErrorAction SilentlyContinue }"
                         % self._profile_query())


class FirefoxSession(_Session):
    LOCK_FILES = ("parent.lock",)

    def start(self):
        self.process = subprocess.Popen(
            [self.browser.path, "-no-remote", "-profile", self.profile,
             "-new-window", self.url])

    def cookie(self):
        db = os.path.join(self.profile, "cookies.sqlite")
        if not os.path.exists(db):
            return None
        # The live database is locked and may have unflushed WAL pages, so
        # work on a copy of the db and its journal.
        scratch = tempfile.mkdtemp(prefix="rbxcookies")
        try:
            for source in [db] + glob.glob(db + "-*"):
                shutil.copy2(source, os.path.join(scratch,
                                                  os.path.basename(source)))
            connection = sqlite3.connect(os.path.join(scratch,
                                                      os.path.basename(db)))
            try:
                row = connection.execute(
                    "SELECT value FROM moz_cookies "
                    "WHERE name = ? AND host LIKE '%roblox.com'",
                    (COOKIE_NAME,)).fetchone()
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            return None
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return row[0] if row and row[0] else None


class ChromiumSession(_Session):
    LOCK_FILES = ("DevToolsActivePort", "SingletonLock", "lockfile")

    def start(self):
        self.process = subprocess.Popen([
            self.browser.path,
            "--user-data-dir=" + self.profile,
            "--remote-debugging-port=0",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            self.url,
        ])

    def _devtools_port(self):
        marker = os.path.join(self.profile, "DevToolsActivePort")
        if not os.path.exists(marker):
            return None
        try:
            with open(marker, "r", encoding="utf-8") as handle:
                return int(handle.readline().strip())
        except (OSError, ValueError):
            return None

    def cookie(self):
        port = self._devtools_port()
        if not port:
            return None
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/version" % port, timeout=5) as r:
                endpoint = json.load(r)["webSocketDebuggerUrl"]
        except (OSError, ValueError, KeyError):
            return None
        try:
            socket_ = _WebSocket(endpoint)
        except (OSError, LoginError):
            return None
        try:
            socket_.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
            deadline = time.time() + 10
            while time.time() < deadline:
                message = json.loads(socket_.recv())
                if message.get("id") != 1:
                    continue
                cookies = message.get("result", {}).get("cookies", [])
                for cookie in cookies:
                    if (cookie.get("name") == COOKIE_NAME
                            and "roblox.com" in cookie.get("domain", "")
                            and cookie.get("value")):
                        return cookie["value"]
                return None
        except (OSError, LoginError, ValueError):
            return None
        finally:
            socket_.close()
        return None


def open_session(browser: Browser, url: str, profile: str = None) -> _Session:
    """Open `url` in a fresh window of `browser` on its own profile."""
    profile = profile or new_profile_path()
    os.makedirs(profile, exist_ok=True)
    session_class = (FirefoxSession if browser.family == "firefox"
                     else ChromiumSession)
    session = session_class(browser, profile, url)
    session.start()
    return session
