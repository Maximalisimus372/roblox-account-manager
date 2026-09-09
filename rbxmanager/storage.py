"""The account list on disk.

Kept in %LOCALAPPDATA%/RobloxAccountManager/accounts.json — the cookie of
each account is encrypted, everything else is plain so the file stays readable.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from . import crypto


def data_dir() -> str:
    base = (os.environ.get("LOCALAPPDATA")
            or os.path.join(os.path.expanduser("~"), ".local", "share"))
    path = os.path.join(base, "RobloxAccountManager")
    os.makedirs(path, exist_ok=True)
    return path


def load_settings() -> dict:
    """Window size, last place ID and so on. Never fails, just returns {}."""
    path = os.path.join(data_dir(), "settings.json")
    try:
        # utf-8-sig: a file someone edited in a Windows editor may carry a BOM.
        with open(path, "r", encoding="utf-8-sig") as handle:
            settings = json.load(handle)
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    path = os.path.join(data_dir(), "settings.json")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
    except OSError:
        pass


@dataclass
class Account:
    username: str
    user_id: int
    cookie_enc: str
    alias: str = ""
    note: str = ""
    display_name: str = ""
    profile_dir: str = ""
    added: float = field(default_factory=time.time)
    last_used: Optional[float] = None
    last_status: str = ""

    @property
    def label(self) -> str:
        return self.alias or self.username

    @property
    def cookie(self) -> str:
        return crypto.decrypt(self.cookie_enc)

    def set_cookie(self, value: str) -> None:
        self.cookie_enc = crypto.encrypt(value)


class Store:
    def __init__(self, path: str = None):
        self.path = path or os.path.join(data_dir(), "accounts.json")
        self.accounts: List[Account] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self.accounts = []
            return
        with open(self.path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        known = {f for f in Account.__dataclass_fields__}
        self.accounts = [Account(**{k: v for k, v in entry.items() if k in known})
                         for entry in raw.get("accounts", [])]

    def save(self) -> None:
        payload = {"version": 1,
                   "accounts": [asdict(a) for a in self.accounts]}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp, self.path)

    def find(self, user_id: int) -> Optional[Account]:
        return next((a for a in self.accounts if a.user_id == user_id), None)

    def add_or_update(self, account: Account) -> Account:
        existing = self.find(account.user_id)
        if existing:
            existing.username = account.username
            existing.display_name = account.display_name
            existing.cookie_enc = account.cookie_enc
            existing.last_status = account.last_status
            if account.alias:
                existing.alias = account.alias
            if account.profile_dir:
                existing.profile_dir = account.profile_dir
            self.save()
            return existing
        self.accounts.append(account)
        self.save()
        return account

    def remove(self, user_id: int) -> None:
        self.accounts = [a for a in self.accounts if a.user_id != user_id]
        self.save()
