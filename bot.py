"""
Telegram Bot (backend) — no Flask, no API server.
----------------------------------------------------------------------
This file ONLY does Telegram-side work:
  /start (optionally /start <referrer_id>)
    -> Creates the user in Supabase if new, credits the REFERRER +1 spin
    -> Channel join check
    -> Device verification (UX step only, not a real device check)
    -> "Open App" button launches the Mini App (hosted separately, e.g. Vercel)

The Mini App (mini_app.html) talks to Supabase DIRECTLY from the browser
(using the public/anon key) for reading wallet/spins/referrals and for
spinning/withdrawing — this file does not serve or proxy that data. See
supabase_setup.sql for the RPC functions and RLS policies that make that
safe to expose publicly.

Requirements:
  pip install -r requirements.txt

Environment:
  Copy .env.example to .env and fill in real values. Never commit .env.
"""

import logging
import os

from dotenv import load_dotenv
from supabase import create_client, Client
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

load_dotenv()

# ------------------- CONFIG (from .env) -------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

CHANNELS = [c.strip() for c in os.getenv("CHANNEL_IDS", os.getenv("CHANNEL_ID", "")).split(",") if c.strip()]
CHANNEL_INVITE_LINKS = [c.strip() for c in os.getenv("CHANNEL_INVITE_LINKS", os.getenv("CHANNEL_INVITE_LINK", "")).split(",") if c.strip()]

WEBAPP_URL = os.getenv("WEBAPP_URL")  # your Vercel URL, e.g. https://yourapp.vercel.app

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # secret key — backend only, never in frontend

SPINS_PER_REFERRAL = int(os.getenv("SPINS_PER_REFERRAL", "1"))
SIGNUP_FREE_SPINS = int(os.getenv("SIGNUP_FREE_SPINS", "1"))  # free spin(s) every new user gets on signup
# ------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ============== SUPABASE (backend writes — uses the SECRET key) ==============
def get_or_create_user(telegram_id, name: str, referred_by=None):
    telegram_id = int(telegram_id)
    existing = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()

    if existing.data:
        if name and existing.data[0].get("name") != name:
            supabase.table("users").update({"name": name}).eq("telegram_id", telegram_id).execute()
        return

    valid_ref = None
    if referred_by and int(referred_by) != telegram_id:
        valid_ref = int(referred_by)

    supabase.table("users").insert({
        "telegram_id": telegram_id,
        "name": name,
        "wallet": 0,
        "spins_available": SIGNUP_FREE_SPINS,
        "spins_earned_total": SIGNUP_FREE_SPINS,
        "referred_by": valid_ref,
    }).execute()

    if valid_ref:
        ref_res = supabase.table("users").select("*").eq("telegram_id", valid_ref).execute()
        if ref_res.data:
            ref_user = ref_res.data[0]
            supabase.table("users").update({
                "spins_available": ref_user.get("spins_available", 0) + SPINS_PER_REFERRAL,
                "spins_earned_total": ref_user.get("spins_earned_total", 0) + SPINS_PER_REFERRAL,
            }).eq("telegram_id", valid_ref).execute()


# ============== TELEGRAM BOT ==============
async def is_user_member_of_channel(bot, user_id: int, channel: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(f"Membership check failed for {user_id} in {channel}: {e}")
        return False


async def is_user_member(bot, user_id: int) -> bool:
    """True only if the user has joined ALL configured channels."""
    if not CHANNELS:
        return True
    for channel in CHANNELS:
        if not await is_user_member_of_channel(bot, user_id, channel):
            return False
    return True


def join_channel_keyboard():
    buttons = [
        [InlineKeyboardButton(f"📢 Join Channel {i+1}", url=link)]
        for i, link in enumerate(CHANNEL_INVITE_LINKS)
    ]
    buttons.append([InlineKeyboardButton("🔄 Check Again", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)


def verify_device_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Verify Device", callback_data="verify_device")]
    ])


def open_app_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Open App", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    if context.args:
        try:
            referred_by = int(context.args[0])
        except ValueError:
            referred_by = None

    get_or_create_user(user.id, user.full_name, referred_by)

    joined = await is_user_member(context.bot, user.id)
    if joined:
        await update.message.reply_text(
            "🔐 <b>Device Verification</b>\n\nPlease verify to continue.",
            parse_mode=ParseMode.HTML,
            reply_markup=verify_device_keyboard(),
        )
    else:
        await update.message.reply_text(
            "🎉 <b>Welcome to Rohit Giveaway Bot!</b>\n\n"
            "📢 Please join all our channels below to continue.\n\n"
            "Channel join karne ke baad '🔄 Check Again' dabao.",
            parse_mode=ParseMode.HTML,
            reply_markup=join_channel_keyboard(),
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "check_membership":
        joined = await is_user_member(context.bot, user_id)
        if joined:
            await query.edit_message_text(
                "🔐 <b>Device Verification</b>\n\nPlease verify to continue.",
                parse_mode=ParseMode.HTML,
                reply_markup=verify_device_keyboard(),
            )
        else:
            await query.answer(text="❌ Aapne abhi tak channel join nahi kiya!", show_alert=True)

    elif query.data == "verify_device":
        await query.edit_message_text(
            "✅ <b>Device Verified</b>\n\nAb app open karo aur earning shuru karo 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=open_app_keyboard(),
        )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot started polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
