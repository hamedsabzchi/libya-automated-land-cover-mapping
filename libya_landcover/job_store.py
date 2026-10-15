"""Single-owner local job ledger. Requires a filesystem with SQLite/flock support."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .bundle import canonical_uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class JobConflict(ValueError):
    """An existing identity has different inputs or a stale revision."""


class JobStore:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "jobs.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, request_key TEXT UNIQUE NOT NULL,
                    fingerprint TEXT NOT NULL, revision INTEGER NOT NULL, state TEXT NOT NULL,
                    document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    record_id TEXT NOT NULL, revision INTEGER NOT NULL, document TEXT NOT NULL,
                    PRIMARY KEY(record_id, revision)
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        try:
            db.execute("PRAGMA synchronous=FULL")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def lock(self, name):
        import fcntl
        if not name.replace("-", "").isalnum():
            raise ValueError("Invalid lock name")
        with (self.root / (name + ".lock")).open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise JobConflict("Another process is handling this work") from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def create(self, kind, request_key, inputs, *, state="queued", extra=None):
        fingerprint = hashlib.sha256(encoded(inputs).encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fingerprint,document FROM records WHERE request_key=?", (request_key,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise JobConflict("Idempotency key already has different inputs")
                return json.loads(row[1])
            timestamp = now()
            record = {"schema_version": "wp05.1", "job_id": str(uuid4()), "kind": kind,
                      "request_key": request_key, "fingerprint": fingerprint, "revision": 0,
                      "state": state, "created_at": timestamp, "updated_at": timestamp,
                      "inputs": inputs, "error": None, **(extra or {})}
            document = encoded(record)
            db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (
                record["job_id"], kind, request_key, fingerprint, 0, state, document))
            db.execute("INSERT INTO events VALUES (?,?,?)", (record["job_id"], 0, document))
            return record

    def get(self, job_id):
        canonical_uuid(job_id)
        with self.connect() as db:
            row = db.execute("SELECT document FROM records WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown job")
        return json.loads(row[0])

    def update(self, record, **changes):
        if set(changes) & {"job_id", "kind", "inputs", "request_key", "fingerprint", "revision", "created_at"}:
            raise ValueError("Job identity and inputs are immutable")
        updated = {**record, **changes, "revision": record["revision"] + 1, "updated_at": now()}
        document = encoded(updated)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("UPDATE records SET revision=?,state=?,document=? WHERE id=? AND revision=?",
                                (updated["revision"], updated["state"], document, record["job_id"], record["revision"]))
            if cursor.rowcount != 1:
                raise JobConflict("Job revision changed; reload before updating")
            db.execute("INSERT INTO events VALUES (?,?,?)", (updated["job_id"], updated["revision"], document))
        return updated

    def list(self, *, kind=None, state=None):
        query, params = "SELECT document FROM records WHERE 1=1", []
        for column, value in (("kind", kind), ("state", state)):
            if value is not None:
                query += " AND " + column + "=?"
                params.append(value)
        with self.connect() as db:
            rows = db.execute(query + " ORDER BY rowid", params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def events(self, job_id):
        self.get(job_id)
        with self.connect() as db:
            rows = db.execute("SELECT document FROM events WHERE record_id=? ORDER BY revision", (job_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def folder(self, job_id):
        canonical_uuid(job_id)
        return self.root / "jobs" / job_id

    def snapshot(self, destination):
        """Consistent database backup; callers must also retain jobs/ graph files."""
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError("Backup destination exists")
        with self.connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
