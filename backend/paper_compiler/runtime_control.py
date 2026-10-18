"""Persistent release controls, independent of generated-program execution.

The caller validates executable code before promotion and authenticates operators
before explicit rollback. This module owns only atomic activation and its audit
trail; it never changes a candidate directory or runs a refinement loop.
"""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3


class RuntimeFrozen(RuntimeError):
    """Automatic activation is disabled by the current freeze setting."""


class VersionConflict(RuntimeError):
    """Activation preconditions no longer match, or a version is not eligible."""


def _nonempty_string(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _reject_json_constant(_value):
    raise ValueError("Package metadata must contain valid JSON")


class RuntimeControl:
    """SQLite-backed freeze state and compare-and-swap release activation.

    Use a dedicated root under /data/runtime in deployment. Every public
    operation opens its own connection, so instances can be shared across
    threads and independent host processes.
    """

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path = self.root / "runtime-control.sqlite3"
        try:
            descriptor = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        with self._transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS runtime_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                freeze INTEGER NOT NULL CHECK (freeze IN (0, 1)),
                generation INTEGER NOT NULL CHECK (generation >= 0),
                active_version TEXT, active_path TEXT
            )""")
            connection.execute("""INSERT OR IGNORE INTO runtime_state
                (id, freeze, generation, active_version, active_path)
                VALUES (1, 0, 0, NULL, NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS runtime_versions (
                version_id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE,
                promoted_at TEXT NOT NULL
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS runtime_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
                generation INTEGER NOT NULL, freeze INTEGER NOT NULL,
                from_version TEXT, to_version TEXT, active_path TEXT
            )""")

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _transaction(self):
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _snapshot(connection):
        row = connection.execute("""SELECT freeze, generation, active_version,
            active_path FROM runtime_state WHERE id = 1""").fetchone()
        return {"freeze": bool(row["freeze"]), "generation": row["generation"],
                "active_version": row["active_version"], "active_path": row["active_path"]}

    def snapshot(self) -> dict:
        with closing(self._connect()) as connection:
            return self._snapshot(connection)

    @staticmethod
    def _event(connection, action, actor, previous, current):
        connection.execute("""INSERT INTO runtime_events
            (action, actor, created_at, generation, freeze, from_version, to_version, active_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                action, actor, datetime.now(timezone.utc).isoformat(),
                current["generation"], int(current["freeze"]),
                previous["active_version"], current["active_version"], current["active_path"],
            ))

    def set_freeze(self, value: bool, *, actor="system") -> dict:
        if type(value) is not bool:
            raise TypeError("freeze must be a boolean")
        _nonempty_string(actor, "actor")
        with self._transaction() as connection:
            previous = self._snapshot(connection)
            if previous["freeze"] == value:
                return previous
            connection.execute("""UPDATE runtime_state SET freeze = ?,
                generation = generation + 1 WHERE id = 1""", (int(value),))
            current = self._snapshot(connection)
            self._event(connection, "set_freeze", actor, previous, current)
            return current

    @staticmethod
    def _candidate_path(candidate_path, version_id):
        try:
            folder = Path(candidate_path).resolve(strict=True)
            if not folder.is_dir():
                raise ValueError("Candidate package directory is unavailable")
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"),
                                  parse_constant=_reject_json_constant)
            validation = json.loads((folder / "validation.json").read_text(encoding="utf-8"),
                                    parse_constant=_reject_json_constant)
        except (OSError, UnicodeError, ValueError):
            raise ValueError("Candidate package metadata is missing or invalid") from None
        if not isinstance(manifest, dict) or manifest.get("version_id") != version_id:
            raise ValueError("Candidate manifest version does not match")
        if not isinstance(validation, dict) or validation.get("status") != "passed":
            raise ValueError("Candidate validation has not passed")
        return str(folder)

    def promote(self, version_id: str, candidate_path: Path, expected_version: str | None,
                *, expected_generation: int | None = None, actor="system") -> dict:
        _nonempty_string(version_id, "version_id")
        _nonempty_string(actor, "actor")
        if expected_version is not None:
            _nonempty_string(expected_version, "expected_version")
        if expected_generation is not None:
            if type(expected_generation) is not int:
                raise TypeError("expected_generation must be an integer")
            if expected_generation < 0:
                raise ValueError("expected_generation must not be negative")
        with self._transaction() as connection:
            previous = self._snapshot(connection)
            if previous["freeze"]:
                raise RuntimeFrozen("Runtime is frozen; automatic promotion is disabled")
            if previous["active_version"] != expected_version:
                raise VersionConflict("Active version changed before promotion")
            if expected_generation is not None and previous["generation"] != expected_generation:
                raise VersionConflict("Runtime generation changed before promotion")
            folder = self._candidate_path(candidate_path, version_id)
            if connection.execute("SELECT 1 FROM runtime_versions WHERE version_id = ? OR path = ?",
                                  (version_id, folder)).fetchone():
                raise VersionConflict("Version or package path is already registered; use rollback")
            connection.execute("""INSERT INTO runtime_versions (version_id, path, promoted_at)
                VALUES (?, ?, ?)""", (version_id, folder, datetime.now(timezone.utc).isoformat()))
            connection.execute("""UPDATE runtime_state SET active_version = ?, active_path = ?,
                generation = generation + 1 WHERE id = 1""", (version_id, folder))
            current = self._snapshot(connection)
            self._event(connection, "promote", actor, previous, current)
            return current

    def rollback(self, target_version: str, *, actor="system") -> dict:
        """Activate a promoted historical version, including while frozen.

        Authorization is the calling application's responsibility. Unlike
        promote(), this is an explicit operator action and never unfreezes.
        """
        _nonempty_string(target_version, "target_version")
        _nonempty_string(actor, "actor")
        with self._transaction() as connection:
            previous = self._snapshot(connection)
            target = connection.execute("SELECT path FROM runtime_versions WHERE version_id = ?",
                                        (target_version,)).fetchone()
            if target is None:
                raise VersionConflict("Rollback target has not been promoted")
            if not Path(target["path"]).is_dir():
                raise ValueError("Rollback package directory is unavailable")
            connection.execute("""UPDATE runtime_state SET active_version = ?, active_path = ?,
                generation = generation + 1 WHERE id = 1""", (target_version, target["path"]))
            current = self._snapshot(connection)
            self._event(connection, "rollback", actor, previous, current)
            return current

    def events(self) -> list:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM runtime_events ORDER BY id").fetchall()
            return [{**dict(row), "freeze": bool(row["freeze"])} for row in rows]
