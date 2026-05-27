"""
multi_outlet_routes.py
Routes untuk sistem multi-outlet SGO.
Di-import oleh main.py dan di-register ke FastAPI app.
"""
import json
import secrets
import hashlib
import logging
from datetime import datetime
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from aiogram import Bot, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# OWNER SESSION STORE
# ─────────────────────────────────────────────
_owner_sessions = {}
OWNER_SESSION_DAYS = 7

def _create_owner_session(username: str) -> str:
    import time as _t
    token = secrets.token_urlsafe(32)
    _owner_sessions[token] = {"username": username, "expires": _t.time() + OWNER_SESSION_DAYS * 86400}
    return token

def _get_owner_session(request: Request):
    import time as _t
    token = request.cookies.get("sgo_owner_session")
    if not token:
        return None
    sess = _owner_sessions.get(token)
    if not sess or _t.time() > sess["expires"]:
        _owner_sessions.pop(token, None)
        return None
    return sess

# ─────────────────────────────────────────────
# OUTLET BOT REGISTRY
# {outlet_id: Bot instance}
# ─────────────────────────────────────────────
_outlet_bots = {}

def get_outlet_bot(outlet_id: int, bot_token: str) -> Bot:
    if outlet_id not in _outlet_bots:
        _outlet_bots[outlet_id] = Bot(token=bot_token)
    return _outlet_bots[outlet_id]

def remove_outlet_bot(outlet_id: int):
    if outlet_id in _outlet_bots:
        del _outlet_bots[outlet_id]

# ─────────────────────────────────────────────
# HELPER: ambil statistik hari ini untuk outlet
# ─────────────────────────────────────────────
def get_outlet_today_stats(outlet_id: int) -> dict:
    from master_db import get_outlet_connection
    try:
        today_start = datetime.now().strftime('%Y-%m-%d 00:00:00')
        today_end   = datetime.now().strftime('%Y-%m-%d 23:59:59')
        conn = get_outlet_connection(outlet_id)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN status != 'cancelled' THEN total_price ELSE 0 END) as rev,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
            FROM orders WHERE created_at >= ? AND created_at <= ?
        """, (today_start, today_end))
        row = cursor.fetchone()
        conn.close()
        return {
            'orders':  row['cnt'] or 0,
            'revenue': row['rev'] or 0,
            'pending': row['pending'] or 0,
        }
    except Exception as e:
        logger.warning(f"Gagal ambil stats outlet {outlet_id}: {e}")
        return {'orders': 0, 'revenue': 0, 'pending': 0}

# ─────────────────────────────────────────────
# REGISTER ROUTES ke FastAPI app
# ─────────────────────────────────────────────
def register_multi_outlet_routes(app, templates, BASE_URL, WEBHOOK_PATH="/webhook"):
    from master_db import (
        get_all_outlets, get_outlet_by_id, get_outlet_connection,
        create_outlet, verify_owner, verify_outlet_admin,
        get_master_connection
    )
    import database as _db_module

    # ── OWNER LOGIN ──
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
            response.set_cookie("sgo_owner_session", token, max_age=OWNER_SESSION_DAYS*86400, httponly=True, samesite="lax")
            logger.info(f"✅ Owner login: {username}")
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
            _owner_sessions.pop(token, None)
        response = RedirectResponse(url="/owner/login", status_code=302)
        response.delete_cookie("sgo_owner_session")
        return response

    # ── OWNER DASHBOARD ──
    @app.get("/owner/dashboard", response_class=HTMLResponse)
    async def owner_dashboard(request: Request):
        sess = _get_owner_session(request)
        if not sess:
            return RedirectResponse(url="/owner/login", status_code=302)

        outlets = get_all_outlets(active_only=False)

        # Tambahkan statistik hari ini per outlet
        total_revenue = 0
        total_orders  = 0
        total_pending = 0
        for outlet in outlets:
            stats = get_outlet_today_stats(outlet['id'])
            outlet['stats'] = stats
            if outlet['is_active']:
                total_revenue += stats['revenue']
                total_orders  += stats['orders']
                total_pending += stats['pending']

        return templates.TemplateResponse("owner_dashboard.html", {
            "request": request,
            "outlets": outlets,
            "username": sess["username"],
            "today": datetime.now().strftime("%d %B %Y"),
            "current_year": datetime.now().year,
            "summary": {
                "total_revenue": total_revenue,
                "total_orders":  total_orders,
                "total_pending": total_pending,
            }
        })

    # ── OWNER API: Tambah Outlet ──
    @app.post("/owner/api/outlets")
    async def owner_add_outlet(request: Request):
        sess = _get_owner_session(request)
        if not sess:
            return JSONResponse({'status': 'error', 'message': 'Unauthorized'}, status_code=401)
        try:
            body = await request.json()
            name         = str(body.get('name', '')).strip()
            bot_token    = str(body.get('bot_token', '')).strip()
            admin_user   = str(body.get('admin_username', '')).strip()
            admin_pass   = str(body.get('admin_password', '')).strip()

            if not name or not bot_token or not admin_user or not admin_pass:
                return JSONResponse({'status': 'error', 'message': 'Semua field wajib diisi'}, status_code=400)
            if len(admin_pass) < 6:
                return JSONResponse({'status': 'error', 'message': 'Password minimal 6 karakter'}, status_code=400)

            # Validasi bot token dengan test API call
            try:
                test_bot = Bot(token=bot_token)
                bot_info = await test_bot.get_me()
                await test_bot.session.close()
                logger.info(f"Bot valid: @{bot_info.username}")
            except Exception as e:
                return JSONResponse({'status': 'error', 'message': f'Bot token tidak valid: {str(e)}'}, status_code=400)

            outlet_id = create_outlet(name, bot_token, admin_user, admin_pass)

            # Register webhook untuk bot outlet baru
            try:
                outlet_bot = get_outlet_bot(outlet_id, bot_token)
                webhook_url = f"{BASE_URL}/outlet/{outlet_id}/webhook"
                await outlet_bot.set_webhook(webhook_url, allowed_updates=["message", "callback_query"])
                logger.info(f"✅ Webhook outlet {outlet_id} set: {webhook_url}")
            except Exception as e:
                logger.warning(f"Gagal set webhook outlet {outlet_id}: {e}")

            return JSONResponse({'status': 'ok', 'outlet_id': outlet_id, 'message': f'Outlet {name} berhasil dibuat'})
        except Exception as e:
            logger.error(f"Error creating outlet: {e}")
            return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

    # ── OWNER API: Toggle Outlet ──
    @app.post("/owner/api/outlets/{outlet_id}/toggle")
    async def owner_toggle_outlet(outlet_id: int, request: Request):
        sess = _get_owner_session(request)
        if not sess:
            return JSONResponse({'status': 'error', 'message': 'Unauthorized'}, status_code=401)
        try:
            conn = get_master_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM outlets WHERE id=?", (outlet_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return JSONResponse({'status': 'error', 'message': 'Outlet tidak ditemukan'}, status_code=404)
            new_val = 0 if row['is_active'] == 1 else 1
            cursor.execute("UPDATE outlets SET is_active=? WHERE id=?", (new_val, outlet_id))
            conn.commit()
            conn.close()
            return JSONResponse({'status': 'ok', 'is_active': new_val})
        except Exception as e:
            return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

    # ── OUTLET WEBHOOK ──
    @app.post("/outlet/{outlet_id}/webhook")
    async def outlet_webhook(outlet_id: int, update: dict):
        """Terima update Telegram untuk outlet tertentu."""
        outlet = get_outlet_by_id(outlet_id)
        if not outlet or not outlet['is_active']:
            return {"ok": False}
        try:
            outlet_bot = get_outlet_bot(outlet_id, outlet['bot_token'])
            # Buat dispatcher khusus outlet
            from aiogram import Dispatcher as _Dp
            from aiogram.filters import CommandStart as _CS
            # Gunakan dispatcher global tapi dengan bot outlet
            telegram_update = types.Update(**update)
            # Inject outlet_id ke update untuk dipakai handler
            # Simpan mapping bot_id -> outlet_id
            _outlet_bot_map[outlet_bot.id if hasattr(outlet_bot, 'id') else outlet_id] = outlet_id
            await _outlet_dp.feed_update(outlet_bot, telegram_update)
        except Exception as e:
            logger.error(f"Outlet {outlet_id} webhook error: {e}")
        return {"ok": True}

    # ── OUTLET MENU (untuk pembeli) ──
    @app.get("/outlet/{outlet_id}", response_class=HTMLResponse)
    async def outlet_menu(outlet_id: int, request: Request):
        outlet = get_outlet_by_id(outlet_id)
        if not outlet or not outlet['is_active']:
            return HTMLResponse("<h2 style='font-family:sans-serif;padding:40px'>Outlet tidak ditemukan atau tidak aktif.</h2>", status_code=404)

        # Ambil menu dari database outlet
        orig_path = _db_module.DB_PATH
        _db_module.DB_PATH = __import__('master_db').get_outlet_db_path(outlet_id)
        from database import get_connection as _gc
        try:
            conn = _gc()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM menu_items WHERE is_available=1")
            rows = [dict(r) for r in cursor.fetchall()]

            # Rating per item
            cursor.execute("SELECT menu_item_name, AVG(rating) as avg_rating, COUNT(*) as cnt FROM item_reviews GROUP BY menu_item_name")
            ratings = {r['menu_item_name']: {'avg': round(r['avg_rating'],1), 'count': r['cnt']} for r in cursor.fetchall()}
            conn.close()
        finally:
            _db_module.DB_PATH = orig_path

        # Susun menu per kategori
        from main import CATEGORY_ORDER, get_setting as _gs
        _db_module.DB_PATH = __import__('master_db').get_outlet_db_path(outlet_id)
        rest_name = _db_module.get_setting('restaurant_name', outlet['name'])
        qris_img  = _db_module.get_setting('qris_image', '/static/images/qris.jpg')
        tax_settings = {
            "enable_service": _db_module.get_setting("enable_service","1") == "1",
            "service_rate":   float(_db_module.get_setting("service_rate","10")),
            "enable_tax":     _db_module.get_setting("enable_tax","1") == "1",
            "tax_rate":       float(_db_module.get_setting("tax_rate","11")),
            "tax_label":      _db_module.get_setting("tax_label","PBJT"),
        }
        _db_module.DB_PATH = orig_path

        menu = {}
        for item in rows:
            img = item.get('image_url','')
            if img and img.startswith('/'):
                img = BASE_URL.rstrip('/') + img
            item['image'] = img
            r = ratings.get(item['name'], {})
            item['avg_rating']   = r.get('avg', 0)
            item['review_count'] = r.get('count', 0)
            cat = item['category']
            if cat not in menu:
                menu[cat] = []
            menu[cat].append(item)

        tgid = request.query_params.get('tgid', '')
        return templates.TemplateResponse("index.html", {
            "request": request,
            "menu": menu,
            "current_year": datetime.now().year,
            "tgid": tgid,
            "restaurant_name": rest_name,
            "qris_image": qris_img,
            "tax_settings": tax_settings,
            "outlet_id": outlet_id,
        })

    # ── OUTLET DASHBOARD (Admin) ──
    @app.get("/outlet/{outlet_id}/login", response_class=HTMLResponse)
    async def outlet_login_page(outlet_id: int, request: Request):
        outlet = get_outlet_by_id(outlet_id)
        if not outlet:
            return HTMLResponse("Outlet tidak ditemukan", status_code=404)
        # Cek session admin outlet
        sess = _get_outlet_admin_session(request, outlet_id)
        if sess:
            return RedirectResponse(url=f"/outlet/{outlet_id}/dashboard", status_code=302)
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": None,
            "next": f"/outlet/{outlet_id}/dashboard",
            "username": "",
            "restaurant_name": outlet['name'],
            "current_year": datetime.now().year,
            "outlet_id": outlet_id,
        })

    @app.post("/outlet/{outlet_id}/login")
    async def outlet_login_submit(outlet_id: int, request: Request):
        outlet = get_outlet_by_id(outlet_id)
        if not outlet:
            return HTMLResponse("Outlet tidak ditemukan", status_code=404)
        form = await request.form()
        username = str(form.get("username","")).strip().lower()
        password = str(form.get("password",""))
        result = verify_outlet_admin(outlet_id, username, password)
        if result:
            token = _create_outlet_admin_session(outlet_id, username)
            response = RedirectResponse(url=f"/outlet/{outlet_id}/dashboard", status_code=302)
            response.set_cookie(f"sgo_outlet_{outlet_id}", token, max_age=7*86400, httponly=True, samesite="lax")
            return response
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Username atau password salah.",
            "next": f"/outlet/{outlet_id}/dashboard",
            "username": username,
            "restaurant_name": outlet['name'],
            "current_year": datetime.now().year,
            "outlet_id": outlet_id,
        }, status_code=401)

    @app.get("/outlet/{outlet_id}/logout")
    async def outlet_logout(outlet_id: int, request: Request):
        token = request.cookies.get(f"sgo_outlet_{outlet_id}")
        if token:
            _outlet_admin_sessions.pop(token, None)
        response = RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)
        response.delete_cookie(f"sgo_outlet_{outlet_id}")
        return response

    # ── OUTLET DASHBOARD ──
    @app.get("/outlet/{outlet_id}/dashboard", response_class=HTMLResponse)
    async def outlet_dashboard(outlet_id: int, request: Request):
        outlet = get_outlet_by_id(outlet_id)
        if not outlet:
            return HTMLResponse("Outlet tidak ditemukan", status_code=404)
        sess = _get_outlet_admin_session(request, outlet_id)
        if not sess:
            return RedirectResponse(url=f"/outlet/{outlet_id}/login", status_code=302)

        orig_path = _db_module.DB_PATH
        _db_module.DB_PATH = __import__('master_db').get_outlet_db_path(outlet_id)
        try:
            conn = _db_module.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM menu_items ORDER BY category, name")
            rows = cursor.fetchall()
            cursor.execute("SELECT menu_item_name, AVG(rating) as avg_rating, COUNT(*) as total_reviews FROM item_reviews GROUP BY menu_item_name")
            item_ratings = {r['menu_item_name']: {'avg': round(r['avg_rating'],1), 'count': r['total_reviews']} for r in cursor.fetchall()}
            conn.close()
            flat_menu = [dict(r) for r in rows]
            for item in flat_menu:
                ri = item_ratings.get(item['name'], {})
                item['avg_rating']   = ri.get('avg', 0)
                item['review_count'] = ri.get('count', 0)
            rest_name = _db_module.get_setting('restaurant_name', outlet['name'])
        finally:
            _db_module.DB_PATH = orig_path

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "items": flat_menu,
            "current_year": datetime.now().year,
            "restaurant_name": rest_name,
            "user_role": "admin",
            "username": sess["username"],
            "outlet_id": outlet_id,
            "base_path": f"/outlet/{outlet_id}",
        })

    logger.info("✅ Multi-outlet routes registered")

# ─────────────────────────────────────────────
# OUTLET ADMIN SESSION STORE
# ─────────────────────────────────────────────
_outlet_admin_sessions = {}
_outlet_bot_map = {}

# Dispatcher untuk outlet bots
from aiogram import Dispatcher as _OutletDp
_outlet_dp = _OutletDp()

def _create_outlet_admin_session(outlet_id: int, username: str) -> str:
    import time as _t
    token = secrets.token_urlsafe(32)
    _outlet_admin_sessions[token] = {
        "outlet_id": outlet_id,
        "username": username,
        "expires": _t.time() + 7 * 86400
    }
    return token

def _get_outlet_admin_session(request: Request, outlet_id: int):
    import time as _t
    token = request.cookies.get(f"sgo_outlet_{outlet_id}")
    if not token:
        return None
    sess = _outlet_admin_sessions.get(token)
    if not sess or _t.time() > sess["expires"] or sess["outlet_id"] != outlet_id:
        _outlet_admin_sessions.pop(token, None)
        return None
    return sess

async def init_outlet_bots(base_url: str):
    """Inisialisasi semua bot outlet saat server start."""
    from master_db import get_all_outlets
    outlets = get_all_outlets(active_only=True)
    for outlet in outlets:
        try:
            outlet_bot = get_outlet_bot(outlet['id'], outlet['bot_token'])
            webhook_url = f"{base_url}/outlet/{outlet['id']}/webhook"
            await outlet_bot.set_webhook(webhook_url, allowed_updates=["message","callback_query"])
            logger.info(f"✅ Outlet {outlet['id']} ({outlet['name']}) webhook: {webhook_url}")
        except Exception as e:
            logger.warning(f"Gagal init bot outlet {outlet['id']}: {e}")
