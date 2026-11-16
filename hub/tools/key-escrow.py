#!/usr/bin/env python3
"""Split HUB_DATA_KEY into shares for separate custodians, and rebuild it from enough of them (Shamir secret sharing over GF(256), standard library only).

Why: a lost HUB_DATA_KEY cannot be recovered and every encrypted item in every backup becomes unreadable. A single copy in one keychain is a single point of
failure; handing the whole key to a second person is a second point of exposure. With a threshold such as 2 of 3, any two custodians can rebuild the key and
one custodian alone learns nothing about it.

  python3 tools/key-escrow.py split --threshold 2 --shares 3      # reads the key from the HUB_DATA_KEY environment variable or a hidden prompt
  python3 tools/key-escrow.py combine SHARE SHARE                  # prints the key; with no arguments, reads shares from stdin, one per line
  python3 tools/key-escrow.py fingerprint                          # prints the key's short fingerprint (the key itself is not shown)

Every share carries the key's fingerprint, so `combine` states whether the rebuilt key is the right one, and a short checksum that catches a mistyped share.
The key is never passed on the command line (it would be kept in shell history and visible to other users of the machine)."""
import argparse, getpass, hashlib, os, secrets, sys

PREFIX = "HUBKEY1"
_EXP, _LOG = [0] * 512, [0] * 256


def _tables():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x ^= (x << 1) ^ (0x11B if x & 0x80 else 0)      # multiply by the generator 3 in GF(2^8), reduced by x^8+x^4+x^3+x+1
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_tables()


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _div(a, b):
    if b == 0:
        raise ZeroDivisionError
    return 0 if a == 0 else _EXP[(_LOG[a] - _LOG[b]) % 255]


def fingerprint(secret: bytes) -> str:
    return hashlib.sha256(secret).hexdigest()[:8]


def _check(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()[:4]


def split(secret: bytes, threshold: int, shares: int) -> list:
    if not secret:
        raise ValueError("The key is empty")
    if not (2 <= threshold <= shares <= 255):
        raise ValueError("Use 2 <= threshold <= shares <= 255")
    ys = [bytearray() for _ in range(shares)]
    for byte in secret:
        coef = [byte] + [secrets.randbelow(256) for _ in range(threshold - 1)]
        for x in range(1, shares + 1):
            y = 0
            for c in reversed(coef):                      # Horner evaluation of the polynomial at x
                y = _mul(y, x) ^ c
            ys[x - 1].append(y)
    fp, out = fingerprint(secret), []
    for x in range(1, shares + 1):
        body = f"{PREFIX}-{threshold}-{x}-{fp}-{bytes(ys[x - 1]).hex()}"
        out.append(f"{body}-{_check(body)}")
    return out


def _parse(share: str):
    parts = share.strip().split("-")
    if len(parts) != 6 or parts[0] != PREFIX:
        raise ValueError("Not a Faculty Hub key share")
    body, check = "-".join(parts[:5]), parts[5]
    if _check(body) != check:
        raise ValueError("A share was mistyped (its checksum does not match): " + share.strip()[:20] + "...")
    try:
        return int(parts[1]), int(parts[2]), parts[3], bytes.fromhex(parts[4])
    except ValueError:
        raise ValueError("A share could not be read")


def combine(share_list: list) -> bytes:
    parsed = [_parse(s) for s in share_list if s.strip()]
    if not parsed:
        raise ValueError("No shares given")
    k, fp, length = parsed[0][0], parsed[0][2], len(parsed[0][3])
    if any(p[0] != k or p[2] != fp or len(p[3]) != length for p in parsed):
        raise ValueError("These shares belong to different keys")
    uniq = {}
    for _, x, _, y in parsed:
        uniq[x] = y
    if len(uniq) < k:
        raise ValueError(f"Need {k} different shares; {len(uniq)} given")
    xs = sorted(uniq)[:k]
    out = bytearray()
    for i in range(length):
        total = 0
        for xi in xs:
            num = den = 1
            for xj in xs:
                if xj != xi:
                    num, den = _mul(num, xj), _mul(den, xi ^ xj)
            total ^= _mul(uniq[xi][i], _div(num, den))      # Lagrange interpolation at x = 0
        out.append(total)
    if fingerprint(bytes(out)) != fp:
        raise ValueError("The shares do not rebuild the key (wrong or damaged shares)")
    return bytes(out)


def _read_key() -> bytes:
    v = os.environ.get("HUB_DATA_KEY") or getpass.getpass("HUB_DATA_KEY (hidden): ")
    return v.strip().encode()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("split"); sp.add_argument("--threshold", type=int, required=True); sp.add_argument("--shares", type=int, required=True)
    cp = sub.add_parser("combine"); cp.add_argument("shares", nargs="*")
    sub.add_parser("fingerprint")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "split":
            key = _read_key()
            for i, sh in enumerate(split(key, a.threshold, a.shares), 1):
                print(f"share {i} of {a.shares}: {sh}")
            print(f"key fingerprint {fingerprint(key)}; any {a.threshold} shares rebuild it. Give each share to a different custodian and store none of them beside the backups.", file=sys.stderr)
        elif a.cmd == "combine":
            shares = a.shares or [l for l in sys.stdin.read().splitlines() if l.strip()]
            shares = [s.split(":")[-1].strip() for s in shares]          # accept the "share 1 of 3: HUBKEY1-..." line as printed
            key = combine(shares)
            print(key.decode())
            print(f"rebuilt; fingerprint {fingerprint(key)} matches the one in the shares", file=sys.stderr)
        else:
            print(fingerprint(_read_key()))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
