"""Pure private account ownership for MinerU; no transport or cache writes.

Select once for a new PDF task, persist account_id as account_sha in pending
state, and keep the returned frozen account for every request/retry/download.
Completed raw layouts are content-addressed independently of this pool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
import re
import stat
from typing import Iterable

_POOL_FORMAT = "mineru-private-key-pool-v1"
_MAX_FILE_BYTES = 256 * 1024
_MAX_TOKEN_BYTES = 16 * 1024
_OWNER_PATTERN = re.compile(r"[0-9a-f]{64}")
_MESSAGES = {
    "pool_invalid": "MinerU private account pool is invalid",
    "pool_unavailable": "MinerU private account pool is unavailable",
    "pool_permissions": "MinerU private account pool permissions are not private",
    "legacy_invalid": "MinerU legacy account configuration is invalid",
    "legacy_unavailable": "MinerU legacy account configuration is unavailable",
    "legacy_permissions": "MinerU legacy account permissions are not private",
    "legacy_missing": "MinerU legacy account is missing from the account pool",
    "owner_invalid": "MinerU pending account identity is invalid",
    "owner_missing": "MinerU pending account is missing from the configured pool",
    "pdf_identity_invalid": "MinerU PDF task identity is invalid",
}


class MinerUAccountPoolError(ValueError):
    """Bounded structural error; never retain a private input or path."""

    def __init__(self, reason_code: str):
        safe = reason_code if type(reason_code) is str and reason_code in _MESSAGES else "pool_invalid"
        self.reason_code = safe
        self.diagnostics = {"reason_code": safe}
        super().__init__(_MESSAGES[safe])


def _secret(value: str, reason_code: str = "pool_invalid") -> str:
    if type(value) is not str:
        raise MinerUAccountPoolError(reason_code)
    token = value.strip()
    if (not token or len(token) > _MAX_TOKEN_BYTES
            or any(not 33 <= ord(char) <= 126 for char in token)):
        raise MinerUAccountPoolError(reason_code)
    return token


@dataclass(frozen=True, slots=True)
class MinerUAccount:
    token: str = field(repr=False, compare=False)
    account_id: str = field(init=False)

    def __post_init__(self):
        token = _secret(self.token)
        object.__setattr__(self, "token", token)
        # Compatible with existing TaskState.account_sha records.
        object.__setattr__(self, "account_id", sha256(token.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class MinerUAccountPool:
    accounts: tuple[MinerUAccount, ...] = field(repr=False)
    legacy_account: MinerUAccount = field(repr=False)

    def __post_init__(self):
        if (type(self.accounts) is not tuple or not self.accounts
                or not all(type(a) is MinerUAccount for a in self.accounts)
                or len({a.account_id for a in self.accounts}) != len(self.accounts)):
            raise MinerUAccountPoolError("pool_invalid")
        if (type(self.legacy_account) is not MinerUAccount
                or self.legacy_account.account_id not in {a.account_id for a in self.accounts}):
            raise MinerUAccountPoolError("legacy_missing")

    def __repr__(self) -> str:
        return f"MinerUAccountPool(account_count={len(self.accounts)})"

    @classmethod
    def from_tokens(cls, tokens: Iterable[str], *, legacy_token: str | None = None) -> MinerUAccountPool:
        if isinstance(tokens, (str, bytes)):
            raise MinerUAccountPoolError("pool_invalid")
        iterator = None
        try:
            iterator = iter(tokens)
        except Exception:
            pass
        if iterator is None:
            raise MinerUAccountPoolError("pool_invalid")
        accounts = []
        seen = set()
        iteration_failed = False
        try:
            for value in iterator:
                account = MinerUAccount(value)
                if account.account_id not in seen:
                    seen.add(account.account_id)
                    accounts.append(account)
                if len(accounts) > 128:
                    raise MinerUAccountPoolError("pool_invalid")
        except MinerUAccountPoolError:
            raise
        except Exception:
            iteration_failed = True
        if iteration_failed:
            raise MinerUAccountPoolError("pool_invalid")
        if not accounts:
            raise MinerUAccountPoolError("pool_invalid")
        legacy = accounts[0]
        if legacy_token is not None:
            account_id = sha256(_secret(legacy_token, "legacy_invalid").encode("utf-8")).hexdigest()
            match = next((a for a in accounts if a.account_id == account_id), None)
            if match is None:
                raise MinerUAccountPoolError("legacy_missing")
            legacy = match
        return cls(tuple(accounts), legacy)

    def diagnostics(self) -> dict[str, str | int]:
        return {"account_count": len(self.accounts),
                "legacy_account_id": self.legacy_account.account_id}

    def select_for_pdf(self, pdf_identity: str | bytes) -> MinerUAccount:
        """Order-independent rendezvous hashing distributes new PDF tasks."""
        if type(pdf_identity) is str:
            if (not pdf_identity or len(pdf_identity) > 4096
                    or any(ord(char) < 32 or ord(char) == 127 for char in pdf_identity)):
                raise MinerUAccountPoolError("pdf_identity_invalid")
            identity = None
            try:
                identity = pdf_identity.encode("utf-8")
            except UnicodeError:
                pass
            if identity is None:
                raise MinerUAccountPoolError("pdf_identity_invalid")
        elif type(pdf_identity) is bytes and pdf_identity:
            identity = pdf_identity
        else:
            raise MinerUAccountPoolError("pdf_identity_invalid")
        digest = sha256(identity).digest()
        return max(self.accounts, key=lambda account: (
            sha256(b"mineru-account-assignment-v1\0" + digest
                   + bytes.fromhex(account.account_id)).digest(),
            account.account_id))

    def resolve_pending_owner(self, owner_id: str | None) -> MinerUAccount:
        """None denotes a legacy unmarked task; a missing marked owner fails."""
        if owner_id is None:
            return self.legacy_account
        if type(owner_id) is not str or _OWNER_PATTERN.fullmatch(owner_id) is None:
            raise MinerUAccountPoolError("owner_invalid")
        for account in self.accounts:
            if account.account_id == owner_id:
                return account
        raise MinerUAccountPoolError("owner_missing")

    def bind_task(self, pdf_identity: str | bytes, *,
                  pending_owner_id: str | None = None,
                  legacy_unmarked: bool = False) -> MinerUAccount:
        """Return one immutable account to retain throughout the task."""
        if pending_owner_id is not None:
            return self.resolve_pending_owner(pending_owner_id)
        if legacy_unmarked:
            return self.resolve_pending_owner(None)
        return self.select_for_pdf(pdf_identity)


def _private_text(path: str | os.PathLike[str], prefix: str) -> str:
    """Read one bounded regular private file, rejecting links and unsafe modes."""
    descriptor = None
    failed = None
    payload = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            failed = prefix + "_unavailable"
        elif os.name == "posix" and (
                stat.S_IMODE(details.st_mode) not in {0o400, 0o600}
                or details.st_uid != os.geteuid()):
            failed = prefix + "_permissions"
        elif details.st_size > _MAX_FILE_BYTES:
            failed = prefix + "_invalid"
        else:
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None
                payload = stream.read(_MAX_FILE_BYTES + 1)
            if len(payload) > _MAX_FILE_BYTES:
                failed = prefix + "_invalid"
    except Exception:
        failed = prefix + "_unavailable"
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    if failed:
        raise MinerUAccountPoolError(failed)
    text = None
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        pass
    if text is None:
        raise MinerUAccountPoolError(prefix + "_invalid")
    return text


def _unique_fields(pairs):
    record = {}
    for name, value in pairs:
        if name in record:
            raise ValueError("Duplicate private pool field")
        record[name] = value
    return record


def load_account_pool(pool_path: str | os.PathLike[str] | None, *,
                      legacy_token_path: str | os.PathLike[str] | None = None) -> MinerUAccountPool:
    """Load strict format/keys JSON, or an explicitly requested legacy-only file.

    A configured bad pool never falls back to another account. Reading the
    legacy file pins unmarked pending tasks even if the JSON order changes.
    Private file contents and paths are excluded from exceptions and reprs.
    """
    legacy = (_secret(_private_text(legacy_token_path, "legacy"), "legacy_invalid")
              if legacy_token_path is not None else None)
    if pool_path is None:
        if legacy is None:
            raise MinerUAccountPoolError("pool_unavailable")
        return MinerUAccountPool.from_tokens([legacy], legacy_token=legacy)
    text = _private_text(pool_path, "pool")
    parsed = False
    try:
        record = json.loads(text, object_pairs_hook=_unique_fields)
        parsed = True
    except (ValueError, TypeError, RecursionError):
        pass
    if not parsed:
        raise MinerUAccountPoolError("pool_invalid")
    if (type(record) is not dict or set(record) != {"format", "keys"}
            or record["format"] != _POOL_FORMAT or type(record["keys"]) is not list):
        raise MinerUAccountPoolError("pool_invalid")
    return MinerUAccountPool.from_tokens(record["keys"], legacy_token=legacy)
