"""Starting the Roblox client, and letting more than one of them run.

Roblox keeps itself to one client per machine with two named kernel objects:
the old `ROBLOX_singletonMutex`, and `ROBLOX_singletonEvent`, which newer
clients use to tell an already-running client to quit. Holding only the mutex
is no longer enough — the new client still signals the event and the window
that was open disappears — so the manager creates both and keeps them for as
long as it is running.

They have to exist *before* the first client starts: a client that is already
running created them itself, and nothing done afterwards takes that away,
which is why `enable_multi_instance` reports whether it got there first.
"""

import ctypes
import glob
import os
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
MUTEX_NAME = "ROBLOX_singletonMutex"
EVENT_NAME = "ROBLOX_singletonEvent"
ERROR_ALREADY_EXISTS = 183

_handles = []
_ours = False


def multi_instance_enabled() -> bool:
    return bool(_handles)


def owns_singleton() -> bool:
    """True when the limit is ours to hold, so launches are actually free."""
    return bool(_handles) and _ours


def reacquire() -> bool:
    """Let go and take the objects again, once Roblox has let go of them.

    Needed after closing clients that were started before the manager: while
    they were running, the objects were theirs, and only a fresh create makes
    them ours.
    """
    disable_multi_instance()
    return enable_multi_instance()


def enable_multi_instance() -> bool:
    """Create both singleton objects and hold them.

    True means we created them; False means Roblox got there first, so a
    client that is already running still owns the limit and has to be closed
    and started again from here.
    """
    global _handles, _ours
    if not IS_WINDOWS:
        raise RuntimeError("multi-instance is a Windows-only trick")
    if _handles:
        return _ours

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateEventW.restype = ctypes.c_void_p

    ours = True
    handles = []
    # The mutex is created *owned* (bInitialOwner=True). A starting client
    # waits on it in `waitForNewPlayerProcess`, and an unowned mutex is
    # signalled straight away, which lets that client carry on and tell the
    # one already running to quit. Owned, the wait never returns and the
    # window that is open stays open.
    for create, arguments in (
            (kernel32.CreateMutexW, (None, True, MUTEX_NAME)),
            (kernel32.CreateEventW, (None, True, False, EVENT_NAME))):
        ctypes.set_last_error(0)
        handle = create(*arguments)
        error = ctypes.get_last_error()
        if not handle:
            for open_handle in handles:
                kernel32.CloseHandle(ctypes.c_void_p(open_handle))
            raise OSError(error, "could not create %s" % arguments[-1])
        if error == ERROR_ALREADY_EXISTS:
            ours = False
        handles.append(handle)

    _handles = handles
    _ours = ours
    return ours


def disable_multi_instance() -> None:
    global _handles, _ours
    if _handles and IS_WINDOWS:
        kernel32 = ctypes.WinDLL("kernel32")
        for handle in _handles:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    _handles = []
    _ours = False


def player_path():
    """Path to RobloxPlayerBeta.exe, or None if it cannot be found."""
    if not IS_WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                            r"roblox-player\shell\open\command") as key:
            command = winreg.QueryValueEx(key, "")[0]
        parts = command.split('"')
        candidate = parts[1] if len(parts) > 1 else command.split()[0]
        if os.path.exists(candidate):
            return candidate
    except OSError:
        pass

    local = os.environ.get("LOCALAPPDATA", "")
    patterns = [
        os.path.join(local, "Roblox", "Versions", "*", "RobloxPlayerBeta.exe"),
        os.path.join(local, "Bloxstrap", "Versions", "*", "RobloxPlayerBeta.exe"),
        r"C:\Program Files (x86)\Roblox\Versions\*\RobloxPlayerBeta.exe",
    ]
    found = [p for pattern in patterns for p in glob.glob(pattern)]
    if not found:
        return None
    return max(found, key=os.path.getmtime)


def launch(uri: str) -> None:
    """Hand the `roblox-player:` URI to the client."""
    exe = player_path()
    if exe:
        subprocess.Popen([exe, uri], close_fds=True)
        return
    if IS_WINDOWS:
        os.startfile(uri)  # falls back to whatever registered the protocol
        return
    raise RuntimeError("Roblox client not found")


def running_clients() -> int:
    """How many Roblox clients are currently running."""
    if not IS_WINDOWS:
        return 0
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq RobloxPlayerBeta.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    return sum(1 for line in out.splitlines()
               if "RobloxPlayerBeta.exe" in line)


def close_all_clients() -> int:
    """Kill every running Roblox client. Returns how many were running."""
    count = running_clients()
    if count and IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/IM", "RobloxPlayerBeta.exe"],
                       capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return count
