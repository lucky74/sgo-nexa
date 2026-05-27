import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restaurant.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Buat tabel jika belum ada."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            cuisine TEXT,
            price INTEGER NOT NULL,
            description TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            is_available INTEGER DEFAULT 1,
            stock INTEGER DEFAULT -1,
            stock_alert INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT DEFAULT 'dine_in',
            customer_name TEXT,
            table_number TEXT,
            items TEXT,
            total_price INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            telegram_id INTEGER DEFAULT NULL,
            delivery_address TEXT DEFAULT NULL,
            delivery_lat REAL DEFAULT NULL,
            delivery_lng REAL DEFAULT NULL,
            delivery_distance REAL DEFAULT NULL,
            delivery_fee INTEGER DEFAULT 0,
            whatsapp TEXT DEFAULT NULL,
            courier_name TEXT DEFAULT NULL,
            courier_token TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tambah kolom baru jika belum ada (untuk database lama)
    new_columns = [
        ("telegram_id",       "INTEGER DEFAULT NULL"),
        ("order_type",        "TEXT DEFAULT 'dine_in'"),
        ("delivery_address",  "TEXT DEFAULT NULL"),
        ("delivery_lat",      "REAL DEFAULT NULL"),
        ("delivery_lng",      "REAL DEFAULT NULL"),
        ("delivery_distance", "REAL DEFAULT NULL"),
        ("delivery_fee",      "INTEGER DEFAULT 0"),
        ("whatsapp",          "TEXT DEFAULT NULL"),
        ("courier_name",      "TEXT DEFAULT NULL"),
        ("courier_token",     "TEXT DEFAULT NULL"),
        ("voucher_code",      "TEXT DEFAULT NULL"),
        ("voucher_discount",  "INTEGER DEFAULT 0"),
    ]
    for col_name, col_def in new_columns:
        try:
            cursor.execute(f"ALTER TABLE orders ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass

    # Tambah kolom stock ke menu_items jika belum ada
    menu_new_columns = [
        ("stock",       "INTEGER DEFAULT -1"),
        ("stock_alert", "INTEGER DEFAULT 5"),
    ]
    for col_name, col_def in menu_new_columns:
        try:
            cursor.execute(f"ALTER TABLE menu_items ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass

    # Tabel sesi Telegram
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tg_sessions (
            tgid_token TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel kurir (multi-kurir)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS couriers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            whatsapp TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel pengaturan sistem
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel log stok
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_item_id INTEGER,
            change INTEGER,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel rating pesanan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            telegram_id INTEGER,
            overall_rating INTEGER,
            comment TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel review item
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS item_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            menu_item_name TEXT,
            rating INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel voucher
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT DEFAULT 'percent',
            discount_value INTEGER NOT NULL,
            min_order INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT -1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            expires_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Tabel admin users (login)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            last_login TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Insert default admin & owner jika belum ada
    import hashlib
    def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()
    default_users = [
        ('admin', _hash('admin123'), 'admin'),
        ('owner', _hash('owner123'), 'owner'),
    ]
    for uname, phash, role in default_users:
        cursor.execute(
            "INSERT OR IGNORE INTO admin_users (username, password_hash, role) VALUES (?, ?, ?)",
            (uname, phash, role)
        )

    # Insert default settings jika belum ada
    defaults = [
        ("restaurant_lat",      "-6.614970215748657"),
        ("restaurant_lng",      "106.80385837668723"),
        ("restaurant_name",     "Restaurant"),
        ("delivery_min_fee",    "5000"),
        ("delivery_fee_per_km", "3000"),
        ("delivery_min_km",     "1"),
        ("delivery_max_km",     "10"),
        ("courier_info",        ""),
        ("qris_image",          "/static/images/qris.jpg"),
        ("enable_service",      "1"),   # 1=aktif, 0=nonaktif
        ("service_rate",        "10"),  # persen
        ("enable_tax",          "1"),   # 1=aktif, 0=nonaktif
        ("tax_rate",            "11"),  # persen
        ("tax_label",           "PBJT"),
        ("daily_report_enabled","1"),
        ("daily_report_hour",   "22"),
        ("daily_report_minute", "0"),
        ("owner_telegram_id",   ""),
    ]
    for key, value in defaults:
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    conn.commit()
    conn.close()
    print("✅ Database SQLite siap:", DB_PATH)

def get_setting(key: str, default: str = "") -> str:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row['value'] if row else default
    except Exception:
        return default

def set_setting(key: str, value: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now', 'localtime'))",
            (key, value)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving setting: {e}")

# Inisialisasi database saat modul diimport
init_db()
