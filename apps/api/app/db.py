import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv('DATABASE_PATH', Path(__file__).resolve().parent.parent / 'rescuemesh.db'))

def connection():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connection() as con:
        con.execute('CREATE TABLE IF NOT EXISTS missions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS merchants (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS ledger (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

def list_records(table):
    with connection() as con:
        return [json.loads(row['payload']) for row in con.execute(f'SELECT payload FROM {table} ORDER BY rowid DESC')]

def get_record(table, record_id):
    with connection() as con:
        row = con.execute(f'SELECT payload FROM {table} WHERE id = ?', (record_id,)).fetchone()
    return json.loads(row['payload']) if row else None

def save_record(table, record):
    with connection() as con:
        con.execute(f'INSERT INTO {table}(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (record['id'], json.dumps(record)))

def delete_record(table, record_id):
    with connection() as con:
        result = con.execute(f'DELETE FROM {table} WHERE id = ?', (record_id,))
        return result.rowcount > 0

def clear_records(table=None):
    tables = [table] if table else ['missions', 'merchants', 'ledger', 'notifications']
    with connection() as con:
        for name in tables:
            con.execute(f'DELETE FROM {name}')
