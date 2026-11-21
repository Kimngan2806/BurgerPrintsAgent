"""Persist the last successful BurgerPrints catalog independently of Render's filesystem."""

import gzip
import hashlib
import io
import json

from core.config import settings
from core.workspace import workspace

FORMAT_VERSION = 1
COLLECTIONS = ('products', 'skus', 'providers')
BATCH_SIZE = 1000


def enabled():
    return workspace.backend == 'postgresql' and bool(settings.BURGERPRINTS_API_KEY)


def _source():
    # An API key change can select a different store or price list.
    credentials = f'{settings.BURGERPRINTS_API_BASE_URL.rstrip("/")}\0{settings.BURGERPRINTS_API_KEY}'
    return hashlib.sha256(credentials.encode('utf-8')).hexdigest()


def save(fetched_at, catalog):
    compressed = io.BytesIO()
    # Encode in batches to avoid allocating a second full copy of the catalog as JSON.
    with gzip.GzipFile(fileobj=compressed, mode='wb', compresslevel=3, mtime=0) as archive:
        for name, rows in zip(COLLECTIONS, catalog, strict=True):
            for offset in range(0, len(rows), BATCH_SIZE):
                batch = json.dumps((name, rows[offset:offset + BATCH_SIZE]), separators=(',', ':'))
                archive.write(batch.encode('utf-8') + b'\n')

    with workspace.connect() as db:
        source = _source()
        saved = db.execute("""
            INSERT INTO catalog_snapshots (source, format_version, fetched_at, payload)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (source, format_version) DO UPDATE
            SET fetched_at = excluded.fetched_at, payload = excluded.payload
            WHERE catalog_snapshots.fetched_at <= excluded.fetched_at
            RETURNING fetched_at
        """, (source, FORMAT_VERSION, fetched_at, compressed.getvalue())).fetchone()
        if saved is None:
            saved = db.execute("""
                SELECT fetched_at FROM catalog_snapshots
                WHERE source = ? AND format_version = ?
            """, (source, FORMAT_VERSION)).fetchone()
    return saved['fetched_at']


def load():
    with workspace.connect() as db:
        saved = db.execute("""
            SELECT fetched_at, payload FROM catalog_snapshots
            WHERE source = ? AND format_version = ?
        """, (_source(), FORMAT_VERSION)).fetchone()
    if saved is None:
        return None

    catalog = {name: [] for name in COLLECTIONS}
    with gzip.GzipFile(fileobj=io.BytesIO(saved['payload']), mode='rb') as archive:
        for line in archive:
            name, rows = json.loads(line)
            catalog[name].extend(rows)
    return saved['fetched_at'], tuple(catalog.values())
