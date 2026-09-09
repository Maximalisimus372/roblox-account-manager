"""Local secret storage.

On Windows the account cookies are encrypted with DPAPI (CryptProtectData),
which ties the ciphertext to the current Windows user account: another user on
the same machine, or the file copied elsewhere, cannot decrypt it.

On other platforms there is no equivalent, so the data is only base64-encoded
and the caller is warned.
"""

import base64
import ctypes
import ctypes.wintypes as wintypes
import sys

IS_WINDOWS = sys.platform == "win32"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]

    @classmethod
    def of(cls, data: bytes) -> "_Blob":
        buf = ctypes.create_string_buffer(data, len(data))
        blob = cls(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob._buf = buf  # keep the buffer alive for as long as the blob is
        return blob

    def value(self) -> bytes:
        return ctypes.string_at(self.pbData, self.cbData)


if IS_WINDOWS:
    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_Blob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL

_ENTROPY = b"rbxmanager/v1"
_DESC = "Roblox Account Manager"


def encrypt(plaintext: str) -> str:
    raw = plaintext.encode("utf-8")
    if not IS_WINDOWS:
        return "b64:" + base64.b64encode(raw).decode("ascii")

    out = _Blob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(_Blob.of(raw)), _DESC, ctypes.byref(_Blob.of(_ENTROPY)),
        None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
    try:
        return "dpapi:" + base64.b64encode(out.value()).decode("ascii")
    finally:
        _kernel32.LocalFree(out.pbData)


def decrypt(stored: str) -> str:
    scheme, _, payload = stored.partition(":")
    raw = base64.b64decode(payload)
    if scheme == "b64":
        return raw.decode("utf-8")
    if scheme != "dpapi":
        raise ValueError("unknown secret format: %r" % scheme)
    if not IS_WINDOWS:
        raise ValueError("DPAPI secrets can only be read on Windows")

    out = _Blob()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(_Blob.of(raw)), None, ctypes.byref(_Blob.of(_ENTROPY)),
        None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError(ctypes.get_last_error(),
                      "CryptUnprotectData failed (wrong Windows user?)")
    try:
        return out.value().decode("utf-8")
    finally:
        _kernel32.LocalFree(out.pbData)
