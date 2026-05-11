import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import requests
import random
import datetime
import time
import threading

# ╔══════════════════════════════════════════════════════════╗
#   CONFIGURATION
# ╚══════════════════════════════════════════════════════════╝
TOKEN        = "8600224839:AAHf63oBYlOU0GlJeGmxkld6YEAjjUHChk0"
OWNER_ID     = 8638310766
ADMIN_IDS    = {OWNER_ID, 6504877406}          # ← all admin IDs here
LOG_CHANNEL  = "-1003745735185"
API_URL      = "https://vehicle-eight-vert.vercel.app/api"
BOT_USERNAME = "RcOsintRobot"
DEVELOPER    = "@BatHaxTG"
PUBLISHER    = "@mythos29"

CHANNELS = [
    {"username": "@dealsandfun99", "url": "https://t.me/dealsandfun99"},
    {"username": "@dealsandfun77", "url": "https://t.me/dealsandfun77"},
]

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ╔══════════════════════════════════════════════════════════╗
#   DATABASE
# ╚══════════════════════════════════════════════════════════╝
conn    = sqlite3.connect("database.db", check_same_thread=False)
cursor  = conn.cursor()
db_lock = threading.Lock()

cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY,
        username      TEXT,
        full_name     TEXT,
        credits       INTEGER DEFAULT 10,
        referred_by   INTEGER,
        last_daily    TEXT    DEFAULT '',
        join_date     TEXT,
        last_seen     TEXT,
        total_lookups INTEGER DEFAULT 0,
        is_banned     INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS promocodes (
        code   TEXT PRIMARY KEY,
        amount INTEGER,
        uses   INTEGER DEFAULT 1
    );
""")
conn.commit()

# ─── DB helpers ─────────────────────────────────────────────
def db_exec(q, p=()):
    with db_lock:
        cursor.execute(q, p)
        conn.commit()

def db_fetch(q, p=()):
    with db_lock:
        cursor.execute(q, p)
        return cursor.fetchone()

def db_fetchall(q, p=()):
    with db_lock:
        cursor.execute(q, p)
        return cursor.fetchall()

# ─── misc helpers ───────────────────────────────────────────
def is_admin(uid):
    return uid in ADMIN_IDS

def update_last_seen(uid):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    db_exec("UPDATE users SET last_seen=? WHERE user_id=?", (now, uid))

def ensure_user(uid, uname="", fname=""):
    existing = db_fetch("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not existing:
        today = str(datetime.date.today())
        now   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        db_exec(
            "INSERT OR IGNORE INTO users "
            "(user_id,username,full_name,credits,join_date,last_seen,last_daily) "
            "VALUES (?,?,?,?,?,?,'')",
            (uid, uname, fname, 999999 if is_admin(uid) else 10, today, now)
        )

def is_banned(uid):
    row = db_fetch("SELECT is_banned FROM users WHERE user_id=?", (uid,))
    return bool(row and row[0])

def is_joined(uid):
    for ch in CHANNELS:
        try:
            s = bot.get_chat_member(ch["username"], uid).status
            if s not in ("member", "administrator", "creator"):
                return False
        except:
            return False
    return True

def get_user_count():
    return db_fetch("SELECT COUNT(*) FROM users")[0]

def get_online_count():
    ago = (datetime.datetime.now() - datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
    return db_fetch("SELECT COUNT(*) FROM users WHERE last_seen>=?", (ago,))[0]

def get_today_joins():
    return db_fetch("SELECT COUNT(*) FROM users WHERE join_date=?", (str(datetime.date.today()),))[0]

def get_total_lookups():
    r = db_fetch("SELECT SUM(total_lookups) FROM users")
    return r[0] or 0


# ╔══════════════════════════════════════════════════════════╗
#   API  — fetch vehicle by RC
# ╚══════════════════════════════════════════════════════════╝
def fetch_vehicle(rc: str):
    """
    Returns:
      dict          – vehicle fields on success
      None          – RC not found / empty record
      "timeout"     – request timed out
      "server_error"– HTTP error or invalid JSON
    """
    url = f"{API_URL}?rc={rc}"
    print(f"[API] GET {url}")

    try:
        res = requests.get(url, timeout=30, headers={"Accept": "application/json"})
    except requests.exceptions.Timeout:
        print("[API] Timeout")
        return "timeout"
    except Exception as e:
        print(f"[API] Error: {e}")
        return "server_error"

    print(f"[API] HTTP {res.status_code} | {res.text[:600]}")

    if res.status_code != 200:
        return "server_error"

    try:
        j = res.json()
    except Exception:
        print("[API] Non-JSON response")
        return "server_error"

    raw = None
    for key in ("details", "data", "result", "vehicle", "response"):
        if isinstance(j.get(key), dict) and j[key]:
            raw = j[key]
            break
    if raw is None and isinstance(j, dict) and len(j) > 2:
        raw = j

    if not raw:
        print(f"[API] Empty / unrecognised: {j}")
        return None

    def g(key, *fallbacks, default="N/A"):
        for k in (key,) + fallbacks:
            v = raw.get(k)
            if v and str(v).strip() not in ("", "null", "None", "N/A"):
                return str(v).strip()
        return default

    vehicle = {
        "owner":      g("Owner Name"),
        "model":      g("Maker Model",       "Model"),
        "make":       g("Model Name",        "Make",   "Brand"),
        "veh_class":  g("Vehicle Class"),
        "fuel":       g("Fuel Type"),
        "fuel_norms": g("Fuel Norms"),
        "city":       g("City Name",         "City"),
        "fitness":    g("Fitness Upto"),
        "insurer":    g("Insurance Company", "Insurer"),
        "ins_expiry": g("Insurance Expiry",  "Insurance Upto"),
        "rto":        g("Registered RTO",    "RTO"),
        "reg_date":   g("Registration Date", "Reg Date"),
        "tax_upto":   g("Tax Upto"),
        "address":    g("Address"),
        "financier":  g("Financier Name",    "Financier"),
    }

    if vehicle["owner"] == "N/A" and vehicle["model"] == "N/A":
        print("[API] Empty record — no owner/model")
        return None

    return vehicle


# ╔══════════════════════════════════════════════════════════╗
#   UI CONSTANTS
# ╚══════════════════════════════════════════════════════════╝
DIV   = "◆━━━━━━━━━━━━━━━━◆"
DIV2  = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
FOOT  = f"👨‍💻 Dev: {DEVELOPER}  •  📢 Pub & Mod: {PUBLISHER}"


# ╔══════════════════════════════════════════════════════════╗
#   KEYBOARDS
# ╚══════════════════════════════════════════════════════════╝
def force_join_markup(uid):
    m = InlineKeyboardMarkup(row_width=1)
    statuses = []
    for ch in CHANNELS:
        try:
            s = bot.get_chat_member(ch["username"], uid).status
            statuses.append(s in ("member", "administrator", "creator"))
        except:
            statuses.append(False)
    m.add(
        InlineKeyboardButton(f"{'✅' if statuses[0] else '🔔'}  Channel 1", url=CHANNELS[0]["url"]),
        InlineKeyboardButton(f"{'✅' if statuses[1] else '🔔'}  Channel 2", url=CHANNELS[1]["url"]),
        InlineKeyboardButton("🔄  Verify Membership", callback_data="verify"),
    )
    return m

def main_menu():
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("🔍  RC Lookup",     callback_data="lookup"),
        InlineKeyboardButton("🪪  My Profile",     callback_data="account"),
        InlineKeyboardButton("💎  Earn Credits",   callback_data="earn"),
        InlineKeyboardButton("📖  How It Works",   callback_data="help"),
    )
    return m

def admin_menu():
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("📊  Statistics",      callback_data="adm_stats"),
        InlineKeyboardButton("👥  User List",       callback_data="adm_users_0"),
        InlineKeyboardButton("🔎  Search User",     callback_data="adm_search_user"),
        InlineKeyboardButton("📨  DM a User",       callback_data="adm_dm_user"),
        InlineKeyboardButton("📢  Broadcast",       callback_data="adm_bc"),
        InlineKeyboardButton("💰  Manage Credits",  callback_data="adm_cr"),
        InlineKeyboardButton("🎟️  Promo Codes",     callback_data="adm_promo_menu"),
        InlineKeyboardButton("🚫  Ban User",        callback_data="adm_ban"),
        InlineKeyboardButton("✅  Unban User",       callback_data="adm_unban"),
        InlineKeyboardButton("📣  Credits → All",   callback_data="adm_credits_all"),
    )
    m.add(InlineKeyboardButton("👁️  Switch to User View", callback_data="adm_user_mode"))
    return m

def user_mode_menu():
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("🔍  RC Lookup",     callback_data="lookup"),
        InlineKeyboardButton("🪪  My Profile",     callback_data="account"),
        InlineKeyboardButton("💎  Earn Credits",   callback_data="earn"),
        InlineKeyboardButton("📖  How It Works",   callback_data="help"),
        InlineKeyboardButton("⬅️  Admin Panel",    callback_data="home"),
    )
    return m

def earn_menu():
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("🎯  Daily Bonus",    callback_data="daily"),
        InlineKeyboardButton("🎟️  Redeem Code",    callback_data="promo_red"),
        InlineKeyboardButton("🤝  Refer & Earn",   callback_data="refer"),
        InlineKeyboardButton("⬅️  Back",           callback_data="home"),
    )
    return m

def back_btn(target="home"):
    m = InlineKeyboardMarkup()
    m.add(InlineKeyboardButton("⬅️  Back", callback_data=target))
    return m


# ╔══════════════════════════════════════════════════════════╗
#   /start
# ╚══════════════════════════════════════════════════════════╝
@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid   = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else "NoUsername"
    fname = message.from_user.first_name or "User"
    now   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    today = str(datetime.date.today())

    # Admin panel ────────────────────────────────────────────
    if is_admin(uid):
        ensure_user(uid, uname, fname)
        update_last_seen(uid)
        bot.send_message(uid,
            f"👑 <b>Admin Panel</b>\n"
            f"{DIV}\n"
            f"Welcome back, <b>{fname}</b>!\n\n"
            f"👥 Total Users:   <b>{get_user_count()}</b>\n"
            f"🟢 Online (10m):  <b>{get_online_count()}</b>\n"
            f"📅 Today Joins:   <b>{get_today_joins()}</b>\n"
            f"🔍 Total Lookups: <b>{get_total_lookups()}</b>\n"
            f"{DIV}\n"
            f"{FOOT}",
            reply_markup=admin_menu()
        )
        return

    # Banned ─────────────────────────────────────────────────
    if is_banned(uid):
        bot.send_message(uid,
            f"🚫 <b>Access Denied</b>\n"
            f"{DIV}\n"
            f"You have been banned from this bot.\n\n"
            f"{FOOT}"
        )
        return

    # Register new user ──────────────────────────────────────
    existing = db_fetch("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not existing:
        ref_id = None
        parts  = message.text.split()
        if len(parts) > 1 and parts[1].isdigit():
            ref_id = int(parts[1])
            if ref_id != uid:
                db_exec("UPDATE users SET credits=credits+10 WHERE user_id=?", (ref_id,))
                try:
                    bot.send_message(ref_id,
                        f"🎉 <b>New Referral!</b>\n"
                        f"{DIV}\n"
                        f"Someone joined using your link!\n"
                        f"<b>+10 Credits</b> added to your wallet 🎊\n"
                        f"{FOOT}"
                    )
                except: pass

        db_exec(
            "INSERT OR IGNORE INTO users "
            "(user_id,username,full_name,referred_by,join_date,last_seen,last_daily) "
            "VALUES (?,?,?,?,?,?,'')",
            (uid, uname, fname, ref_id, today, now)
        )
        try:
            ref_link = f"<a href='tg://user?id={ref_id}'>{ref_id}</a>" if ref_id else "Organic"
            bot.send_message(LOG_CHANNEL,
                f"🆕 <b>New User Joined</b>\n"
                f"{DIV}\n"
                f"👤 <b>Name:</b>   {fname}  {uname}\n"
                f"🆔 <b>ID:</b>     <code>{uid}</code>\n"
                f"🤝 <b>Ref:</b>    {ref_link}\n"
                f"📅 <b>Time:</b>   {now}\n"
                f"📊 <b>Total:</b>  <b>{get_user_count()}</b>"
            )
        except Exception as e:
            print(f"[LOG] {e}")
    else:
        update_last_seen(uid)

    # Force join check ───────────────────────────────────────
    if not is_joined(uid):
        bot.send_message(uid,
            f"👋 <b>Welcome, {fname}!</b>\n\n"
            f"{DIV}\n"
            f"🔔 Please join our channels first,\n"
            f"then tap <b>Verify Membership</b> below 👇\n"
            f"{DIV}\n"
            f"{FOOT}",
            reply_markup=force_join_markup(uid)
        )
    else:
        bot.send_message(uid,
            f"✨ <b>Welcome, {fname}!</b>\n\n"
            f"{DIV}\n"
            f"🔍 Instant Vehicle RC Lookup Bot\n"
            f"Get complete vehicle info in seconds!\n"
            f"{DIV}\n"
            f"{FOOT}",
            reply_markup=main_menu()
        )


# ╔══════════════════════════════════════════════════════════╗
#   /admin
# ╚══════════════════════════════════════════════════════════╝
@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return
    ensure_user(uid)
    update_last_seen(uid)
    fname = message.from_user.first_name or "Admin"
    bot.send_message(uid,
        f"👑 <b>Admin Panel</b>\n"
        f"{DIV}\n"
        f"Welcome, <b>{fname}</b>!\n\n"
        f"👥 Total Users:   <b>{get_user_count()}</b>\n"
        f"🟢 Online (10m):  <b>{get_online_count()}</b>\n"
        f"📅 Today Joins:   <b>{get_today_joins()}</b>\n"
        f"🔍 Total Lookups: <b>{get_total_lookups()}</b>\n"
        f"{DIV}\n"
        f"{FOOT}",
        reply_markup=admin_menu()
    )


# ╔══════════════════════════════════════════════════════════╗
#   CALLBACKS
# ╚══════════════════════════════════════════════════════════╝
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    uid = call.from_user.id
    mid = call.message.message_id

    # Banned check (skip for admins)
    if not is_admin(uid) and is_banned(uid):
        bot.answer_callback_query(call.id, "🚫 You are banned.", show_alert=True)
        return

    update_last_seen(uid)
    d = call.data

    # ── noop ────────────────────────────────────────────────
    if d == "noop":
        bot.answer_callback_query(call.id)
        return

    # ── verify membership ────────────────────────────────────
    if d == "verify":
        if is_joined(uid):
            bot.edit_message_text(
                f"✨ <b>Verified! Welcome!</b>\n\n"
                f"{DIV}\n"
                f"🔍 Instant Vehicle RC Lookup Bot\n"
                f"Get complete vehicle info in seconds!\n"
                f"{DIV}\n"
                f"{FOOT}",
                uid, mid, reply_markup=main_menu()
            )
        else:
            bot.answer_callback_query(call.id, "❌ Please join both channels first!", show_alert=True)
        return

    # ── home ────────────────────────────────────────────────
    if d == "home":
        if is_admin(uid):
            bot.edit_message_text(
                f"👑 <b>Admin Panel</b>\n"
                f"{DIV}\n"
                f"👥 Total Users:   <b>{get_user_count()}</b>\n"
                f"🟢 Online (10m):  <b>{get_online_count()}</b>\n"
                f"📅 Today Joins:   <b>{get_today_joins()}</b>\n"
                f"🔍 Total Lookups: <b>{get_total_lookups()}</b>\n"
                f"{DIV}\n"
                f"{FOOT}",
                uid, mid, reply_markup=admin_menu()
            )
        else:
            bot.edit_message_text(
                f"🏠 <b>Main Menu</b>\n"
                f"{DIV}\n"
                f"Select an option below 👇\n"
                f"{DIV}\n"
                f"{FOOT}",
                uid, mid, reply_markup=main_menu()
            )
        return

    # ── account / profile ────────────────────────────────────
    if d == "account":
        row = db_fetch(
            "SELECT credits,referred_by,join_date,total_lookups FROM users WHERE user_id=?", (uid,)
        )
        if not row:
            bot.answer_callback_query(call.id, "⚠️ Account not found. Send /start first.", show_alert=True)
            return
        uname_txt   = f"@{call.from_user.username}" if call.from_user.username else "—"
        ref_display = f"<a href='tg://user?id={row[1]}'>{row[1]}</a>" if row[1] else "None"
        credits_txt = "∞ Unlimited" if row[0] >= 999999 else str(row[0])
        bot.edit_message_text(
            f"🪪 <b>My Profile</b>\n"
            f"{DIV}\n"
            f"👤 <b>Name:</b>        {call.from_user.first_name}\n"
            f"🔗 <b>Username:</b>    {uname_txt}\n"
            f"🆔 <b>User ID:</b>     <code>{uid}</code>\n"
            f"{DIV2}\n"
            f"💰 <b>Credits:</b>     <b>{credits_txt}</b>\n"
            f"🔍 <b>Lookups:</b>     {row[3]}\n"
            f"📅 <b>Joined:</b>      {row[2] or '—'}\n"
            f"🤝 <b>Referred By:</b> {ref_display}\n"
            f"{DIV}\n"
            f"🔗 <b>Your Referral Link:</b>\n"
            f"<code>https://t.me/{BOT_USERNAME}?start={uid}</code>\n"
            f"{DIV}\n"
            f"{FOOT}",
            uid, mid,
            reply_markup=back_btn("home"),
            disable_web_page_preview=True
        )
        return

    # ── help ────────────────────────────────────────────────
    if d == "help":
        bot.edit_message_text(
            f"📖 <b>How It Works</b>\n"
            f"{DIV}\n"
            f"1️⃣  Tap <b>RC Lookup</b>\n"
            f"2️⃣  Type the RC number\n"
            f"     e.g. <code>MH12AB1234</code>\n"
            f"3️⃣  Get full vehicle details instantly!\n\n"
            f"{DIV2}\n"
            f"💰 Each lookup costs <b>1 credit</b>\n"
            f"🎯 Claim free credits via Daily Bonus\n"
            f"🤝 Earn <b>+10</b> credits per referral\n"
            f"{DIV}\n"
            f"{FOOT}",
            uid, mid, reply_markup=back_btn("home")
        )
        return

    # ── earn ────────────────────────────────────────────────
    if d == "earn":
        row = db_fetch("SELECT credits FROM users WHERE user_id=?", (uid,))
        credits_txt = "∞ Unlimited" if row and row[0] >= 999999 else (str(row[0]) if row else "0")
        bot.edit_message_text(
            f"💎 <b>Earn Credits</b>\n"
            f"{DIV}\n"
            f"💰 <b>Balance:</b>  {credits_txt} credits\n\n"
            f"🎯 <b>Daily Bonus</b>\n"
            f"   Claim 1–5 free credits every 24h\n\n"
            f"🎟️ <b>Promo Code</b>\n"
            f"   Enter a code to get bonus credits\n\n"
            f"🤝 <b>Refer & Earn</b>\n"
            f"   Get <b>+10 credits</b> per referral\n"
            f"{DIV}\n"
            f"{FOOT}",
            uid, mid, reply_markup=earn_menu()
        )
        return

    # ── daily bonus ─────────────────────────────────────────
    if d == "daily":
        row   = db_fetch("SELECT last_daily FROM users WHERE user_id=?", (uid,))
        last  = (row[0] or "") if row else ""
        today = str(datetime.date.today())
        if last == today:
            bot.answer_callback_query(call.id, "⏰ Already claimed today! Come back tomorrow.", show_alert=True)
        else:
            amt = random.randint(1, 5)
            db_exec(
                "UPDATE users SET credits=credits+?, last_daily=? WHERE user_id=?",
                (amt, today, uid)
            )
            bot.answer_callback_query(call.id, f"🎉 +{amt} credits claimed! See you tomorrow 🌟", show_alert=True)
        return

    # ── refer ────────────────────────────────────────────────
    if d == "refer":
        bot.edit_message_text(
            f"🤝 <b>Refer & Earn</b>\n"
            f"{DIV}\n"
            f"Share your link and earn\n"
            f"<b>+10 credits</b> for every friend\n"
            f"who joins using it!\n\n"
            f"🔗 <b>Your Referral Link:</b>\n"
            f"<code>https://t.me/{BOT_USERNAME}?start={uid}</code>\n"
            f"{DIV}\n"
            f"{FOOT}",
            uid, mid,
            reply_markup=back_btn("earn"),
            disable_web_page_preview=True
        )
        return

    # ── lookup ───────────────────────────────────────────────
    if d == "lookup":
        row = db_fetch("SELECT credits FROM users WHERE user_id=?", (uid,))
        bal = row[0] if row else 0
        if not is_admin(uid) and bal < 1:
            bot.answer_callback_query(
                call.id,
                "❌ No credits! Earn some via Daily Bonus or Referral.",
                show_alert=True
            )
            return
        msg = bot.send_message(uid,
            f"🔍 <b>RC Lookup</b>\n"
            f"{DIV}\n"
            f"Send the RC number:\n"
            f"Example: <code>MH12AB1234</code>"
        )
        bot.register_next_step_handler(msg, rc_lookup)
        return

    # ── promo redeem ─────────────────────────────────────────
    if d == "promo_red":
        msg = bot.send_message(uid,
            f"🎟️ <b>Redeem Promo Code</b>\n"
            f"{DIV}\n"
            f"Enter your promo code below:"
        )
        bot.register_next_step_handler(msg, promo_redeem)
        return

    # ════════ ADMIN-ONLY BELOW ════════════════════════════════
    if not is_admin(uid):
        return

    # ── user view mode ───────────────────────────────────────
    if d == "adm_user_mode":
        bot.edit_message_text(
            f"👁️ <b>User View Mode</b>\n"
            f"{DIV}\n"
            f"You're browsing as a regular user.\n"
            f"Your credits are <b>never deducted</b>.\n"
            f"Tap <b>⬅️ Admin Panel</b> to return.\n"
            f"{DIV}\n"
            f"{FOOT}",
            uid, mid, reply_markup=user_mode_menu()
        )
        return

    # ── statistics ───────────────────────────────────────────
    if d == "adm_stats":
        banned_c = db_fetch("SELECT COUNT(*) FROM users WHERE is_banned=1")[0]
        promos   = db_fetch("SELECT COUNT(*) FROM promocodes")[0]
        bot.edit_message_text(
            f"📊 <b>Bot Statistics</b>\n"
            f"{DIV}\n"
            f"👥 Total Users:    <b>{get_user_count()}</b>\n"
            f"🟢 Online (10m):   <b>{get_online_count()}</b>\n"
            f"📅 Joined Today:   <b>{get_today_joins()}</b>\n"
            f"🔍 Total Lookups:  <b>{get_total_lookups()}</b>\n"
            f"🚫 Banned Users:   <b>{banned_c}</b>\n"
            f"🎟️ Active Promos:  <b>{promos}</b>\n"
            f"{DIV}\n"
            f"🕐 {datetime.datetime.now().strftime('%d %b %Y  %H:%M:%S')}\n"
            f"{FOOT}",
            uid, mid, reply_markup=back_btn("home")
        )
        return

    # ── search user ──────────────────────────────────────────
    if d == "adm_search_user":
        msg = bot.send_message(uid,
            f"🔎 <b>Search User</b>\n"
            f"{DIV}\n"
            f"Send User ID or @username:"
        )
        bot.register_next_step_handler(msg, adm_search_user_handler, uid)
        return

    # ── DM a user ────────────────────────────────────────────
    if d == "adm_dm_user":
        msg = bot.send_message(uid,
            f"📨 <b>DM a User</b>\n"
            f"{DIV}\n"
            f"Send User ID or @username to message:"
        )
        bot.register_next_step_handler(msg, adm_dm_step1, uid)
        return

    # ── user list (paginated) ────────────────────────────────
    if d.startswith("adm_users_"):
        try:
            page = int(d.replace("adm_users_", ""))
        except ValueError:
            page = 0
        per_page = 10
        offset   = page * per_page
        rows = db_fetchall(
            "SELECT user_id,username,full_name,credits,join_date,is_banned "
            "FROM users ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )
        total = get_user_count()
        if not rows:
            bot.answer_callback_query(call.id, "No users on this page.", show_alert=True)
            return
        text = f"👥 <b>User List</b>  (page {page+1})\n{DIV}\n"
        for r in rows:
            badge = "🚫" if r[5] else "✅"
            text += (
                f"{badge} <a href='tg://user?id={r[0]}'>{r[2] or 'Unknown'}</a> "
                f"{r[1] or ''}\n"
                f"  <code>{r[0]}</code>  💰 {r[3]} cr  📅 {r[4] or '—'}\n"
            )
        total_pages = max(1, (total - 1) // per_page + 1)
        nav = InlineKeyboardMarkup(row_width=3)
        btns = []
        if page > 0:
            btns.append(InlineKeyboardButton("◀️", callback_data=f"adm_users_{page-1}"))
        btns.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if offset + per_page < total:
            btns.append(InlineKeyboardButton("▶️", callback_data=f"adm_users_{page+1}"))
        if btns:
            nav.add(*btns)
        nav.add(InlineKeyboardButton("⬅️  Back", callback_data="home"))
        bot.edit_message_text(text, uid, mid, reply_markup=nav, disable_web_page_preview=True)
        return

    # ── broadcast ────────────────────────────────────────────
    if d == "adm_bc":
        msg = bot.send_message(uid,
            f"📢 <b>Broadcast Message</b>\n"
            f"{DIV}\n"
            f"Send the message to broadcast to all users:"
        )
        bot.register_next_step_handler(msg, do_broadcast, uid)
        return

    # ── manage credits ───────────────────────────────────────
    if d == "adm_cr":
        msg = bot.send_message(uid,
            f"💰 <b>Manage Credits</b>\n"
            f"{DIV}\n"
            f"Send User ID or @username:"
        )
        bot.register_next_step_handler(msg, adm_cr_user, uid)
        return

    # ── promo menu ───────────────────────────────────────────
    if d == "adm_promo_menu":
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(
            InlineKeyboardButton("➕  Create Promo",  callback_data="adm_promo_create"),
            InlineKeyboardButton("🗑️  Delete Promo",  callback_data="adm_promo_del"),
            InlineKeyboardButton("📋  List All",      callback_data="adm_list_promos"),
            InlineKeyboardButton("⬅️  Back",          callback_data="home"),
        )
        bot.edit_message_text(
            f"🎟️ <b>Promo Code Manager</b>\n{DIV}",
            uid, mid, reply_markup=mk
        )
        return

    if d == "adm_promo_create":
        msg = bot.send_message(uid, f"🎟️ Enter the <b>Promo Code</b> name:")
        bot.register_next_step_handler(msg, adm_promo_name, uid)
        return

    if d == "adm_promo_del":
        msg = bot.send_message(uid, f"🗑️ Enter the <b>Promo Code</b> to delete:")
        bot.register_next_step_handler(msg, adm_promo_delete, uid)
        return

    if d == "adm_list_promos":
        rows = db_fetchall("SELECT code,amount,uses FROM promocodes")
        if not rows:
            bot.answer_callback_query(call.id, "No promo codes exist.", show_alert=True)
            return
        text = f"🎟️ <b>Active Promo Codes</b>\n{DIV}\n"
        for r in rows:
            text += f"• <code>{r[0]}</code>  💰 {r[1]} cr  |  Uses left: {r[2]}\n"
        bot.edit_message_text(text, uid, mid, reply_markup=back_btn("adm_promo_menu"))
        return

    # ── ban user ─────────────────────────────────────────────
    if d == "adm_ban":
        msg = bot.send_message(uid,
            f"🚫 <b>Ban User</b>\n"
            f"{DIV}\n"
            f"Send User ID or @username:"
        )
        bot.register_next_step_handler(msg, adm_ban_user, uid)
        return

    # ── unban user ───────────────────────────────────────────
    if d == "adm_unban":
        msg = bot.send_message(uid,
            f"✅ <b>Unban User</b>\n"
            f"{DIV}\n"
            f"Send User ID:"
        )
        bot.register_next_step_handler(msg, adm_unban_user, uid)
        return

    # ── credits → all users ──────────────────────────────────
    if d == "adm_credits_all":
        msg = bot.send_message(uid,
            f"📣 <b>Credits For All Users</b>\n"
            f"{DIV}\n"
            f"Send amount to add or remove:\n"
            f"Examples: <code>+5</code>  or  <code>-3</code>"
        )
        bot.register_next_step_handler(msg, adm_credits_all, uid)
        return


# ╔══════════════════════════════════════════════════════════╗
#   RC LOOKUP HANDLER
# ╚══════════════════════════════════════════════════════════╝
def rc_lookup(message):
    uid = message.from_user.id
    rc  = message.text.strip().replace(" ", "").upper()

    if is_admin(uid):
        ensure_user(uid)

    row = db_fetch("SELECT credits FROM users WHERE user_id=?", (uid,))
    if not row:
        bot.reply_to(message, "⚠️ Please send /start first.")
        return

    bal = row[0]
    if not is_admin(uid) and bal < 1:
        bot.reply_to(message,
            f"❌ <b>No Credits Left!</b>\n"
            f"{DIV}\n"
            f"Earn credits via /start → Earn Credits.\n"
            f"{FOOT}"
        )
        return

    m = bot.reply_to(message,
        f"🔍 <b>Searching...</b>\n"
        f"{DIV}\n"
        f"RC: <code>{rc}</code>\n"
        f"⏳ Please wait a moment…"
    )

    result = fetch_vehicle(rc)

    if result == "timeout":
        bot.edit_message_text(
            f"⏱ <b>Request Timed Out</b>\n"
            f"{DIV}\n"
            f"Server took too long. Please try again.",
            uid, m.message_id
        )
        return

    if result == "server_error":
        bot.edit_message_text(
            f"⚠️ <b>Server Error</b>\n"
            f"{DIV}\n"
            f"Could not reach the lookup server.\nPlease try again later.",
            uid, m.message_id
        )
        return

    if result is None:
        bot.edit_message_text(
            f"❌ <b>RC Not Found</b>\n"
            f"{DIV}\n"
            f"No record found for <code>{rc}</code>.\n"
            f"Check the number and try again.",
            uid, m.message_id
        )
        return

    # ── success ─────────────────────────────────────────────
    v = result
    if not is_admin(uid):
        db_exec(
            "UPDATE users SET credits=credits-1, total_lookups=total_lookups+1 WHERE user_id=?",
            (uid,)
        )
        bal_txt = f"{bal - 1} credits"
    else:
        db_exec("UPDATE users SET total_lookups=total_lookups+1 WHERE user_id=?", (uid,))
        bal_txt = "∞ Unlimited"

    out = (
        f"🚘 <b>Vehicle Details</b>\n"
        f"{DIV}\n"
        f"🔢 <b>RC Number:</b>    <code>{rc}</code>\n"
        f"{DIV2}\n"
        f"👤 <b>Owner:</b>        <code>{v['owner']}</code>\n"
        f"🏷 <b>Make:</b>         <code>{v['make']}</code>\n"
        f"🏍 <b>Model:</b>        <code>{v['model']}</code>\n"
        f"🚗 <b>Class:</b>        <code>{v['veh_class']}</code>\n"
        f"⛽ <b>Fuel:</b>         <code>{v['fuel']}</code>\n"
        f"🌿 <b>Fuel Norms:</b>   <code>{v['fuel_norms']}</code>\n"
        f"{DIV2}\n"
        f"📅 <b>Reg Date:</b>     <code>{v['reg_date']}</code>\n"
        f"🏥 <b>Fitness Upto:</b> <code>{v['fitness']}</code>\n"
        f"💸 <b>Tax Upto:</b>     <code>{v['tax_upto']}</code>\n"
        f"{DIV2}\n"
        f"🛡 <b>Insurer:</b>      <code>{v['insurer']}</code>\n"
        f"⏳ <b>Ins. Expiry:</b>  <code>{v['ins_expiry']}</code>\n"
        f"{DIV2}\n"
        f"📍 <b>RTO:</b>          <code>{v['rto']}</code>\n"
        f"🏙 <b>City:</b>         <code>{v['city']}</code>\n"
        f"🏠 <b>Address:</b>      <code>{v['address']}</code>\n"
        f"{DIV2}\n"
        f"🏦 <b>Financier:</b>    <code>{v['financier']}</code>\n"
        f"{DIV}\n"
        f"💰 <b>Credits Left:</b> {bal_txt}\n"
        f"{FOOT}"
    )

    bot.edit_message_text(out, uid, m.message_id)

    try:
        bot.send_message(LOG_CHANNEL,
            f"🔍 <b>New Lookup</b>\n"
            f"By: <a href='tg://user?id={uid}'>{message.from_user.first_name}</a> "
            f"(<code>{uid}</code>)\n"
            f"RC: <code>{rc}</code>\n"
            f"Owner: {v['owner']}"
        )
    except: pass


# ╔══════════════════════════════════════════════════════════╗
#   PROMO REDEEM
# ╚══════════════════════════════════════════════════════════╝
def promo_redeem(message):
    code = message.text.strip()
    uid  = message.from_user.id
    row  = db_fetch("SELECT amount,uses FROM promocodes WHERE code=?", (code,))
    if row:
        db_exec("UPDATE users SET credits=credits+? WHERE user_id=?", (row[0], uid))
        new_uses = row[1] - 1
        if new_uses <= 0:
            db_exec("DELETE FROM promocodes WHERE code=?", (code,))
        else:
            db_exec("UPDATE promocodes SET uses=? WHERE code=?", (new_uses, code))
        bot.reply_to(message,
            f"✅ <b>Code Redeemed!</b>\n"
            f"{DIV}\n"
            f"🎟️ Code:    <code>{code}</code>\n"
            f"💰 Added:  <b>+{row[0]} credits</b>\n"
            f"{FOOT}"
        )
    else:
        bot.reply_to(message,
            f"❌ <b>Invalid or Expired Code</b>\n"
            f"{FOOT}"
        )


# ╔══════════════════════════════════════════════════════════╗
#   ADMIN ACTION HANDLERS
#   BUG FIX: all handlers now receive `admin_uid` so replies
#   go to the correct admin, not hardcoded OWNER_ID.
# ╚══════════════════════════════════════════════════════════╝

# ── broadcast ───────────────────────────────────────────────
def do_broadcast(message, admin_uid):
    users = db_fetchall("SELECT user_id FROM users WHERE is_banned=0")
    sent = failed = 0
    for (target,) in users:
        try:
            bot.copy_message(target, message.chat.id, message.message_id)
            sent += 1
            time.sleep(0.05)
        except:
            failed += 1
    bot.send_message(admin_uid,
        f"📢 <b>Broadcast Complete</b>\n"
        f"{DIV}\n"
        f"✅ Sent:   <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>"
    )

# ── manage credits ───────────────────────────────────────────
def adm_cr_user(message, admin_uid):
    val = message.text.strip()
    if val.startswith("@"):
        row = db_fetch("SELECT user_id FROM users WHERE username=?", (val,))
    elif val.lstrip("-").isdigit():
        row = db_fetch("SELECT user_id FROM users WHERE user_id=?", (int(val),))
    else:
        row = None
    if row:
        msg = bot.send_message(admin_uid,
            f"✅ Found: <code>{row[0]}</code>\n\n"
            f"Send amount:\n"
            f"<code>+50</code> add  •  <code>-10</code> remove  •  <code>0</code> = unlimited"
        )
        bot.register_next_step_handler(msg, adm_cr_final, row[0], admin_uid)
    else:
        bot.send_message(admin_uid, "❌ User not found.")

def adm_cr_final(message, target_id, admin_uid):
    val = message.text.strip()
    if val == "0":
        db_exec("UPDATE users SET credits=999999999 WHERE user_id=?", (target_id,))
        bot.send_message(admin_uid, f"✅ <code>{target_id}</code> → set to ∞ Unlimited credits.")
    else:
        try:
            amt = int(val)
            db_exec("UPDATE users SET credits=MAX(0,credits+?) WHERE user_id=?", (amt, target_id))
            bot.send_message(admin_uid,
                f"✅ Credits updated for <code>{target_id}</code>: {amt:+} credits"
            )
        except:
            bot.send_message(admin_uid, "❌ Invalid amount.")

# ── search user ──────────────────────────────────────────────
def adm_search_user_handler(message, admin_uid):
    val = message.text.strip()
    if val.startswith("@"):
        row = db_fetch(
            "SELECT user_id,username,full_name,credits,join_date,last_seen,"
            "total_lookups,is_banned,referred_by FROM users WHERE username=?", (val,)
        )
    elif val.lstrip("-").isdigit():
        row = db_fetch(
            "SELECT user_id,username,full_name,credits,join_date,last_seen,"
            "total_lookups,is_banned,referred_by FROM users WHERE user_id=?", (int(val),)
        )
    else:
        row = None

    if row:
        status   = "🚫 Banned" if row[7] else "✅ Active"
        cred_txt = "∞ Unlimited" if row[3] >= 999999 else str(row[3])
        ref_txt  = f"<a href='tg://user?id={row[8]}'>{row[8]}</a>" if row[8] else "None"
        bot.send_message(admin_uid,
            f"🔎 <b>User Details</b>\n"
            f"{DIV}\n"
            f"👤 <b>Name:</b>        {row[2] or '—'}\n"
            f"🔗 <b>Username:</b>    {row[1] or '—'}\n"
            f"🆔 <b>User ID:</b>     <code>{row[0]}</code>\n"
            f"{DIV2}\n"
            f"🔰 <b>Status:</b>      {status}\n"
            f"💰 <b>Credits:</b>     {cred_txt}\n"
            f"🔍 <b>Lookups:</b>     {row[6]}\n"
            f"📅 <b>Joined:</b>      {row[4] or '—'}\n"
            f"🕐 <b>Last Seen:</b>   {row[5] or '—'}\n"
            f"🤝 <b>Referred By:</b> {ref_txt}\n"
            f"{DIV}",
            disable_web_page_preview=True
        )
    else:
        bot.send_message(admin_uid, "❌ User not found.")

# ── DM a user ────────────────────────────────────────────────
def adm_dm_step1(message, admin_uid):
    val = message.text.strip()
    if val.startswith("@"):
        row = db_fetch("SELECT user_id FROM users WHERE username=?", (val,))
    elif val.lstrip("-").isdigit():
        row = db_fetch("SELECT user_id FROM users WHERE user_id=?", (int(val),))
    else:
        row = None

    if row:
        target_uid = row[0]
        msg = bot.send_message(admin_uid,
            f"📨 <b>DM a User</b>\n"
            f"{DIV}\n"
            f"Target: <code>{target_uid}</code>\n"
            f"Now send the message to deliver:"
        )
        bot.register_next_step_handler(msg, adm_dm_step2, target_uid, admin_uid)
    else:
        bot.send_message(admin_uid, "❌ User not found.")

def adm_dm_step2(message, target_uid, admin_uid):
    try:
        bot.copy_message(target_uid, message.chat.id, message.message_id)
        bot.send_message(admin_uid, f"✅ Message delivered to <code>{target_uid}</code>.")
    except Exception as e:
        bot.send_message(admin_uid, f"❌ Failed to deliver: {e}")

# ── promo create ─────────────────────────────────────────────
def adm_promo_name(message, admin_uid):
    code = message.text.strip()
    msg  = bot.send_message(admin_uid, f"💰 Credit value for promo <b>{code}</b>:")
    bot.register_next_step_handler(msg, adm_promo_amount, code, admin_uid)

def adm_promo_amount(message, code, admin_uid):
    try:
        amt = int(message.text.strip())
    except:
        bot.send_message(admin_uid, "❌ Invalid amount.")
        return
    msg = bot.send_message(admin_uid, "🔢 How many uses? (<code>0</code> = unlimited):")
    bot.register_next_step_handler(msg, adm_promo_final, code, amt, admin_uid)

def adm_promo_final(message, code, amt, admin_uid):
    try:
        uses = int(message.text.strip())
        if uses <= 0:
            uses = 999999
    except:
        uses = 1
    db_exec("INSERT OR REPLACE INTO promocodes(code,amount,uses) VALUES(?,?,?)", (code, amt, uses))
    bot.send_message(admin_uid,
        f"✅ <b>Promo Created!</b>\n"
        f"{DIV}\n"
        f"🎟️ Code:   <code>{code}</code>\n"
        f"💰 Value:  {amt} credits\n"
        f"🔢 Uses:   {uses if uses < 999999 else 'Unlimited'}"
    )

# ── promo delete ─────────────────────────────────────────────
def adm_promo_delete(message, admin_uid):
    code = message.text.strip()
    if db_fetch("SELECT code FROM promocodes WHERE code=?", (code,)):
        db_exec("DELETE FROM promocodes WHERE code=?", (code,))
        bot.send_message(admin_uid, f"🗑️ Promo <code>{code}</code> deleted.")
    else:
        bot.send_message(admin_uid, "❌ Promo not found.")

# ── ban user ─────────────────────────────────────────────────
def adm_ban_user(message, admin_uid):
    val = message.text.strip()
    tid = None
    # BUG FIX: properly resolve username OR numeric ID
    if val.lstrip("-").isdigit():
        tid = int(val)
    else:
        uname = val if val.startswith("@") else f"@{val}"
        row   = db_fetch("SELECT user_id FROM users WHERE username=?", (uname,))
        if row:
            tid = row[0]

    if not tid:
        bot.send_message(admin_uid, "❌ User not found.")
        return

    if tid in ADMIN_IDS:
        bot.send_message(admin_uid, "⚠️ You cannot ban another admin.")
        return

    db_exec("UPDATE users SET is_banned=1 WHERE user_id=?", (tid,))
    bot.send_message(admin_uid, f"🚫 User <code>{tid}</code> has been banned.")
    try:
        bot.send_message(tid, f"🚫 You have been banned from this bot.\n{FOOT}")
    except: pass

# ── unban user ───────────────────────────────────────────────
def adm_unban_user(message, admin_uid):
    val = message.text.strip()
    tid = int(val) if val.lstrip("-").isdigit() else None
    if tid:
        db_exec("UPDATE users SET is_banned=0 WHERE user_id=?", (tid,))
        bot.send_message(admin_uid, f"✅ User <code>{tid}</code> has been unbanned.")
        try:
            bot.send_message(tid,
                f"✅ <b>You have been unbanned!</b>\n"
                f"{DIV}\n"
                f"You can use the bot again — tap /start\n"
                f"{FOOT}"
            )
        except: pass
    else:
        bot.send_message(admin_uid, "❌ Invalid User ID.")

# ── credits → all users ──────────────────────────────────────
def adm_credits_all(message, admin_uid):
    try:
        val = int(message.text.strip())
    except:
        bot.send_message(admin_uid, "❌ Invalid amount.")
        return
    # BUG FIX: exclude ALL admins, not just OWNER_ID
    admin_ids_str = ",".join(str(a) for a in ADMIN_IDS)
    db_exec(
        f"UPDATE users SET credits=MAX(0,credits+?) WHERE user_id NOT IN ({admin_ids_str})",
        (val,)
    )
    bot.send_message(admin_uid,
        f"✅ {'Added' if val > 0 else 'Removed'} <b>{abs(val)} credits</b> "
        f"{'to' if val > 0 else 'from'} all users."
    )


# ╔══════════════════════════════════════════════════════════╗
#   BOOT
# ╚══════════════════════════════════════════════════════════╝
print("✅ Bot is online.")
bot.infinity_polling(timeout=60, long_polling_timeout=30)
