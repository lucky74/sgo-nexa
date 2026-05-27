import asyncio
import logging
import os
import sys
import json
import shutil
import io
import math
import hashlib
import secrets
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from fastapi import FastAPI, Request, HTTPException, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any
import time
import uuid
from datetime import datetime

# Import database SQLite
from database import get_connection, init_db, get_setting, set_setting

# Import master database untuk multi-outlet
from master_db import (
    get_master_connection, init_master_db, get_outlet_db_path,
    get_outlet_connection, get_all_outlets, get_outlet_by_id,
    get_outlet_by_token, create_outlet, init_outlet_db,
    verify_owner, verify_outlet_admin, OUTLETS_DIR,
    save_session, load_session, delete_session
)

# Load environment variables
load_dotenv()

# Configuration
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
WEBHOOK_PATH = "/webhook"

# Folder untuk simpan gambar menu
UPLOAD_DIR = os.path.join("static", "images", "menu")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# AUTH  —  SESSION STORE (in-memory)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# {session_token: {"username": ..., "role": ..., "expires": timestamp}}
_sessions: dict = {}
SESSION_DAYS = 7

def _hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _create_session(username: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    import time as _time
    expires = _time.time() + (SESSION_DAYS * 86400)
    _sessions[token] = {"username": username, "role": role, "expires": expires}
    return token

def _get_session(request: Request):
    """Ambil session dari cookie. Return dict atau None."""
    import time as _time
    token = request.cookies.get("sgo_session")
    if not token:
        return None
    sess = _sessions.get(token)
    if not sess:
        return None
    if _time.time() > sess["expires"]:
        _sessions.pop(token, None)
        return None
    return sess

def _require_admin(request: Request):
    """Cek apakah user login sebagai admin. Return session atau None."""
    sess = _get_session(request)
    if not sess or sess["role"] != "admin":
        return None
    return sess

def _require_any_login(request: Request):
    """Cek apakah user sudah login (admin atau owner)."""
    return _get_session(request)

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize Bot
if not API_TOKEN:
    logger.error("API_TOKEN is not set in .env file!")

bot = Bot(token=API_TOKEN) if API_TOKEN else None
dp = Dispatcher()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HELPER FUNCTIONS  —  DATABASE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

CATEGORY_ORDER = [
    "Appetizer", "Soup", "Main Course", "Dessert", "Drink",
    "Indonesian Food", "Western Food", "Japanese Food", "Korean Food", "Chinese Food",
    "Fusion Food", "Middle Eastern", "Thai Food", "Italian Food", "Indian Food",
    "Mexican Food", "Vietnamese Food", "Mediterranean Food", "French Food",
    "Spanish Food", "Turkish Food", "Singaporean & Malaysian Food",
    "Brazilian Food", "Peruvian Food"
]

def get_menu_from_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM menu_items WHERE is_available = 1")
        rows = cursor.fetchall()

        # Ambil rating per item sekaligus
        cursor.execute("""
            SELECT menu_item_name, AVG(rating) as avg_rating, COUNT(*) as total_reviews
            FROM item_reviews GROUP BY menu_item_name
        """)
        item_ratings = {row['menu_item_name']: {
            'avg': round(row['avg_rating'], 1),
            'count': row['total_reviews']
        } for row in cursor.fetchall()}

        conn.close()

        temp_menu = {}
        for row in rows:
            item = dict(row)
            # Pastikan image URL absolut agar bisa diload dari Telegram WebApp
            img = item.get('image_url', '')
            if img and img.startswith('/'):
                img = BASE_URL.rstrip('/') + img
            item['image'] = img
            # Tambahkan rating
            rating_info = item_ratings.get(item['name'], {})
            item['avg_rating']   = rating_info.get('avg', 0)
            item['review_count'] = rating_info.get('count', 0)
            cat = item['category']
            if cat not in temp_menu:
                temp_menu[cat] = []
            temp_menu[cat].append(item)

        # Urutkan kategori
        sorted_menu = {}
        for cat in CATEGORY_ORDER:
            if cat in temp_menu:
                sorted_menu[cat] = temp_menu.pop(cat)
        # Sisa kategori yang tidak ada di CATEGORY_ORDER
        for cat in temp_menu:
            sorted_menu[cat] = temp_menu[cat]

        return sorted_menu
    except Exception as e:
        logger.error(f"Error fetching menu: {e}")
        return {}

# Buffer untuk stock alerts yang perlu dikirim async
_stock_alerts = []

def save_order_to_db(user_name, table_number, order_data_json, total_price, note,
                     telegram_id=None, order_type='dine_in',
                     delivery_address=None, delivery_lat=None, delivery_lng=None,
                     delivery_distance=None, delivery_fee=0, whatsapp=None,
                     voucher_code=None, voucher_discount=0):
    try:
        clean_price = total_price.replace("TOTAL: ", "").replace("Rp ", "").replace(".", "").replace(",", "")
        clean_price = "".join(filter(str.isdigit, clean_price))

        if isinstance(order_data_json, dict):
            items_str = json.dumps(order_data_json)
        else:
            items_str = order_data_json

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (customer_name, table_number, items, total_price, note, status,
                                telegram_id, order_type, delivery_address, delivery_lat, delivery_lng,
                                delivery_distance, delivery_fee, whatsapp, voucher_code, voucher_discount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_name, table_number, items_str,
            int(clean_price) if clean_price else 0,
            note, "pending", telegram_id, order_type,
            delivery_address, delivery_lat, delivery_lng,
            delivery_distance, delivery_fee, whatsapp,
            voucher_code, voucher_discount
        ))
        order_id = cursor.lastrowid

        # Kurangi stok untuk setiap item yang dipesan
        try:
            items_parsed = json.loads(items_str) if isinstance(items_str, str) else items_str
            if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                actual_items = items_parsed['items']
            else:
                actual_items = items_parsed

            for item_name, details in actual_items.items():
                if not isinstance(details, dict):
                    continue
                qty = details.get('qty', 0)
                if qty <= 0:
                    continue
                cursor.execute("SELECT id, stock, stock_alert, name FROM menu_items WHERE name=?", (item_name,))
                menu_row = cursor.fetchone()
                if not menu_row:
                    continue
                if menu_row['stock'] == -1:
                    continue  # unlimited
                new_stock = max(0, menu_row['stock'] - qty)
                cursor.execute("UPDATE menu_items SET stock=? WHERE id=?", (new_stock, menu_row['id']))
                cursor.execute(
                    "INSERT INTO stock_logs (menu_item_id, change, reason) VALUES (?, ?, ?)",
                    (menu_row['id'], -qty, f"Order #{order_id}")
                )
                # Auto nonaktifkan jika stok habis
                if new_stock == 0:
                    cursor.execute("UPDATE menu_items SET is_available=0 WHERE id=?", (menu_row['id'],))
                    # Kirim notifikasi ke admin (async tidak bisa di sini, simpan ke list)
                    _stock_alerts.append(('out', menu_row['name'], menu_row['id']))
                elif new_stock <= menu_row['stock_alert']:
                    _stock_alerts.append(('low', menu_row['name'], new_stock, menu_row['stock_alert']))
        except Exception as e:
            logger.warning(f"Gagal update stok: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Order [{order_type}] saved to SQLite (id={order_id})")
        return order_id
    except Exception as e:
        logger.error(f"Failed to save order to DB: {e}")
        return None

async def flush_stock_alerts():
    """Kirim notifikasi stok yang tertunda ke admin."""
    if not bot or not ADMIN_ID:
        _stock_alerts.clear()
        return
    while _stock_alerts:
        alert = _stock_alerts.pop(0)
        try:
            if alert[0] == 'out':
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"<b>STOK HABIS!</b>\n\n"
                         f"Menu <b>{alert[1]}</b> stoknya habis dan telah dinonaktifkan otomatis.\n"
                         f"Silakan update stok di dashboard.",
                    parse_mode="HTML"
                )
            elif alert[0] == 'low':
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"âš⚠️ <b>STOK MENIPIS!</b>\n\n"
                         f"Menu <b>{alert[1]}</b> tersisa <b>{alert[2]}</b> porsi "
                         f"(batas peringatan: {alert[3]}).",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.warning(f"Gagal kirim stock alert: {e}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# DAILY REPORT FUNCTION
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def send_daily_report():
    """Kirim ringkasan penjualan harian ke owner via Telegram."""
    if not bot:
        return

    # Cek apakah fitur aktif
    if get_setting('daily_report_enabled', '1') != '1':
        return

    # Tentukan penerima  —  owner_telegram_id atau fallback ke ADMIN_ID
    owner_id = get_setting('owner_telegram_id', '')
    recipients = []
    if owner_id and owner_id.strip():
        try:
            recipients.append(int(owner_id.strip()))
        except ValueError:
            pass
    if ADMIN_ID and ADMIN_ID not in recipients:
        recipients.append(ADMIN_ID)

    if not recipients:
        return

    try:
        today = datetime.now()
        today_start = today.strftime('%Y-%m-%d 00:00:00')
        today_end   = today.strftime('%Y-%m-%d 23:59:59')
        yesterday_start = (today.replace(hour=0, minute=0, second=0) - __import__('datetime').timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
        yesterday_end   = (today.replace(hour=0, minute=0, second=0) - __import__('datetime').timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')

        conn = get_connection()
        cursor = conn.cursor()

        # Data hari ini
        cursor.execute("""
            SELECT * FROM orders
            WHERE created_at >= ? AND created_at <= ?
        """, (today_start, today_end))
        today_orders = [dict(r) for r in cursor.fetchall()]

        # Data kemarin untuk perbandingan
        cursor.execute("""
            SELECT COUNT(*) as cnt, SUM(total_price) as rev FROM orders
            WHERE created_at >= ? AND created_at <= ? AND status != 'cancelled'
        """, (yesterday_start, yesterday_end))
        yesterday = dict(cursor.fetchone())

        conn.close()

        # Hitung statistik hari ini
        total_orders    = len(today_orders)
        cancelled       = sum(1 for o in today_orders if o.get('status') == 'cancelled')
        completed       = sum(1 for o in today_orders if o.get('status') in ('served', 'completed'))
        delivery_orders = sum(1 for o in today_orders if o.get('order_type') == 'delivery')
        dine_in_orders  = sum(1 for o in today_orders if o.get('order_type') == 'dine_in')

        # Hitung pendapatan dengan tax & service
        enable_service = get_setting('enable_service', '1') == '1'
        enable_tax     = get_setting('enable_tax', '1') == '1'
        service_rate   = float(get_setting('service_rate', '10')) / 100
        tax_rate       = float(get_setting('tax_rate', '11')) / 100

        total_revenue = 0
        for o in today_orders:
            if o.get('status') == 'cancelled':
                continue
            # Parse items untuk hitung subtotal yang benar
            items_raw = o.get('items', '{}')
            try:
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                    actual = items_parsed['items']
                else:
                    actual = items_parsed
                subtotal_order = sum(
                    d.get('harga', 0) * d.get('qty', 0)
                    for d in actual.values()
                    if isinstance(d, dict)
                )
            except Exception:
                subtotal_order = o.get('total_price', 0)

            service_amt = subtotal_order * service_rate if enable_service else 0
            tax_amt     = subtotal_order * tax_rate     if enable_tax     else 0
            ongkir      = o.get('delivery_fee', 0) or 0
            total_revenue += subtotal_order + service_amt + tax_amt + ongkir

        # Menu terlaris
        item_counts = {}
        for order in today_orders:
            if order.get('status') == 'cancelled':
                continue
            items_raw = order.get('items', '{}')
            try:
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                    actual = items_parsed['items']
                else:
                    actual = items_parsed
                for item_name, details in actual.items():
                    if isinstance(details, dict):
                        qty = details.get('qty', 0)
                        if qty > 0:
                            item_counts[item_name] = item_counts.get(item_name, 0) + qty
            except Exception:
                pass

        top_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:3]

        # Perbandingan dengan kemarin
        yesterday_rev   = yesterday.get('rev') or 0
        yesterday_count = yesterday.get('cnt') or 0
        rev_diff   = total_revenue - yesterday_rev
        count_diff = total_orders - yesterday_count
        rev_arrow   = "📈" if rev_diff >= 0 else "📉"
        count_arrow = "📈" if count_diff >= 0 else "📉"

        rest_name = get_setting('restaurant_name', 'Restaurant')
        date_str  = today.strftime('%d %B %Y')

        # Format pesan
        lines = [
            f"<b>RINGKASAN HARIAN</b>",
            f"🏪 {rest_name}",
            f"📅 {date_str}",
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”",
            f"",
            f"<b>Pesanan Hari Ini</b>",
            f"Total Pesanan    : <b>{total_orders}</b> {count_arrow} ({'+' if count_diff >= 0 else ''}{count_diff} vs kemarin)",
            f"Selesai        : {completed}",
            f"âŒ Dibatalkan     : {cancelled}",
            f"🍽️ Dine-in        : {dine_in_orders}",
            f"🚵 Delivery       : {delivery_orders}",
            f"",
            f"<b>Pendapatan</b>",
            f"Total Revenue    : <b>Rp {int(total_revenue):,}</b>".replace(',', '.'),
            f"                   {rev_arrow} ({'+' if rev_diff >= 0 else ''}Rp {abs(int(rev_diff)):,} vs kemarin)".replace(',', '.'),
        ]

        if top_items:
            lines.extend([
                f"",
                f"<b>Menu Terlaris</b>",
            ])
            medals = ["🥇", "🥈", "🥉"]
            for i, (name, qty) in enumerate(top_items):
                lines.append(f"{medals[i]} {name} ({qty} porsi)")

        lines.extend([
            f"",
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”",
        ])

        if total_orders == 0:
            lines.append(f"😴 Tidak ada pesanan hari ini.")
        elif total_orders >= 20:
            lines.append(f"🔥 Hari yang sibuk! Kerja bagus tim!")
        elif total_orders >= 10:
            lines.append(f"👍 Hari yang cukup ramai.")
        else:
            lines.append(f"💪 Semangat untuk hari esok!")

        msg = "\n".join(lines)

        for recipient in recipients:
            try:
                await bot.send_message(chat_id=recipient, text=msg, parse_mode="HTML")
                logger.info(f"Daily report dikirim ke {recipient}")
            except Exception as e:
                logger.warning(f"Gagal kirim daily report ke {recipient}: {e}")

    except Exception as e:
        logger.error(f"Error generating daily report: {e}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# BACKUP DATABASE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

async def backup_database():
    """Backup database SQLite ke folder backups/, simpan 30 hari terakhir."""
    try:
        from database import DB_PATH
        today_str = datetime.now().strftime('%Y-%m-%d')
        backup_filename = f"restaurant_{today_str}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        # Copy database
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"Backup database berhasil: {backup_path}")

        # Hapus backup lebih dari 30 hari
        deleted = []
        for fname in os.listdir(BACKUP_DIR):
            if not fname.startswith("restaurant_") or not fname.endswith(".db"):
                continue
            fpath = os.path.join(BACKUP_DIR, fname)
            try:
                # Ambil tanggal dari nama file
                date_str = fname.replace("restaurant_", "").replace(".db", "")
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                age_days = (datetime.now() - file_date).days
                if age_days > 30:
                    os.remove(fpath)
                    deleted.append(fname)
            except Exception:
                pass

        if deleted:
            logger.info(f"🗑ï¸ Backup lama dihapus: {', '.join(deleted)}")

        # Hitung ukuran backup
        size_kb = os.path.getsize(backup_path) / 1024

        # Kirim notifikasi ke admin
        if bot and ADMIN_ID:
            backup_list = sorted([
                f for f in os.listdir(BACKUP_DIR)
                if f.startswith("restaurant_") and f.endswith(".db")
            ], reverse=True)[:5]

            msg = (
                f"<b>BACKUP DATABASE BERHASIL</b>\n\n"
                f"📅 Tanggal: {today_str}\n"
                f"📦 Ukuran: {size_kb:.1f} KB\n"
                f"📁 File: <code>{backup_filename}</code>\n\n"
                f"<b>5 Backup Terakhir:</b>\n"
            )
            for b in backup_list:
                msg += f"  - {b}\n"
            if deleted:
                msg += f"\n🗑ï¸ Dihapus (>30 hari): {len(deleted)} file"

            try:
                await bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Gagal kirim notif backup: {e}")

        return {"status": "ok", "file": backup_filename, "size_kb": round(size_kb, 1)}

    except Exception as e:
        logger.error(f"Error backup database: {e}")
        if bot and ADMIN_ID:
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"<b>BACKUP DATABASE GAGAL!</b>\n\nError: {str(e)}",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        return {"status": "error", "message": str(e)}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SCHEDULER
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")
# HARUS dideklarasi sebelum lifespan & handlers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
tg_sessions = {}  # {tgid_token: telegram_id}

def save_tg_session(telegram_id: int):
    """Simpan telegram_id ke memory dan database."""
    token = str(telegram_id)
    tg_sessions[token] = telegram_id
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO tg_sessions (tgid_token, telegram_id) VALUES (?, ?)",
            (token, telegram_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Gagal simpan sesi ke DB: {e}")

def get_telegram_id_from_token(token: str):
    """Ambil telegram_id dari token, cek memory dulu lalu database."""
    if not token:
        return None
    # Cek memory
    if token in tg_sessions:
        return tg_sessions[token]
    # Cek database
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM tg_sessions WHERE tgid_token=?", (token,))
        row = cursor.fetchone()
        conn.close()
        if row:
            tg_sessions[token] = row['telegram_id']  # cache
            return row['telegram_id']
    except Exception as e:
        logger.warning(f"Gagal lookup sesi dari DB: {e}")
    return None

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# LIFESPAN (startup)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


# ─────────────────────────────────────────────
# OUTLET BOT REGISTRY (harus sebelum lifespan)
# ─────────────────────────────────────────────
_outlet_bots = {}  # {outlet_id: Bot instance}

async def register_outlet_bot(outlet_id: int, bot_token: str):
    try:
        # Reload BASE_URL dari .env agar selalu pakai URL tunnel terbaru
        load_dotenv(override=True)
        current_base_url = os.getenv("BASE_URL", BASE_URL)

        outlet_bot = Bot(token=bot_token)
        _outlet_bots[outlet_id] = outlet_bot
        webhook_url = f"{current_base_url}/outlet/{outlet_id}/webhook"
        await outlet_bot.set_webhook(webhook_url, allowed_updates=["message", "callback_query"])
        logger.info(f"Outlet {outlet_id} bot registered, webhook: {webhook_url}")
        return outlet_bot
    except Exception as e:
        logger.error(f"Gagal register bot outlet {outlet_id}: {e}")
        return None

async def load_all_outlet_bots():
    outlets = get_all_outlets(active_only=True)
    for outlet in outlets:
        await register_outlet_bot(outlet["id"], outlet["bot_token"])
    logger.info(f"Loaded {len(outlets)} outlet bots")
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("SQLite database initialized")

    # Load sesi telegram
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT tgid_token, telegram_id FROM tg_sessions")
        for row in cursor.fetchall():
            tg_sessions[row['tgid_token']] = row['telegram_id']
        conn.close()
        logger.info(f"Loaded {len(tg_sessions)} sesi Telegram dari database")
    except Exception as e:
        logger.warning(f"Gagal load sesi dari DB: {e}")

    # Setup scheduler untuk daily report
    hour   = int(get_setting('daily_report_hour', '22'))
    minute = int(get_setting('daily_report_minute', '0'))
    scheduler.add_job(
        send_daily_report,
        CronTrigger(hour=hour, minute=minute, timezone="Asia/Jakarta"),
        id='daily_report',
        replace_existing=True
    )

    # Backup otomatis jam 02:00 WIB
    scheduler.add_job(
        backup_database,
        CronTrigger(hour=2, minute=0, timezone="Asia/Jakarta"),
        id='auto_backup',
        replace_existing=True
    )

    scheduler.start()
    logger.info(f"Scheduler aktif  —  daily report jam {hour:02d}:{minute:02d} WIB, backup jam 02:00 WIB")

    # Load semua outlet bots
    try:
        await load_all_outlet_bots()
    except Exception as e:
        logger.warning(f"Gagal load outlet bots: {e}")

    if bot and BASE_URL:
        webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
        try:
            await bot.set_webhook(
                webhook_url,
                allowed_updates=["message", "callback_query", "inline_query"]
            )
            logger.info(f"Webhook set to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# FASTAPI APP
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

app = FastAPI(lifespan=lifespan)

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory=str(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")))

# Custom Jinja2 filter
def format_idr(value):
    try:
        return f"{int(value):,}".replace(',', '.')
    except Exception:
        return str(value)

templates.env.filters['format_idr'] = format_idr

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# INVOICE IMAGE GENERATOR
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def generate_invoice_image(data: dict, order_id: int = None) -> io.BytesIO:
    """Generate invoice sebagai gambar PNG yang keren menggunakan Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    # â”€â”€ Warna & ukuran â”€â”€
    W, PAD = 600, 40
    BG       = (18, 18, 30)       # dark navy
    HEADER   = (45, 17, 66)       # ungu gelap
    ACCENT   = (212, 175, 55)     # gold
    WHITE    = (255, 255, 255)
    GRAY     = (160, 160, 180)
    LIGHT    = (230, 230, 240)
    GREEN    = (16, 185, 129)
    LINE     = (50, 50, 70)

    # â”€â”€ Font â”€â”€ (pakai default jika tidak ada custom font)
    def get_font(size, bold=False):
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            return ImageFont.truetype(font_path, size)
        except Exception:
            return ImageFont.load_default()

    f_title   = get_font(22, bold=True)
    f_rest    = get_font(16, bold=True)
    f_sub     = get_font(12)
    f_bold    = get_font(14, bold=True)
    f_normal  = get_font(13)
    f_small   = get_font(11)
    f_total   = get_font(18, bold=True)

    # â”€â”€ Hitung tinggi dinamis â”€â”€
    items = data.get('items', {})
    n_items = len(items)
    H = 420 + (n_items * 28) + 60

    img  = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    # â”€â”€ Header gradient â”€â”€
    for y in range(120):
        ratio = y / 120
        r = int(45 + (18 - 45) * ratio)
        g = int(17 + (18 - 17) * ratio)
        b = int(66 + (30 - 66) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # â”€â”€ Gold accent bar â”€â”€
    draw.rectangle([0, 0, W, 4], fill=ACCENT)

    # â”€â”€ Nama restaurant â”€â”€
    rest_name = get_setting('restaurant_name', 'Restaurant')
    draw.text((W//2, 30), rest_name.upper(), font=f_rest, fill=ACCENT, anchor="mm")

    # â”€â”€ Judul INVOICE â”€â”€
    draw.text((W//2, 58), "INVOICE PESANAN", font=f_title, fill=WHITE, anchor="mm")

    # â”€â”€ Nomor invoice & tanggal â”€â”€
    inv_no = f"INV-{order_id or datetime.now().strftime('%Y%m%d%H%M%S')}"
    now_str = datetime.now().strftime("%d %B %Y, %H:%M")
    draw.text((PAD, 88), inv_no, font=f_small, fill=GRAY)
    draw.text((W - PAD, 88), now_str, font=f_small, fill=GRAY, anchor="ra")

    # â”€â”€ Divider â”€â”€
    draw.rectangle([0, 110, W, 114], fill=ACCENT)

    y = 130

    # â”€â”€ Info pembeli â”€â”€
    order_type = data.get('order_type', 'dine_in')
    customer   = data.get('customer', 'Tamu')

    draw.text((PAD, y), "KEPADA:", font=f_small, fill=GRAY)
    y += 18
    draw.text((PAD, y), customer, font=f_bold, fill=WHITE)
    y += 20

    if order_type == 'delivery':
        addr = data.get('delivery_address', '-')
        # Wrap alamat jika terlalu panjang
        if len(addr) > 55:
            addr = addr[:55] + '...'
        draw.text((PAD, y), f"📍 {addr}", font=f_small, fill=GRAY)
        y += 16
        wa = data.get('whatsapp', '')
        if wa:
            draw.text((PAD, y), f"📱 {wa}", font=f_small, fill=GRAY)
            y += 16
    else:
        draw.text((PAD, y), f"🏪 Meja: {data.get('table', '-')}", font=f_small, fill=GRAY)
        y += 16

    y += 8

    # â”€â”€ Divider â”€â”€
    draw.line([(PAD, y), (W - PAD, y)], fill=LINE, width=1)
    y += 12

    # â”€â”€ Header tabel â”€â”€
    draw.rectangle([PAD, y, W - PAD, y + 26], fill=(35, 25, 55))
    draw.text((PAD + 8, y + 6), "ITEM", font=f_small, fill=ACCENT)
    draw.text((W - PAD - 8, y + 6), "SUBTOTAL", font=f_small, fill=ACCENT, anchor="ra")
    y += 30

    # â”€â”€ Item pesanan â”€â”€
    subtotal = 0
    for i, (item_name, details) in enumerate(items.items()):
        qty   = details.get('qty', 0)
        harga = details.get('harga', 0)
        total = qty * harga
        subtotal += total

        row_bg = (25, 20, 40) if i % 2 == 0 else BG
        draw.rectangle([PAD, y, W - PAD, y + 26], fill=row_bg)

        # Truncate nama jika terlalu panjang
        name_display = item_name if len(item_name) <= 30 else item_name[:28] + '..'
        draw.text((PAD + 8, y + 6), f"{name_display}  Ã—{qty}", font=f_normal, fill=LIGHT)
        draw.text((W - PAD - 8, y + 6), f"Rp {total:,}".replace(',', '.'), font=f_normal, fill=WHITE, anchor="ra")

        # Catatan item
        note = details.get('currentNote', '')
        if note and note not in ('Tanpa catatan', '-', ''):
            y += 24
            draw.text((PAD + 16, y + 2), f"  â†³ {note}", font=f_small, fill=GRAY)

        y += 28

    y += 4
    draw.line([(PAD, y), (W - PAD, y)], fill=LINE, width=1)
    y += 12

    # â”€â”€ Rincian biaya  —  ambil dari settings â”€â”€
    enable_service = get_setting('enable_service', '1') == '1'
    enable_tax     = get_setting('enable_tax', '1') == '1'
    service_rate   = float(get_setting('service_rate', '10')) / 100
    tax_rate       = float(get_setting('tax_rate', '11')) / 100
    tax_label      = get_setting('tax_label', 'PBJT')

    service = subtotal * service_rate if enable_service else 0
    tax     = subtotal * tax_rate     if enable_tax     else 0
    ongkir  = int(data.get('delivery_fee', 0) or 0)
    grand   = subtotal + service + tax + ongkir

    def draw_row(label, value, bold=False, color=GRAY, val_color=LIGHT):
        nonlocal y
        font_l = f_bold if bold else f_normal
        font_v = f_bold if bold else f_normal
        draw.text((PAD + 8, y), label, font=font_l, fill=color)
        draw.text((W - PAD - 8, y), value, font=font_v, fill=val_color, anchor="ra")
        y += 22

    draw_row("Subtotal", f"Rp {subtotal:,}".replace(',', '.'))
    if enable_service:
        draw_row(f"Service Charge ({int(service_rate*100)}%)", f"Rp {int(service):,}".replace(',', '.'))
    if enable_tax:
        draw_row(f"{tax_label} ({int(tax_rate*100)}%)", f"Rp {int(tax):,}".replace(',', '.'))
    if ongkir > 0:
        draw_row("Ongkos Kirim", f"Rp {ongkir:,}".replace(',', '.'))

    y += 4
    # â”€â”€ Total box â”€â”€
    draw.rectangle([PAD, y, W - PAD, y + 44], fill=HEADER)
    draw.rectangle([PAD, y, W - PAD, y + 44], outline=ACCENT, width=1)
    draw.text((PAD + 16, y + 12), "TOTAL PEMBAYARAN", font=f_bold, fill=ACCENT)
    draw.text((W - PAD - 16, y + 10), f"Rp {int(grand):,}".replace(',', '.'), font=f_total, fill=WHITE, anchor="ra")
    y += 52

    # â”€â”€ Catatan umum â”€â”€
    general_note = data.get('generalNote', '')
    if general_note and general_note.strip():
        y += 4
        draw.text((PAD, y), f"📝 Catatan: {general_note[:60]}", font=f_small, fill=GRAY)
        y += 18

    # â”€â”€ Footer â”€â”€
    y += 8
    draw.line([(PAD, y), (W - PAD, y)], fill=LINE, width=1)
    y += 12
    draw.text((W//2, y), "Pesanan Anda telah diterima!", font=f_bold, fill=GREEN, anchor="mm")
    y += 22
    draw.text((W//2, y), "Terima kasih telah memesan 🙏", font=f_small, fill=GRAY, anchor="mm")
    y += 18
    draw.text((W//2, y), rest_name, font=f_small, fill=ACCENT, anchor="mm")

    # â”€â”€ Gold bottom bar â”€â”€
    draw.rectangle([0, H - 4, W, H], fill=ACCENT)

    # Crop ke tinggi aktual
    img = img.crop((0, 0, W, min(H, y + 30)))

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# TELEGRAM BOT HANDLERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    logger.info(f"Start command from {message.from_user.full_name} (ID: {message.from_user.id})")

    save_tg_session(message.from_user.id)

    # Reload BASE_URL dari .env agar selalu pakai URL tunnel terbaru
    load_dotenv(override=True)
    current_base_url = os.getenv("BASE_URL", BASE_URL)

    tgid = message.from_user.id
    dine_url     = f"{current_base_url}?tgid={tgid}&mode=dine_in"
    delivery_url = f"{current_base_url}/delivery?tgid={tgid}"

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="Makan di Tempat",
            web_app=types.WebAppInfo(url=dine_url)
        ),
        types.InlineKeyboardButton(
            text="Pesan Antar (Online)",
            web_app=types.WebAppInfo(url=delivery_url)
        )
    )

    restaurant_name = get_setting('restaurant_name', 'Restaurant')

    await message.answer(
        f"<b>{restaurant_name.upper()}</b>\n\n"
        f"Selamat datang, {message.from_user.full_name}!\n\n"
        "Silakan pilih jenis pesanan Anda:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

def format_order_message(data, source="Web"):
    try:
        customer_name = data.get('customer', 'Tamu')
        table_number  = data.get('table', '-')
        items         = data.get('items', {})
        total_str     = data.get('total', '0')
        general_note  = data.get('generalNote', '-')
        order_type    = data.get('order_type', 'dine_in')

        if order_type == 'delivery':
            header = f"<b>PESANAN ANTAR BARU! ({source})</b>"
        else:
            header = f"<b>PESANAN BARU! ({source})</b>"

        msg_lines = [
            header,
            f"<b>Nama:</b> {customer_name}",
        ]

        if order_type == 'delivery':
            msg_lines.append(f"<b>WhatsApp:</b> {data.get('whatsapp', '-')}")
            msg_lines.append(f"<b>Alamat:</b> {data.get('delivery_address', '-')}")
            dist = data.get('delivery_distance')
            fee  = data.get('delivery_fee', 0)
            if dist:
                msg_lines.append(f"<b>Jarak:</b> {dist:.1f} km")
            if fee:
                msg_lines.append(f"<b>Ongkir:</b> Rp {int(fee):,}".replace(',', '.'))
            maps_url = data.get('maps_url', '')
            if maps_url:
                msg_lines.append(f"🗺ï¸ <a href='{maps_url}'>Lihat di Google Maps</a>")
        else:
            msg_lines.append(f"<b>Meja:</b> {table_number}")

        msg_lines.extend(["", "<b>Detail Pesanan:</b>"])

        for item_name, details in items.items():
            qty  = details.get('qty', 0)
            note = details.get('currentNote', '-')
            if note in ("Tanpa catatan", "", None):
                note = "-"
            msg_lines.append(f"<b>{item_name}</b> (x{qty})")
            if note != "-":
                msg_lines.append(f"   <i>Catatan: {note}</i>")

        msg_lines.append("")
        if general_note and general_note not in ("-", ""):
            msg_lines.append(f"<b>Catatan:</b> {general_note}")
            msg_lines.append("")

        msg_lines.append(f"<b>{total_str}</b>")
        return "\n".join(msg_lines)
    except Exception as e:
        logger.error(f"Error formatting message: {e}")
        return f"âš⚠️ Error: {str(e)}"

@dp.message(F.web_app_data)
async def handle_order(message: types.Message):
    raw_data = message.web_app_data.data
    nama_tamu = message.from_user.full_name

    logger.info(f"Order received from {nama_tamu}: {raw_data}")

    try:
        data = json.loads(raw_data)
        if 'customer' not in data:
            data['customer'] = nama_tamu

        formatted_msg = format_order_message(data, source="Telegram WebApp")

        save_order_to_db(
            data.get('customer', nama_tamu),
            data.get('table', '-'),
            raw_data,
            data.get('total', '0'),
            data.get('generalNote', ''),
            telegram_id=message.from_user.id
        )

        # Konfirmasi ke pembeli
        await message.answer(f"Pesanan Anda telah diterima!\n\n{formatted_msg}", parse_mode="HTML")

        # Kirim notifikasi ke admin
        if ADMIN_ID and bot and ADMIN_ID != message.from_user.id:
            try:
                await bot.send_message(chat_id=ADMIN_ID, text=formatted_msg, parse_mode="HTML")
                logger.info(f"Notifikasi pesanan dikirim ke admin {ADMIN_ID}")
            except Exception as e:
                logger.error(f"Gagal kirim notifikasi ke admin: {e}")

    except json.JSONDecodeError:
        logger.error("Failed to decode JSON data")
        await message.answer("âš⚠️ Terjadi kesalahan dalam memproses data pesanan.")
    except Exception as e:
        logger.error(f"Error handling order: {e}")
        await message.answer("âš⚠️ Terjadi kesalahan sistem.")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# RATING CALLBACK HANDLERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dp.callback_query(F.data.startswith("ro_"))
async def handle_order_rating(callback: types.CallbackQuery):
    """Handle rating keseluruhan pesanan.
    Format callback_data: ro_{order_id}_{rating}  (max 64 bytes)
    """
    try:
        # ro_{order_id}_{rating}
        parts = callback.data.split("_")
        order_id = int(parts[1])
        rating   = int(parts[2])
        telegram_id = callback.from_user.id

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO order_ratings (order_id, telegram_id, overall_rating)
            VALUES (?, ?, ?)
        """, (order_id, telegram_id, rating))

        cursor.execute("SELECT items FROM orders WHERE id=?", (order_id,))
        order_row = cursor.fetchone()
        conn.commit()
        conn.close()

        stars = "⭐" * rating
        await callback.message.edit_text(
            f"Terima kasih! Rating Anda: {stars} ({rating}/5)\n\n"
            f"Sekarang, bagaimana dengan menu yang Anda pesan?"
        )

        # Kirim notifikasi ke admin
        if ADMIN_ID and bot:
            try:
                customer_name = callback.from_user.full_name or "Tamu"
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"<b>⭐ RATING PESANAN BARU</b>\n\n"
                         f"<b>Dari:</b> {customer_name}\n"
                         f"<b>Pesanan:</b> #{order_id}\n"
                         f"<b>Rating:</b> {stars} ({rating}/5)",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Gagal kirim notif rating ke admin: {e}")

        # Tanya rating per item  —  gunakan index agar callback_data pendek
        if order_row:
            try:
                items_parsed = json.loads(order_row['items']) if isinstance(order_row['items'], str) else order_row['items']
                if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                    actual_items = items_parsed['items']
                else:
                    actual_items = items_parsed

                item_names = [k for k, v in actual_items.items() if isinstance(v, dict) and v.get('qty', 0) > 0]

                for idx, item_name in enumerate(item_names[:5]):
                    builder = InlineKeyboardBuilder()
                    for r in range(1, 6):
                        # ri_{order_id}_{idx}_{rating}   —  pendek, max ~20 chars
                        builder.button(
                            text=f"{'⭐' * r}",
                            callback_data=f"ri_{order_id}_{idx}_{r}"
                        )
                    builder.adjust(5)
                    # Simpan mapping idxâ†’nama di pesan agar bisa diambil saat callback
                    await callback.message.answer(
                        f"Bagaimana <b>{item_name}</b>?\n"
                        f"<code>ref:{order_id}:{idx}:{item_name[:40]}</code>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.warning(f"Gagal kirim item rating: {e}")

        await callback.answer()
    except Exception as e:
        logger.error(f"Error handling order rating: {e}")
        await callback.answer("Terjadi kesalahan")


@dp.callback_query(F.data.startswith("ri_"))
async def handle_item_rating(callback: types.CallbackQuery):
    """Handle rating per item menu.
    Format callback_data: ri_{order_id}_{idx}_{rating}
    Nama item diambil dari teks pesan (baris ref:).
    """
    try:
        parts = callback.data.split("_")
        order_id = int(parts[1])
        # parts[2] = idx (tidak dipakai langsung, nama diambil dari pesan)
        rating   = int(parts[3])

        # Ambil nama item dari teks pesan  —  baris "ref:order_id:idx:nama"
        item_name = "Menu"
        try:
            msg_text = callback.message.text or ""
            for line in msg_text.splitlines():
                if line.startswith("ref:"):
                    item_name = line.split(":", 3)[3]
                    break
        except Exception:
            pass

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO item_reviews (order_id, menu_item_name, rating)
            VALUES (?, ?, ?)
        """, (order_id, item_name, rating))
        conn.commit()
        conn.close()

        stars = "⭐" * rating
        await callback.message.edit_text(
            f"<b>{item_name}</b>: {stars} ({rating}/5)",
            parse_mode="HTML"
        )
        await callback.answer("Rating tersimpan!")

        # Kirim notifikasi ke admin
        if ADMIN_ID and bot:
            try:
                customer_name = callback.from_user.full_name or "Tamu"
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"<b>⭐ REVIEW MENU BARU</b>\n\n"
                         f"<b>Dari:</b> {customer_name}\n"
                         f"<b>Pesanan:</b> #{order_id}\n"
                         f"<b>Menu:</b> {item_name}\n"
                         f"<b>Rating:</b> {stars} ({rating}/5)",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Gagal kirim notif item rating ke admin: {e}")
    except Exception as e:
        logger.error(f"Error handling item rating: {e}")
        await callback.answer("Terjadi kesalahan")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PYDANTIC MODELS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class OrderRequest(BaseModel):
    customer: str = "Tamu"
    table: str = "-"
    items: Dict[str, Any]
    total: str = "0"
    generalNote: str = ""

class WaiterRequest(BaseModel):
    nama: str = "Tamu Tanpa Nama"
    table_number: str = "Tidak Disebutkan"

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROUTES  —  AUTH (LOGIN / LOGOUT)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/dashboard"):
    sess = _get_session(request)
    if sess:
        # Sudah login  —  redirect sesuai role
        if sess["role"] == "owner":
            return RedirectResponse(url="/sales-report", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "next": next,
        "username": "",
        "restaurant_name": get_setting("restaurant_name", "Restaurant"),
        "current_year": datetime.now().year,
    })

@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip().lower()
    password = str(form.get("password", ""))
    next_url = str(form.get("next", "/dashboard"))

    # Validasi next_url  —  hanya izinkan path internal
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/dashboard"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users WHERE username=?", (username,))
    user = cursor.fetchone()

    if user and user["password_hash"] == _hash_password(password):
        # Update last_login
        cursor.execute(
            "UPDATE admin_users SET last_login=datetime('now','localtime') WHERE id=?",
            (user["id"],)
        )
        conn.commit()
        conn.close()

        token = _create_session(username, user["role"])

        # Redirect sesuai role
        if user["role"] == "owner":
            redirect_url = "/sales-report"
        else:
            redirect_url = next_url if next_url != "/login" else "/dashboard"

        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key="sgo_session",
            value=token,
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            samesite="lax"
        )
        logger.info(f"Login berhasil: {username} ({user['role']})")
        return response
    else:
        conn.close()
        logger.warning(f"âš⚠️ Login gagal: username={username}")
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Username atau password salah.",
            "next": next_url,
            "username": username,
            "restaurant_name": get_setting("restaurant_name", "Restaurant"),
            "current_year": datetime.now().year,
        }, status_code=401)

@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("sgo_session")
    if token:
        _sessions.pop(token, None)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("sgo_session")
    return response

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROUTES  —  HALAMAN UTAMA
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    menu_data = get_menu_from_db()
    tgid = request.query_params.get('tgid', '')
    restaurant_name = get_setting('restaurant_name', 'Restaurant')
    # Pisah nama untuk header (baris 1 = nama utama, baris 2 = sub nama)
    name_parts = restaurant_name.split(' ', 2)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "menu": menu_data,
        "current_year": datetime.now().year,
        "tgid": tgid,
        "restaurant_name": restaurant_name,
        "qris_image": get_setting("qris_image", "/static/images/qris.jpg"),
        "tax_settings": {
            "enable_service": get_setting("enable_service", "1") == "1",
            "service_rate":   float(get_setting("service_rate", "10")),
            "enable_tax":     get_setting("enable_tax", "1") == "1",
            "tax_rate":       float(get_setting("tax_rate", "11")),
            "tax_label":      get_setting("tax_label", "PBJT"),
        }
    })

@app.get("/sales-report", response_class=HTMLResponse)
async def sales_report(request: Request, date: str = None):
    sess = _require_any_login(request)
    if not sess:
        return RedirectResponse(url="/login?next=/sales-report", status_code=302)
    try:
        if date:
            try:
                target_date = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                target_date = datetime.now()
        else:
            target_date = datetime.now()

        today_start = target_date.strftime('%Y-%m-%d 00:00:00')
        today_end = target_date.strftime('%Y-%m-%d 23:59:59')

        conn = get_connection()
        cursor = conn.cursor()

        # Ambil orders berdasarkan tanggal
        cursor.execute("""
            SELECT * FROM orders
            WHERE created_at >= ? AND created_at <= ?
        """, (today_start, today_end))
        orders = [dict(row) for row in cursor.fetchall()]

        # Ambil semua menu untuk mapping nama â†’ kategori
        cursor.execute("SELECT name, category FROM menu_items")
        menu_map = {row['name']: row['category'] for row in cursor.fetchall()}
        conn.close()

        # Agregasi penjualan
        sales_data = {}
        total_sales = 0
        total_service = 0
        total_tax = 0
        total_revenue = 0

        for order in orders:
            items_raw = order.get('items', '{}')
            if isinstance(items_raw, str):
                try:
                    items = json.loads(items_raw)
                except:
                    continue
            else:
                items = items_raw

            # Handle nested items
            actual_items = {}
            if 'items' in items and isinstance(items['items'], dict):
                actual_items = items['items']
            else:
                actual_items = items

            order_subtotal = 0

            for item_name, details in actual_items.items():
                if isinstance(details, dict):
                    qty = details.get('qty', 0)
                    price = details.get('harga', 0)

                    if qty > 0:
                        category = menu_map.get(item_name, 'Uncategorized')
                        if category not in sales_data:
                            sales_data[category] = []

                        found = False
                        for entry in sales_data[category]:
                            if entry['name'] == item_name:
                                entry['qty'] += qty
                                entry['total'] += (qty * price)
                                found = True
                                break

                        if not found:
                            sales_data[category].append({
                                'name': item_name,
                                'qty': qty,
                                'price': price,
                                'total': qty * price
                            })

                        order_subtotal += (qty * price)

            service = order_subtotal * (float(get_setting('service_rate', '10')) / 100) if get_setting('enable_service', '1') == '1' else 0
            tax = order_subtotal * (float(get_setting('tax_rate', '11')) / 100) if get_setting('enable_tax', '1') == '1' else 0

            total_sales += order_subtotal
            total_service += service
            total_tax += tax
            total_revenue += (order_subtotal + service + tax)

        # Urutkan kategori
        sorted_sales = {}
        for cat in CATEGORY_ORDER:
            if cat in sales_data:
                sorted_sales[cat] = sales_data.pop(cat)
        for cat in sales_data:
            sorted_sales[cat] = sales_data[cat]

        return templates.TemplateResponse("sales_report.html", {
            "request": request,
            "sales": sorted_sales,
            "total_sales": total_sales,
            "total_service": total_service,
            "total_tax": total_tax,
            "total_revenue": total_revenue,
            "date": target_date.strftime("%d %B %Y"),
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "current_year": datetime.now().year,
            "restaurant_name": get_setting('restaurant_name', 'Restaurant'),
            "user_role": sess["role"],
            "username": sess["username"],
            "is_outlet": False,
            "outlet_id": None,
        })
    except Exception as e:
        logger.error(f"Error generating sales report: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

@app.post("/submit_order")
async def submit_order(order: Request):
    try:
        data = await order.json()

        tgid_token = str(data.get('tgid', '')) if data.get('tgid') else ''
        telegram_id = get_telegram_id_from_token(tgid_token) if tgid_token else None
        order_type = data.get('order_type', 'dine_in')
        source = "Telegram" if telegram_id else "Browser/Web"
        logger.info(f"Order [{order_type}/{source}] customer={data.get('customer')} telegram_id={telegram_id}")

        # Validasi & terapkan voucher
        voucher_code = data.get('voucher_code', '').strip().upper() if data.get('voucher_code') else None
        voucher_discount = 0
        if voucher_code:
            try:
                conn_v = get_connection()
                cur_v = conn_v.cursor()
                cur_v.execute("""
                    SELECT * FROM vouchers WHERE code=? AND is_active=1
                    AND (expires_at IS NULL OR expires_at >= datetime('now', 'localtime'))
                    AND (max_uses = -1 OR used_count < max_uses)
                """, (voucher_code,))
                voucher = cur_v.fetchone()
                if voucher:
                    voucher = dict(voucher)
                    # Hitung subtotal dari items
                    items_raw = data.get('items', {})
                    subtotal_calc = sum(
                        v.get('harga', 0) * v.get('qty', 0)
                        for v in items_raw.values()
                        if isinstance(v, dict)
                    )
                    if subtotal_calc >= voucher['min_order']:
                        if voucher['discount_type'] == 'percent':
                            voucher_discount = int(subtotal_calc * voucher['discount_value'] / 100)
                        else:
                            voucher_discount = voucher['discount_value']
                        # Increment used_count
                        cur_v.execute("UPDATE vouchers SET used_count=used_count+1 WHERE id=?", (voucher['id'],))
                conn_v.commit()
                conn_v.close()
            except Exception as e:
                logger.warning(f"Gagal proses voucher: {e}")

        formatted_msg = format_order_message(data, source=source)

        order_id = save_order_to_db(
            data.get('customer', 'Tamu'),
            data.get('table', '-'),
            json.dumps(data),
            data.get('total', '0'),
            data.get('generalNote', ''),
            telegram_id=telegram_id,
            order_type=order_type,
            delivery_address=data.get('delivery_address'),
            delivery_lat=data.get('delivery_lat'),
            delivery_lng=data.get('delivery_lng'),
            delivery_distance=data.get('delivery_distance'),
            delivery_fee=data.get('delivery_fee', 0),
            whatsapp=data.get('whatsapp'),
            voucher_code=voucher_code,
            voucher_discount=voucher_discount,
        )

        # Flush stock alerts
        await flush_stock_alerts()

        if ADMIN_ID and bot:
            try:
                await bot.send_message(chat_id=ADMIN_ID, text=formatted_msg, parse_mode="HTML",
                                       disable_web_page_preview=True)
            except Exception as e:
                logger.error(f"Gagal kirim notifikasi ke admin: {e}")

        # Kirim invoice ke pembeli jika ada telegram_id
        if telegram_id and bot:
            try:
                if order_id is None:
                    conn_inv = get_connection()
                    cur_inv  = conn_inv.cursor()
                    cur_inv.execute("SELECT id FROM orders ORDER BY id DESC LIMIT 1")
                    last_row = cur_inv.fetchone()
                    conn_inv.close()
                    order_id = last_row['id'] if last_row else None

                logger.info(f"🔄 Generating invoice untuk order_id={order_id}, telegram_id={telegram_id}")

                # Generate invoice gambar
                invoice_buf = generate_invoice_image(data, order_id)

                if invoice_buf:
                    from aiogram.types import BufferedInputFile
                    await bot.send_photo(
                        chat_id=telegram_id,
                        photo=BufferedInputFile(invoice_buf.read(), filename="invoice.png"),
                        caption=f"<b>Invoice #{order_id}</b>  —  {get_setting('restaurant_name', 'Restaurant')}",
                        parse_mode="HTML"
                    )
                    logger.info(f"Invoice gambar terkirim ke {telegram_id}")
                else:
                    logger.warning(f"âš⚠️ generate_invoice_image return None  —  Pillow mungkin tidak terinstall")
                    # Fallback teks jika Pillow tidak tersedia
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=f"<b>Pesanan #{order_id} diterima!</b>\n\n{formatted_msg}",
                        parse_mode="HTML"
                    )
                    logger.info(f"Invoice teks (fallback) terkirim ke {telegram_id}")
            except Exception as e:
                logger.error(f"âŒ Gagal kirim invoice ke pembeli {telegram_id}: {e}", exc_info=True)
        else:
            logger.info(f"â„¹ï¸ Invoice tidak dikirim  —  telegram_id={telegram_id}, bot={bot is not None}")

        return JSONResponse({'status': 'ok', 'message': 'Order processed', 'voucher_discount': voucher_discount})
    except Exception as e:
        logger.error(f"Error in submit_order: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.post("/call_waiter")
async def call_waiter(req: WaiterRequest):
    try:
        nama_tamu = req.nama
        table_number = req.table_number

        logger.info(f"Waiter called by {nama_tamu} at Table {table_number}")

        if ADMIN_ID and bot:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"<b>PANGGILAN PELAYAN!</b>\n\n"
                     f"<b>Tamu:</b> {nama_tamu}\n"
                     f"<b>Meja:</b> {table_number}\n\n"
                     f"Mohon segera dihampiri.",
                parse_mode="HTML"
            )
            return JSONResponse({'status': 'ok', 'message': 'Waiter has been notified'})
        else:
            return JSONResponse({'status': 'error', 'message': 'Admin ID not configured'}, status_code=500)
    except Exception as e:
        logger.error(f"Error calling waiter: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.get("/delivery", response_class=HTMLResponse)
async def delivery_page(request: Request):
    tgid = request.query_params.get('tgid', '')
    menu_data = get_menu_from_db()
    restaurant_name = get_setting('restaurant_name', 'Restaurant')
    settings = {
        'restaurant_lat': get_setting('restaurant_lat', '-6.614970215748657'),
        'restaurant_lng': get_setting('restaurant_lng', '106.80385837668723'),
        'delivery_min_fee': get_setting('delivery_min_fee', '5000'),
        'delivery_fee_per_km': get_setting('delivery_fee_per_km', '3000'),
        'delivery_min_km': get_setting('delivery_min_km', '1'),
        'delivery_max_km': get_setting('delivery_max_km', '10'),
    }
    return templates.TemplateResponse("delivery.html", {
        "request": request,
        "menu": menu_data,
        "current_year": datetime.now().year,
        "tgid": tgid,
        "settings": settings,
        "restaurant_name": restaurant_name,
        "qris_image": get_setting("qris_image", "/static/images/qris.jpg"),
        "tax_settings": {
            "enable_service": get_setting("enable_service", "1") == "1",
            "service_rate":   float(get_setting("service_rate", "10")),
            "enable_tax":     get_setting("enable_tax", "1") == "1",
            "tax_rate":       float(get_setting("tax_rate", "11")),
            "tax_label":      get_setting("tax_label", "PBJT"),
        }
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse(url="/login?next=/settings", status_code=302)
    settings = {
        'restaurant_lat':      get_setting('restaurant_lat', '-6.614970215748657'),
        'restaurant_lng':      get_setting('restaurant_lng', '106.80385837668723'),
        'restaurant_name':     get_setting('restaurant_name', 'Restaurant'),
        'delivery_min_fee':    get_setting('delivery_min_fee', '5000'),
        'delivery_fee_per_km': get_setting('delivery_fee_per_km', '3000'),
        'delivery_min_km':     get_setting('delivery_min_km', '1'),
        'delivery_max_km':     get_setting('delivery_max_km', '10'),
        'courier_whatsapp':    get_setting('courier_whatsapp', ''),
        'courier_info':        get_setting('courier_info', ''),
        'qris_image':          get_setting('qris_image', '/static/images/qris.jpg'),
        'enable_service':      get_setting('enable_service', '1'),
        'service_rate':        get_setting('service_rate', '10'),
        'enable_tax':          get_setting('enable_tax', '1'),
        'tax_rate':            get_setting('tax_rate', '11'),
        'tax_label':           get_setting('tax_label', 'PBJT'),
        'daily_report_enabled':get_setting('daily_report_enabled', '1'),
        'daily_report_hour':   get_setting('daily_report_hour', '22'),
        'daily_report_minute': get_setting('daily_report_minute', '0'),
        'owner_telegram_id':   get_setting('owner_telegram_id', ''),
    }
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "current_year": datetime.now().year,
        "restaurant_name": settings['restaurant_name'],
        "user_role": sess["role"],
        "username": sess["username"],
        "is_outlet": False,
        "outlet_id": None,
    })

@app.post("/api/settings/upload-qris")
async def upload_qris(image_file: UploadFile = File(...)):
    """Upload gambar QRIS baru."""
    try:
        if not image_file or not image_file.filename:
            return JSONResponse({'status': 'error', 'message': 'File tidak ditemukan'}, status_code=400)

        file_ext = image_file.filename.rsplit(".", 1)[-1].lower()
        if file_ext not in ('jpg', 'jpeg', 'png'):
            return JSONResponse({'status': 'error', 'message': 'Format harus JPG atau PNG'}, status_code=400)

        # Simpan ke static/images/qris_custom.jpg
        qris_path = os.path.join("static", "images", f"qris_custom.{file_ext}")
        file_content = await image_file.read()
        with open(qris_path, "wb") as f:
            f.write(file_content)

        qris_url = f"/static/images/qris_custom.{file_ext}"
        set_setting("qris_image", qris_url)
        logger.info(f"QRIS image updated: {qris_url}")

        return RedirectResponse(url="/settings?saved=1", status_code=303)
    except Exception as e:
        logger.error(f"Error uploading QRIS: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.post("/api/settings")
async def save_settings(request: Request):
    try:
        form = await request.form()
        keys = ['restaurant_lat', 'restaurant_lng', 'restaurant_name',
                'delivery_min_fee', 'delivery_fee_per_km', 'delivery_min_km', 'delivery_max_km',
                'courier_whatsapp', 'courier_info',
                'service_rate', 'tax_rate', 'tax_label',
                'daily_report_hour', 'daily_report_minute', 'owner_telegram_id']
        for key in keys:
            if key in form:
                set_setting(key, str(form[key]))
        set_setting('enable_service',      '1' if 'enable_service'      in form else '0')
        set_setting('enable_tax',          '1' if 'enable_tax'          in form else '0')
        set_setting('daily_report_enabled','1' if 'daily_report_enabled' in form else '0')

        # Update scheduler dengan jam baru
        try:
            hour   = int(get_setting('daily_report_hour', '22'))
            minute = int(get_setting('daily_report_minute', '0'))
            scheduler.reschedule_job(
                'daily_report',
                trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Jakarta")
            )
            logger.info(f"Scheduler diupdate ke jam {hour:02d}:{minute:02d}")
        except Exception as e:
            logger.warning(f"Gagal update scheduler: {e}")

        return RedirectResponse(url="/settings?saved=1", status_code=303)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.get("/api/tax-settings")
async def get_tax_settings():
    """Ambil pengaturan tax & service untuk kalkulasi di frontend."""
    return JSONResponse({
        'enable_service': get_setting('enable_service', '1') == '1',
        'service_rate':   float(get_setting('service_rate', '10')),
        'enable_tax':     get_setting('enable_tax', '1') == '1',
        'tax_rate':       float(get_setting('tax_rate', '11')),
        'tax_label':      get_setting('tax_label', 'PBJT'),
    })

@app.get("/api/delivery-fee")
async def get_delivery_fee(lat: float, lng: float):
    """Hitung ongkos kirim berdasarkan koordinat pembeli."""
    import math
    try:
        rest_lat = float(get_setting('restaurant_lat', '-6.614970215748657'))
        rest_lng = float(get_setting('restaurant_lng', '106.80385837668723'))
        min_fee     = int(get_setting('delivery_min_fee', '5000'))
        fee_per_km  = int(get_setting('delivery_fee_per_km', '3000'))
        min_km      = float(get_setting('delivery_min_km', '1'))
        max_km      = float(get_setting('delivery_max_km', '10'))

        # Haversine formula
        R = 6371
        dlat = math.radians(lat - rest_lat)
        dlng = math.radians(lng - rest_lng)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(rest_lat)) * math.cos(math.radians(lat)) * math.sin(dlng/2)**2
        distance = R * 2 * math.asin(math.sqrt(a))

        if distance > max_km:
            return JSONResponse({'status': 'error', 'message': f'Lokasi terlalu jauh (maks {max_km:.0f} km)', 'distance': round(distance, 2)})

        if distance <= min_km:
            fee = min_fee
        else:
            fee = min_fee + int((distance - min_km) * fee_per_km)

        # Buat URL Google Maps dari restaurant ke pembeli
        maps_url = f"https://www.google.com/maps/dir/{rest_lat},{rest_lng}/{lat},{lng}"

        return JSONResponse({
            'status': 'ok',
            'distance': round(distance, 2),
            'fee': fee,
            'maps_url': maps_url,
            'max_km': max_km,
        })
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.get("/couriers", response_class=HTMLResponse)
async def couriers_page(request: Request):
    """Halaman manajemen daftar kurir."""
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse(url="/login?next=/couriers", status_code=302)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM couriers ORDER BY is_active DESC, name ASC")
        couriers = [dict(row) for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching couriers: {e}")
        couriers = []
    return templates.TemplateResponse("couriers.html", {
        "request": request,
        "couriers": couriers,
        "current_year": datetime.now().year,
        "restaurant_name": get_setting('restaurant_name', 'Restaurant'),
        "user_role": sess["role"],
        "username": sess["username"],
        "is_outlet": False,
        "outlet_id": None,
    })

@app.post("/api/couriers")
async def add_courier(request: Request):
    try:
        form = await request.form()
        name = str(form.get('name', '')).strip()
        whatsapp = str(form.get('whatsapp', '')).strip()
        if not name or not whatsapp:
            return JSONResponse({'status': 'error', 'message': 'Nama dan WhatsApp wajib diisi'}, status_code=400)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO couriers (name, whatsapp) VALUES (?, ?)", (name, whatsapp))
        conn.commit()
        conn.close()
        return RedirectResponse(url="/couriers", status_code=303)
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.post("/api/couriers/delete/{courier_id}")
async def delete_courier(courier_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM couriers WHERE id=?", (courier_id,))
        conn.commit()
        conn.close()
        return RedirectResponse(url="/couriers", status_code=303)
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.post("/api/couriers/toggle/{courier_id}")
async def toggle_courier(courier_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM couriers WHERE id=?", (courier_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({'status': 'error', 'message': 'Kurir tidak ditemukan'}, status_code=404)
        new_val = 0 if row['is_active'] == 1 else 1
        cursor.execute("UPDATE couriers SET is_active=? WHERE id=?", (new_val, courier_id))
        conn.commit()
        conn.close()
        return JSONResponse({'status': 'ok', 'is_active': new_val})
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.get("/api/couriers/list")
async def list_couriers():
    """API untuk ambil daftar kurir aktif (dipakai di modal assign kurir)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, whatsapp FROM couriers WHERE is_active=1 ORDER BY name")
        couriers = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return JSONResponse({'status': 'ok', 'couriers': couriers})
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.get("/api/orders/status-poll")
async def poll_order_statuses(date: str = None):
    """API polling  —  kembalikan status terbaru semua order hari ini + order baru.
    Dipakai dashboard admin untuk update real-time tanpa full reload."""
    try:
        if date:
            try:
                target_date = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                target_date = datetime.now()
        else:
            target_date = datetime.now()

        today_start = target_date.strftime('%Y-%m-%d 00:00:00')
        today_end   = target_date.strftime('%Y-%m-%d 23:59:59')

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, status, courier_name, order_type,
                   customer_name, table_number, total_price,
                   items, note, created_at, whatsapp,
                   delivery_address, delivery_distance, delivery_fee,
                   delivery_lat, delivery_lng
            FROM orders
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at DESC
        """, (today_start, today_end))
        rows = cursor.fetchall()
        conn.close()

        orders = []
        for r in rows:
            o = dict(r)
            # Parse items summary
            items_raw = o.get('items', '{}')
            try:
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                    actual = items_parsed['items']
                else:
                    actual = items_parsed
                summary = ", ".join([f"{k} x{v.get('qty',0)}" for k,v in actual.items() if isinstance(v,dict) and v.get('qty',0)>0])
            except Exception:
                summary = " — "
            o['items_summary'] = summary or " — "
            orders.append(o)

        return JSONResponse({'status': 'ok', 'orders': orders})
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.post("/api/orders/assign-courier/{order_id}")
async def assign_courier(order_id: int, request: Request):
    try:
        body = await request.json()
        courier_name = body.get('courier_name', '').strip()
        courier_wa   = body.get('courier_whatsapp', '').strip()
        if not courier_name:
            return JSONResponse({'status': 'error', 'message': 'Nama kurir wajib diisi'}, status_code=400)

        import secrets
        courier_token = secrets.token_urlsafe(12)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET courier_name=?, courier_token=?, status='on_delivery' WHERE id=?",
            (courier_name, courier_token, order_id)
        )
        cursor.execute("SELECT customer_name, telegram_id, delivery_address FROM orders WHERE id=?", (order_id,))
        order_row = cursor.fetchone()
        conn.commit()
        conn.close()

        courier_url = f"{BASE_URL}/courier/{order_id}/{courier_token}"

        if order_row and order_row['telegram_id'] and bot:
            try:
                # Format nomor WA kurir untuk link wa.me
                wa_clean = courier_wa.replace('+', '').replace('-', '').replace(' ', '')
                if wa_clean.startswith('0'):
                    wa_clean = '62' + wa_clean[1:]
                wa_link = f"https://wa.me/{wa_clean}" if wa_clean else None

                notif_text = (
                    f"<b>Pesanan Anda sedang dalam perjalanan!</b>\n\n"
                    f"<b>Kurir:</b> {courier_name}\n"
                )
                if courier_wa:
                    notif_text += f"<b>WhatsApp Kurir:</b> {courier_wa}\n"
                    if wa_link:
                        notif_text += f"💬 <a href='{wa_link}'>Hubungi Kurir via WhatsApp</a>\n"
                notif_text += (
                    f"<b>Alamat:</b> {order_row['delivery_address'] or '-'}\n\n"
                    f"Kurir sedang menuju lokasi Anda."
                )

                await bot.send_message(
                    chat_id=order_row['telegram_id'],
                    text=notif_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.warning(f"Gagal kirim notifikasi ke pembeli: {e}")

        return JSONResponse({'status': 'ok', 'courier_url': courier_url})
    except Exception as e:
        logger.error(f"Error assigning courier: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.get("/courier/{order_id}/{token}", response_class=HTMLResponse)
async def courier_page(order_id: int, token: str, request: Request):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id=? AND courier_token=?", (order_id, token))
        order = cursor.fetchone()
        conn.close()
        if not order:
            return HTMLResponse("<h2 style='font-family:sans-serif;padding:40px'>Link tidak valid atau sudah kadaluarsa.</h2>", status_code=404)
        order = dict(order)

        # Parse items JSON dengan aman untuk dikirim ke template
        import json as _json
        items_raw = order.get('items', '{}')
        try:
            items_parsed = _json.loads(items_raw) if isinstance(items_raw, str) else items_raw
            # Handle nested items
            if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                items_parsed = items_parsed['items']
        except Exception:
            items_parsed = {}

        # Serialize kembali sebagai JSON string yang aman untuk embed di JS
        items_json_str = _json.dumps(items_parsed)

        restaurant_name = get_setting('restaurant_name', 'Restaurant')
        restaurant_lat  = get_setting('restaurant_lat', '-6.614970215748657')
        restaurant_lng  = get_setting('restaurant_lng', '106.80385837668723')
        return templates.TemplateResponse("courier.html", {
            "request": request,
            "order": order,
            "items_json": items_json_str,
            "restaurant_name": restaurant_name,
            "restaurant_lat": restaurant_lat,
            "restaurant_lng": restaurant_lng,
            "current_year": datetime.now().year,
        })
    except Exception as e:
        logger.error(f"Courier page error: {e}")
        return HTMLResponse(f"<h2 style='font-family:sans-serif;padding:40px'>Error: {str(e)}</h2>", status_code=500)

@app.post("/courier/{order_id}/{token}/confirm")
async def courier_confirm(order_id: int, token: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id=? AND courier_token=?", (order_id, token))
        order = cursor.fetchone()
        if not order:
            return JSONResponse({'status': 'error', 'message': 'Token tidak valid'}, status_code=404)
        order = dict(order)
        if order['status'] == 'completed':
            return JSONResponse({'status': 'already', 'message': 'Pesanan sudah dikonfirmasi'})
        cursor.execute("UPDATE orders SET status='completed' WHERE id=?", (order_id,))
        conn.commit()
        conn.close()

        if order.get('telegram_id') and bot:
            try:
                await bot.send_message(
                    chat_id=order['telegram_id'],
                    text=f"<b>Pesanan Anda telah sampai!</b>\n\n"
                         f"Terima kasih telah memesan. Selamat menikmati! 😊\n\n"
                         f" —  {get_setting('restaurant_name', 'Restaurant')}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Gagal kirim notifikasi selesai ke pembeli: {e}")

        if ADMIN_ID and bot:
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"<b>Pesanan #{order_id} selesai dikirim!</b>\n\n"
                         f"👤 Pembeli: {order.get('customer_name', '-')}\n"
                         f"🚴 Kurir: {order.get('courier_name', '-')}\n"
                         f"📍 Alamat: {order.get('delivery_address', '-')}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Gagal kirim notifikasi ke admin: {e}")

        return JSONResponse({'status': 'ok'})
    except Exception as e:
        logger.error(f"Error confirming delivery: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

async def test_notif(telegram_id: int):
    """Test kirim notifikasi ke telegram_id tertentu."""
    if not bot:
        return {"status": "error", "message": "Bot tidak aktif"}
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text="<b>Test Notifikasi Berhasil!</b>\n\nBot dapat mengirim pesan ke Anda.",
            parse_mode="HTML"
        )
        return {"status": "ok", "message": f"Pesan dikirim ke {telegram_id}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/send-daily-report")
async def send_report_now():
    """Kirim daily report sekarang (untuk test)."""
    await send_daily_report()
    return {"status": "ok", "message": "Daily report dikirim"}


@app.get("/api/backup-now")
async def backup_now():
    """Jalankan backup database sekarang (manual)."""
    result = await backup_database()
    return result


@app.post("/api/reset-orders")
async def reset_orders(request: Request):
    """Reset (hapus) semua data orders. Backup otomatis dibuat sebelum reset."""
    try:
        body = await request.json()
        confirm = body.get('confirm', '')
        if confirm != 'RESET':
            return JSONResponse(
                {'status': 'error', 'message': 'Konfirmasi tidak valid. Ketik RESET untuk melanjutkan.'},
                status_code=400
            )

        # Backup dulu sebelum reset
        backup_result = await backup_database()
        logger.info(f"Backup sebelum reset: {backup_result}")

        # Reset tabel orders, order_ratings, item_reviews, stock_logs
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM order_ratings")
        cursor.execute("DELETE FROM item_reviews")
        cursor.execute("DELETE FROM stock_logs")
        # Reset auto-increment
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders','order_ratings','item_reviews','stock_logs')")
        conn.commit()

        # Hitung berapa data yang dihapus
        deleted_count = cursor.rowcount
        conn.close()

        rest_name = get_setting('restaurant_name', 'Restaurant')
        now_str   = datetime.now().strftime('%d %B %Y, %H:%M')

        # Notifikasi ke admin
        if bot and ADMIN_ID:
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"<b>DATABASE ORDERS DIRESET</b>\n\n"
                         f"🏪 {rest_name}\n"
                         f"📅 {now_str}\n\n"
                         f"Semua data pesanan telah dihapus.\n"
                         f"💾 Backup tersimpan: <code>{backup_result.get('file', '-')}</code>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Gagal kirim notif reset: {e}")

        logger.info(f"Database orders direset oleh admin")
        return JSONResponse({
            'status': 'ok',
            'message': 'Data pesanan berhasil direset',
            'backup_file': backup_result.get('file', '-')
        })

    except Exception as e:
        logger.error(f"Error reset orders: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.get("/api/backup-list")
async def backup_list():
    """Ambil daftar file backup yang tersedia."""
    try:
        files = []
        for fname in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if fname.startswith("restaurant_") and fname.endswith(".db"):
                fpath = os.path.join(BACKUP_DIR, fname)
                size_kb = os.path.getsize(fpath) / 1024
                files.append({
                    'name': fname,
                    'size_kb': round(size_kb, 1),
                    'date': fname.replace("restaurant_", "").replace(".db", "")
                })
        return JSONResponse({'status': 'ok', 'backups': files})
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.post("/api/change-password")
async def change_password(request: Request):
    """Ganti password admin/owner. Hanya bisa dilakukan oleh admin yang sedang login."""
    sess = _require_admin(request)
    if not sess:
        return JSONResponse({'status': 'error', 'message': 'Unauthorized'}, status_code=401)
    try:
        body = await request.json()
        target_user = body.get('username', '').strip().lower()
        new_password = body.get('new_password', '').strip()

        if not target_user or not new_password:
            return JSONResponse({'status': 'error', 'message': 'Username dan password wajib diisi'}, status_code=400)
        if len(new_password) < 6:
            return JSONResponse({'status': 'error', 'message': 'Password minimal 6 karakter'}, status_code=400)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM admin_users WHERE username=?", (target_user,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return JSONResponse({'status': 'error', 'message': 'User tidak ditemukan'}, status_code=404)

        cursor.execute(
            "UPDATE admin_users SET password_hash=? WHERE username=?",
            (_hash_password(new_password), target_user)
        )
        conn.commit()
        conn.close()
        logger.info(f"Password {target_user} diubah oleh {sess['username']}")
        return JSONResponse({'status': 'ok', 'message': f'Password {target_user} berhasil diubah'})
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.get("/set_webhook")
async def set_webhook_manual():
    if not bot or not BASE_URL:
        return {"status": "error", "message": "Bot or BASE_URL not configured"}

    webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
    try:
        await bot.set_webhook(
            webhook_url,
            allowed_updates=["message", "callback_query", "inline_query"]
        )
        return {"status": "ok", "message": f"Webhook set to {webhook_url}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/set_outlet_webhooks")
async def set_outlet_webhooks_manual():
    """Reset webhook semua outlet — panggil setelah URL tunnel berubah."""
    results = []
    outlets = get_all_outlets(active_only=True)
    for outlet in outlets:
        try:
            result = await register_outlet_bot(outlet["id"], outlet["bot_token"])
            results.append({"outlet_id": outlet["id"], "name": outlet["name"], "status": "ok" if result else "error"})
        except Exception as e:
            results.append({"outlet_id": outlet["id"], "name": outlet["name"], "status": "error", "message": str(e)})
    return {"status": "ok", "results": results}

@app.post(WEBHOOK_PATH)
async def bot_webhook(update: dict):
    try:
        telegram_update = types.Update(**update)
        await dp.feed_update(bot, telegram_update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return {"ok": True}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROUTES  —  DASHBOARD ADMIN
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse(url=f"/login?next=/dashboard", status_code=302)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM menu_items ORDER BY category, name")
        rows = cursor.fetchall()

        # Ambil rating per item
        cursor.execute("""
            SELECT menu_item_name, AVG(rating) as avg_rating, COUNT(*) as total_reviews
            FROM item_reviews GROUP BY menu_item_name
        """)
        item_ratings = {row['menu_item_name']: {
            'avg': round(row['avg_rating'], 1),
            'count': row['total_reviews']
        } for row in cursor.fetchall()}

        conn.close()
        flat_menu = [dict(row) for row in rows]
        # Tambahkan rating ke setiap item
        for item in flat_menu:
            rating_info = item_ratings.get(item['name'], {})
            item['avg_rating'] = rating_info.get('avg', 0)
            item['review_count'] = rating_info.get('count', 0)
    except Exception as e:
        logger.error(f"Error fetching all menu for dashboard: {e}")
        flat_menu = []
    restaurant_name = get_setting('restaurant_name', 'Restaurant')
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "items": flat_menu,
        "current_year": datetime.now().year,
        "restaurant_name": restaurant_name,
        "user_role": sess["role"],
        "username": sess["username"],
        "is_outlet": False,
        "outlet_id": None,
    })

@app.post("/api/menu")
async def add_menu_item(
    name: str = Form(...),
    category: str = Form(...),
    cuisine: str = Form(None),
    price: int = Form(...),
    description: str = Form(""),
    image_file: UploadFile = File(None),
):
    try:
        image_url = ""
        if image_file and image_file.filename:
            # Simpan gambar ke folder static/images/menu/
            file_ext = image_file.filename.rsplit(".", 1)[-1].lower()
            file_name = f"{int(time.time())}_{name.replace(' ', '_')}.{file_ext}"
            file_path = os.path.join(UPLOAD_DIR, file_name)

            file_content = await image_file.read()
            with open(file_path, "wb") as f:
                f.write(file_content)

            # URL relatif yang bisa diakses dari browser
            image_url = f"/static/images/menu/{file_name}"
            logger.info(f"Image saved: {file_path}")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO menu_items (name, category, cuisine, price, description, image_url, is_available)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (name, category, cuisine, price, description, image_url))
        conn.commit()
        conn.close()

        return RedirectResponse(url="/dashboard", status_code=303)
    except Exception as e:
        logger.error(f"Error adding menu: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.post("/api/menu/delete/{item_id}")
async def delete_menu_item(item_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Ambil image_url dulu untuk hapus file-nya juga
        cursor.execute("SELECT image_url FROM menu_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if row and row['image_url']:
            img_path = row['image_url'].lstrip('/')
            if os.path.exists(img_path):
                os.remove(img_path)
                logger.info(f"Deleted image: {img_path}")

        cursor.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

        return RedirectResponse(url="/dashboard", status_code=303)
    except Exception as e:
        logger.error(f"Error deleting menu: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.post("/api/menu/edit/{item_id}")
async def edit_menu_item(
    item_id: int,
    name: str = Form(...),
    category: str = Form(...),
    cuisine: str = Form(None),
    price: int = Form(...),
    description: str = Form(""),
    image_file: UploadFile = File(None),
):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Ambil data lama
        cursor.execute("SELECT image_url FROM menu_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({'status': 'error', 'message': 'Item not found'}, status_code=404)

        old_image_url = row['image_url'] if row else ''
        new_image_url = old_image_url  # default: tetap pakai gambar lama

        # Jika ada gambar baru, simpan dan hapus yang lama
        if image_file and image_file.filename:
            file_ext = image_file.filename.rsplit(".", 1)[-1].lower()
            file_name = f"{int(time.time())}_{name.replace(' ', '_')}.{file_ext}"
            file_path = os.path.join(UPLOAD_DIR, file_name)

            file_content = await image_file.read()
            with open(file_path, "wb") as f:
                f.write(file_content)

            new_image_url = f"/static/images/menu/{file_name}"
            logger.info(f"New image saved: {file_path}")

            # Hapus gambar lama jika ada
            if old_image_url:
                old_path = old_image_url.lstrip('/')
                if os.path.exists(old_path):
                    os.remove(old_path)
                    logger.info(f"Old image deleted: {old_path}")

        cursor.execute("""
            UPDATE menu_items
            SET name=?, category=?, cuisine=?, price=?, description=?, image_url=?
            WHERE id=?
        """, (name, category, cuisine, price, description, new_image_url, item_id))
        conn.commit()
        conn.close()

        return RedirectResponse(url="/dashboard", status_code=303)
    except Exception as e:
        logger.error(f"Error editing menu: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.post("/api/menu/toggle/{item_id}")
async def toggle_menu_item(item_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT is_available FROM menu_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({'status': 'error', 'message': 'Item not found'}, status_code=404)

        new_val = 0 if row['is_available'] == 1 else 1
        cursor.execute("UPDATE menu_items SET is_available=? WHERE id=?", (new_val, item_id))
        conn.commit()
        conn.close()

        return JSONResponse({'status': 'ok', 'is_available': new_val})
    except Exception as e:
        logger.error(f"Error toggling menu: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, date: str = None, order_type: str = None):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse(url="/login?next=/orders", status_code=302)
    try:
        if date:
            try:
                target_date = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                target_date = datetime.now()
        else:
            target_date = datetime.now()

        today_start = target_date.strftime('%Y-%m-%d 00:00:00')
        today_end   = target_date.strftime('%Y-%m-%d 23:59:59')

        conn = get_connection()
        cursor = conn.cursor()

        if order_type and order_type in ('dine_in', 'delivery'):
            cursor.execute("""
                SELECT * FROM orders WHERE created_at >= ? AND created_at <= ? AND order_type = ?
                ORDER BY created_at DESC
            """, (today_start, today_end, order_type))
        else:
            cursor.execute("""
                SELECT * FROM orders WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at DESC
            """, (today_start, today_end))

        raw_orders = [dict(row) for row in cursor.fetchall()]
        conn.close()

        orders = []
        total_revenue = 0
        for order in raw_orders:
            items_raw = order.get('items', '{}')
            if isinstance(items_raw, str):
                try:
                    items_parsed = json.loads(items_raw)
                except Exception:
                    items_parsed = {}
            else:
                items_parsed = items_raw

            if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                actual_items = items_parsed['items']
            else:
                actual_items = items_parsed

            items_summary = []
            for item_name, details in actual_items.items():
                if isinstance(details, dict):
                    qty = details.get('qty', 0)
                    if qty > 0:
                        items_summary.append(f"{item_name} x{qty}")

            order['items_summary'] = ", ".join(items_summary) if items_summary else " — "
            order['items_count']   = len(items_summary)
            orders.append(order)

            if order.get('status') not in ('cancelled',):
                total_revenue += order.get('total_price', 0)

        rest_lat = get_setting('restaurant_lat', '-6.614970215748657')
        rest_lng = get_setting('restaurant_lng', '106.80385837668723')

        return templates.TemplateResponse("orders.html", {
            "request": request,
            "orders": orders,
            "total_orders": len(orders),
            "total_revenue": total_revenue,
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "date_display": target_date.strftime("%d %B %Y"),
            "current_year": datetime.now().year,
            "filter_type": order_type or 'all',
            "restaurant_lat": rest_lat,
            "restaurant_lng": rest_lng,
            "restaurant_name": get_setting('restaurant_name', 'Restaurant'),
            "user_role": sess["role"],
            "username": sess["username"],
            "is_outlet": False,
            "outlet_id": None,
        })
    except Exception as e:
        logger.error(f"Error loading orders page: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

@app.post("/api/orders/status/{order_id}")
async def update_order_status(order_id: int, request: Request):
    try:
        body = await request.json()
        new_status = body.get('status', '')
        valid_statuses = ['pending', 'preparing', 'on_delivery', 'served', 'completed', 'cancelled']
        if new_status not in valid_statuses:
            return JSONResponse({'status': 'error', 'message': 'Invalid status'}, status_code=400)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT customer_name, table_number, telegram_id, order_type FROM orders WHERE id=?", (order_id,))
        order_row = cursor.fetchone()
        cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
        conn.commit()
        conn.close()

        if order_row and order_row['telegram_id'] and bot:
            customer_name = order_row['customer_name'] or 'Tamu'
            order_type    = order_row['order_type'] or 'dine_in'
            table_number  = order_row['table_number'] or '-'

            if order_type == 'delivery':
                status_messages = {
                    'pending':     "<b>Pesanan Anda sedang menunggu konfirmasi.</b>",
                    'preparing':   "<b>Pesanan Anda sedang diproses!</b>\nDapur kami sedang menyiapkan hidangan Anda.",
                    'on_delivery': "<b>Pesanan Anda sedang dalam perjalanan!</b>\nKurir sedang menuju lokasi Anda.",
                    'completed':   "<b>Pesanan Anda telah sampai!</b>\nSelamat menikmati hidangan Anda. 😊",
                    'cancelled':   "<b>Pesanan Anda dibatalkan.</b>\nMohon hubungi staf kami untuk informasi lebih lanjut.",
                }
            else:
                status_messages = {
                    'pending':   "<b>Pesanan Anda sedang menunggu konfirmasi.</b>",
                    'preparing': "<b>Pesanan Anda sedang diproses!</b>\nDapur kami sedang menyiapkan hidangan Anda.",
                    'served':    "<b>Pesanan Anda sudah disajikan!</b>\nSelamat menikmati hidangan Anda. 😊",
                    'cancelled': "<b>Pesanan Anda dibatalkan.</b>\nMohon hubungi staf kami untuk informasi lebih lanjut.",
                }

            notif_text = (
                f"<b>UPDATE PESANAN</b>\n\n"
                f"<b>Nama:</b> {customer_name}\n\n"
                f"{status_messages.get(new_status, f'Status: {new_status}')}"
            )

            try:
                await bot.send_message(chat_id=order_row['telegram_id'], text=notif_text, parse_mode="HTML")
                logger.info(f"Notifikasi '{new_status}' dikirim ke {order_row['telegram_id']}")
            except Exception as e:
                logger.warning(f"Gagal kirim notifikasi ke pembeli: {e}")

            # Kirim permintaan rating jika status served/completed
            if new_status in ('served', 'completed'):
                try:
                    builder = InlineKeyboardBuilder()
                    for r in range(1, 6):
                        # ro_{order_id}_{rating}  —  pendek, max ~15 chars, aman di bawah 64 byte
                        builder.button(
                            text=f"{'⭐' * r}",
                            callback_data=f"ro_{order_id}_{r}"
                        )
                    builder.adjust(5)
                    await bot.send_message(
                        chat_id=order_row['telegram_id'],
                        text=f"<b>Bagaimana pesanan Anda?</b>\n\nBerikan rating 1-5 ⭐ untuk pesanan #{order_id}:",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Gagal kirim rating request: {e}")

        return JSONResponse({'status': 'ok'})
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROUTES  —  STOCK MANAGEMENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/api/menu/stock/{item_id}")
async def update_stock(item_id: int, request: Request):
    """Update nilai stok menu item."""
    try:
        body = await request.json()
        new_stock = int(body.get('stock', -1))
        stock_alert = int(body.get('stock_alert', 5))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, stock FROM menu_items WHERE id=?", (item_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({'status': 'error', 'message': 'Item tidak ditemukan'}, status_code=404)

        old_stock = row['stock']
        cursor.execute(
            "UPDATE menu_items SET stock=?, stock_alert=? WHERE id=?",
            (new_stock, stock_alert, item_id)
        )
        # Jika stok diisi ulang, aktifkan kembali
        if new_stock > 0 or new_stock == -1:
            cursor.execute("UPDATE menu_items SET is_available=1 WHERE id=? AND is_available=0", (item_id,))

        # Log perubahan stok
        change = new_stock - old_stock if old_stock != -1 and new_stock != -1 else 0
        cursor.execute(
            "INSERT INTO stock_logs (menu_item_id, change, reason) VALUES (?, ?, ?)",
            (item_id, change, "Manual update")
        )
        conn.commit()
        conn.close()

        return JSONResponse({'status': 'ok', 'stock': new_stock, 'stock_alert': stock_alert})
    except Exception as e:
        logger.error(f"Error updating stock: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROUTES  —  RATINGS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/ratings")
async def get_ratings():
    """Ambil ringkasan rating per menu item."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Rating keseluruhan per order
        cursor.execute("""
            SELECT o.id, o.customer_name, r.overall_rating, r.comment, r.created_at
            FROM order_ratings r
            JOIN orders o ON o.id = r.order_id
            ORDER BY r.created_at DESC
            LIMIT 50
        """)
        order_ratings = [dict(row) for row in cursor.fetchall()]

        # Rating per item
        cursor.execute("""
            SELECT menu_item_name,
                   AVG(rating) as avg_rating,
                   COUNT(*) as total_reviews
            FROM item_reviews
            GROUP BY menu_item_name
        """)
        item_ratings = {row['menu_item_name']: {
            'avg': round(row['avg_rating'], 1),
            'count': row['total_reviews']
        } for row in cursor.fetchall()}

        conn.close()
        return JSONResponse({
            'status': 'ok',
            'order_ratings': order_ratings,
            'item_ratings': item_ratings
        })
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROUTES  —  VOUCHER MANAGEMENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/voucher/check")
async def check_voucher(code: str, subtotal: int = 0):
    """Validasi voucher dan kembalikan jumlah diskon."""
    try:
        code = code.strip().upper()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM vouchers WHERE code=? AND is_active=1
            AND (expires_at IS NULL OR expires_at >= datetime('now', 'localtime'))
            AND (max_uses = -1 OR used_count < max_uses)
        """, (code,))
        voucher = cursor.fetchone()
        conn.close()

        if not voucher:
            return JSONResponse({'status': 'error', 'message': 'Voucher tidak valid atau sudah kadaluarsa'})

        voucher = dict(voucher)
        if subtotal < voucher['min_order']:
            return JSONResponse({
                'status': 'error',
                'message': f"Minimum order Rp {voucher['min_order']:,}".replace(',', '.')
            })

        if voucher['discount_type'] == 'percent':
            discount = int(subtotal * voucher['discount_value'] / 100)
        else:
            discount = voucher['discount_value']

        return JSONResponse({
            'status': 'ok',
            'discount': discount,
            'discount_type': voucher['discount_type'],
            'discount_value': voucher['discount_value'],
            'code': voucher['code'],
        })
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.post("/api/vouchers")
async def create_voucher(request: Request):
    """Buat voucher baru (admin)."""
    try:
        form = await request.form()
        code = str(form.get('code', '')).strip().upper()
        discount_type = str(form.get('discount_type', 'percent'))
        discount_value = int(form.get('discount_value', 0))
        min_order = int(form.get('min_order', 0))
        max_uses = int(form.get('max_uses', -1))
        expires_at = str(form.get('expires_at', '')).strip() or None

        if not code or discount_value <= 0:
            return JSONResponse({'status': 'error', 'message': 'Kode dan nilai diskon wajib diisi'}, status_code=400)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vouchers (code, discount_type, discount_value, min_order, max_uses, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, discount_type, discount_value, min_order, max_uses, expires_at))
        conn.commit()
        conn.close()
        return RedirectResponse(url="/vouchers", status_code=303)
    except Exception as e:
        logger.error(f"Error creating voucher: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.post("/api/vouchers/delete/{voucher_id}")
async def delete_voucher(voucher_id: int):
    """Hapus voucher."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vouchers WHERE id=?", (voucher_id,))
        conn.commit()
        conn.close()
        return RedirectResponse(url="/vouchers", status_code=303)
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.post("/api/vouchers/toggle/{voucher_id}")
async def toggle_voucher(voucher_id: int):
    """Toggle aktif/nonaktif voucher."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM vouchers WHERE id=?", (voucher_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({'status': 'error', 'message': 'Voucher tidak ditemukan'}, status_code=404)
        new_val = 0 if row['is_active'] == 1 else 1
        cursor.execute("UPDATE vouchers SET is_active=? WHERE id=?", (new_val, voucher_id))
        conn.commit()
        conn.close()
        return JSONResponse({'status': 'ok', 'is_active': new_val})
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


@app.get("/vouchers", response_class=HTMLResponse)
async def vouchers_page(request: Request):
    """Halaman manajemen voucher."""
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse(url="/login?next=/vouchers", status_code=302)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vouchers ORDER BY created_at DESC")
        vouchers = [dict(row) for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching vouchers: {e}")
        vouchers = []
    return templates.TemplateResponse("vouchers.html", {
        "request": request,
        "vouchers": vouchers,
        "current_year": datetime.now().year,
        "restaurant_name": get_setting('restaurant_name', 'Restaurant'),
        "user_role": sess["role"],
        "username": sess["username"],
        "is_outlet": False,
        "outlet_id": None,
    })


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROUTES  —  RIWAYAT PELANGGAN
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    """Halaman riwayat pelanggan."""
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse(url="/login?next=/customers", status_code=302)
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Ambil semua orders yang tidak cancelled
        cursor.execute("""
            SELECT customer_name, telegram_id, whatsapp, order_type,
                   total_price, items, created_at, status
            FROM orders
            WHERE status != 'cancelled'
            ORDER BY created_at DESC
        """)
        all_orders = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Agregasi per pelanggan (group by nama + telegram_id)
        customer_map = {}
        for order in all_orders:
            name = (order.get('customer_name') or 'Tamu').strip()
            tg_id = order.get('telegram_id')
            wa    = order.get('whatsapp') or ''

            # Key unik: telegram_id jika ada, else nama
            key = str(tg_id) if tg_id else name.lower()

            if key not in customer_map:
                customer_map[key] = {
                    'name': name,
                    'telegram_id': tg_id,
                    'whatsapp': wa,
                    'total_orders': 0,
                    'dine_in_count': 0,
                    'delivery_count': 0,
                    'total_spent': 0,
                    'item_counts': {},
                    'last_order': order.get('created_at', ''),
                }
            else:
                # Update nama & wa jika ada yang lebih baru
                if tg_id and not customer_map[key]['telegram_id']:
                    customer_map[key]['telegram_id'] = tg_id
                if wa and not customer_map[key]['whatsapp']:
                    customer_map[key]['whatsapp'] = wa

            c = customer_map[key]
            c['total_orders'] += 1
            c['total_spent']  += order.get('total_price', 0) or 0

            if order.get('order_type') == 'delivery':
                c['delivery_count'] += 1
            else:
                c['dine_in_count'] += 1

            # Hitung item favorit
            try:
                items_raw = order.get('items', '{}')
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                if 'items' in items_parsed and isinstance(items_parsed['items'], dict):
                    actual = items_parsed['items']
                else:
                    actual = items_parsed
                for item_name, details in actual.items():
                    if isinstance(details, dict):
                        qty = details.get('qty', 0)
                        if qty > 0:
                            c['item_counts'][item_name] = c['item_counts'].get(item_name, 0) + qty
            except Exception:
                pass

        # Konversi ke list, tambah fav_items, sort by total_orders desc
        customers = []
        for c in customer_map.values():
            fav = sorted(c['item_counts'].items(), key=lambda x: x[1], reverse=True)
            c['fav_items'] = [name for name, _ in fav[:5]]
            del c['item_counts']
            customers.append(c)

        customers.sort(key=lambda x: x['total_orders'], reverse=True)

        return templates.TemplateResponse("customers.html", {
            "request": request,
            "customers": customers,
            "current_year": datetime.now().year,
            "restaurant_name": get_setting('restaurant_name', 'Restaurant'),
            "user_role": sess["role"],
            "username": sess["username"],
            "is_outlet": False,
            "outlet_id": None,
        })
    except Exception as e:
        logger.error(f"Error loading customers page: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)


@app.post("/api/customers/send-message")
async def send_customer_message(request: Request):
    """Kirim pesan promo/info ke pelanggan via Telegram."""
    sess = _require_admin(request)
    if not sess:
        return JSONResponse({'status': 'error', 'message': 'Unauthorized'}, status_code=401)
    try:
        body = await request.json()
        telegram_id = int(body.get('telegram_id', 0))
        message     = str(body.get('message', '')).strip()
        name        = str(body.get('name', 'Pelanggan'))

        if not telegram_id or not message:
            return JSONResponse({'status': 'error', 'message': 'telegram_id dan pesan wajib diisi'}, status_code=400)

        if not bot:
            return JSONResponse({'status': 'error', 'message': 'Bot tidak aktif'}, status_code=500)

        rest_name = get_setting('restaurant_name', 'Restaurant')
        full_msg = (
            f"<b>Pesan dari {rest_name}</b>\n\n"
            f"{message}"
        )

        await bot.send_message(
            chat_id=telegram_id,
            text=full_msg,
            parse_mode="HTML"
        )
        logger.info(f"Pesan terkirim ke pelanggan {name} ({telegram_id})")
        return JSONResponse({'status': 'ok', 'message': f'Pesan terkirim ke {name}'})

    except Exception as e:
        logger.error(f"Error sending customer message: {e}")
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MULTI-OUTLET  —  OWNER SESSION STORE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_owner_sessions = {}

def _create_owner_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    save_session(token, 'owner', username)
    return token

def _get_owner_session(request):
    token = request.cookies.get("sgo_owner_session")
    if not token: return None
    row = load_session(token)
    if not row or row['session_type'] != 'owner': return None
    return {"username": row['username']}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def get_outlet_setting(outlet_id: int, key: str, default: str = "") -> str:
    try:
        import database as _db
        original = _db.DB_PATH
        _db.DB_PATH = get_outlet_db_path(outlet_id)
        val = _db.get_setting(key, default)
        _db.DB_PATH = original
        return val
    except Exception:
        return default

def get_outlet_stats_today(outlet_id: int) -> dict:
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN status != 'cancelled' THEN total_price ELSE 0 END) as rev,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
            FROM orders WHERE created_at LIKE ?
        """, (f"{today}%",))
        row = dict(cursor.fetchone())
        conn.close()
        return {
            "orders": row.get("cnt") or 0,
            "revenue": row.get("rev") or 0,
            "pending": row.get("pending") or 0,
        }
    except Exception:
        return {"orders": 0, "revenue": 0, "pending": 0}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MULTI-OUTLET  —  OWNER ROUTES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/owner/login", response_class=HTMLResponse)
async def owner_login_page(request: Request):
    sess = _get_owner_session(request)
    if sess:
        return RedirectResponse(url="/owner/dashboard", status_code=302)
    return templates.TemplateResponse("owner_login.html", {
        "request": request,
        "error": None,
        "username": "",
        "current_year": datetime.now().year,
    })

@app.post("/owner/login")
async def owner_login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip().lower()
    password = str(form.get("password", ""))
    user = verify_owner(username, password)
    if user:
        token = _create_owner_session(username)
        response = RedirectResponse(url="/owner/dashboard", status_code=302)
        response.set_cookie("sgo_owner_session", token, max_age=7*86400, httponly=True, samesite="lax")
        logger.info(f"Owner login: {username}")
        return response
    return templates.TemplateResponse("owner_login.html", {
        "request": request,
        "error": "Username atau password salah.",
        "username": username,
        "current_year": datetime.now().year,
    }, status_code=401)

@app.get("/owner/logout")
async def owner_logout(request: Request):
    token = request.cookies.get("sgo_owner_session")
    if token:
        delete_session(token)
    response = RedirectResponse(url="/owner/login", status_code=302)
    response.delete_cookie("sgo_owner_session")
    return response

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request):
    sess = _get_owner_session(request)
    if not sess:
        return RedirectResponse(url="/owner/login", status_code=302)
    try:
        outlets = get_all_outlets(active_only=False)

        # Tambahkan "Outlet Utama" (restaurant.db) sebagai outlet pertama
        # Ambil stats dari database utama
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            conn_main = get_connection()
            cur_main  = conn_main.cursor()
            cur_main.execute("""
                SELECT COUNT(*) as cnt,
                       SUM(CASE WHEN status != 'cancelled' THEN total_price ELSE 0 END) as rev,
                       SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
                FROM orders WHERE created_at LIKE ?
            """, (f"{today}%",))
            row_main = dict(cur_main.fetchone())
            conn_main.close()
            main_stats = {
                "orders":  row_main.get("cnt") or 0,
                "revenue": row_main.get("rev") or 0,
                "pending": row_main.get("pending") or 0,
            }
        except Exception:
            main_stats = {"orders": 0, "revenue": 0, "pending": 0}

        main_outlet = {
            "id": "main",
            "name": get_setting("restaurant_name", "Outlet Utama"),
            "is_active": 1,
            "stats": main_stats,
            "is_main": True,
        }

        # Gabungkan outlet utama + outlet multi
        all_outlets = [main_outlet] + outlets

        total_revenue = main_stats["revenue"]
        total_orders  = main_stats["orders"]
        total_pending = main_stats["pending"]

        for outlet in outlets:
            stats = get_outlet_stats_today(outlet["id"])
            outlet["stats"] = stats
            outlet["is_main"] = False
            if outlet["is_active"]:
                total_revenue += stats["revenue"]
                total_orders  += stats["orders"]
                total_pending += stats["pending"]

        return templates.TemplateResponse("owner_dashboard.html", {
            "request": request,
            "outlets": all_outlets,
            "username": sess["username"],
            "today": datetime.now().strftime("%d %B %Y"),
            "current_year": datetime.now().year,
            "summary": {
                "total_revenue": total_revenue,
                "total_orders":  total_orders,
                "total_pending": total_pending,
            }
        })
    except Exception as e:
        logger.error(f"Owner dashboard error: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

@app.post("/owner/api/outlets")
async def owner_create_outlet(request: Request):
    sess = _get_owner_session(request)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
        name           = str(body.get("name", "")).strip()
        bot_token      = str(body.get("bot_token", "")).strip()
        admin_username = str(body.get("admin_username", "admin")).strip()
        admin_password = str(body.get("admin_password", "")).strip()
        if not name or not bot_token or not admin_password:
            return JSONResponse({"status": "error", "message": "Semua field wajib diisi"}, status_code=400)
        if len(admin_password) < 6:
            return JSONResponse({"status": "error", "message": "Password minimal 6 karakter"}, status_code=400)
        outlet_id = create_outlet(name, bot_token, admin_username, admin_password)
        # Register bot webhook
        await register_outlet_bot(outlet_id, bot_token)
        logger.info(f"Outlet baru dibuat: {name} (id={outlet_id})")
        return JSONResponse({"status": "ok", "outlet_id": outlet_id, "message": f"Outlet '{name}' berhasil dibuat"})
    except Exception as e:
        logger.error(f"Error creating outlet: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/owner/api/outlets/{outlet_id}/toggle")
async def owner_toggle_outlet(outlet_id: int, request: Request):
    sess = _get_owner_session(request)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        conn = get_master_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM outlets WHERE id=?", (outlet_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({"status": "error", "message": "Outlet tidak ditemukan"}, status_code=404)
        new_val = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE outlets SET is_active=? WHERE id=?", (new_val, outlet_id))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "ok", "is_active": new_val})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/owner/print-report/{outlet_ref}", response_class=HTMLResponse)
async def owner_print_report(outlet_ref: str, request: Request, date: str = None):
    """Laporan penjualan per outlet untuk owner — langsung bisa cetak PDF."""
    sess = _get_owner_session(request)
    if not sess:
        return RedirectResponse(url="/owner/login", status_code=302)
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        today_start = target_date.strftime("%Y-%m-%d 00:00:00")
        today_end   = target_date.strftime("%Y-%m-%d 23:59:59")

        # Tentukan koneksi DB dan nama outlet
        if outlet_ref == "main":
            conn = get_connection()
            outlet_name = get_setting("restaurant_name", "Outlet Utama")
            enable_service = get_setting("enable_service", "1") == "1"
            enable_tax     = get_setting("enable_tax", "1") == "1"
            service_rate   = float(get_setting("service_rate", "10")) / 100
            tax_rate       = float(get_setting("tax_rate", "11")) / 100
            tax_label      = get_setting("tax_label", "PBJT")
        else:
            outlet_id = int(outlet_ref)
            outlet    = get_outlet_by_id(outlet_id)
            if not outlet:
                return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
            conn = get_outlet_connection(outlet_id)
            outlet_name    = outlet["name"]
            enable_service = get_outlet_setting(outlet_id, "enable_service", "1") == "1"
            enable_tax     = get_outlet_setting(outlet_id, "enable_tax", "1") == "1"
            service_rate   = float(get_outlet_setting(outlet_id, "service_rate", "10")) / 100
            tax_rate       = float(get_outlet_setting(outlet_id, "tax_rate", "11")) / 100
            tax_label      = get_outlet_setting(outlet_id, "tax_label", "PBJT")

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE created_at >= ? AND created_at <= ?", (today_start, today_end))
        orders = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT name, category FROM menu_items")
        menu_map = {r["name"]: r["category"] for r in cursor.fetchall()}
        conn.close()

        # Agregasi penjualan
        sales_data = {}
        total_sales = total_service_amt = total_tax_amt = total_revenue = 0

        for order in orders:
            if order.get("status") == "cancelled":
                continue
            items_raw = order.get("items", "{}")
            try:
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                actual = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
            except Exception:
                continue
            order_subtotal = 0
            for item_name, details in actual.items():
                if isinstance(details, dict):
                    qty   = details.get("qty", 0)
                    price = details.get("harga", 0)
                    if qty > 0:
                        cat = menu_map.get(item_name, "Lainnya")
                        if cat not in sales_data:
                            sales_data[cat] = []
                        found = False
                        for entry in sales_data[cat]:
                            if entry["name"] == item_name:
                                entry["qty"] += qty; entry["total"] += qty * price; found = True; break
                        if not found:
                            sales_data[cat].append({"name": item_name, "qty": qty, "price": price, "total": qty * price})
                        order_subtotal += qty * price
            svc = order_subtotal * service_rate if enable_service else 0
            tax = order_subtotal * tax_rate     if enable_tax     else 0
            ongkir = order.get("delivery_fee", 0) or 0
            total_sales        += order_subtotal
            total_service_amt  += svc
            total_tax_amt      += tax
            total_revenue      += order_subtotal + svc + tax + ongkir

        sorted_sales = {}
        for cat in CATEGORY_ORDER:
            if cat in sales_data:
                sorted_sales[cat] = sales_data.pop(cat)
        for cat in sales_data:
            sorted_sales[cat] = sales_data[cat]

        return templates.TemplateResponse("sales_report.html", {
            "request": request,
            "sales": sorted_sales,
            "total_sales": total_sales,
            "total_service": total_service_amt,
            "total_tax": total_tax_amt,
            "total_revenue": total_revenue,
            "date": target_date.strftime("%d %B %Y"),
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "current_year": datetime.now().year,
            "restaurant_name": outlet_name,
            "user_role": "owner",
            "username": sess["username"],
            "is_outlet": False,
            "outlet_id": None,
        })
    except Exception as e:
        logger.error(f"Owner print report error: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MULTI-OUTLET  —  OUTLET ADMIN ROUTES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_outlet_admin_sessions = {}  # kept for compatibility

def _create_outlet_session(outlet_id: int, username: str) -> str:
    token = secrets.token_urlsafe(32)
    save_session(token, 'outlet_admin', username, outlet_id=outlet_id)
    return token

def _get_outlet_session(request: Request, outlet_id: int):
    token = request.cookies.get(f"sgo_outlet_{outlet_id}")
    if not token: return None
    row = load_session(token)
    if not row: return None
    if row['session_type'] != 'outlet_admin': return None
    # Pastikan tipe data sama saat compare
    if int(row['outlet_id']) != int(outlet_id): return None
    return {"outlet_id": outlet_id, "username": row['username']}

@app.get("/outlet/{outlet_id}/login", response_class=HTMLResponse)
async def outlet_login_page(outlet_id: int, request: Request):
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    # Cek session outlet — jika sudah login ke outlet ini, langsung ke dashboard outlet
    sess = _get_outlet_session(request, outlet_id)
    if sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/dashboard", status_code=302)
    # Tampilkan halaman login outlet (JANGAN cek sgo_session admin utama)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "next": f"/outlet/{outlet_id}/dashboard",
        "username": "",
        "restaurant_name": outlet["name"],
        "current_year": datetime.now().year,
        "outlet_id": outlet_id,
        "form_action": f"/outlet/{outlet_id}/login",
    })

@app.post("/outlet/{outlet_id}/login")
async def outlet_login_submit(outlet_id: int, request: Request):
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    logger.info(f"Outlet {outlet_id} login attempt: username='{username}' password_len={len(password)}")
    result = verify_outlet_admin(outlet_id, username, password)
    logger.info(f"Outlet {outlet_id} verify result: {result is not None}")
    if result:
        token = _create_outlet_session(outlet_id, username)
        response = RedirectResponse(url=f"/outlet/{outlet_id}/dashboard", status_code=302)
        response.set_cookie(f"sgo_outlet_{outlet_id}", token, max_age=7*86400, httponly=True, samesite="lax")
        # Hapus cookie sgo_session (admin utama) agar tidak ada konflik
        response.delete_cookie("sgo_session")
        logger.info(f"✅ Outlet {outlet_id} login: {username}")
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Username atau password salah.",
        "next": f"/outlet/{outlet_id}/dashboard",
        "username": username,
        "restaurant_name": outlet["name"],
        "current_year": datetime.now().year,
        "outlet_id": outlet_id,
        "form_action": f"/outlet/{outlet_id}/login",
    }, status_code=401)

@app.get("/outlet/{outlet_id}/logout")
async def outlet_logout(outlet_id: int, request: Request):
    token = request.cookies.get(f"sgo_outlet_{outlet_id}")
    if token:
        delete_session(token)
    response = RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    response.delete_cookie(f"sgo_outlet_{outlet_id}")
    return response

def _get_outlet_db(outlet_id: int):
    """Context manager-like: set DB_PATH ke outlet, return original."""
    import database as _db
    return _db, _db.DB_PATH

@app.get("/outlet/{outlet_id}/dashboard", response_class=HTMLResponse)
async def outlet_dashboard(outlet_id: int, request: Request):
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    outlet = get_outlet_by_id(outlet_id)
    if not outlet or not outlet["is_active"]:
        return HTMLResponse("<h2>Outlet tidak aktif atau tidak ditemukan</h2>", status_code=404)
    import database as _db
    original_path = _db.DB_PATH
    _db.DB_PATH = get_outlet_db_path(outlet_id)
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM menu_items ORDER BY category, name")
        rows = cursor.fetchall()
        cursor.execute("""
            SELECT menu_item_name, AVG(rating) as avg_rating, COUNT(*) as total_reviews
            FROM item_reviews GROUP BY menu_item_name
        """)
        item_ratings = {row["menu_item_name"]: {"avg": round(row["avg_rating"], 1), "count": row["total_reviews"]} for row in cursor.fetchall()}
        conn.close()
        flat_menu = [dict(row) for row in rows]
        for item in flat_menu:
            ri = item_ratings.get(item["name"], {})
            item["avg_rating"]   = ri.get("avg", 0)
            item["review_count"] = ri.get("count", 0)
    except Exception as e:
        flat_menu = []
        logger.error(f"Outlet {outlet_id} dashboard error: {e}")
    finally:
        _db.DB_PATH = original_path
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "items": flat_menu,
        "current_year": datetime.now().year,
        "restaurant_name": outlet["name"],
        "user_role": "admin",
        "username": sess["username"],
        "outlet_id": outlet_id,
        "is_outlet": True,
    })

@app.get("/outlet/{outlet_id}/orders", response_class=HTMLResponse)
async def outlet_orders(outlet_id: int, request: Request, date: str = None, order_type: str = None):
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        today_start = target_date.strftime("%Y-%m-%d 00:00:00")
        today_end   = target_date.strftime("%Y-%m-%d 23:59:59")
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        if order_type and order_type in ("dine_in", "delivery"):
            cursor.execute("SELECT * FROM orders WHERE created_at >= ? AND created_at <= ? AND order_type=? ORDER BY created_at DESC", (today_start, today_end, order_type))
        else:
            cursor.execute("SELECT * FROM orders WHERE created_at >= ? AND created_at <= ? ORDER BY created_at DESC", (today_start, today_end))
        raw_orders = [dict(r) for r in cursor.fetchall()]
        conn.close()
        orders = []
        total_revenue = 0
        for order in raw_orders:
            items_raw = order.get("items", "{}")
            try:
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                actual = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
                summary = ", ".join([f"{k} x{v.get('qty',0)}" for k,v in actual.items() if isinstance(v,dict) and v.get("qty",0)>0])
            except Exception:
                summary = " — "
            order["items_summary"] = summary or " — "
            order["items_count"]   = len(summary.split(",")) if summary != " — " else 0
            orders.append(order)
            if order.get("status") not in ("cancelled",):
                total_revenue += order.get("total_price", 0)
        rest_lat = get_outlet_setting(outlet_id, "restaurant_lat", "-6.614970")
        rest_lng = get_outlet_setting(outlet_id, "restaurant_lng", "106.803858")
        return templates.TemplateResponse("orders.html", {
            "request": request,
            "orders": orders,
            "total_orders": len(orders),
            "total_revenue": total_revenue,
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "date_display": target_date.strftime("%d %B %Y"),
            "current_year": datetime.now().year,
            "filter_type": order_type or "all",
            "restaurant_lat": rest_lat,
            "restaurant_lng": rest_lng,
            "restaurant_name": outlet["name"],
            "user_role": "admin",
            "username": sess["username"],
            "outlet_id": outlet_id,
            "is_outlet": True,
        })
    except Exception as e:
        logger.error(f"Outlet orders error: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

@app.get("/outlet/{outlet_id}/sales-report", response_class=HTMLResponse)
async def outlet_sales_report(outlet_id: int, request: Request, date: str = None):
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        today_start = target_date.strftime("%Y-%m-%d 00:00:00")
        today_end   = target_date.strftime("%Y-%m-%d 23:59:59")
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE created_at >= ? AND created_at <= ?", (today_start, today_end))
        orders = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT name, category FROM menu_items")
        menu_map = {r["name"]: r["category"] for r in cursor.fetchall()}
        conn.close()
        sales_data = {}
        total_sales = total_service = total_tax = total_revenue = 0
        enable_service = get_outlet_setting(outlet_id, "enable_service", "1") == "1"
        enable_tax     = get_outlet_setting(outlet_id, "enable_tax", "1") == "1"
        service_rate   = float(get_outlet_setting(outlet_id, "service_rate", "10")) / 100
        tax_rate       = float(get_outlet_setting(outlet_id, "tax_rate", "11")) / 100
        for order in orders:
            items_raw = order.get("items", "{}")
            try:
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                actual = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
            except Exception:
                continue
            order_subtotal = 0
            for item_name, details in actual.items():
                if isinstance(details, dict):
                    qty = details.get("qty", 0)
                    price = details.get("harga", 0)
                    if qty > 0:
                        cat = menu_map.get(item_name, "Uncategorized")
                        if cat not in sales_data:
                            sales_data[cat] = []
                        found = False
                        for entry in sales_data[cat]:
                            if entry["name"] == item_name:
                                entry["qty"] += qty; entry["total"] += qty * price; found = True; break
                        if not found:
                            sales_data[cat].append({"name": item_name, "qty": qty, "price": price, "total": qty * price})
                        order_subtotal += qty * price
            svc = order_subtotal * service_rate if enable_service else 0
            tax = order_subtotal * tax_rate     if enable_tax     else 0
            total_sales   += order_subtotal
            total_service += svc
            total_tax     += tax
            total_revenue += order_subtotal + svc + tax
        sorted_sales = {}
        for cat in CATEGORY_ORDER:
            if cat in sales_data:
                sorted_sales[cat] = sales_data.pop(cat)
        for cat in sales_data:
            sorted_sales[cat] = sales_data[cat]
        return templates.TemplateResponse("sales_report.html", {
            "request": request,
            "sales": sorted_sales,
            "total_sales": total_sales,
            "total_service": total_service,
            "total_tax": total_tax,
            "total_revenue": total_revenue,
            "date": target_date.strftime("%d %B %Y"),
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "current_year": datetime.now().year,
            "restaurant_name": outlet["name"],
            "user_role": "admin",
            "username": sess["username"],
            "outlet_id": outlet_id,
            "is_outlet": True,
        })
    except Exception as e:
        logger.error(f"Outlet sales report error: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MULTI-OUTLET  —  WEBHOOK PER OUTLET
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/outlet/{outlet_id}/webhook")
async def outlet_webhook(outlet_id: int, update: dict):
    """Terima webhook dari bot outlet tertentu."""
    try:
        # Selalu ambil data outlet
        outlet = get_outlet_by_id(outlet_id)
        if not outlet:
            return {"ok": True}

        outlet_bot = _outlet_bots.get(outlet_id)
        if not outlet_bot:
            outlet_bot = await register_outlet_bot(outlet_id, outlet["bot_token"])

        if outlet_bot:
            outlet_dp = Dispatcher()
            # Capture outlet_name sekarang agar tidak ada closure issue
            _outlet_name = get_outlet_setting(outlet_id, "restaurant_name", outlet.get("name", "Restaurant"))
            _outlet_id   = outlet_id

            @outlet_dp.message(CommandStart())
            async def outlet_start(message: types.Message):
                save_tg_session(message.from_user.id)
                tgid         = message.from_user.id
                # Reload BASE_URL terbaru
                load_dotenv(override=True)
                _base = os.getenv("BASE_URL", BASE_URL)
                dine_url     = f"{_base}/outlet/{_outlet_id}?tgid={tgid}&mode=dine_in"
                delivery_url = f"{_base}/outlet/{_outlet_id}/delivery?tgid={tgid}"
                builder = InlineKeyboardBuilder()
                builder.row(
                    types.InlineKeyboardButton(text="Makan di Tempat", web_app=types.WebAppInfo(url=dine_url)),
                    types.InlineKeyboardButton(text="Pesan Antar", web_app=types.WebAppInfo(url=delivery_url))
                )
                await message.answer(
                    f"<b>{_outlet_name.upper()}</b>\n\nSelamat datang, {message.from_user.full_name}!\n\nSilakan pilih jenis pesanan:",
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )

            @outlet_dp.callback_query(lambda c: c.data and c.data.startswith("ro_"))
            async def outlet_rating_callback(callback: types.CallbackQuery):
                """Handle rating keseluruhan pesanan outlet."""
                try:
                    parts = callback.data.split("_")
                    order_id_cb = int(parts[1])
                    rating      = int(parts[2])
                    customer_name = callback.from_user.full_name or "Tamu"
                    telegram_id_cb = callback.from_user.id

                    # Simpan rating ke DB outlet
                    conn_r = get_outlet_connection(_outlet_id)
                    cur_r  = conn_r.cursor()
                    cur_r.execute(
                        "INSERT OR REPLACE INTO order_ratings (order_id, telegram_id, overall_rating) VALUES (?,?,?)",
                        (order_id_cb, telegram_id_cb, rating)
                    )
                    conn_r.commit()

                    # Ambil items untuk rating per item
                    cur_r.execute("SELECT items FROM orders WHERE id=?", (order_id_cb,))
                    order_row_r = cur_r.fetchone()
                    conn_r.close()

                    stars = "⭐" * rating
                    await callback.message.edit_text(
                        f"<b>Terima kasih atas rating Anda!</b>\n\n"
                        f"Pesanan #{order_id_cb}: {stars} ({rating}/5)\n\n"
                        f"Sekarang berikan rating untuk setiap menu:",
                        parse_mode="HTML"
                    )

                    # Kirim notif rating ke admin outlet
                    outlet_admin_tg = get_outlet_setting(_outlet_id, "admin_telegram_id", "")
                    notify_ids_r = []
                    if outlet_admin_tg.strip():
                        try:
                            notify_ids_r.append(int(outlet_admin_tg.strip()))
                        except ValueError:
                            pass
                    if ADMIN_ID and ADMIN_ID not in notify_ids_r:
                        notify_ids_r.append(ADMIN_ID)

                    for notify_id in notify_ids_r:
                        try:
                            await outlet_bot.send_message(
                                chat_id=notify_id,
                                text=f"<b>⭐ RATING PESANAN BARU</b>\n\n"
                                     f"<b>[{_outlet_name}]</b>\n"
                                     f"<b>Dari:</b> {customer_name}\n"
                                     f"<b>Pesanan:</b> #{order_id_cb}\n"
                                     f"<b>Rating:</b> {stars} ({rating}/5)",
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass

                    # Kirim rating per item jika ada
                    if order_row_r:
                        try:
                            items_raw = order_row_r["items"]
                            items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                            actual = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
                            item_names = [k for k, v in actual.items() if isinstance(v, dict) and v.get("qty", 0) > 0]

                            for idx, item_name in enumerate(item_names[:5]):
                                builder_item = InlineKeyboardBuilder()
                                for r in range(1, 6):
                                    builder_item.button(
                                        text="⭐" * r,
                                        callback_data=f"ri_{order_id_cb}_{idx}_{r}"
                                    )
                                builder_item.adjust(5)
                                await callback.message.answer(
                                    f"<b>{item_name}</b>\nBerikan rating:",
                                    reply_markup=builder_item.as_markup(),
                                    parse_mode="HTML"
                                )
                        except Exception as e:
                            logger.warning(f"Outlet {_outlet_id} - Gagal kirim item rating: {e}")

                    await callback.answer()
                except Exception as e:
                    logger.error(f"Outlet {_outlet_id} rating callback error: {e}")
                    await callback.answer("Terjadi kesalahan")

            @outlet_dp.callback_query(lambda c: c.data and c.data.startswith("ri_"))
            async def outlet_item_rating_callback(callback: types.CallbackQuery):
                """Handle rating per item menu outlet."""
                try:
                    parts = callback.data.split("_")
                    order_id_cb = int(parts[1])
                    idx         = int(parts[2])
                    rating      = int(parts[3])

                    # Ambil nama item dari order
                    conn_r = get_outlet_connection(_outlet_id)
                    cur_r  = conn_r.cursor()
                    cur_r.execute("SELECT items FROM orders WHERE id=?", (order_id_cb,))
                    order_row_r = cur_r.fetchone()

                    item_name = f"Item #{idx+1}"
                    if order_row_r:
                        try:
                            items_raw = order_row_r["items"]
                            items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                            actual = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
                            item_names = [k for k, v in actual.items() if isinstance(v, dict) and v.get("qty", 0) > 0]
                            if idx < len(item_names):
                                item_name = item_names[idx]
                        except Exception:
                            pass

                    # Simpan review item
                    cur_r.execute(
                        "INSERT INTO item_reviews (order_id, menu_item_name, rating) VALUES (?,?,?)",
                        (order_id_cb, item_name, rating)
                    )
                    conn_r.commit()
                    conn_r.close()

                    stars = "⭐" * rating
                    await callback.message.edit_text(
                        f"<b>{item_name}</b>\nRating: {stars} ({rating}/5) — Terima kasih!",
                        parse_mode="HTML"
                    )

                    # Kirim notif review ke admin outlet
                    outlet_admin_tg2 = get_outlet_setting(_outlet_id, "admin_telegram_id", "")
                    notify_ids_r2 = []
                    if outlet_admin_tg2.strip():
                        try:
                            notify_ids_r2.append(int(outlet_admin_tg2.strip()))
                        except ValueError:
                            pass
                    if ADMIN_ID and ADMIN_ID not in notify_ids_r2:
                        notify_ids_r2.append(ADMIN_ID)

                    for notify_id in notify_ids_r2:
                        try:
                            await outlet_bot.send_message(
                                chat_id=notify_id,
                                text=f"<b>⭐ REVIEW MENU BARU</b>\n\n"
                                     f"<b>[{_outlet_name}]</b>\n"
                                     f"<b>Dari:</b> {callback.from_user.full_name}\n"
                                     f"<b>Pesanan:</b> #{order_id_cb}\n"
                                     f"<b>Menu:</b> {item_name}\n"
                                     f"<b>Rating:</b> {stars} ({rating}/5)",
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass

                    await callback.answer("Rating tersimpan!")
                except Exception as e:
                    logger.error(f"Outlet {_outlet_id} item rating callback error: {e}")
                    await callback.answer("Terjadi kesalahan")

            telegram_update = types.Update(**update)
            await outlet_dp.feed_update(outlet_bot, telegram_update)
    except Exception as e:
        logger.error(f"Outlet {outlet_id} webhook error: {e}")
    return {"ok": True}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MULTI-OUTLET  —  MENU PAGE PER OUTLET
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/outlet/{outlet_id}", response_class=HTMLResponse)
async def outlet_menu_page(outlet_id: int, request: Request):
    """Halaman menu untuk pembeli outlet tertentu."""
    outlet = get_outlet_by_id(outlet_id)
    if not outlet or not outlet["is_active"]:
        return HTMLResponse("<h2>Outlet tidak tersedia</h2>", status_code=404)
    import database as _db
    original_path = _db.DB_PATH
    _db.DB_PATH = get_outlet_db_path(outlet_id)
    try:
        menu_data = get_menu_from_db()
        tgid = request.query_params.get("tgid", "")
        qris_image = _db.get_setting("qris_image", "/static/images/qris.jpg")
        tax_settings = {
            "enable_service": _db.get_setting("enable_service", "1") == "1",
            "service_rate":   float(_db.get_setting("service_rate", "10")),
            "enable_tax":     _db.get_setting("enable_tax", "1") == "1",
            "tax_rate":       float(_db.get_setting("tax_rate", "11")),
            "tax_label":      _db.get_setting("tax_label", "PBJT"),
        }
    finally:
        _db.DB_PATH = original_path
    return templates.TemplateResponse("index.html", {
        "request": request,
        "menu": menu_data,
        "current_year": datetime.now().year,
        "tgid": tgid,
        "restaurant_name": outlet["name"],
        "qris_image": qris_image,
        "tax_settings": tax_settings,
        "outlet_id": outlet_id,
    })

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MULTI-OUTLET  —  STATUS API PER OUTLET
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/outlet/{outlet_id}/api/orders/status-poll")
async def outlet_poll_orders(outlet_id: int, request: Request, date: str = None):
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        today_start = target_date.strftime("%Y-%m-%d 00:00:00")
        today_end   = target_date.strftime("%Y-%m-%d 23:59:59")
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, status, courier_name, order_type, customer_name, table_number,
                   total_price, items, note, created_at, whatsapp,
                   delivery_address, delivery_distance, delivery_fee, delivery_lat, delivery_lng
            FROM orders WHERE created_at >= ? AND created_at <= ? ORDER BY created_at DESC
        """, (today_start, today_end))
        rows = cursor.fetchall()
        conn.close()
        orders = []
        for r in rows:
            o = dict(r)
            try:
                items_parsed = json.loads(o.get("items","{}")) if isinstance(o.get("items"), str) else o.get("items",{})
                actual = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
                summary = ", ".join([f"{k} x{v.get('qty',0)}" for k,v in actual.items() if isinstance(v,dict) and v.get("qty",0)>0])
            except Exception:
                summary = " — "
            o["items_summary"] = summary or " — "
            orders.append(o)
        return JSONResponse({"status": "ok", "orders": orders})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/outlet/{outlet_id}/api/orders/status/{order_id}")
async def outlet_update_order_status(outlet_id: int, order_id: int, request: Request):
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
        new_status = body.get("status", "")
        valid_statuses = ["pending","preparing","on_delivery","served","completed","cancelled"]
        if new_status not in valid_statuses:
            return JSONResponse({"status": "error", "message": "Invalid status"}, status_code=400)
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT customer_name, telegram_id, order_type FROM orders WHERE id=?", (order_id,))
        order_row = cursor.fetchone()
        cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
        conn.commit()
        conn.close()
        # Kirim notifikasi ke pembeli jika ada telegram_id
        if order_row and order_row["telegram_id"]:
            outlet_bot = _outlet_bots.get(outlet_id)
            if outlet_bot:
                status_msgs = {
                    "preparing": "🍳 <b>Pesanan Anda sedang diproses!</b>\n\nDapur kami sedang menyiapkan hidangan Anda.",
                    "served":    "✅ <b>Pesanan Anda sudah disajikan!</b>\n\nSelamat menikmati hidangan Anda. 😊",
                    "completed": "✅ <b>Pesanan Anda selesai!</b>\n\nTerima kasih telah memesan di sini.",
                    "cancelled": "❌ <b>Pesanan Anda dibatalkan.</b>",
                }
                msg = status_msgs.get(new_status)
                if msg:
                    try:
                        customer_name = order_row["customer_name"] or "Pelanggan"
                        await outlet_bot.send_message(
                            chat_id=order_row["telegram_id"],
                            text=f"<b>UPDATE PESANAN</b>\n\n<b>Nama:</b> {customer_name}\n\n{msg}",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"Gagal kirim notif outlet {outlet_id}: {e}")

                # Kirim rating request setelah served/completed
                if new_status in ("served", "completed"):
                    try:
                        # Ambil items dari order untuk rating per item
                        conn2 = get_outlet_connection(outlet_id)
                        cur2  = conn2.cursor()
                        cur2.execute("SELECT items, customer_name FROM orders WHERE id=?", (order_id,))
                        order_data = cur2.fetchone()
                        conn2.close()

                        if order_data:
                            # Rating keseluruhan pesanan
                            from aiogram.utils.keyboard import InlineKeyboardBuilder as _IKB
                            builder = _IKB()
                            for r in range(1, 6):
                                builder.button(
                                    text="⭐" * r,
                                    callback_data=f"ro_{order_id}_{r}"
                                )
                            builder.adjust(5)
                            await outlet_bot.send_message(
                                chat_id=order_row["telegram_id"],
                                text=f"<b>Bagaimana pesanan Anda?</b>\n\nBerikan rating 1-5 ⭐ untuk pesanan #{order_id}:",
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        logger.warning(f"Outlet {outlet_id} - Gagal kirim rating request: {e}")
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MULTI-OUTLET  —  LOAD BOTS ON STARTUP (tambahkan ke lifespan)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Catatan: load_all_outlet_bots() dipanggil dari lifespan di atas
# Tambahkan baris ini di fungsi lifespan setelah scheduler.start():
# await load_all_outlet_bots()



# if __name__ == "__main__" dipindah ke akhir file — jangan hapus baris ini




# ─────────────────────────────────────────────
# MULTI-OUTLET — MENU API
# ─────────────────────────────────────────────

@app.post("/outlet/{outlet_id}/api/menu")
async def outlet_add_menu_item(
    outlet_id: int,
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    cuisine: str = Form(None),
    price: int = Form(...),
    description: str = Form(""),
    image_file: UploadFile = File(None),
):
    """Tambah menu item ke outlet tertentu."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    outlet = get_outlet_by_id(outlet_id)
    if not outlet or not outlet["is_active"]:
        return JSONResponse({"status": "error", "message": "Outlet tidak ditemukan"}, status_code=404)
    
    try:
        image_url = ""
        if image_file and image_file.filename:
            file_ext = image_file.filename.rsplit(".", 1)[-1].lower()
            file_name = f"outlet{outlet_id}_{int(time.time())}_{name.replace(' ', '_')}.{file_ext}"
            file_path = os.path.join(UPLOAD_DIR, file_name)
            
            file_content = await image_file.read()
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            image_url = f"/static/images/menu/{file_name}"
            logger.info(f"Outlet {outlet_id} - Image saved: {file_path}")

        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO menu_items (name, category, cuisine, price, description, image_url, is_available)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (name, category, cuisine, price, description, image_url))
        conn.commit()
        conn.close()

        return RedirectResponse(url=f"/outlet/{outlet_id}/dashboard", status_code=303)
    except Exception as e:
        logger.error(f"Error adding menu to outlet {outlet_id}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/menu/delete/{item_id}")
async def outlet_delete_menu_item(outlet_id: int, item_id: int, request: Request):
    """Hapus menu item dari outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        
        cursor.execute("SELECT image_url FROM menu_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if row and row["image_url"]:
            img_path = row["image_url"].lstrip("/")
            if os.path.exists(img_path):
                os.remove(img_path)
                logger.info(f"Outlet {outlet_id} - Deleted image: {img_path}")

        cursor.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

        return RedirectResponse(url=f"/outlet/{outlet_id}/dashboard", status_code=303)
    except Exception as e:
        logger.error(f"Error deleting menu from outlet {outlet_id}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/menu/edit/{item_id}")
async def outlet_edit_menu_item(
    outlet_id: int,
    item_id: int,
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    cuisine: str = Form(None),
    price: int = Form(...),
    description: str = Form(""),
    image_file: UploadFile = File(None),
):
    """Edit menu item di outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        
        cursor.execute("SELECT image_url FROM menu_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({"status": "error", "message": "Item not found"}, status_code=404)

        old_image_url = row["image_url"] if row else ""
        new_image_url = old_image_url

        if image_file and image_file.filename:
            file_ext = image_file.filename.rsplit(".", 1)[-1].lower()
            file_name = f"outlet{outlet_id}_{int(time.time())}_{name.replace(' ', '_')}.{file_ext}"
            file_path = os.path.join(UPLOAD_DIR, file_name)
            
            file_content = await image_file.read()
            with open(file_path, "wb") as f:
                f.write(file_content)

            new_image_url = f"/static/images/menu/{file_name}"
            logger.info(f"Outlet {outlet_id} - New image saved: {file_path}")

            if old_image_url:
                old_path = old_image_url.lstrip("/")
                if os.path.exists(old_path):
                    os.remove(old_path)
                    logger.info(f"Outlet {outlet_id} - Old image deleted: {old_path}")

        cursor.execute("""
            UPDATE menu_items
            SET name=?, category=?, cuisine=?, price=?, description=?, image_url=?
            WHERE id=?
        """, (name, category, cuisine, price, description, new_image_url, item_id))
        conn.commit()
        conn.close()

        return RedirectResponse(url=f"/outlet/{outlet_id}/dashboard", status_code=303)
    except Exception as e:
        logger.error(f"Error editing menu in outlet {outlet_id}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/menu/toggle/{item_id}")
async def outlet_toggle_menu_item(outlet_id: int, item_id: int, request: Request):
    """Toggle ketersediaan menu item di outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        
        cursor.execute("SELECT is_available FROM menu_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({"status": "error", "message": "Item not found"}, status_code=404)

        new_val = 0 if row["is_available"] == 1 else 1
        cursor.execute("UPDATE menu_items SET is_available=? WHERE id=?", (new_val, item_id))
        conn.commit()
        conn.close()

        return JSONResponse({"status": "ok", "is_available": new_val})
    except Exception as e:
        logger.error(f"Error toggling menu in outlet {outlet_id}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/menu/stock/{item_id}")
async def outlet_update_stock(outlet_id: int, item_id: int, request: Request):
    """Update stok menu item di outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        body = await request.json()
        new_stock = int(body.get("stock", -1))
        stock_alert = int(body.get("stock_alert", 5))
        
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        
        # Jika stok 0, nonaktifkan otomatis
        if new_stock == 0:
            cursor.execute("UPDATE menu_items SET stock=?, stock_alert=?, is_available=0 WHERE id=?", 
                          (new_stock, stock_alert, item_id))
        else:
            cursor.execute("UPDATE menu_items SET stock=?, stock_alert=? WHERE id=?", 
                          (new_stock, stock_alert, item_id))
        
        conn.commit()
        conn.close()

        return JSONResponse({"status": "ok", "stock": new_stock, "stock_alert": stock_alert})
    except Exception as e:
        logger.error(f"Error updating stock in outlet {outlet_id}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# MULTI-OUTLET — SETTINGS & OTHER PAGES
# ─────────────────────────────────────────────

@app.get("/outlet/{outlet_id}/settings", response_class=HTMLResponse)
async def outlet_settings_page(outlet_id: int, request: Request):
    """Halaman pengaturan untuk outlet tertentu."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    
    settings = {
        'restaurant_lat':      get_outlet_setting(outlet_id, 'restaurant_lat', '-6.614970215748657'),
        'restaurant_lng':      get_outlet_setting(outlet_id, 'restaurant_lng', '106.80385837668723'),
        'restaurant_name':     get_outlet_setting(outlet_id, 'restaurant_name', outlet['name']),
        'delivery_min_fee':    get_outlet_setting(outlet_id, 'delivery_min_fee', '5000'),
        'delivery_fee_per_km': get_outlet_setting(outlet_id, 'delivery_fee_per_km', '3000'),
        'delivery_min_km':     get_outlet_setting(outlet_id, 'delivery_min_km', '1'),
        'delivery_max_km':     get_outlet_setting(outlet_id, 'delivery_max_km', '10'),
        'courier_whatsapp':    get_outlet_setting(outlet_id, 'courier_whatsapp', ''),
        'courier_info':        get_outlet_setting(outlet_id, 'courier_info', ''),
        'qris_image':          get_outlet_setting(outlet_id, 'qris_image', '/static/images/qris.jpg'),
        'enable_service':      get_outlet_setting(outlet_id, 'enable_service', '1'),
        'service_rate':        get_outlet_setting(outlet_id, 'service_rate', '10'),
        'enable_tax':          get_outlet_setting(outlet_id, 'enable_tax', '1'),
        'tax_rate':            get_outlet_setting(outlet_id, 'tax_rate', '11'),
        'tax_label':           get_outlet_setting(outlet_id, 'tax_label', 'PBJT'),
        'daily_report_enabled':get_outlet_setting(outlet_id, 'daily_report_enabled', '1'),
        'daily_report_hour':   get_outlet_setting(outlet_id, 'daily_report_hour', '22'),
        'daily_report_minute': get_outlet_setting(outlet_id, 'daily_report_minute', '0'),
        'owner_telegram_id':   get_outlet_setting(outlet_id, 'owner_telegram_id', ''),
    }
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "current_year": datetime.now().year,
        "restaurant_name": outlet['name'],
        "user_role": "admin",
        "username": sess["username"],
        "is_outlet": True,
        "outlet_id": outlet_id,
    })


def set_outlet_setting(outlet_id: int, key: str, value: str):
    """Simpan setting ke database outlet tertentu."""
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now','localtime'))",
            (key, value)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving outlet {outlet_id} setting {key}: {e}")


@app.post("/outlet/{outlet_id}/api/settings")
async def outlet_save_settings(outlet_id: int, request: Request):
    """Simpan pengaturan outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        form = await request.form()
        keys = ['restaurant_lat', 'restaurant_lng', 'restaurant_name',
                'delivery_min_fee', 'delivery_fee_per_km', 'delivery_min_km', 'delivery_max_km',
                'courier_whatsapp', 'courier_info',
                'service_rate', 'tax_rate', 'tax_label',
                'daily_report_hour', 'daily_report_minute', 'owner_telegram_id']
        
        for key in keys:
            if key in form:
                set_outlet_setting(outlet_id, key, str(form[key]))
        
        set_outlet_setting(outlet_id, 'enable_service', '1' if 'enable_service' in form else '0')
        set_outlet_setting(outlet_id, 'enable_tax', '1' if 'enable_tax' in form else '0')
        set_outlet_setting(outlet_id, 'daily_report_enabled', '1' if 'daily_report_enabled' in form else '0')

        return RedirectResponse(url=f"/outlet/{outlet_id}/settings?saved=1", status_code=303)
    except Exception as e:
        logger.error(f"Error saving outlet {outlet_id} settings: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/settings/upload-qris")
async def outlet_upload_qris(outlet_id: int, request: Request, image_file: UploadFile = File(...)):
    """Upload gambar QRIS untuk outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        if not image_file or not image_file.filename:
            return JSONResponse({"status": "error", "message": "File tidak ditemukan"}, status_code=400)

        file_ext = image_file.filename.rsplit(".", 1)[-1].lower()
        if file_ext not in ('jpg', 'jpeg', 'png'):
            return JSONResponse({"status": "error", "message": "Format harus JPG atau PNG"}, status_code=400)

        qris_path = os.path.join("static", "images", f"qris_outlet_{outlet_id}.{file_ext}")
        file_content = await image_file.read()
        with open(qris_path, "wb") as f:
            f.write(file_content)

        qris_url = f"/static/images/qris_outlet_{outlet_id}.{file_ext}"
        set_outlet_setting(outlet_id, "qris_image", qris_url)
        logger.info(f"Outlet {outlet_id} QRIS updated: {qris_url}")

        return RedirectResponse(url=f"/outlet/{outlet_id}/settings?saved=1", status_code=303)
    except Exception as e:
        logger.error(f"Error uploading QRIS for outlet {outlet_id}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/outlet/{outlet_id}/couriers", response_class=HTMLResponse)
async def outlet_couriers_page(outlet_id: int, request: Request):
    """Halaman manajemen kurir untuk outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM couriers ORDER BY name")
        couriers = [dict(r) for r in cursor.fetchall()]
        conn.close()
    except Exception:
        couriers = []
    
    return templates.TemplateResponse("couriers.html", {
        "request": request,
        "couriers": couriers,
        "current_year": datetime.now().year,
        "restaurant_name": outlet['name'],
        "user_role": "admin",
        "username": sess["username"],
        "is_outlet": True,
        "outlet_id": outlet_id,
    })


@app.post("/outlet/{outlet_id}/api/couriers")
async def outlet_add_courier(outlet_id: int, request: Request):
    """Tambah kurir baru ke outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
            name = str(body.get("name", "")).strip()
            whatsapp = str(body.get("whatsapp", "")).strip()
        else:
            form = await request.form()
            name = str(form.get("name", "")).strip()
            whatsapp = str(form.get("whatsapp", "")).strip()
            # Tambahkan prefix +62 jika belum ada
            if whatsapp and not whatsapp.startswith("+"):
                whatsapp = "62" + whatsapp.lstrip("0")
        
        if not name or not whatsapp:
            return JSONResponse({"status": "error", "message": "Nama dan WhatsApp wajib diisi"}, status_code=400)
        
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO couriers (name, whatsapp) VALUES (?, ?)", (name, whatsapp))
        conn.commit()
        conn.close()
        
        # Jika form POST, redirect kembali ke halaman kurir
        if "application/json" not in content_type:
            return RedirectResponse(url=f"/outlet/{outlet_id}/couriers", status_code=303)
        return JSONResponse({"status": "ok", "message": "Kurir berhasil ditambahkan"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/couriers/{courier_id}/toggle")
async def outlet_toggle_courier(outlet_id: int, courier_id: int, request: Request):
    """Toggle status kurir di outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM couriers WHERE id=?", (courier_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({"status": "error", "message": "Kurir tidak ditemukan"}, status_code=404)
        
        new_val = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE couriers SET is_active=? WHERE id=?", (new_val, courier_id))
        conn.commit()
        conn.close()
        
        return JSONResponse({"status": "ok", "is_active": new_val})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/couriers/{courier_id}/delete")
async def outlet_delete_courier(outlet_id: int, courier_id: int, request: Request):
    """Hapus kurir dari outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM couriers WHERE id=?", (courier_id,))
        conn.commit()
        conn.close()
        
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/outlet/{outlet_id}/vouchers", response_class=HTMLResponse)
async def outlet_vouchers_page(outlet_id: int, request: Request):
    """Halaman manajemen voucher untuk outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vouchers ORDER BY created_at DESC")
        vouchers = [dict(r) for r in cursor.fetchall()]
        conn.close()
    except Exception:
        vouchers = []
    
    return templates.TemplateResponse("vouchers.html", {
        "request": request,
        "vouchers": vouchers,
        "current_year": datetime.now().year,
        "restaurant_name": outlet['name'],
        "user_role": "admin",
        "username": sess["username"],
        "is_outlet": True,
        "outlet_id": outlet_id,
    })


@app.post("/outlet/{outlet_id}/api/vouchers")
async def outlet_add_voucher(outlet_id: int, request: Request):
    """Tambah voucher baru ke outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        body = await request.json()
        code = str(body.get("code", "")).strip().upper()
        discount_type = str(body.get("discount_type", "percent"))
        discount_value = int(body.get("discount_value", 0))
        min_order = int(body.get("min_order", 0))
        max_uses = int(body.get("max_uses", -1))
        expires_at = body.get("expires_at") or None
        
        if not code or discount_value <= 0:
            return JSONResponse({"status": "error", "message": "Kode dan nilai diskon wajib diisi"}, status_code=400)
        
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vouchers (code, discount_type, discount_value, min_order, max_uses, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, discount_type, discount_value, min_order, max_uses, expires_at))
        conn.commit()
        conn.close()
        
        return JSONResponse({"status": "ok", "message": "Voucher berhasil dibuat"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/vouchers/{voucher_id}/toggle")
async def outlet_toggle_voucher(outlet_id: int, voucher_id: int, request: Request):
    """Toggle status voucher di outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM vouchers WHERE id=?", (voucher_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({"status": "error", "message": "Voucher tidak ditemukan"}, status_code=404)
        
        new_val = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE vouchers SET is_active=? WHERE id=?", (new_val, voucher_id))
        conn.commit()
        conn.close()
        
        return JSONResponse({"status": "ok", "is_active": new_val})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/vouchers/{voucher_id}/delete")
async def outlet_delete_voucher(outlet_id: int, voucher_id: int, request: Request):
    """Hapus voucher dari outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vouchers WHERE id=?", (voucher_id,))
        conn.commit()
        conn.close()
        
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/outlet/{outlet_id}/customers", response_class=HTMLResponse)
async def outlet_customers_page(outlet_id: int, request: Request):
    """Halaman riwayat pelanggan untuk outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
    
    outlet = get_outlet_by_id(outlet_id)
    if not outlet:
        return HTMLResponse("<h2>Outlet tidak ditemukan</h2>", status_code=404)
    
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT customer_name, telegram_id, whatsapp, order_type,
                   total_price, items, created_at, status
            FROM orders
            WHERE status != 'cancelled'
            ORDER BY created_at DESC
        """)
        all_orders = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Agregasi per pelanggan
        customer_map = {}
        for order in all_orders:
            name  = (order.get('customer_name') or 'Tamu').strip()
            tg_id = order.get('telegram_id')
            wa    = order.get('whatsapp') or ''
            key   = str(tg_id) if tg_id else name.lower()

            if key not in customer_map:
                customer_map[key] = {
                    'name': name, 'telegram_id': tg_id, 'whatsapp': wa,
                    'total_orders': 0, 'dine_in_count': 0, 'delivery_count': 0,
                    'total_spent': 0, 'item_counts': {}, 'last_order': order.get('created_at', ''),
                }
            else:
                if tg_id and not customer_map[key]['telegram_id']:
                    customer_map[key]['telegram_id'] = tg_id
                if wa and not customer_map[key]['whatsapp']:
                    customer_map[key]['whatsapp'] = wa

            c = customer_map[key]
            c['total_orders'] += 1
            c['total_spent']  += order.get('total_price', 0) or 0
            if order.get('order_type') == 'delivery':
                c['delivery_count'] += 1
            else:
                c['dine_in_count'] += 1

            try:
                items_raw = order.get('items', '{}')
                items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                actual = items_parsed.get('items', items_parsed) if isinstance(items_parsed, dict) else items_parsed
                for item_name, details in actual.items():
                    if isinstance(details, dict) and details.get('qty', 0) > 0:
                        c['item_counts'][item_name] = c['item_counts'].get(item_name, 0) + details['qty']
            except Exception:
                pass

        customers = []
        for c in customer_map.values():
            fav = sorted(c['item_counts'].items(), key=lambda x: x[1], reverse=True)
            c['fav_items'] = [n for n, _ in fav[:5]]
            del c['item_counts']
            customers.append(c)
        customers.sort(key=lambda x: x['total_orders'], reverse=True)

    except Exception as e:
        logger.error(f"Outlet {outlet_id} customers error: {e}")
        customers = []
    
    return templates.TemplateResponse("customers.html", {
        "request": request,
        "customers": customers,
        "current_year": datetime.now().year,
        "restaurant_name": outlet['name'],
        "user_role": "admin",
        "username": sess["username"],
        "is_outlet": True,
        "outlet_id": outlet_id,
    })


# ─────────────────────────────────────────────
# MULTI-OUTLET — COURIERS LIST & ASSIGN
# ─────────────────────────────────────────────

@app.get("/outlet/{outlet_id}/api/couriers/list")
async def outlet_list_couriers(outlet_id: int, request: Request):
    """Daftar kurir aktif untuk outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, whatsapp FROM couriers WHERE is_active=1 ORDER BY name")
        couriers = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return JSONResponse({"status": "ok", "couriers": couriers})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/outlet/{outlet_id}/api/orders/assign-courier/{order_id}")
async def outlet_assign_courier(outlet_id: int, order_id: int, request: Request):
    """Assign kurir ke pesanan outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
        courier_name = str(body.get("courier_name", "")).strip()
        courier_wa   = str(body.get("courier_whatsapp", "")).strip()

        # Generate token unik untuk link konfirmasi kurir
        import secrets as _sec
        courier_token = _sec.token_urlsafe(12)

        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET courier_name=?, courier_token=?, status='on_delivery' WHERE id=?",
            (courier_name, courier_token, order_id)
        )
        conn.commit()
        
        # Ambil info pesanan untuk notifikasi
        cursor.execute("SELECT customer_name, telegram_id, delivery_address FROM orders WHERE id=?", (order_id,))
        order_row_raw = cursor.fetchone()
        conn.close()
        # Convert sqlite3.Row ke dict
        order_row = dict(order_row_raw) if order_row_raw else None

        # Buat URL konfirmasi kurir — pakai BASE_URL terbaru
        load_dotenv(override=True)
        current_base = os.getenv("BASE_URL", BASE_URL)
        courier_url = f"{current_base}/outlet/{outlet_id}/courier/{order_id}/{courier_token}"
        
        # Kirim notifikasi ke pembeli jika ada telegram_id
        if order_row and order_row["telegram_id"]:
            outlet_bot = _outlet_bots.get(outlet_id)
            if outlet_bot:
                try:
                    # Format nomor WA kurir untuk link wa.me
                    wa_clean = courier_wa.replace('+', '').replace('-', '').replace(' ', '')
                    if wa_clean.startswith('0'):
                        wa_clean = '62' + wa_clean[1:]
                    wa_link = f"https://wa.me/{wa_clean}" if wa_clean else None

                    notif_text = (
                        f"<b>Pesanan Anda sedang dalam perjalanan!</b>\n\n"
                        f"<b>Kurir:</b> {courier_name}\n"
                    )
                    if courier_wa:
                        notif_text += f"<b>WhatsApp Kurir:</b> {courier_wa}\n"
                        if wa_link:
                            notif_text += f"💬 <a href='{wa_link}'>Hubungi Kurir via WhatsApp</a>\n"
                    if order_row.get("delivery_address"):
                        notif_text += f"<b>Alamat:</b> {order_row['delivery_address']}\n"
                    notif_text += "\nKurir sedang menuju lokasi Anda."

                    await outlet_bot.send_message(
                        chat_id=order_row["telegram_id"],
                        text=notif_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.warning(f"Gagal kirim notif outlet {outlet_id}: {e}")
        
        return JSONResponse({"status": "ok", "courier_name": courier_name, "courier_url": courier_url})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# MULTI-OUTLET — CUSTOMERS SEND MESSAGE
# ─────────────────────────────────────────────

@app.post("/outlet/{outlet_id}/api/customers/send-message")
async def outlet_send_customer_message(outlet_id: int, request: Request):
    """Kirim pesan ke pelanggan via bot outlet."""
    sess = _get_outlet_session(request, outlet_id)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    
    try:
        body = await request.json()
        telegram_id = int(body.get("telegram_id", 0))
        message     = str(body.get("message", "")).strip()
        name        = str(body.get("name", "Pelanggan"))

        if not telegram_id or not message:
            return JSONResponse({"status": "error", "message": "telegram_id dan pesan wajib diisi"}, status_code=400)

        outlet_bot = _outlet_bots.get(outlet_id)
        if not outlet_bot:
            return JSONResponse({"status": "error", "message": "Bot outlet tidak aktif"}, status_code=500)

        outlet = get_outlet_by_id(outlet_id)
        rest_name = get_outlet_setting(outlet_id, "restaurant_name", outlet["name"] if outlet else "Restaurant")
        full_msg = f"<b>Pesan dari {rest_name}</b>\n\n{message}"

        await outlet_bot.send_message(chat_id=telegram_id, text=full_msg, parse_mode="HTML")
        logger.info(f"Outlet {outlet_id} - Pesan terkirim ke {name} ({telegram_id})")
        return JSONResponse({"status": "ok", "message": f"Pesan terkirim ke {name}"})

    except Exception as e:
        logger.error(f"Outlet {outlet_id} - Error sending customer message: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# ALIAS ROUTES — untuk kompatibilitas format URL baru
# ─────────────────────────────────────────────

@app.post("/api/couriers/{courier_id}/toggle")
async def toggle_courier_alias(courier_id: int, request: Request):
    """Alias toggle kurir (format URL baru)."""
    sess = _require_admin(request)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM couriers WHERE id=?", (courier_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({"status": "error", "message": "Kurir tidak ditemukan"}, status_code=404)
        new_val = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE couriers SET is_active=? WHERE id=?", (new_val, courier_id))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "ok", "is_active": new_val})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/couriers/{courier_id}/delete")
async def delete_courier_alias(courier_id: int, request: Request):
    """Alias hapus kurir (format URL baru)."""
    sess = _require_admin(request)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM couriers WHERE id=?", (courier_id,))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/vouchers/{voucher_id}/toggle")
async def toggle_voucher_alias(voucher_id: int, request: Request):
    """Alias toggle voucher (format URL baru)."""
    sess = _require_admin(request)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM vouchers WHERE id=?", (voucher_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse({"status": "error", "message": "Voucher tidak ditemukan"}, status_code=404)
        new_val = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE vouchers SET is_active=? WHERE id=?", (new_val, voucher_id))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "ok", "is_active": new_val})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/vouchers/{voucher_id}/delete")
async def delete_voucher_alias(voucher_id: int, request: Request):
    """Alias hapus voucher (format URL baru)."""
    sess = _require_admin(request)
    if not sess:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vouchers WHERE id=?", (voucher_id,))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# MULTI-OUTLET — SUBMIT ORDER
# ─────────────────────────────────────────────

@app.post("/outlet/{outlet_id}/submit_order")
async def outlet_submit_order(outlet_id: int, order: Request):
    """Terima pesanan dari halaman menu outlet dan simpan ke DB outlet."""
    try:
        data = await order.json()

        outlet = get_outlet_by_id(outlet_id)
        if not outlet or not outlet["is_active"]:
            return JSONResponse({"status": "error", "message": "Outlet tidak aktif"}, status_code=404)

        tgid_token  = str(data.get("tgid", "")) if data.get("tgid") else ""
        telegram_id = get_telegram_id_from_token(tgid_token) if tgid_token else None
        order_type  = data.get("order_type", "dine_in")
        source      = "Telegram" if telegram_id else "Browser/Web"
        logger.info(f"Outlet {outlet_id} Order [{order_type}/{source}] customer={data.get('customer')}")

        # Validasi & terapkan voucher dari DB outlet
        voucher_code     = data.get("voucher_code", "").strip().upper() if data.get("voucher_code") else None
        voucher_discount = 0
        if voucher_code:
            try:
                conn_v = get_outlet_connection(outlet_id)
                cur_v  = conn_v.cursor()
                cur_v.execute("""
                    SELECT * FROM vouchers WHERE code=? AND is_active=1
                    AND (expires_at IS NULL OR expires_at >= datetime('now','localtime'))
                    AND (max_uses = -1 OR used_count < max_uses)
                """, (voucher_code,))
                voucher = cur_v.fetchone()
                if voucher:
                    voucher = dict(voucher)
                    items_raw = data.get("items", {})
                    subtotal_calc = sum(
                        v.get("harga", 0) * v.get("qty", 0)
                        for v in items_raw.values() if isinstance(v, dict)
                    )
                    if subtotal_calc >= voucher["min_order"]:
                        if voucher["discount_type"] == "percent":
                            voucher_discount = int(subtotal_calc * voucher["discount_value"] / 100)
                        else:
                            voucher_discount = voucher["discount_value"]
                        cur_v.execute("UPDATE vouchers SET used_count=used_count+1 WHERE id=?", (voucher["id"],))
                conn_v.commit()
                conn_v.close()
            except Exception as e:
                logger.warning(f"Outlet {outlet_id} - Gagal proses voucher: {e}")

        # Simpan order ke database OUTLET (bukan database utama)
        try:
            clean_price = str(data.get("total", "0")).replace("TOTAL: ", "").replace("Rp ", "").replace(".", "").replace(",", "")
            clean_price = "".join(filter(str.isdigit, clean_price))
            items_str   = json.dumps(data)

            conn_o  = get_outlet_connection(outlet_id)
            cur_o   = conn_o.cursor()
            cur_o.execute("""
                INSERT INTO orders (customer_name, table_number, items, total_price, note, status,
                                    telegram_id, order_type, delivery_address, delivery_lat, delivery_lng,
                                    delivery_distance, delivery_fee, whatsapp, voucher_code, voucher_discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("customer", "Tamu"),
                data.get("table", "-"),
                items_str,
                int(clean_price) if clean_price else 0,
                data.get("generalNote", ""),
                "pending",
                telegram_id,
                order_type,
                data.get("delivery_address"),
                data.get("delivery_lat"),
                data.get("delivery_lng"),
                data.get("delivery_distance"),
                data.get("delivery_fee", 0),
                data.get("whatsapp"),
                voucher_code,
                voucher_discount,
            ))
            order_id = cur_o.lastrowid

            # Kurangi stok di DB outlet
            try:
                items_parsed = json.loads(items_str) if isinstance(items_str, str) else items_str
                actual_items = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
                for item_name, details in actual_items.items():
                    if not isinstance(details, dict):
                        continue
                    qty = details.get("qty", 0)
                    if qty <= 0:
                        continue
                    cur_o.execute("SELECT id, stock, stock_alert FROM menu_items WHERE name=?", (item_name,))
                    menu_row = cur_o.fetchone()
                    if not menu_row or menu_row["stock"] == -1:
                        continue
                    new_stock = max(0, menu_row["stock"] - qty)
                    cur_o.execute("UPDATE menu_items SET stock=? WHERE id=?", (new_stock, menu_row["id"]))
                    if new_stock == 0:
                        cur_o.execute("UPDATE menu_items SET is_available=0 WHERE id=?", (menu_row["id"],))
            except Exception as e:
                logger.warning(f"Outlet {outlet_id} - Gagal update stok: {e}")

            conn_o.commit()
            conn_o.close()
            logger.info(f"Outlet {outlet_id} - Order #{order_id} saved [{order_type}]")
        except Exception as e:
            logger.error(f"Outlet {outlet_id} - Gagal simpan order: {e}")
            return JSONResponse({"status": "error", "message": "Gagal menyimpan pesanan"}, status_code=500)

        # Format pesan notifikasi
        formatted_msg = format_order_message(data, source=source)

        # Kirim notifikasi ke admin outlet via bot outlet
        outlet_bot = _outlet_bots.get(outlet_id)
        if outlet_bot:
            # Ambil admin_telegram_id dari settings outlet, fallback ke ADMIN_ID global
            outlet_admin_tg = get_outlet_setting(outlet_id, "admin_telegram_id", "")
            notify_ids = []
            if outlet_admin_tg and outlet_admin_tg.strip():
                try:
                    notify_ids.append(int(outlet_admin_tg.strip()))
                except ValueError:
                    pass
            # Juga kirim ke ADMIN_ID global jika berbeda
            if ADMIN_ID and ADMIN_ID not in notify_ids:
                notify_ids.append(ADMIN_ID)

            outlet_name = outlet.get("name", "Outlet")
            for notify_id in notify_ids:
                try:
                    await outlet_bot.send_message(
                        chat_id=notify_id,
                        text=f"<b>[{outlet_name}]</b>\n{formatted_msg}",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.warning(f"Outlet {outlet_id} - Gagal kirim notif ke {notify_id}: {e}")

            # Kirim invoice ke pembeli
            if telegram_id:
                try:
                    # Patch DB_PATH ke outlet agar invoice pakai nama restoran outlet
                    import database as _db
                    _orig_path = _db.DB_PATH
                    _db.DB_PATH = get_outlet_db_path(outlet_id)
                    invoice_buf = generate_invoice_image(data, order_id)
                    _db.DB_PATH = _orig_path

                    if invoice_buf:
                        from aiogram.types import BufferedInputFile
                        await outlet_bot.send_photo(
                            chat_id=telegram_id,
                            photo=BufferedInputFile(invoice_buf.read(), filename="invoice.png"),
                            caption=f"<b>Invoice #{order_id}</b> — {outlet.get('name', 'Restaurant')}",
                            parse_mode="HTML"
                        )
                    else:
                        await outlet_bot.send_message(
                            chat_id=telegram_id,
                            text=f"<b>Pesanan #{order_id} diterima!</b>\n\n{formatted_msg}",
                            parse_mode="HTML"
                        )
                except Exception as e:
                    logger.error(f"Outlet {outlet_id} - Gagal kirim invoice ke {telegram_id}: {e}")

        return JSONResponse({"status": "ok", "message": "Order processed", "voucher_discount": voucher_discount})

    except Exception as e:
        logger.error(f"Outlet {outlet_id} - Error submit_order: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# MULTI-OUTLET — DELIVERY PAGE
# ─────────────────────────────────────────────

@app.get("/outlet/{outlet_id}/delivery", response_class=HTMLResponse)
async def outlet_delivery_page(outlet_id: int, request: Request):
    """Halaman delivery untuk outlet tertentu."""
    outlet = get_outlet_by_id(outlet_id)
    if not outlet or not outlet["is_active"]:
        return HTMLResponse("<h2>Outlet tidak tersedia</h2>", status_code=404)

    tgid = request.query_params.get("tgid", "")

    import database as _db
    original_path = _db.DB_PATH
    _db.DB_PATH = get_outlet_db_path(outlet_id)
    try:
        menu_data = get_menu_from_db()
        settings = {
            "restaurant_lat":      _db.get_setting("restaurant_lat", "-6.614970215748657"),
            "restaurant_lng":      _db.get_setting("restaurant_lng", "106.80385837668723"),
            "delivery_min_fee":    _db.get_setting("delivery_min_fee", "5000"),
            "delivery_fee_per_km": _db.get_setting("delivery_fee_per_km", "3000"),
            "delivery_min_km":     _db.get_setting("delivery_min_km", "1"),
            "delivery_max_km":     _db.get_setting("delivery_max_km", "10"),
        }
        qris_image = _db.get_setting("qris_image", "/static/images/qris.jpg")
        tax_settings = {
            "enable_service": _db.get_setting("enable_service", "1") == "1",
            "service_rate":   float(_db.get_setting("service_rate", "10")),
            "enable_tax":     _db.get_setting("enable_tax", "1") == "1",
            "tax_rate":       float(_db.get_setting("tax_rate", "11")),
            "tax_label":      _db.get_setting("tax_label", "PBJT"),
        }
    finally:
        _db.DB_PATH = original_path

    return templates.TemplateResponse("delivery.html", {
        "request": request,
        "menu": menu_data,
        "current_year": datetime.now().year,
        "tgid": tgid,
        "settings": settings,
        "restaurant_name": outlet["name"],
        "qris_image": qris_image,
        "tax_settings": tax_settings,
        "outlet_id": outlet_id,
    })


@app.get("/outlet/{outlet_id}/api/delivery-fee")
async def outlet_delivery_fee(outlet_id: int, lat: float, lng: float):
    """Hitung ongkos kirim untuk outlet tertentu."""
    try:
        rest_lat    = float(get_outlet_setting(outlet_id, "restaurant_lat", "-6.614970215748657"))
        rest_lng    = float(get_outlet_setting(outlet_id, "restaurant_lng", "106.80385837668723"))
        min_fee     = int(get_outlet_setting(outlet_id, "delivery_min_fee", "5000"))
        fee_per_km  = int(get_outlet_setting(outlet_id, "delivery_fee_per_km", "3000"))
        min_km      = float(get_outlet_setting(outlet_id, "delivery_min_km", "1"))
        max_km      = float(get_outlet_setting(outlet_id, "delivery_max_km", "10"))

        R    = 6371
        dlat = math.radians(lat - rest_lat)
        dlng = math.radians(lng - rest_lng)
        a    = math.sin(dlat/2)**2 + math.cos(math.radians(rest_lat)) * math.cos(math.radians(lat)) * math.sin(dlng/2)**2
        distance = R * 2 * math.asin(math.sqrt(a))

        if distance > max_km:
            return JSONResponse({"status": "error", "message": f"Lokasi terlalu jauh (maks {max_km:.0f} km)", "distance": round(distance, 2)})

        fee = min_fee if distance <= min_km else min_fee + int((distance - min_km) * fee_per_km)
        maps_url = f"https://www.google.com/maps/dir/{rest_lat},{rest_lng}/{lat},{lng}"

        return JSONResponse({"status": "ok", "distance": round(distance, 2), "fee": fee, "maps_url": maps_url, "max_km": max_km})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# if __name__ == "__main__" dipindah ke bawah semua route


# ─────────────────────────────────────────────
# MULTI-OUTLET — COURIER CONFIRMATION PAGE
# ─────────────────────────────────────────────

@app.get("/outlet/{outlet_id}/courier/{order_id}/{token}", response_class=HTMLResponse)
async def outlet_courier_page(outlet_id: int, order_id: int, token: str, request: Request):
    """Halaman konfirmasi pengiriman untuk kurir outlet."""
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id=? AND courier_token=?", (order_id, token))
        order = cursor.fetchone()
        conn.close()

        if not order:
            return HTMLResponse("<h2 style='font-family:sans-serif;padding:40px'>Link tidak valid atau sudah kadaluarsa.</h2>", status_code=404)

        order = dict(order)
        outlet = get_outlet_by_id(outlet_id)
        rest_name = get_outlet_setting(outlet_id, "restaurant_name", outlet["name"] if outlet else "Restaurant")
        rest_lat  = get_outlet_setting(outlet_id, "restaurant_lat", "-6.614970")
        rest_lng  = get_outlet_setting(outlet_id, "restaurant_lng", "106.803858")

        # Parse items untuk ditampilkan
        try:
            items_raw = order.get("items", "{}")
            items_parsed = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
            actual = items_parsed.get("items", items_parsed) if isinstance(items_parsed, dict) else items_parsed
        except Exception:
            actual = {}

        return templates.TemplateResponse("courier.html", {
            "request": request,
            "order": order,
            "restaurant_name": rest_name,
            "restaurant_lat": rest_lat,
            "restaurant_lng": rest_lng,
            "items_json": json.dumps(actual),
            "current_year": datetime.now().year,
        })
    except Exception as e:
        logger.error(f"Outlet {outlet_id} courier page error: {e}")
        return HTMLResponse(f"<h2>Error: {str(e)}</h2>", status_code=500)


@app.post("/outlet/{outlet_id}/courier/{order_id}/{token}/confirm")
async def outlet_courier_confirm(outlet_id: int, order_id: int, token: str):
    """Konfirmasi pengiriman selesai oleh kurir outlet."""
    try:
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id=? AND courier_token=?", (order_id, token))
        order = cursor.fetchone()

        if not order:
            conn.close()
            return JSONResponse({"status": "error", "message": "Order tidak ditemukan"}, status_code=404)

        if order["status"] == "completed":
            conn.close()
            return JSONResponse({"status": "already", "message": "Sudah dikonfirmasi"})

        cursor.execute("UPDATE orders SET status='completed' WHERE id=?", (order_id,))
        conn.commit()

        telegram_id = order["telegram_id"]
        customer_name = order["customer_name"] or "Pelanggan"
        conn.close()

        # Notifikasi ke pembeli
        if telegram_id:
            outlet_bot = _outlet_bots.get(outlet_id)
            if outlet_bot:
                try:
                    await outlet_bot.send_message(
                        chat_id=telegram_id,
                        text=f"<b>✅ PESANAN SELESAI DIKIRIM!</b>\n\n"
                             f"Halo <b>{customer_name}</b>!\n"
                             f"Pesanan #{order_id} telah sampai di tujuan.\n\n"
                             f"Terima kasih telah memesan! 😊",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Outlet {outlet_id} - Gagal kirim notif selesai: {e}")

        # Notifikasi ke admin
        if ADMIN_ID:
            outlet_bot = _outlet_bots.get(outlet_id)
            if outlet_bot:
                try:
                    outlet = get_outlet_by_id(outlet_id)
                    outlet_name = outlet["name"] if outlet else f"Outlet {outlet_id}"
                    await outlet_bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"<b>✅ [{outlet_name}] Pesanan #{order_id} selesai dikirim!</b>\n\n"
                             f"Kurir: {order['courier_name']}\n"
                             f"Pembeli: {customer_name}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Outlet {outlet_id} - Gagal kirim notif admin: {e}")

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Outlet {outlet_id} courier confirm error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
