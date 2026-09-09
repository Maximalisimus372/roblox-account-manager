"""Make a password-protected archive of the built exe, one per buyer.

Google Drive gives a file one link for everyone, so the individual part is
the password: the link is shared once, and each buyer gets their own AES-256
password. Without it the archive is useless, and because every buyer's
password is different, a leaked build points back to whoever it was sold to.

Usage:
    python make_release.py <order-id>          # e.g. an order number
    python make_release.py <order-id> --exe path\to\other.exe

Each run writes releases\<order-id>\RobloxAccountManager.zip and appends the
order and its password to releases\passwords.csv. Keep that file to yourself.
"""

import argparse
import csv
import os
import secrets
import string
import sys
import time

import pyzipper

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXE = os.path.join(HERE, "dist", "RobloxAccountManager.exe")
RELEASES = os.path.join(HERE, "releases")
LEDGER = os.path.join(RELEASES, "passwords.csv")
ALPHABET = string.ascii_letters + string.digits


def make_password(length=14):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def build(order_id, exe_path):
    if not os.path.exists(exe_path):
        sys.exit("exe not found: %s\nBuild it first: "
                 "python -m PyInstaller RobloxAccountManager.spec" % exe_path)

    order_dir = os.path.join(RELEASES, order_id)
    os.makedirs(order_dir, exist_ok=True)
    archive = os.path.join(order_dir, "RobloxAccountManager.zip")
    password = make_password()

    with pyzipper.AESZipFile(archive, "w", compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.write(exe_path, arcname="RobloxAccountManager.exe")
        readme = ("Roblox Account Manager\r\n\r\n"
                  "Order: %s\r\n"
                  "Unzip with the password you were given, then run "
                  "RobloxAccountManager.exe.\r\n" % order_id)
        zf.writestr("READ ME.txt", readme)

    os.makedirs(RELEASES, exist_ok=True)
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["order", "password", "created"])
        writer.writerow([order_id, password,
                         time.strftime("%Y-%m-%d %H:%M:%S")])

    print("Archive : %s" % archive)
    print("Password: %s" % password)
    print("\nGive the buyer the Google Drive link + this password.")
    print("The order and password are saved in %s" % LEDGER)


def main():
    parser = argparse.ArgumentParser(description="Make a per-buyer release.")
    parser.add_argument("order_id", help="order number or buyer tag")
    parser.add_argument("--exe", default=DEFAULT_EXE,
                        help="path to the exe (default: dist build)")
    args = parser.parse_args()
    build(args.order_id.strip(), args.exe)


if __name__ == "__main__":
    main()
