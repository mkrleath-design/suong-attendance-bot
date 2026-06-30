import os
import csv
import calendar
from datetime import datetime, timedelta
import pytz
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

# កំណត់ទីតាំងសាលាក្រុងសួង
OFFICE_LAT = 11.9167
OFFICE_LON = 105.6667
ALLOWED_RADIUS_M = 150

# ឈ្មោះឯកសាររក្សាទុកទិន្នន័យ
REPORT_FILE = "attendance_records.csv"
LEAVE_FILE = "leave_records.csv"

# ID ក្រុមរបស់លោក (សូមប្តូរឱ្យត្រូវនឹង Group របស់លោកពិតប្រាកដ)
GROUP_ID = "-5126809493" 

# ស្ថានភាពសម្រាប់ Conversation វត្តមាន និងសុំច្បាប់
PHOTO, LOCATION = range(2)
LEAVE_DURATION, LEAVE_REASON = range(2, 4)

# បង្កើតឯកសារ CSV បើមិនទាន់មាន
if not os.path.exists(REPORT_FILE):
    with open(REPORT_FILE, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["កាលបរិច្ឆេទ", "ម៉ោង", "ID មន្ត្រី", "ឈ្មោះគណនី", "ប្រភេទវត្តមាន", "ស្ថានភាពម៉ោង", "ចម្ងាយ(ម៉ែត្រ)", "រដូវកាល", "ខែ", "ត្រីមាស", "ឆមាស"])

if not os.path.exists(LEAVE_FILE):
    with open(LEAVE_FILE, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["កាលបរិច្ឆេទស្នើសុំ", "ID មន្ត្រី", "ឈ្មោះមន្ត្រី", "ប្រភេទច្បាប់", "ថ្ងៃចាប់ផ្តើម", "រយៈពេល", "មូលហេតុ", "ស្ថានភាព"])

def get_khmer_timezone_now():
    return datetime.now(pytz.timezone('Asia/Phnom_Penh'))

def get_khmer_season_info(dt):
    month = dt.month
    season = "រដូវវស្សា" if 5 <= month <= 10 else "រដូវប្រាំង"
    quarter = f"ត្រីមាសទី{(month-1)//3 + 1}"
    semester = "ឆមាសទី១" if month <= 6 else "ឆមាសទី២"
    return season, quarter, semester

def calculate_distance(lat1, lon1, lat2, lon2):
    from math import radians, cos, sin, asin, sqrt
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371000

def check_attendance_shift(now_dt):
    current_time = now_dt.time()
    shift_morning_in_start = datetime.strptime("07:30", "%H:%M").time()
    shift_morning_in_end   = datetime.strptime("08:00", "%H:%M").time()
    shift_morning_out_start = datetime.strptime("11:00", "%H:%M").time()
    shift_morning_out_end   = datetime.strptime("11:30", "%H:%M").time()
    
    shift_afternoon_in_start = datetime.strptime("14:00", "%H:%M").time()
    shift_afternoon_in_end   = datetime.strptime("14:30", "%H:%M").time()
    shift_afternoon_out_start = datetime.strptime("17:00", "%H:%M").time()
    shift_afternoon_out_end   = datetime.strptime("17:30", "%H:%M").time()

    if shift_morning_in_start <= current_time <= shift_morning_in_end:
        return "ចូលការងារ (ព្រឹក)", "ទាន់ពេល"
    elif shift_morning_in_end < current_time < shift_morning_out_start:
        return "ចូលការងារ (ព្រឹក)", "យឺត / អវត្តមាន"
    elif shift_morning_out_start <= current_time <= shift_morning_out_end:
        return "ចេញការងារ (ព្រឹក)", "ទាន់ពេល"
    elif shift_morning_out_end < current_time < shift_afternoon_in_start:
        return "ចេញការងារ (ព្រឹក)", "យឺត / អវត្តមាន"
    elif shift_afternoon_in_start <= current_time <= shift_afternoon_in_end:
        return "ចូលការងារ (រសៀល)", "ទាន់ពេល"
    elif shift_afternoon_in_end < current_time < shift_afternoon_out_start:
        return "ចូលការងារ (រសៀល)", "យឺត / អវត្តមាន"
    elif shift_afternoon_out_start <= current_time <= shift_afternoon_out_end:
        return "ចេញការងារ (រសៀល)", "ទាន់ពេល"
    else:
        return "ក្រៅម៉ោងរដ្ឋបាល", "យឺត / អវត្តមាន"

# --- 📅 ផ្នែកប្រតិទិន ---
def create_calendar(year, month):
    keyboard = []
    row_header = [InlineKeyboardButton(f"🗓️ {calendar.month_name[month]} {year}", callback_data="IGNORE")]
    keyboard.append(row_header)
    
    row_days = []
    for day in ["ច", "អ", "ព", "ព្រ", "សុ", "ស", "អា"]:
        row_days.append(InlineKeyboardButton(day, callback_data="IGNORE"))
    keyboard.append(row_days)
    
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row_week = []
        for day in week:
            if day == 0:
                row_week.append(InlineKeyboardButton(" ", callback_data="IGNORE"))
            else:
                row_week.append(InlineKeyboardButton(str(day), callback_data=f"CAL_{year}_{month}_{day}"))
        keyboard.append(row_week)
        
    row_nav = [
        InlineKeyboardButton("◀️ ខែមុន", callback_data=f"PREV_{year}_{month}"),
        InlineKeyboardButton("ខែបន្ទាប់ ▶️", callback_data=f"NEXT_{year}_{month}")
    ]
    keyboard.append(row_nav)
    
    return InlineKeyboardMarkup(keyboard)

# --- 📱 ផ្នែកកូដចុះវត្តមានធម្មតា ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📥 ស្វាគមន៍មកកាន់ប្រព័ន្ធរដ្ឋបាលក្រុងសួង!\n"
        "• ចុះវត្តមាន៖ សូមផ្ញើរូបថត Selfie របស់អ្នក\n"
        "• សុំច្បាប់សម្រាក៖ សូមវាយបញ្ជា /leave"
    )
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    context.user_data['photo_id'] = photo_file.file_id
    location_keyboard = [[{"text": "📍 ផ្ញើទីតាំងបច្ចុប្បន្ន (Share GPS)", "request_location": True}]]
    reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📸 ទទួលបានរូបថតជោគជ័យ! សូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើទីតាំង GPS។", reply_markup=reply_markup)
    return LOCATION

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_loc = update.message.location
    now = get_khmer_timezone_now()
    distance = calculate_distance(user_loc.latitude, user_loc.longitude, OFFICE_LAT, OFFICE_LON)
    
    if distance > ALLOWED_RADIUS_M:
        await update.message.reply_text(f"❌ មិនអាចចុះវត្តមានបានទេ! អ្នកស្ថិតនៅចម្ងាយ {int(distance)}ម ក្រៅតំបន់សាលាក្រុងសួង។", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    attendance_type, status_time = check_attendance_shift(now)
    season, quarter, semester = get_khmer_season_info(now)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    with open(REPORT_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([date_str, time_str, update.message.from_user.id, update.message.from_user.full_name, attendance_type, status_time, int(distance), season, now.strftime("%B"), quarter, semester])

    await update.message.reply_text(f"✅ ចុះវត្តមានជោគជ័យ!\n🗓 កាលបរិច្ឆេទ៖ {date_str}\n⏰ ម៉ោង៖ {time_str}\n📋 ប្រភេទ៖ {attendance_type}\n🎯 ស្ថានភាព៖ {status_time}", reply_markup=ReplyKeyboardRemove())
    
    try:
        caption = f"📢 វត្តមានមន្ត្រី៖ {update.message.from_user.full_name}\n⏰ ម៉ោង៖ {time_str} ({attendance_type})\n📍 ចម្ងាយ៖ {int(distance)}ម\n📌 ស្ថានភាព៖ {status_time}"
        await context.bot.send_photo(chat_id=GROUP_ID, photo=context.user_data['photo_id'], caption=caption)
    except Exception as e:
        print(f"Error: {e}")
    return ConversationHandler.END

# =========================================================================
# 🛠️ ផ្នែកកូដប្រព័ន្ធសុំច្បាប់សម្រាក ( Leave System - FIXED )
# =========================================================================
async def leave_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["ច្បាប់ឈឺ (Sick Leave)", "ច្បាប់ផ្ទាល់ខ្លួន (Special Leave)"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📋 សូមជ្រើសរើសប្រភេទច្បាប់សម្រាក៖", reply_markup=reply_markup)
    return LEAVE_DURATION # ផ្លាស់ទៅរង់ចាំ Duration តែម្តង ដោយចោលការរើសថ្ងៃទៅក្រៅ

async def leave_duration_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # រក្សាទុកប្រភេទច្បាប់ និងរយៈពេលរួមគ្នា
    text_input = update.message.text
    
    if "ច្បាប់ឈឺ" in text_input or "ច្បាប់ផ្ទាល់ខ្លួន" in text_input:
        context.user_data['leave_type'] = text_input
        # បង្ហាញប្រតិទិនឱ្យរើសថ្ងៃ
        now = get_khmer_timezone_now()
        reply_markup = create_calendar(now.year, now.month)
        await update.message.reply_text(
            "📅 **សូមជ្រើសរើសកាលបរិច្ឆេទឈប់សម្រាកពីប្រតិទិនខាងក្រោម៖**\n"
            "*(លក្ខខណ្ឌ៖ ត្រូវសុំច្បាប់មុនថ្ងៃបំពេញការងារ ចាប់ពីថ្ងៃស្អែកឡើងទៅ)*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return LEAVE_DURATION # នៅចាំក្នុង State ដដែលរហូតដល់ចុចប្រតិទិនរួច

    # បើមន្ត្រីចុចរើសរយៈពេល (បន្ទាប់ពីចុចប្រតិទិនរួច)
    context.user_data['leave_duration'] = text_input
    await update.message.reply_text("📝 សូមសរសេររៀបរាប់ពីមូលហេតុនៃការសុំច្បាប់សម្រាកនេះ៖", reply_markup=ReplyKeyboardRemove())
    return LEAVE_REASON

async def leave_reason_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    context.user_data['leave_reason'] = update.message.text
    
    # ពិនិត្យសុវត្ថិភាពទិន្នន័យការពារការគាំង
    l_date = context.user_data.get('leave_date', 'មិនបានកំណត់')
    l_type = context.user_data.get('leave_type', 'មិនបានកំណត់')
    l_dur  = context.user_data.get('leave_duration', 'មិនបានកំណត់')
    l_reas = context.user_data.get('leave_reason', 'មិនបានកំណត់')

    callback_approve = f"lv_appv_{user.id}_{l_date}"
    callback_reject  = f"lv_rjct_{user.id}_{l_date}"

    inline_keyboard = [[
        InlineKeyboardButton("✅ អនុម័ត", callback_data=callback_approve),
        InlineKeyboardButton("❌ បដិសេធ", callback_data=callback_reject)
    ]]
    reply_markup = InlineKeyboardMarkup(inline_keyboard)

    group_message = (
        f"📩 **ពាក្យសុំច្បាប់សម្រាកការងារ**\n"
        f"👤 ឈ្មោះមន្ត្រី៖ {user.full_name}\n"
        f"📋 ប្រភេទច្បាប់៖ {l_type}\n"
        f"📅 សម្រាប់ថ្ងៃទី៖ {l_date}\n"
        f"⏳ រយៈពេល៖ {l_dur}\n"
        f"📝 មូលហេតុ៖ {l_reas}\n\n"
        f"👉 គោរពជូនថ្នាក់ដឹកនាំមេត្តាពិនិត្យ និងសម្រេច៖"
    )
    
    await context.bot.send_message(chat_id=GROUP_ID, text=group_message, reply_markup=reply_markup, parse_mode="Markdown")
    await update.message.reply_text("⏳ ពាក្យសុំច្បាប់របស់លោកស្រីត្រូវបានបញ្ជូនទៅកាន់ថ្នាក់ដឹកនាំរួចរាល់ហើយ។ សូមរង់ចាំការពិនិត្យអនុម័ត!")
    return ConversationHandler.END

# --- ⚙️ ផ្នែកគ្រប់គ្រងប៊ូតុងទាំងអស់ (All Callbacks Unified) ---
async def global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # ១. ករណីចុចលើប៊ូតុងដែលមិនត្រូវធ្វើអ្វីសោះ
    if data == "IGNORE":
        await query.answer()
        return

    # ២. ករណីចុចប្តូរខែនៅលើប្រតិទិន
    if data.startswith("PREV_") or data.startswith("NEXT_"):
        await query.answer()
        parts = data.split("_")
        year, month = int(parts[1]), int(parts[2])
        if data.startswith("PREV_"):
            month -= 1
            if month == 0: month = 12; year -= 1
        else:
            month += 1
            if month == 13: month = 1; year += 1
        await query.edit_message_reply_markup(reply_markup=create_calendar(year, month))
        return

    # ៣. ករណីមន្ត្រីចុចរើសថ្ងៃសុំច្បាប់ពីប្រតិទិន
    if data.startswith("CAL_"):
        await query.answer()
        parts = data.split("_")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        chosen_date = datetime(year, month, day).date()
        now_khmer = get_khmer_timezone_now().date()

        if chosen_date <= now_khmer:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ មិនអាចសុំច្បាប់សម្រាប់ថ្ងៃនេះ ឬថ្ងៃកន្លងទៅបានទេ។ សូមជ្រើសរើសថ្ងៃចាប់ពីថ្ងៃស្អែកឡើងទៅនៅលើប្រតិទិនម្តងទៀត៖"
            )
            return

        date_str = chosen_date.strftime("%Y-%m-%d")
        context.user_data['leave_date'] = date_str
        
        # លុបប្រតិទិនចោល រួចលោតប៊ូតុងរើសរយៈពេលជំនួស
        keyboard = [["កន្លះថ្ងៃ (១ ព្រឹក)", "កន្លះថ្ងៃ (១ រសៀល)"], ["១ ថ្ងៃ", "២ ថ្ងៃ", "៣ ថ្ងៃ"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await query.edit_message_text(text=f"📅 ប្រតិទិន៖ បានជ្រើសរើសថ្ងៃ {date_str} រួចរាល់។")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"⏳ សូមជ្រើសរើសរយៈពេល ឬចំនួនថ្ងៃដែលត្រូវសុំ៖",
            reply_markup=reply_markup
        )
        return

    # ៤. ករណីថ្នាក់ដឹកនាំចុច អនុម័ត ឬ បដិសេធ ក្នុង Group
    if data.startswith("lv_appv_") or data.startswith("lv_rjct_"):
        await query.answer()
        leader_name = query.from_user.full_name
        original_text = query.message.text
        
        lines = original_text.split("\n")
        emp_name = lines[1].replace("👤 ឈ្មោះមន្ត្រី៖ ", "") if len(lines) > 1 else "មិនច្បាស់"
        leave_type = lines[2].replace("📋 ប្រភេទច្បាប់៖ ", "") if len(lines) > 2 else "មិនច្បាស់"
        leave_date = lines[3].replace("📅 សម្រាប់ថ្ងៃទី៖ ", "") if len(lines) > 3 else "មិនច្បាស់"
        duration = lines[4].replace("⏳ រយៈពេល៖ ", "") if len(lines) > 4 else "មិនច្បាស់"
        reason = lines[5].replace("📝 មូលហេតុ៖ ", "") if len(lines) > 5 else "មិនច្បាស់"
        
        now_str = get_khmer_timezone_now().strftime("%Y-%m-%d %H:%M:%S")

        if data.startswith("lv_appv_"):
            new_status = f"✅ បានអនុម័ត (ដោយ៖ {leader_name})"
            with open(LEAVE_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([now_str, data.split("_")[2], emp_name, leave_type, leave_date, duration, reason, "Approved"])
        else:
            new_status = f"❌ មិនអនុម័ត/បដិសេធ (ដោយ៖ {leader_name})"

        updated_text = f"{original_text}\n\n📌 **ស្ថានភាព៖** {new_status}"
        await query.edit_message_text(text=updated_text, parse_mode="Markdown", reply_markup=None)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ដំណើរការត្រូវបានបោះបង់។", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- 📊 ផ្នែកទាញរបាយការណ៍ ---
async def get_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text
    if command == "/report_leave":
        if os.path.exists(LEAVE_FILE):
            await update.message.reply_text("📊 កំពុងផ្ញើរបាយការណ៍ច្បាប់សម្រាកមន្ត្រី...")
            await update.message.reply_document(document=open(LEAVE_FILE, "rb"))
        else:
            await update.message.reply_text("ℹ️ មិនទាន់មានទិន្នន័យច្បាប់សម្រាកឡើយ។")
        return
    
    if not os.path.exists(REPORT_FILE):
        await update.message.reply_text("❌ មិនទាន់មានទិន្នន័យវត្តមានក្នុងប្រព័ន្ធឡើយ។")
        return
    now = get_khmer_timezone_now()
    output_filename = f"វត្តមាន_{command.replace('/', '')}_{now.strftime('%Y%m%d')}.csv"
    has_data = False
    with open(REPORT_FILE, mode="r", encoding="utf-8-sig") as src, open(output_filename, mode="w", newline="", encoding="utf-8-sig") as dest:
        writer = csv.writer(dest)
        reader = csv.reader(src)
        header = next(reader, None)
        if header: writer.writerow(header)
        for row in reader:
            if command == "/report_day" and row[0] == now.strftime("%Y-%m-%d"):
                writer.writerow(row)
                has_data = True
            elif command == "/report_month" and int(row[0].split("-")[1]) == now.month:
                writer.writerow(row)
                has_data = True
    if has_data:
        await update.message.reply_document(document=open(output_filename, "rb"))
    else:
        await update.message.reply_text("ℹ️ មិនមានទិន្នន័យឡើយ។")
    if os.path.exists(output_filename): os.remove(output_filename)

def main():
    # Token ផ្លូវការរបស់លោក
    BOT_TOKEN = "8966159307:AAFnHG8h-D6uhEhSh6LmUVe7Ujkpry9du2E"
    app = Application.builder().token(BOT_TOKEN).build()

    attendance_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
            LOCATION: [MessageHandler(filters.LOCATION, handle_location)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    leave_handler = ConversationHandler(
        entry_points=[CommandHandler("leave", leave_start)],
        states={
            LEAVE_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, leave_duration_chosen)],
            LEAVE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, leave_reason_chosen)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(attendance_handler)
    app.add_handler(leave_handler)
    
    # ចាប់រាល់សកម្មភាពចុចប៊ូតុងប្រតិទិន និងប៊ូតុងអនុម័តទាំងអស់រួមគ្នាដោយសុវត្ថិភាព
    app.add_handler(CallbackQueryHandler(global_callback_handler)) 
    
    app.add_handler(CommandHandler("report_day", get_report))
    app.add_handler(CommandHandler("report_month", get_report))
    app.add_handler(CommandHandler("report_leave", get_report))

    print("🚀 ប្រព័ន្ធសុវត្ថិភាពកម្រិតខ្ពស់ (Bug Fixed) ត្រូវបានចាប់ផ្តើមដំណើរការ...")
    app.run_polling()

if __name__ == "__main__":
    main()
