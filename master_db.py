"""
master_db.py — Database pusat untuk multi-outlet SGO
Menyimpan: daftar outlet, akun owner, session owner
"""
import sqlite3
import os
import hashlib

MASTER_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master.db")
OUTLETS_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outlets")

os.makedirs(OUTLETS_DIR, exist_ok=True)

def get_master_connection():
    conn = sqlite3.connect(MASTER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_master_db():
    conn = get_master_connection()
    cursor = conn.cursor()

    # Tabel outlet
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outlets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            bot_token TEXT NOT NULL,
            admin_username TEXT NOT NULL DEFAULT 'admin',
            admin_password_hash TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel owner (bisa lebih dari satu owner)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS owner_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_id INTEGER DEFAULT NULL,
            last_login TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel sessions persisten (owner & outlet admin)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            session_type TEXT NOT NULL,
            username TEXT NOT NULL,
            outlet_id INTEGER DEFAULT NULL,
            expires_at REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Insert default owner jika belum ada
    def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()
    cursor.execute(
        "INSERT OR IGNORE INTO owner_users (username, password_hash) VALUES (?, ?)",
        ('owner', _hash('owner123'))
    )

    conn.commit()
    conn.close()
    print("✅ Master database siap:", MASTER_DB_PATH)

def get_outlet_db_path(outlet_id: int) -> str:
    """Kembalikan path database untuk outlet tertentu."""
    return os.path.join(OUTLETS_DIR, f"outlet_{outlet_id}.db")

def get_outlet_connection(outlet_id: int):
    """Buat koneksi ke database outlet tertentu."""
    db_path = get_outlet_db_path(outlet_id)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_all_outlets(active_only=True):
    """Ambil semua outlet dari master database."""
    conn = get_master_connection()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT * FROM outlets WHERE is_active=1 ORDER BY id")
    else:
        cursor.execute("SELECT * FROM outlets ORDER BY id")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_outlet_by_id(outlet_id: int):
    """Ambil satu outlet berdasarkan ID."""
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM outlets WHERE id=?", (outlet_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_outlet_by_token(bot_token: str):
    """Ambil outlet berdasarkan bot token."""
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM outlets WHERE bot_token=?", (bot_token,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_outlet(name: str, bot_token: str, admin_username: str, admin_password: str) -> int:
    """Buat outlet baru — buat entry di master DB dan inisialisasi DB outlet."""
    import hashlib
    pw_hash = hashlib.sha256(admin_password.encode()).hexdigest()

    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO outlets (name, bot_token, admin_username, admin_password_hash)
        VALUES (?, ?, ?, ?)
    """, (name, bot_token, admin_username, pw_hash))
    outlet_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Inisialisasi database outlet
    init_outlet_db(outlet_id, name)
    return outlet_id

def init_outlet_db(outlet_id: int, outlet_name: str = "Restaurant"):
    """Inisialisasi database untuk outlet baru — sama strukturnya dengan database.py."""
    from database import init_db as _orig_init_db
    import database as _db

    db_path = get_outlet_db_path(outlet_id)

    # Simpan DB_PATH lama, ganti sementara
    original_path = _db.DB_PATH
    _db.DB_PATH = db_path

    # Jalankan init_db dengan path baru
    _orig_init_db()

    # Set nama restoran sesuai outlet
    _db.set_setting('restaurant_name', outlet_name)

    # Kembalikan DB_PATH ke semula
    _db.DB_PATH = original_path

    print(f"✅ Database outlet {outlet_id} ({outlet_name}) siap: {db_path}")

def verify_owner(username: str, password: str):
    """Verifikasi login owner."""
    import hashlib
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM owner_users WHERE username=? AND password_hash=?", (username, pw_hash))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE owner_users SET last_login=datetime('now','localtime') WHERE id=?", (row['id'],))
        conn.commit()
    conn.close()
    return dict(row) if row else None

def verify_outlet_admin(outlet_id: int, username: str, password: str):
    """Verifikasi login admin untuk outlet tertentu."""
    import hashlib
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM outlets
        WHERE id=? AND admin_username=? AND admin_password_hash=? AND is_active=1
    """, (outlet_id, username, pw_hash))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_session(token: str, session_type: str, username: str, outlet_id=None, expires_at=None):
    """Simpan session ke database."""
    import time
    if expires_at is None:
        expires_at = time.time() + (7 * 86400)
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (token, session_type, username, outlet_id, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """, (token, session_type, username, outlet_id, expires_at))
    conn.commit()
    conn.close()

def load_session(token: str):
    """Ambil session dari database."""
    import time
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE token=?", (token,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    row = dict(row)
    if time.time() > row['expires_at']:
        delete_session(token)
        return None
    return row

def delete_session(token: str):
    """Hapus session dari database."""
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()

def cleanup_expired_sessions():
    """Hapus semua session yang sudah expired."""
    import time
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    conn.commit()
    conn.close()

# Inisialisasi saat modul diimport
init_master_db()
