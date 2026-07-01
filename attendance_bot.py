import os
import csv
import calendar
import asyncio
from datetime import datetime
import pytz
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =========================================================================
# ⚙️ ទាញយកតម្លៃ Token និង URL ពី Render Environment
# =========================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8966159307:AAFnHG8h-D6uhEhSh6LmUVe7Ujkpry9du2E")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://suong-attendance-bot.onrender.com")

OFFICE_LAT = 11.9167
OFFICE_LON = 105.6667
ALLOWED_RADIUS_M = 150

REPORT_FILE = "attendance_records.csv"
LEAVE_FILE = "leave_records.csv"
GROUP_ID = "-5126809493" 

PHOTO, LOCATION = range(2)
LEAVE_DURATION, LEAVE_REASON = range(2, 4)

for file, headers in [(REPORT_FILE, ["កាលបរិច្ឆេទ", "ម៉ោង", "ID មន្ត្រី", "ឈ្មោះគណនី", "ប្រភេទវត្តមាន", "ស្ថានភាពម៉ោង", "ចម្ងាយ(ម៉ែត្រ)", "រដូវកាល", "ខែ", "ត្រីមាស", "ឆមាស"]),
                      (LEAVE_FILE, ["កាលបរិច្ឆេទស្នើសុំ", "ID មន្ត្រី", "ឈ្មោះមន្ត្រី", "ប្រភេទច្បាប់", "ថ្ងៃចាប់ផ្តើម", "រយៈពេល", "មូលហេតុ", "ស្ថានភាព"])]:
    if not os.path.exists(file):
        with open(file, mode="w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(headers)

def get_khmer_timezone_now(): return datetime.now(pytz.timezone('Asia/Phnom_Penh'))

def get_khmer_season_info(dt):
    month = dt.month
    return ("រដូវវស្សา" if 5 <= month <= 10 else "រដូវប្រាំង", f"ត្រីមាសទី{(month-1)//3 + 1}", "ឆមាសទី១" if month <= 6 else "ឆមាសទី២")

def calculate_distance(lat1, lon1, lat2, lon2):
    from math import radians, cos, sin, asin, sqrt
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * asin(sqrt(sin((lat2 - lat1)/2)**2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1)/2)**2)) * 6371000

def check_attendance_shift(now_dt):
    current_time = now_dt.time()
    shifts = [
        ("07:30", "08:00", "ចូលការងារ (ព្រឹក)", "ទាន់ពេល"),
        ("08:00", "11:00", "ចូលការងារ (ព្រឹក)", "យឺត / អវត្តមាន"),
        ("11:00", "11:30", "ចេញការងារ (ព្រឹក)", "ទាន់ពេល"),
        ("11:30", "14:00", "ចេញការងារ (ព្រឹក)", "យឺត / អវត្តមាន"),
        ("14:00", "14:30", "ចូលការងារ (រសៀល)", "ទាន់ពេល"),
        ("14:30", "17:00", "ចូលការងារ (រសៀល)", "យឺត / អវត្តមាន"),
        ("17:00", "17:30", "ចេញការងារ (រសៀល)", "ទាន់ពេល")
    ]
    for start, end, att_type, status in shifts:
        if datetime.strptime(start, "%H:%M").time() <= current_time <= datetime.strptime(end, "%H:%M").time():
            return att_type, status
    return "ក្រៅម៉ោងរដ្ឋបាល", "យឺត / អវត្តមាន"

def create_calendar(year, month):
    keyboard = [[InlineKeyboardButton(f"🗓️ {calendar.month_name[month]} {year}", callback_data="IGNORE")],
                [InlineKeyboardButton(day, callback_data="IGNORE") for day in ["ច", "អ", "ព", "ព្រ", "សុ", "ស", "អា"]]]
    for week in calendar.monthcalendar(year, month):
        keyboard.append([InlineKeyboardButton(str(day) if day != 0 else " ", callback_data=f"CAL_{year}_{month}_{day}" if day != 0 else "IGNORE") for day in week])
    keyboard.append([InlineKeyboardButton("◀️ ខែមុន", callback_data=f"PREV_{year}_{month}"), InlineKeyboardButton("ខែបន្ទាប់ ▶️", callback_data=f"NEXT_{year}_{month}")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 ស្វាគមន៍មកកាន់ប្រព័ន្ធរដ្ឋបាលក្រុងសួង!\n• ចុះវត្តមាន៖ សូមផ្ញើរូបថត Selfie\n• សុំច្បាប់៖ វាយបញ្ជា /leave")
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['photo_id'] = update.message.photo[-1].file_id
    await update.message.reply_text("📸 ទទួលបានរូបថតជោគជ័យ! សូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើទីតាំង GPS។", reply_markup=ReplyKeyboardMarkup([[{"text": "📍 ផ្ញើទីតាំងបច្ចុប្បន្ន (Share GPS)", "request_location": True}]], one_time_keyboard=True, resize_keyboard=True))
    return LOCATION

# =========================================================================
# 📍 ផ្នែកពិនិត្យទីតាំង GPS ដ៏តឹងរ៉ឹង (កែសម្រួលរួចរាល់)
# =========================================================================
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_loc = update.message.location
    now = get_khmer_timezone_now()
    distance = calculate_distance(user_loc.latitude, user_loc.longitude, OFFICE_LAT, OFFICE_LON)
    
    # 🚨 បើចម្ងាយលើសពីការកំណត់ ត្រូវផ្ដាច់ដំណើរការចោលភ្លាមៗ មិនឱ្យសរសេរចូល CSV ឬផ្ញើទៅគ្រុបឡើយ
    if distance > ALLOWED_RADIUS_M:
        await update.message.reply_text(
            f"❌ មិនអាចចុះវត្តមានបានទេ!\n📍 ទីតាំងបច្ចុប្បន្ន៖ ស្ថិតនៅចម្ងាយ {int(distance)} ម៉ែត្រ\n🚫 លក្ខខណ្ឌ៖ ត្រូវស្ថិតនៅក្នុងរង្វង់ {ALLOWED_RADIUS_M} ម៉ែត្រ ពីសាលាក្រុងសួង។", 
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END  # 🛑 បញ្ឈប់ និងកាត់ផ្ដាច់លំហូរកូដត្រឹមកន្លែងនេះ

    # 🟢 បើស្ថិតក្នុងរង្វង់ ១៥០ម៉ែត្រ ដំណើរការកូដខាងក្រោមជាធម្មតា
    att_type, status_time = check_attendance_shift(now)
    season, quarter, semester = get_khmer_season_info(now)
    
    with open(REPORT_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), update.message.from_user.id, update.message.from_user.full_name, att_type, status_time, int(distance), season, now.strftime("%B"), quarter, semester])
    
    await update.message.reply_text(f"✅ ចុះវត្តមានជោគជ័យ!\n🗓 កាលបរិច្ឆេទ៖ {now.strftime('%Y-%m-%d')}\n⏰ ម៉ោង៖ {now.strftime('%H:%M:%S')}\n📋 ប្រភេទ៖ {att_type}\n🎯 ស្ថានភាព៖ {status_time}", reply_markup=ReplyKeyboardRemove())
    
    try:
        await context.bot.send_photo(chat_id=GROUP_ID, photo=context.user_data['photo_id'], caption=f"📢 វត្តមាន៖ {update.message.from_user.full_name}\n⏰ ម៉ោង៖ {now.strftime('%H:%M:%S')} ({att_type})\n📍 ចម្ងាយ៖ {int(distance)}ម\n📌 ស្ថានភាព៖ {status_time}")
    except: 
        pass
    return ConversationHandler.END

async def leave_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 សូមជ្រើសរើសប្រភេទច្បាប់សម្រាក៖", reply_markup=ReplyKeyboardMarkup([["ច្បាប់ឈឺ (Sick Leave)", "ច្បាប់ផ្ទាល់ខ្លួន (Special Leave)"]], one_time_keyboard=True, resize_keyboard=True))
    return LEAVE_DURATION

async def leave_duration_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "ច្បាប់" in text:
        context.user_data['leave_type'] = text
        now = get_khmer_timezone_now()
        await update.message.reply_text("📅 **សូមជ្រើសរើសកាលបរិច្ឆេទឈប់សម្រាកពីប្រតិទិន៖**", parse_mode="Markdown", reply_markup=create_calendar(now.year, now.month))
        return LEAVE_DURATION
    context.user_data['leave_duration'] = text
    await update.message.reply_text("📝 សូមសរសេររៀបរាប់ពីមូលហេតុនៃការសុំច្បាប់សម្រាក៖", reply_markup=ReplyKeyboardRemove())
    return LEAVE_REASON

async def leave_reason_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    context.user_data['leave_reason'] = update.message.text
    l_date, l_type, l_dur, l_reas = context.user_data.get('leave_date', 'មិនបានកំណត់'), context.user_data.get('leave_type', 'មិនបានកំណត់'), context.user_data.get('leave_duration', 'មិនបានកំណត់'), context.user_data.get('leave_reason', 'មិនបានកំណត់')
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("✅ អនុម័ត", callback_data=f"lv_appv_{user.id}_{l_date}"), InlineKeyboardButton("❌ បដិសេធ", callback_data=f"lv_rjct_{user.id}_{l_date}")]])
    await context.bot.send_message(chat_id=GROUP_ID, text=f"📩 **ពាក្យសុំច្បាប់សម្រាកការងារ**\n👤 ឈ្មោះមន្ត្រី៖ {user.full_name}\n📋 ប្រភេទច្បាប់៖ {l_type}\n📅 សម្រាប់ថ្ងៃទី៖ {l_date}\n⏳ រយៈពេល៖ {l_dur}\n📝 មូលហេតុ៖ {l_reas}", reply_markup=reply_markup, parse_mode="Markdown")
    await update.message.reply_text("⏳ ពាក្យសុំច្បាប់របស់លោកស្រីត្រូវបានបញ្ជូនទៅកាន់ថ្នាក់ដឹកនាំរួចរាល់ហើយ។")
    return ConversationHandler.END

async def global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "IGNORE": return await query.answer()
    if data.startswith("PREV_") or data.startswith("NEXT_"):
        parts = data.split("_")
        year, month = int(parts[1]), int(parts[2]) + (-1 if data.startswith("PREV_") else 1)
        if month == 0: month = 12; year -= 1
        elif month == 13: month = 1; year += 1
        return await query.edit_message_reply_markup(reply_markup=create_calendar(year, month))
    if data.startswith("CAL_"):
        parts = data.split("_")
        chosen_date = datetime(int(parts[1]), int(parts[2]), int(parts[3])).date()
        if chosen_date <= get_khmer_timezone_now().date():
            return await context.bot.send_message(chat_id=query.message.chat_id, text="❌ មិនអាចសុំច្បាប់សម្រាប់ថ្ងៃនេះ ឬថ្ងៃកន្លងទៅបានទេ។")
        context.user_data['leave_date'] = chosen_date.strftime("%Y-%m-%d")
        await query.edit_message_text(text=f"📅 ប្រតិទិន៖ បានជ្រើសរើសថ្ងៃ {context.user_data['leave_date']} រួចរាល់។")
        return await context.bot.send_message(chat_id=query.message.chat_id, text=f"⏳ សូមជ្រើសរើសរយៈពេល ឬចំនួនថ្ងៃ៖", reply_markup=ReplyKeyboardMarkup([["កន្លះថ្ងៃ (១ ព្រឹក)", "កន្លះថ្ងៃ (១ រសៀល)"], ["១ ថ្ងៃ", "២ ថ្ងៃ", "៣ ថ្ងៃ"]], one_time_keyboard=True, resize_keyboard=True))
    if data.startswith("lv_appv_") or data.startswith("lv_rjct_"):
        leader = query.from_user.full_name
        parts = data.split("_")
        officer_id = int(parts[2])
        status = "Approved" if data.startswith("lv_appv_") else "Rejected"
        await query.edit_message_text(text=f"{query.message.text}\n\n📌 **ស្ថានភាព៖** {'✅ បានអនុម័ត' if status=='Approved' else '❌ បដិសេធ'} (ដោយ៖ {leader})")
        try: await context.bot.send_message(chat_id=officer_id, text=f"🔔 ដំណឹង៖ ពាក្យសុំច្បាប់សម្រាកថ្ងៃទី `{parts[3]}` ត្រូវបានថ្នាក់ដឹកនាំសម្រេច **«{'អនុម័ត ✅' if status=='Approved' else 'បដិសេធ ❌'}»**។", parse_mode="Markdown")
        except: pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ដំណើរការត្រូវបានបោះបង់ nudge។", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# =========================================================================
# 🌐 ផ្នែក Web Server (Flask) រួមបញ្ចូលជាមួយ Webhook ផ្លូវការ
# =========================================================================
web_app = Flask('')
telegram_app = Application.builder().token(BOT_TOKEN).build()

telegram_app.add_handler(ConversationHandler(entry_points=[CommandHandler("start", start)], states={PHOTO: [MessageHandler(filters.PHOTO, handle_photo)], LOCATION: [MessageHandler(filters.LOCATION, handle_location)]}, fallbacks=[CommandHandler("cancel", cancel)]))
telegram_app.add_handler(ConversationHandler(entry_points=[CommandHandler("leave", leave_start)], states={LEAVE_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, leave_duration_chosen)], LEAVE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, leave_reason_chosen)]}, fallbacks=[CommandHandler("cancel", cancel)]))
telegram_app.add_handler(CallbackQueryHandler(global_callback_handler))

@web_app.route('/')
def home(): 
    return "Bot របស់រដ្ឋបាលក្រុងសួង កំពុងដំណើរការយ៉ាងរលូន!"

@web_app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_app.process_update(update))
    return "OK", 200

def set_webhook_init():
    async def _init():
        await telegram_app.initialize()
        await telegram_app.bot.set_webhook(url=f"{RENDER_URL}/webhook")
        print("🚀 Webhook Connected Successfully!")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_init())

if __name__ == "__main__":
    set_webhook_init()
    web_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
