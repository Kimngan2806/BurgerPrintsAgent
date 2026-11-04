"""Durable account-scoped work. SQLite transactions serialize competing tabs/workers."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, Request
from core.config import settings


class Workspace:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT UNIQUE, password TEXT);
                CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, owner TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS documents(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
                    version INTEGER NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS docs_owner ON documents(owner,kind,updated);
                CREATE TABLE IF NOT EXISTS revisions(
                    id TEXT, version INTEGER, body TEXT, created REAL, PRIMARY KEY(id,version));
                CREATE TABLE IF NOT EXISTS submissions(
                    reference TEXT PRIMARY KEY, owner TEXT, draft TEXT, version INTEGER,
                    state TEXT, payload TEXT, result TEXT, updated REAL,
                    UNIQUE(draft,version));
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY, owner TEXT, name TEXT, entity TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS chat_leases(id TEXT PRIMARY KEY, token TEXT, expires REAL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def register(self, name, password):
        name = name.strip().casefold()
        if not 3 <= len(name) <= 80 or not 10 <= len(password) <= 256:
            raise HTTPException(422, 'Tên tài khoản 3–80 ký tự, mật khẩu 10–256 ký tự.')
        salt = secrets.token_hex(16)
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        owner = secrets.token_hex(16)
        try:
            with self.connect() as db:
                db.execute('INSERT INTO users VALUES(?,?,?)', (owner, name, salt + ':' + digest))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Tên tài khoản đã tồn tại.')
        return owner

    def login(self, name, password):
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE name=?', (name.strip().casefold(),)).fetchone()
        # Do the same expensive hash for unknown names.
        salt, expected = (row['password'] if row else '00' * 16 + ':' + '00' * 64).split(':')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        if not row or not hmac.compare_digest(actual, expected):
            raise HTTPException(401, 'Tài khoản hoặc mật khẩu không đúng.')
        return row['id']

    def token(self, owner):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM tokens WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO tokens VALUES(?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), owner, time.time() + 86400 * 7))
        return token

    def owner(self, token):
        with self.connect() as db:
            row = db.execute('SELECT owner FROM tokens WHERE hash=? AND expires>?',
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if not row:
            raise HTTPException(401, 'Vui lòng đăng nhập.')
        return row['owner']

    def create(self, owner, kind, body):
        ident = secrets.token_hex(16)
        with self.connect() as db:
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?)',
                       (ident, owner, kind, 1, json.dumps(body, ensure_ascii=False), time.time()))
            db.execute('INSERT INTO revisions VALUES(?,?,?,?)',
                       (ident, 1, json.dumps(body, ensure_ascii=False), time.time()))
        return self.get(owner, ident, kind)

    @staticmethod
    def decode(row):
        return dict(id=row['id'], version=row['version'], updated_at=row['updated'], **json.loads(row['body']))

    def get(self, owner, ident, kind):
        with self.connect() as db:
            row = db.execute('SELECT * FROM documents WHERE id=? AND owner=? AND kind=?',
                             (ident, owner, kind)).fetchone()
        if not row:
            raise HTTPException(404, 'Không tìm thấy dữ liệu trong tài khoản này.')
        return self.decode(row)

    def list(self, owner, kind):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute(
                'SELECT * FROM documents WHERE owner=? AND kind=? ORDER BY updated DESC', (owner, kind))]

    def update(self, owner, ident, kind, version, body):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Submitted/uncertain drafts are frozen until reconciled.
            if kind == 'draft' and db.execute(
                "SELECT 1 FROM submissions WHERE draft=? AND state IN ('sending','verifying','created')", (ident,)
            ).fetchone():
                raise HTTPException(409, 'Đơn đang gửi/đang xác minh hoặc đã tạo. Không thể sửa; hãy kiểm tra đơn hàng.')
            result = db.execute('UPDATE documents SET version=version+1, body=?, updated=? '
                                'WHERE id=? AND owner=? AND kind=? AND version=?',
                                (json.dumps(body, ensure_ascii=False), time.time(), ident, owner, kind, version))
            if result.rowcount != 1:
                raise HTTPException(409, 'Dữ liệu đã thay đổi ở tab khác. Tải lại trước khi sửa.')
            db.execute('INSERT INTO revisions VALUES(?,?,?,?)',
                       (ident, version + 1, json.dumps(body, ensure_ascii=False), time.time()))
        return self.get(owner, ident, kind)

    def event(self, owner, name, entity=''):
        with self.connect() as db:
            db.execute('INSERT INTO events(owner,name,entity,created) VALUES(?,?,?,?)',
                       (owner, name, entity, time.time()))


workspace = Workspace(settings.WORKSPACE_DB_PATH)


def current_owner(request: Request):
    return workspace.owner(request.cookies.get('bp_session', ''))
