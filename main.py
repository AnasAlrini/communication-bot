import os
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserIsBlocked, PeerIdInvalid, UserDeactivated
from dotenv import load_dotenv
import sqlite3
from datetime import datetime

# Load environment variables
load_dotenv()

# Bot configuration
"""
قم بإنشاء ملف .env في نفس المجلد وأضف المتغيرات التالية:

API_ID=your_api_id          # احصل عليه من my.telegram.org
API_HASH=your_api_hash      # احصل عليه من my.telegram.org
BOT_TOKEN=your_bot_token    # احصل عليه من @BotFather
OWNER_ID=your_telegram_id   # معرف تيليجرام الخاص بك (يمكنك الحصول عليه من @userinfobot)

للحصول على API_ID و API_HASH:
1. قم بزيارة https://my.telegram.org
2. سجل دخول بحسابك
3. اختر API Development Tools
4. أنشئ تطبيق جديد

للحصول على BOT_TOKEN:
1. افتح @BotFather في تيليجرام
2. أرسل /newbot
3. اتبع التعليمات لإنشاء بوت جديد
"""

# تهيئة البوت
app = Client(
    "my_anonymous_bot",  # اسم الجلسة - سيتم إنشاء ملف .session
    api_id=os.getenv('API_ID'),
    api_hash=os.getenv('API_HASH'),
    bot_token=os.getenv('BOT_TOKEN')
)

# معرف المالك - يجب تعيينه في ملف .env
OWNER_ID = int(os.getenv('OWNER_ID', '0'))

# User states dictionary to track conversation states
user_states = {}

class UserState:
    NORMAL = 0
    WAITING_MESSAGE = 1
    WAITING_SEND_MESSAGE = 2  # حالة جديدة لانتظار رسالة للإرسال

# قاموس لتخزين معرف المستخدم المستهدف عند إرسال رسالة
send_message_targets = {}

# Database setup
def setup_database():
    conn = sqlite3.connect('anonymous_bot.db')
    c = conn.cursor()
    
    # Create users table if not exists
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  join_date TEXT,
                  is_banned INTEGER DEFAULT 0,
                  ban_reason TEXT)''')
    
    # Create bot settings table if not exists
    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings
                 (setting TEXT PRIMARY KEY,
                  value INTEGER DEFAULT 1)''')
    
    # Insert default settings
    c.execute('INSERT OR IGNORE INTO bot_settings (setting, value) VALUES (?, ?)', ('bot_active', 1))
    c.execute('INSERT OR IGNORE INTO bot_settings (setting, value) VALUES (?, ?)', ('block_photos', 0))
    c.execute('INSERT OR IGNORE INTO bot_settings (setting, value) VALUES (?, ?)', ('block_videos', 0))
    c.execute('INSERT OR IGNORE INTO bot_settings (setting, value) VALUES (?, ?)', ('block_documents', 0))
    c.execute('INSERT OR IGNORE INTO bot_settings (setting, value) VALUES (?, ?)', ('block_voice', 0))
    c.execute('INSERT OR IGNORE INTO bot_settings (setting, value) VALUES (?, ?)', ('block_stickers', 0))
    
    conn.commit()
    conn.close()

def get_bot_setting(setting):
    conn = sqlite3.connect('anonymous_bot.db')
    c = conn.cursor()
    c.execute('SELECT value FROM bot_settings WHERE setting = ?', (setting,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 1

def set_bot_setting(setting, value):
    conn = sqlite3.connect('anonymous_bot.db')
    c = conn.cursor()
    c.execute('UPDATE bot_settings SET value = ? WHERE setting = ?', (value, setting))
    conn.commit()
    conn.close()

# Add or update user in database
def update_user_info(user):
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, join_date, is_banned)
        VALUES (?, ?, ?, ?, ?, 0)
    ''', (user.id, user.username, user.first_name, user.last_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    conn.commit()
    conn.close()

# Ban user
async def ban_user(user_id: int, reason: str = None):
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?', (reason, user_id))
    conn.commit()
    
    # Get user info for notification
    cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
    user_info = cursor.fetchone()
    
    conn.close()
    return user_info

# Unban user
async def unban_user(user_id: int):
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?', (user_id,))
    conn.commit()
    
    # Get user info for notification
    cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
    user_info = cursor.fetchone()
    
    conn.close()
    return user_info

# Check if user is banned
def is_user_banned(user_id: int) -> bool:
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    return bool(result and result[0])

# Check if user is owner
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# Get banned users list
def get_banned_users():
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, first_name, last_name, ban_reason
        FROM users 
        WHERE is_banned = 1
        ORDER BY join_date DESC
    ''')
    users = cursor.fetchall()
    
    conn.close()
    return users

# Get total users count
def get_total_users():
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users WHERE user_id != ?', (OWNER_ID,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# Get users for specific page
def get_users_page(page: int, per_page: int = 5):
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    
    offset = (page - 1) * per_page
    cursor.execute("""
        SELECT user_id, username, first_name, last_name, is_banned 
        FROM users 
        WHERE user_id != ?
        ORDER BY join_date DESC 
        LIMIT ? OFFSET ?
    """, (OWNER_ID, per_page, offset))
    users = cursor.fetchall()
    conn.close()
    return users

# Command handler for ban/unban
@app.on_message(filters.command(["ban", "unban"]) & filters.user(OWNER_ID))
async def handle_ban_commands(client: Client, message: Message):
    command = message.command[0]
    
    # Check if user ID is provided
    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply("❌ الرجاء تحديد معرف المستخدم أو الرد على رسالته")
        return
    
    # Get target user ID
    target_user_id = None
    reason = None
    
    if message.reply_to_message and message.reply_to_message.forward_from:
        target_user_id = message.reply_to_message.forward_from.id
    elif len(message.command) > 1:
        try:
            target_user_id = int(message.command[1])
            # Get ban reason if provided
            if len(message.command) > 2:
                reason = " ".join(message.command[2:])
        except ValueError:
            await message.reply("❌ معرف المستخدم غير صالح")
            return
    
    if target_user_id == OWNER_ID:
        await message.reply("❌ لا يمكن حظر المالك!")
        return
    
    if command == "ban":
        user_info = await ban_user(target_user_id, reason)
        if user_info:
            username, first_name = user_info
            name = first_name or username or str(target_user_id)
            reason_text = f"\nالسبب: {reason}" if reason else ""
            await message.reply(f"✅ تم حظر المستخدم {name} بنجاح{reason_text}")
        else:
            await message.reply("❌ لم يتم العثور على المستخدم")
    
    elif command == "unban":
        user_info = await unban_user(target_user_id)
        if user_info:
            username, first_name = user_info
            name = first_name or username or str(target_user_id)
            await message.reply(f"✅ تم إلغاء حظر المستخدم {name} بنجاح")
        else:
            await message.reply("❌ لم يتم العثور على المستخدم")

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    if not is_owner(callback_query.from_user.id):
        return
    
    data = callback_query.data
    
    if data == "show_settings":
        bot_active = get_bot_setting('bot_active')
        block_photos = get_bot_setting('block_photos')
        block_videos = get_bot_setting('block_videos')
        block_documents = get_bot_setting('block_documents')
        block_voice = get_bot_setting('block_voice')
        block_stickers = get_bot_setting('block_stickers')
        
        keyboard = [
            [InlineKeyboardButton("🤖 حالة البوت: " + ("مفعل ✅" if bot_active else "معطل ❌"), 
                                 callback_data="toggle_bot_active")],
            [InlineKeyboardButton("📷 الصور: " + ("محظورة 🚫" if block_photos else "مسموحة ✅"), 
                                 callback_data="toggle_block_photos")],
            [InlineKeyboardButton("🎥 الفيديو: " + ("محظور 🚫" if block_videos else "مسموح ✅"), 
                                 callback_data="toggle_block_videos")],
            [InlineKeyboardButton("📄 الملفات: " + ("محظورة 🚫" if block_documents else "مسموحة ✅"), 
                                 callback_data="toggle_block_documents")],
            [InlineKeyboardButton("🎤 الصوتيات: " + ("محظورة 🚫" if block_voice else "مسموحة ✅"), 
                                 callback_data="toggle_block_voice")],
            [InlineKeyboardButton("😀 الملصقات: " + ("محظورة 🚫" if block_stickers else "مسموحة ✅"), 
                                 callback_data="toggle_block_stickers")],
            [InlineKeyboardButton("👥 المستخدمين", callback_data="list_users")],
            [InlineKeyboardButton("⛔️ المحظورين", callback_data="banned_users")]
        ]
        await callback_query.message.edit_text("⚙️ إعدادات البوت:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "toggle_bot_active":
        current = get_bot_setting('bot_active')
        set_bot_setting('bot_active', 0 if current else 1)
        await callback_query.answer("✅ تم " + ("تفعيل" if not current else "تعطيل") + " البوت")
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="show_settings",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
    
    elif data == "toggle_block_photos":
        current = get_bot_setting('block_photos')
        set_bot_setting('block_photos', 0 if current else 1)
        await callback_query.answer("تم " + ("حظر" if not current else "السماح بـ") + " الصور")
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="show_settings",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
        
    elif data == "toggle_block_videos":
        current = get_bot_setting('block_videos')
        set_bot_setting('block_videos', 0 if current else 1)
        await callback_query.answer("تم " + ("حظر" if not current else "السماح بـ") + " الفيديو")
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="show_settings",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
        
    elif data == "toggle_block_documents":
        current = get_bot_setting('block_documents')
        set_bot_setting('block_documents', 0 if current else 1)
        await callback_query.answer("تم " + ("حظر" if not current else "السماح بـ") + " الملفات")
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="show_settings",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
        
    elif data == "toggle_block_voice":
        current = get_bot_setting('block_voice')
        set_bot_setting('block_voice', 0 if current else 1)
        await callback_query.answer("تم " + ("حظر" if not current else "السماح بـ") + " الصوتيات")
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="show_settings",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
        
    elif data == "toggle_block_stickers":
        current = get_bot_setting('block_stickers')
        set_bot_setting('block_stickers', 0 if current else 1)
        await callback_query.answer("تم " + ("حظر" if not current else "السماح بـ") + " الملصقات")
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="show_settings",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
        
    elif data == "list_users":
        page = 1
        per_page = 5
        total_users = get_total_users()
        total_pages = (total_users + per_page - 1) // per_page  # التقريب لأعلى
        
        users = get_users_page(page)
        
        text = f"👥 **قائمة المستخدمين** (الصفحة {page}/{total_pages}):\n"
        text += f"إجمالي المستخدمين: {total_users}\n\n"
        
        keyboard = []
        
        for user in users:
            user_id, username, first_name, last_name, is_banned = user
            status = "🚫" if is_banned else "✅"
            name = first_name or 'مستخدم'
            if username:
                name += f" (@{username})"
            text += f"{status} [{name}](tg://user?id={user_id})\n"
            text += f"• المعرف: `{user_id}`\n\n"
            
            if is_banned:
                keyboard.append([InlineKeyboardButton(f"إلغاء حظر {name}", callback_data=f"unban_user_{user_id}")])
            else:
                keyboard.append([InlineKeyboardButton(f"حظر {name}", callback_data=f"ban_user_{user_id}")])
                keyboard.append([InlineKeyboardButton(f"إرسال رسالة إلى {name}", callback_data=f"start_send_{user_id}")])
        
        # أزرار التنقل
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"users_page_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"users_page_{page+1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="show_settings")])
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith("users_page_"):
        page = int(data.split("_")[2])
        per_page = 5
        total_users = get_total_users()
        total_pages = (total_users + per_page - 1) // per_page
        
        users = get_users_page(page)
        
        text = f"👥 **قائمة المستخدمين** (الصفحة {page}/{total_pages}):\n"
        text += f"إجمالي المستخدمين: {total_users}\n\n"
        
        keyboard = []
        
        for user in users:
            user_id, username, first_name, last_name, is_banned = user
            status = "🚫" if is_banned else "✅"
            name = first_name or 'مستخدم'
            if username:
                name += f" (@{username})"
            text += f"{status} [{name}](tg://user?id={user_id})\n"
            text += f"• المعرف: `{user_id}`\n\n"
            
            if is_banned:
                keyboard.append([InlineKeyboardButton(f"إلغاء حظر {name}", callback_data=f"unban_user_{user_id}")])
            else:
                keyboard.append([InlineKeyboardButton(f"حظر {name}", callback_data=f"ban_user_{user_id}")])
                keyboard.append([InlineKeyboardButton(f"إرسال رسالة إلى {name}", callback_data=f"start_send_{user_id}")])
        
        # أزرار التنقل
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"users_page_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"users_page_{page+1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="show_settings")])
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith("ban_user_"):
        target_user_id = int(data.split("_")[2])
        await ban_user(target_user_id)
        await callback_query.answer("تم حظر المستخدم بنجاح ✅")
        
        # Refresh users list
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="list_users",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
        
    elif data.startswith("unban_user_"):
        target_user_id = int(data.split("_")[2])
        await unban_user(target_user_id)
        await callback_query.answer("تم إلغاء حظر المستخدم بنجاح ✅")
        
        # Refresh users list
        await handle_callback(client, CallbackQuery(
            id=callback_query.id,
            client=client,
            data="list_users",
            from_user=callback_query.from_user,
            message=callback_query.message,
            chat_instance=callback_query.chat_instance
        ))
        
    elif data == "banned_users":
        banned_users = get_banned_users()
        
        text = "🚫 **المستخدمين المحظورين**:\n\n"
        keyboard = []
        
        if not banned_users:
            text += "لا يوجد مستخدمين محظورين حالياً"
        else:
            for user in banned_users:
                user_id, username, first_name, last_name, reason = user
                name = first_name or 'مستخدم'
                if username:
                    name += f" (@{username})"
                text += f"• [{name}](tg://user?id={user_id})\n"
                text += f"المعرف: `{user_id}`"
                if reason:
                    text += f"\nسبب الحظر: {reason}"
                text += "\n\n"
                keyboard.append([InlineKeyboardButton(f"إلغاء حظر {name}", callback_data=f"unban_user_{user_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="show_settings")])
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # معالجة تأكيد إرسال الرسالة
    elif data.startswith("confirm_send_"):
        try:
            # استخراج معرف المستخدم والرسالة
            parts = data.split("_", 2)  # تقسيم إلى ثلاثة أجزاء
            if len(parts) != 3:
                raise ValueError("Invalid callback data format")
                
            _, _, payload = parts
            user_id, msg_text = payload.split("_", 1)
            user_id = int(user_id)
            
            # محاولة إرسال الرسالة
            try:
                await client.send_message(user_id, msg_text)
                await callback_query.message.edit_text(
                    "✅ تم إرسال الرسالة بنجاح",
                    reply_markup=None
                )
            except UserIsBlocked:
                user_info = await get_user_info(user_id)
                if user_info:
                    username, first_name, last_name = user_info
                    name = format_name(first_name, last_name)
                    await callback_query.message.edit_text(
                        f"❌ تعذر إرسال الرسالة!\n"
                        f"المستخدم: {name}\n"
                        f"المعرف: `{user_id}`\n"
                        f"السبب: المستخدم قام بحظر البوت",
                        reply_markup=None
                    )
            except (PeerIdInvalid, UserDeactivated):
                user_info = await get_user_info(user_id)
                if user_info:
                    username, first_name, last_name = user_info
                    name = format_name(first_name, last_name)
                    await callback_query.message.edit_text(
                        f"❌ تعذر إرسال الرسالة!\n"
                        f"المستخدم: {name}\n"
                        f"المعرف: `{user_id}`\n"
                        f"السبب: حساب المستخدم غير نشط أو محذوف",
                        reply_markup=None
                    )
            except Exception as e:
                await callback_query.message.edit_text(
                    f"❌ حدث خطأ أثناء إرسال الرسالة: {str(e)}",
                    reply_markup=None
                )
        except Exception as e:
            await callback_query.message.edit_text(
                "❌ حدث خطأ أثناء معالجة الطلب",
                reply_markup=None
            )
    
    # معالجة إلغاء إرسال الرسالة
    elif data == "cancel_send":
        await callback_query.message.edit_text(
            "❌ تم إلغاء إرسال الرسالة",
            reply_markup=None
        )
    
    # معالجة بدء إرسال رسالة من زر القائمة
    elif data.startswith("start_send_"):
        user_id = int(data.split("_")[2])
        user_info = await get_user_info(user_id)
        
        if not user_info:
            await callback_query.answer("❌ لم يتم العثور على المستخدم", show_alert=True)
            return
            
        username, first_name, last_name = user_info
        name = format_name(first_name, last_name)
        
        # تخزين معرف المستخدم المستهدف وتغيير الحالة
        send_message_targets[callback_query.from_user.id] = user_id
        user_states[callback_query.from_user.id] = UserState.WAITING_SEND_MESSAGE
        
        await callback_query.message.reply(
            f"📤 إرسال رسالة إلى {name}\n"
            f"المعرف: `{user_id}`\n"
            f"{('@' + username) if username else ''}\n\n"
            "📝 اكتب رسالتك الآن..."
        )

@app.on_message(filters.command("send") & filters.user(OWNER_ID))
async def send_command(client: Client, message: Message):
    # التحقق من صحة الأمر
    if len(message.command) < 3:
        await message.reply(
            "⚠️ صيغة الأمر غير صحيحة\n\n"
            "الصيغة الصحيحة:\n"
            "`/send #123456 الرسالة`\n"
            "`/send @username الرسالة`"
        )
        return
    
    # استخراج معرف المستخدم والرسالة
    target = message.command[1]
    msg_text = " ".join(message.command[2:])
    
    # تحديد المستخدم المستهدف
    target_user_id = None
    if target.startswith('#'):
        try:
            target_user_id = int(target[1:])
        except ValueError:
            await message.reply("❌ معرف المستخدم غير صالح")
            return
    elif target.startswith('@'):
        username = target[1:]
        conn = sqlite3.connect('anonymous_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            target_user_id = result[0]
        else:
            await message.reply("❌ لم يتم العثور على المستخدم")
            return
    else:
        await message.reply(
            "❌ صيغة المعرف غير صحيحة\n\n"
            "استخدم:\n"
            "• `#123456` للمعرف الرقمي\n"
            "• `@username` لاسم المستخدم"
        )
        return
    
    # التحقق من أن المستخدم ليس المالك
    if target_user_id == OWNER_ID:
        await message.reply("❌ لا يمكن إرسال رسالة للمالك!")
        return
        
    # التحقق من حالة الحظر
    if is_user_banned(target_user_id):
        await message.reply("⚠️ لا يمكن إرسال رسالة لمستخدم محظور")
        return
    
    # إرسال رسالة التأكيد
    user_info = await get_user_info(target_user_id)
    if not user_info:
        await message.reply("❌ لم يتم العثور على المستخدم")
        return
    
    username, first_name, last_name = user_info
    name = format_name(first_name, last_name)
    
    confirm_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد", callback_data=f"confirm_send_{target_user_id}_{msg_text}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel_send")
        ]
    ])
    
    await message.reply(
        f"📤 تأكيد إرسال رسالة إلى {name}\n"
        f"المعرف: `{target_user_id}`\n"
        f"{('@' + username) if username else ''}\n"
        "───────────────\n"
        f"{msg_text}\n"
        "───────────────\n"
        "هل تريد إرسال الرسالة؟",
        reply_markup=confirm_keyboard
    )

@app.on_message(filters.command("settings") & filters.user(OWNER_ID))
async def settings_command(client: Client, message: Message):
    # الحصول على الإعدادات الحالية
    bot_active = "✅" if get_bot_setting('bot_active') else "❌"
    block_photos = "✅" if get_bot_setting('block_photos') else "❌"
    block_videos = "✅" if get_bot_setting('block_videos') else "❌"
    block_documents = "✅" if get_bot_setting('block_documents') else "❌"
    block_voice = "✅" if get_bot_setting('block_voice') else "❌"
    block_stickers = "✅" if get_bot_setting('block_stickers') else "❌"
    
    # إنشاء أزرار التحكم
    keyboard = [
        [
            InlineKeyboardButton(f"حالة البوت {bot_active}", callback_data="toggle_bot_active"),
        ],
        [
            InlineKeyboardButton(f"حظر الصور {block_photos}", callback_data="toggle_block_photos"),
            InlineKeyboardButton(f"حظر الفيديو {block_videos}", callback_data="toggle_block_videos"),
        ],
        [
            InlineKeyboardButton(f"حظر الملفات {block_documents}", callback_data="toggle_block_documents"),
            InlineKeyboardButton(f"حظر الصوتيات {block_voice}", callback_data="toggle_block_voice"),
        ],
        [
            InlineKeyboardButton(f"حظر الملصقات {block_stickers}", callback_data="toggle_block_stickers"),
        ]
    ]
    
    settings_text = (
        "⚙️ إعدادات البوت\n\n"
        f"• حالة البوت: {bot_active}\n"
        f"• حظر الصور: {block_photos}\n"
        f"• حظر الفيديو: {block_videos}\n"
        f"• حظر الملفات: {block_documents}\n"
        f"• حظر الصوتيات: {block_voice}\n"
        f"• حظر الملصقات: {block_stickers}\n\n"
        "اضغط على أي زر لتغيير الإعداد"
    )
    
    await message.reply(settings_text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_message(~filters.command(["start", "help", "settings", "ban", "unban", "search", "send"]) & filters.private)
async def forward_message(client: Client, message: Message):
    if not is_owner(message.from_user.id):
        # معالجة رسائل المستخدمين العاديين
        # Check if bot is active
        if not get_bot_setting('bot_active'):
            return
            
        # Check if user is banned
        if is_user_banned(message.from_user.id):
            return
            
        # Check media restrictions
        if message.photo and get_bot_setting('block_photos'):
            await message.reply("⚠️ عذراً، إرسال الصور غير مسموح حالياً.")
            return
            
        if message.video and get_bot_setting('block_videos'):
            await message.reply("⚠️ عذراً، إرسال الفيديو غير مسموح حالياً.")
            return
            
        if message.document and get_bot_setting('block_documents'):
            await message.reply("⚠️ عذراً، إرسال الملفات غير مسموح حالياً.")
            return
            
        if (message.voice or message.audio) and get_bot_setting('block_voice'):
            await message.reply("⚠️ عذراً، إرسال الصوتيات غير مسموح حالياً.")
            return
            
        if message.sticker and get_bot_setting('block_stickers'):
            await message.reply("⚠️ عذراً، إرسال الملصقات غير مسموح حالياً.")
            return
            
        # Forward message to owner
        try:
            owner_id = int(os.getenv('OWNER_ID'))
            await message.forward(owner_id)
            update_user_info(message.from_user)
        except Exception as e:
            print(f"Error forwarding message: {e}")
    else:
        # معالجة رسائل المالك
        if message.from_user.id in user_states and user_states[message.from_user.id] == UserState.WAITING_SEND_MESSAGE:
            # المالك في وضع إرسال رسالة لمستخدم
            target_user_id = send_message_targets.get(message.from_user.id)
            if target_user_id:
                confirm_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد", callback_data=f"confirm_send_{target_user_id}_{message.text}"),
                        InlineKeyboardButton("❌ إلغاء", callback_data="cancel_send")
                    ]
                ])
                
                user_info = await get_user_info(target_user_id)
                if user_info:
                    username, first_name, last_name = user_info
                    name = format_name(first_name, last_name)
                    
                    await message.reply(
                        f"📤 تأكيد إرسال رسالة إلى {name}\n"
                        f"المعرف: `{target_user_id}`\n"
                        f"{('@' + username) if username else ''}\n"
                        "───────────────\n"
                        f"{message.text}\n"
                        "───────────────\n"
                        "هل تريد إرسال الرسالة؟",
                        reply_markup=confirm_keyboard
                    )
                
                # إعادة تعيين الحالة
                user_states[message.from_user.id] = UserState.NORMAL
                del send_message_targets[message.from_user.id]
            
        elif message.reply_to_message and message.reply_to_message.forward_from:
            # الرد على رسالة محولة
            target_user_id = message.reply_to_message.forward_from.id
            try:
                await client.copy_message(
                    chat_id=target_user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.id
                )
            except UserIsBlocked:
                user_info = message.reply_to_message.forward_from
                await message.reply(
                    f"❌ تعذر إرسال الرسالة!\n"
                    f"المستخدم: {user_info.first_name} " + (f"(@{user_info.username})" if user_info.username else "") + f"\n"
                    f"المعرف: `{user_info.id}`\n"
                    f"السبب: المستخدم قام بحظر البوت"
                )
            except (PeerIdInvalid, UserDeactivated):
                user_info = message.reply_to_message.forward_from
                await message.reply(
                    f"❌ تعذر إرسال الرسالة!\n"
                    f"المستخدم: {user_info.first_name} " + (f"(@{user_info.username})" if user_info.username else "") + f"\n"
                    f"المعرف: `{user_info.id}`\n"
                    f"السبب: حساب المستخدم غير نشط أو محذوف أو حظر البوت"
                )
            except Exception as e:
                await message.reply("❌ فشل إرسال الرسالة للمستخدم")
                print(f"Error sending message: {e}")

def format_name(first_name: str, last_name: str) -> str:
    """تنسيق الاسم بحيث يظهر الاسم الأول فقط إذا كان الاسم الأخير None"""
    if last_name and last_name.lower() != 'none':
        return f"{first_name} {last_name}".strip()
    return first_name.strip()

def search_users(query: str) -> list:
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    
    if query.startswith('#'):  # البحث بالمعرف الرقمي
        try:
            user_id = int(query[1:])
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        except ValueError:
            return []
    elif query.startswith('@'):  # البحث باسم المستخدم
        username = query[1:]
        cursor.execute('SELECT * FROM users WHERE username LIKE ?', (username,))
    else:  # البحث بالاسم الأول أو الأخير
        search_term = f"%{query}%"
        cursor.execute('SELECT * FROM users WHERE first_name LIKE ? OR last_name LIKE ?', 
                      (search_term, search_term))
    
    results = cursor.fetchall()
    conn.close()
    return results

@app.on_message(filters.command("search") & filters.user(OWNER_ID))
async def search_command(client: Client, message: Message):
    # التحقق من وجود نص للبحث
    if len(message.command) < 2:
        await message.reply("⚠️ الرجاء إدخال نص للبحث\n\nمثال:\n`/search #123456`\n`/search @username`\n`/search محمد`")
        return
    
    # استخراج نص البحث
    search_query = message.command[1]
    
    # البحث عن المستخدمين
    results = search_users(search_query)
    
    if not results:
        await message.reply("❌ لم يتم العثور على أي نتائج")
        return
    
    # تحضير نص النتائج
    text = "🔍 نتائج البحث:\n\n"
    keyboard = []
    
    for user in results:
        user_id, username, first_name, last_name, join_date, is_banned, ban_reason = user
        name = format_name(first_name, last_name)
        username_text = f"@{username}" if username else "لا يوجد"
        status = "🚫 محظور" if is_banned else "✅ نشط"
        
        text += f"• {name}\n"
        text += f"  └ المعرف: {username_text}\n"
        text += f"  └ ID: {user_id}\n"
        text += f"  └ الحالة: {status}\n"
        text += f"  └ تاريخ الانضمام: {join_date}\n\n"
        
        # إضافة أزرار التحكم لكل مستخدم
        if is_banned:
            keyboard.append([InlineKeyboardButton(f"إلغاء حظر {name}", callback_data=f"unban_user_{user_id}")])
        else:
            keyboard.append([InlineKeyboardButton(f"حظر {name}", callback_data=f"ban_user_{user_id}")])
    
    # إضافة زر العودة
    keyboard.append([InlineKeyboardButton("🔙 عرض قائمة المستخدمين", callback_data="list_users")])
    
    await message.reply(text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_message(filters.command("help") & filters.user(OWNER_ID))
async def help_command(client: Client, message: Message):
    help_text = """
🔰 **أوامر المالك**

📋 **إدارة المستخدمين**
• `/ban` - حظر مستخدم (رد على رسالة)
• `/unban` - إلغاء حظر مستخدم (رد على رسالة)
• `/search` - البحث عن المستخدمين
• `/send` - إرسال رسالة خاصة لمستخدم

🔍 **طرق البحث**
• `/search #1234` - البحث برقم المعرف
• `/search @username` - البحث باسم المستخدم
• `/search محمد` - البحث بالاسم الأول أو الأخير

📤 **إرسال الرسائل**
• `/send #1234 الرسالة` - إرسال رسالة برقم المعرف
• `/send @username الرسالة` - إرسال رسالة باسم المستخدم

⚙️ **إعدادات البوت**
• `/settings` - إدارة إعدادات البوت
  - تفعيل/تعطيل البوت
  - عرض قائمة المستخدمين
  - عرض المستخدمين المحظورين

💡 **ملاحظات**
• يمكنك الرد على أي رسالة لحظر/إلغاء حظر المستخدم
• قائمة المستخدمين تعرض 5 مستخدمين في كل صفحة
• البحث يدعم البحث في الاسم الأول والأخير معاً
• لا يمكن إرسال رسائل للمستخدمين المحظورين
"""
    await message.reply(help_text)

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user = message.from_user
    update_user_info(user)
    
    if is_user_banned(user.id):
        await message.reply("عذراً، أنت محظور من استخدام البوت ⚠️")
        return
        
    if user.id == OWNER_ID:
        keyboard = [
            [InlineKeyboardButton("⚙️ الإعدادات", callback_data="show_settings")]
        ]
        await message.reply(
            "مرحباً بك في لوحة التحكم الخاصة بالبوت 🤖\n\n"
            "يمكنك استخدام الأزرار أدناه للتحكم في إعدادات البوت:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await message.reply(
            "مرحباً بك! 👋\n\n"
            "يمكنك إرسال رسالتك وسيتم إيصالها للمالك. 📬"
        )
        user_states[user.id] = UserState.NORMAL

# دالة مساعدة للحصول على معلومات المستخدم
async def get_user_info(user_id: int):
    conn = sqlite3.connect('anonymous_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

# Run the bot
if __name__ == "__main__":
    setup_database()
    app.run()
