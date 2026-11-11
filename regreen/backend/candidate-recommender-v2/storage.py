"""Server-owned recommendation snapshots; SQLite is for a single-host deployment."""
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

@contextmanager
def connection():
    path=Path(os.getenv('RECOMMENDATION_DB',str(Path(__file__).parent/'var/recommendations.sqlite3')))
    path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path,timeout=10) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, expires REAL NOT NULL, payload TEXT NOT NULL)')
        yield conn

def save_snapshot(result):
    key=str(uuid.uuid4())
    expires=time.time()+int(os.getenv('RECOMMENDATION_TTL_SECONDS','86400'))
    with connection() as conn:
        conn.execute('DELETE FROM snapshots WHERE expires < ?',(time.time(),))
        # Bound disk use by limiting active snapshots, never evict an active selection silently.
        if conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]>=10_000:
            raise RuntimeError('추천 저장 한도입니다. 만료 데이터 정리/저장소 확장이 필요합니다.')
        conn.execute('INSERT INTO snapshots VALUES (?,?,?)',(key,expires,json.dumps(result,allow_nan=False)))
    return {**result,'recommendation_id':key,'expires_at_unix':expires}

def load_snapshot(key):
    with connection() as conn:
        row=conn.execute('SELECT expires,payload FROM snapshots WHERE id=?',(key,)).fetchone()
    if not row or row[0]<=time.time():
        raise LookupError('추천 결과가 없거나 만료되었습니다. 다시 추천을 요청하세요.')
    return json.loads(row[1])
