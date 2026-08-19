# ============================================================================
# FILE: migrate_beta_db.py
# PATH: backend/scripts/migrate_beta_db.py
# PURPOSE: One-time migration of the beta Firestore database
#          (aerosafety-sms-prod / sms-db-beta) into the isolated beta project
#          (gap-analysis-ssp / sms-db-beta). Walks every top-level collection
#          recursively (including nested subcollections) and copies documents
#          verbatim (same document ids), preserving timestamps and field types.
#
#   - Reads  : paginated (orderBy __name__ + start_after) in small chunks so a
#              single gRPC stream never exceeds the backend deadline.
#   - Writes : batched (up to 500 ops per Firestore batch commit).
#   - Safety : each read/write is retried a few times; any document that still
#              fails is logged to a failures file (never silently dropped).
#
# Usage (from backend/):
#   python scripts/migrate_beta_db.py --dry-run
#   python scripts/migrate_beta_db.py                # live migration
#   python scripts/migrate_beta_db.py --verify       # count + checksum audit
#
# Service-account key files come from env or CLI args and are never committed
# (see .gitignore '*-sa.json').
# ============================================================================

import argparse
import hashlib
import json
import os
import sys
import time

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore as fb_firestore

DEFAULT_DB = "sms-db-beta"
CHUNK = 300
BATCH_OPS = 500
MAX_TRIES = 5
FAILURES_LOG = "migration_failures.log"


def _cert(path: str):
    if not path or not os.path.exists(path):
        sys.exit(f"ERROR: service-account key not found: {path!r}")
    return credentials.Certificate(path)


def _run(fn):
    for attempt in range(1, MAX_TRIES + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - keep going on transient 503/504s
            if attempt == MAX_TRIES:
                raise
            wait = 2 * attempt
            print(f"  ... transient {type(exc).__name__}; retry {attempt}/{MAX_TRIES} in {wait}s",
                  flush=True)
            time.sleep(wait)


def iter_docs(ref):
    last = None
    while True:
        query = ref.order_by("__name__").limit(CHUNK)
        if last is not None:
            query = query.start_after(last)
        docs = _run(query.get)
        if not docs:
            return
        for doc in docs:
            yield doc
        last = docs[-1]


class BatchWriter:
    """Accumulates writes and commits them in Firestore batches (<= 500 ops)."""

    def __init__(self, dst_db):
        self.dst_db = dst_db
        self.batch = dst_db.batch()
        self.size = 0
        self.total = 0
        self.failed = []  # [(path, error)]

    def add(self, col_path, doc_id, data):
        ref = self.dst_db.collection(col_path).document(doc_id)
        self.batch.set(ref, data, merge=False)
        self.size += 1
        self.total += 1
        if self.size >= BATCH_OPS:
            self.flush()

    def flush(self):
        if self.size == 0:
            return
        pending = self.batch
        ops = self.size
        self.batch = self.dst_db.batch()
        self.size = 0
        try:
            _run(pending.commit)
        except Exception as exc:  # noqa: BLE001
            # Batch-level failure: fall back to per-document writes so one bad
            # doc can't silently drop the whole batch.
            print(f"  batch commit failed ({type(exc).__name__}); retrying {ops} docs individually",
                  flush=True)
            for path, doc_id, data in _iter_batch_ops(pending):
                try:
                    _run(lambda: self.dst_db.collection(path).document(doc_id).set(data, merge=False))
                except Exception as e2:  # noqa: BLE001
                    self.failed.append((f"{path}/{doc_id}", f"{type(e2).__name__}: {e2}"))
                    print(f"  FAILED {path}/{doc_id}: {type(e2).__name__}", flush=True)
        if self.total % 200 < ops:
            print(f"  ... {self.total} documents written", flush=True)

    def close(self):
        self.flush()
        return self.total, self.failed


def _iter_batch_ops(batch):
    for wr in batch._writes:  # internal: name + document
        name = wr.document.name
        # name like projects/<p>/databases/<db>/documents/<path>
        parts = name.split("/documents/")[1].split("/")
        col_path = "/".join(parts[0::2])
        doc_id = parts[1] if len(parts) > 1 else ""
        data = wr.document.fields or {}
        yield col_path, doc_id, data


def migrate_collection(src_db, writer, col_path: str, dry_run: bool) -> int:
    ref = src_db.collection(col_path)
    count = 0
    for doc in iter_docs(ref):
        data = doc.to_dict()
        if not dry_run:
            writer.add(col_path, doc.id, data)
        for sub in _run(doc.reference.collections) or []:
            count += migrate_collection(src_db, writer, f"{col_path}/{doc.id}/{sub.id}", dry_run)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Verification: count + checksum comparison between source and destination.
# ---------------------------------------------------------------------------

def _checksum(data):
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot(db, label):
    index = {}  # path -> checksum
    seen = 0

    def walk(col_path):
        nonlocal seen
        for doc in iter_docs(db.collection(col_path)):
            key = f"{col_path}/{doc.id}"
            index[key] = _checksum(doc.to_dict() or {})
            seen += 1
            if seen % 100 == 0:
                print(f"  {label}: {seen} docs indexed ...", flush=True)
            for sub in _run(doc.reference.collections) or []:
                walk(f"{col_path}/{doc.id}/{sub.id}")

    for col in _run(db.collections) or []:
        walk(col.id)
    print(f"  {label}: {seen} documents indexed (done)", flush=True)
    return index


def verify(src_db, dst_db):
    print("Snapshotting source ...", flush=True)
    src = snapshot(src_db, "source")
    print(f"  source: {len(src)} documents", flush=True)
    print("Snapshotting destination ...", flush=True)
    dst = snapshot(dst_db, "destination")
    print(f"  destination: {len(dst)} documents", flush=True)

    missing = sorted(set(src) - set(dst))
    extra = sorted(set(dst) - set(src))
    mismatched = sorted(k for k in set(src) & set(dst) if src[k] != dst[k])

    print("\n== Verification ==")
    print(f"Source      : {len(src)} docs")
    print(f"Destination : {len(dst)} docs")
    print(f"Missing     : {len(missing)}")
    for p in missing[:20]:
        print(f"  - {p}")
    print(f"Extra       : {len(extra)}")
    for p in extra[:20]:
        print(f"  - {p}")
    print(f"Checksum mismatch: {len(mismatched)}")
    for p in mismatched[:20]:
        print(f"  ~ {p}")
    ok = not missing and not extra and not mismatched
    print(f"\nRESULT: {'VERIFIED — source and destination match exactly' if ok else 'MISMATCH FOUND'}")
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Migrate sms-db-beta between Firebase projects.")
    parser.add_argument("--src-key", default=os.environ.get("SRC_SA_KEY", "aerosafety-sms-prod-sa.json"),
                        help="Source project service-account key (aerosafety-sms-prod).")
    parser.add_argument("--dst-key", default=os.environ.get("DST_SA_KEY", "gap-analysis-ssp-sa.json"),
                        help="Destination project service-account key (gap-analysis-ssp).")
    parser.add_argument("--database", default=DEFAULT_DB, help="Database id to migrate.")
    parser.add_argument("--dry-run", action="store_true", help="Count documents only.")
    parser.add_argument("--verify", action="store_true",
                        help="Compare source vs destination (count + checksum) instead of migrating.")
    args = parser.parse_args(argv)

    src_cred = _cert(args.src_key)
    dst_cred = _cert(args.dst_key)

    src_app = firebase_admin.initialize_app(src_cred, name="src",
                                            options={"projectId": src_cred.project_id})
    dst_app = firebase_admin.initialize_app(dst_cred, name="dst",
                                            options={"projectId": dst_cred.project_id})
    src_db = fb_firestore.client(app=src_app, database_id=args.database)
    dst_db = fb_firestore.client(app=dst_app, database_id=args.database)

    if args.verify:
        return 0 if verify(src_db, dst_db) else 1

    print(f"Source      : {src_cred.project_id} / {args.database}")
    print(f"Destination : {dst_cred.project_id} / {args.database}")

    writer = BatchWriter(dst_db)
    total = 0
    for col in _run(src_db.collections) or []:
        path = col.id
        n = migrate_collection(src_db, writer, path, args.dry_run)
        total += n
        print(f"{'[DRY-RUN]' if args.dry_run else '[copied]'} {path}: {n} docs", flush=True)

    written, failed = (0, []) if args.dry_run else writer.close()

    if not args.dry_run and failed:
        with open(FAILURES_LOG, "w", encoding="utf-8") as fh:
            for path, err in failed:
                fh.write(f"{path}\t{err}\n")
        print(f"\nFAILURES: {len(failed)} document(s) could not be written "
              f"(logged to {FAILURES_LOG})", flush=True)

    if args.dry_run:
        print(f"\nDry-run total: {total}")
    else:
        print(f"\nMigrated: {written} documents (source total {total})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
