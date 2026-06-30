import math
import os
import csv
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# =====================================
# SUONG CITY ADMINISTRATION CONFIG
# =====================================
OFFICE_LAT = 11.916389  # និយាមការរដ្ឋបាលក្រុងសួង
OFFICE_LON = 105.651028
ALLOWED_RADIUS = 150    # រង្វង់ប្រតិបត្តិការ ១៥០ ម៉ែត្រ

# ⏰ កំណត់ម៉ោងរដ្ឋបាលផ្លូវការ (ចូលយឺតបំផុតត្រឹមម៉ោង ០៨:០០:០០ ព្រឹក)
OFFICIAL_START_TIME = "08:00:00"  

# 🆔 ដាក់លេខ ID Group ថ្នាក់ដឹកនាំដែលលោកទទួលបានពីជំហានទី១ ចូលទីនេះ
LEADER_GROUP_ID = "-5126809493"  

REPORT_FILE = "advanced_attendance_report.csv"
PHOTO, LOCATION = range(2)

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def process_attendance_logic(user_id):
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M:%S")
    
    attendance_type = "Check-In (ចូលធ្វើការ)"
    punctuality = "ទាន់ពេលវេលា"
    
    if os.path.exists(REPORT_FILE):
        with open(REPORT_FILE, mode="r", encoding="utf-8-sig") as file:
            reader = csv.reader(file)
            next(reader, None)
            for row in reader:
                if row[0] == today_str and row[2] == str(user_id):
                    attendance_type = "Check-Out (ចេញពីការិយាល័យ)"
                    punctuality = "សម្រាកតាមម៉ោងកំណត់"
                    break

    if attendance_type == "Check-In (ចូលធ្វើការ)":
        fmt = "%H:%M:%S"
        t_actual = datetime.strptime(current_time_str, fmt)
        t_official = datetime.strptime(OFFICIAL_START_TIME, fmt)
        if t_actual > t_official:
            minutes_late = int((t_actual - t_official).total_seconds() / 60)
            punctuality = f"យឺតពេល ({minutes_late} នាទី)"
            
    return attendance_type, punctuality

def save_to_advanced_report(user_id, username, full_name, distance, att_type, punctuality):
    file_exists = os.path.isfile(REPORT_FILE)
    now = datetime.now()
    month = now.month
    quarter = f"ត្រីមាសទី{(month-1)//3 + 1}"
    semester = "ឆមាសទី១" if month <= 6 else "ឆមាសទី២"
    year = now.strftime("%Y")

    with open(REPORT_FILE, mode="a", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["កាលបរិច្ឆេទ", "ម៉ោងជាក់ស្តែង", "Telegram ID", "គណនី", "ឈ្មោះមន្ត្រី", "ប្រភេទវត្តមាន", "ស្ថានភាពម៉ោង", "ចម្ងាយ (ម)", "ត្រីមាស", "ឆមាស", "ឆ្នាំ"])
        writer.writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), user_id, f"@{username}" if username else "គ្មាន", full_name, att_type, punctuality, round(distance, 1), quarter, semester, year])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 សូមស្វាគមន៍មកកាន់ប្រព័ន្ធកត់ត្រាវត្តមានរដ្ឋបាលក្រុងសួង\n\n"
        "📸 សូមថតរូប **រូបថតផ្ទាល់ភ្លាមៗ (Selfie)** របស់អ្នកដើម្បីបញ្ជាក់វត្តមាន។",
        reply_markup=ReplyKeyboardRemove()
    )
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("❌ សូមផ្ញើជារូបថត (Selfie) របស់អ្នក!")
        return PHOTO

    context.user_data['photo_id'] = update.message.photo[-1].file_id
    
    # 🔒 បង្ខំឱ្យប្រើប្រាស់ប្រព័ន្ធទាញ GPS ពីឧបករណ៍ផ្ទាល់ទូរស័ព្ទដៃ
    location_button = KeyboardButton(text="📍 ផ្ញើទីតាំងបច្ចុប្បន្ន (Share GPS Location)", request_location=True)
    keyboard = ReplyKeyboardMarkup([[location_button]], resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📷 រូបថតត្រូវបានបញ្ចូលជោគជ័យ។\n\n"
        "📍 សូមចុចប៊ូតុងខាងក្រោម `📍 ផ្ញើទីតាំងបច្ចុប្បន្ន` ដើម្បីផ្ទៀងផ្ទាត់ចម្ងាយការិយាល័យ។",
        reply_markup=keyboard
    )
    return LOCATION

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.location:
        await update.message.reply_text("❌ សូមប្រើប្រាស់ប៊ូតុងផ្ញើទីតាំងផ្លូវការរបស់ប្រព័ន្ធ!")
        return LOCATION

    user_loc = update.message.location
    distance = calculate_distance(user_loc.latitude, user_loc.longitude, OFFICE_LAT, OFFICE_LON)
    user_info = update.message.from_user
    photo_id = context.user_data.get('photo_id')
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if distance <= ALLOWED_RADIUS:
        att_type, punctuality = process_attendance_logic(user_info.id)
        save_to_advanced_report(user_info.id, user_info.username, user_info.full_name, distance, att_type, punctuality)

        await update.message.reply_text(
            f"✅ **កត់ត្រាវត្តមានជោគជ័យ!**\n\n👤 មន្ត្រី៖ {user_info.full_name}\n📝 ប្រភេទ៖ {att_type}\n⏰ ស្ថានភាព៖ {punctuality}\n📍 ចម្ងាយ៖ {round(distance, 1)} ម៉ែត្រ។",
            reply_markup=ReplyKeyboardRemove()
        )

        leader_msg = (
            f"📢 **របាយការណ៍វត្តមានមន្ត្រី (រដ្ឋបាលក្រុងសួង)**\n\n"
            f"👤 មន្ត្រី៖ {user_info.full_name}\n"
            f"📅 ពេលវេលា៖ {current_time}\n"
            f"📝 ស្ថានភាព៖ {att_type} - {punctuality}\n"
            f"📍 ទីតាំង៖ ផ្ទៀងផ្ទាត់រួចរាល់ (ចម្ងាយ {round(distance, 1)} ម៉ែត្រពីសាលាក្រុង)"
        )
        try:
            await context.bot.send_photo(chat_id=LEADER_GROUP_ID, photo=photo_id, caption=leader_msg)
        except Exception as e:
            print(f"Error Send To Leaders: {e}")
    else:
        await update.message.reply_text(
            f"❌ **ចុះវត្តមានមិនជោគជ័យទេ!**\n\nឧបករណ៍បង្ហាញថាអ្នកស្ថិតនៅក្រៅតំបន់ការិយាល័យរដ្ឋបាលក្រុងសួង។\n📍 ចម្ងាយជាក់ស្តែង៖ {round(distance, 1)} ម៉ែត្រ។",
            reply_markup=ReplyKeyboardRemove()
        )
        
    context.user_data.clear()
    return ConversationHandler.END

async def get_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text
    if not os.path.exists(REPORT_FILE):
        await update.message.reply_text("❌ មិនទាន់មានទិន្នន័យវត្តមានក្នុងប្រព័ន្ធឡើយ។")
        return

    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.month
    output_filename = f"វត្តមាន_{command.replace('/', '')}_{now.strftime('%Y%m%d')}.csv"
    
    with open(REPORT_FILE, mode="r", encoding="utf-8-sig") as src, open(output_filename, mode="w", newline="", encoding="utf-8-sig") as dest:
        reader = csv.reader(src)
        writer = csv.writer(dest)
        header = next(reader, None)
        if header: writer.writerow(header)
            
        for row in reader:
            if row[10] != current_year: continue
            if command == "/report_quarter":
                if row[8] == f"ត្រីមាសទី{(current_month-1)//3 + 1}": writer.writerow(row)
            elif command == "/report_semester":
                if row[9] == ("ឆមាសទី១" if current_month <= 6 else "ឆមាសទី២"): writer.writerow(row)
            elif command == "/report_year":
                writer.writerow(row)

    await update.message.reply_text(f"📊 កំពុងផ្ញើរបាយការណ៍ {command}...")
    await update.message.reply_document(document=open(output_filename, "rb"))
    os.remove(output_filename)

def main():
    BOT_TOKEN = "8966159307:AAFnHG8h-D6uhEhSh6LmUVe7Ujkpry9du2E"
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
            LOCATION: [MessageHandler(filters.LOCATION, handle_location)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("report_quarter", get_report))
    app.add_handler(CommandHandler("report_semester", get_report))
    app.add_handler(CommandHandler("report_year", get_report))

    print("🚀 ដំណើរការប្រព័ន្ធគ្រប់គ្រងវត្តមានឆ្លាតវៃ កម្រិតរដ្ឋបាលក្រុងសួង...")
    app.run_polling()

if __name__ == "__main__":
    main()
