import os
import csv
from datetime import datetime, timedelta
import pytz  # បណ្ណាល័យសម្រាប់កំណត់ Timezone ឱ្យត្រូវម៉ោងខ្មែរ
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# កំណត់ទីតាំងសាលាក្រុងសួង (Latitude, Longitude)
OFFICE_LAT = 11.9167
OFFICE_LON = 105.6667
ALLOWED_RADIUS_M = 150  # រង្វង់ ១៥០ ម៉ែត្រ

# ឈ្មោះឯកសាររក្សាទុកទិន្នន័យ
REPORT_FILE = "attendance_records.csv"

# ស្ថានភាពសម្រាប់ Conversation
PHOTO, LOCATION = range(2)

# បង្កើតឯកសារ CSV បើមិនទាន់មាន (ថែម ک្បាលតារាង "ប្រភេទវត្តមាន")
if not os.path.exists(REPORT_FILE):
    with open(REPORT_FILE, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["កាលបរិច្ឆេទ", "ម៉ោង", "ID មន្ត្រី", "ឈ្មោះគណនី", "ប្រភេទវត្តមាន", "ស្ថានភាពម៉ោង", "ចម្ងាយ(ម៉ែត្រ)", "រដូវកាល", "ខែ", "ត្រីមាស", "ឆមាស"])

def get_khmer_timezone_now():
    """ទាញយកម៉ោងបច្ចុប្បន្ននៅក្នុងប្រទេសកម្ពុជា ទោះ Server នៅឯណាក៏ដោយ"""
    khmer_tz = pytz.timezone('Asia/Phnom_Penh')
    return datetime.now(khmer_tz)

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
    """
    ពិនិត្យមើលម៉ោងខែ្មរជាក់ស្តែង ដើម្បីបែងចែកវេន និងស្ថានភាពវត្តមាន
    ត្រឡប់មកវិញនូវ៖ (ប្រភេទវេន, ស្ថានភាពម៉ោង)
    """
    current_time = now_dt.time()
    
    # កំណត់ដែនម៉ោងនីមួយៗជាទម្រង់ (ចាប់ផ្តើម, បញ្ចប់)
    shift_morning_in_start = datetime.strptime("07:30", "%H:%M").time()
    shift_morning_in_end   = datetime.strptime("08:00", "%H:%M").time()
    
    shift_morning_out_start = datetime.strptime("11:00", "%H:%M").time()
    shift_morning_out_end   = datetime.strptime("11:30", "%H:%M").time()
    
    shift_afternoon_in_start = datetime.strptime("14:00", "%H:%M").time()
    shift_afternoon_in_end   = datetime.strptime("14:30", "%H:%M").time()
    
    shift_afternoon_out_start = datetime.strptime("17:00", "%H:%M").time()
    shift_afternoon_out_end   = datetime.strptime("17:30", "%H:%M").time()

    # --- ពិនិត្យវេនព្រឹក ---
    # ១. ចូលការងារពេលព្រឹក
    if shift_morning_in_start <= current_time <= shift_morning_in_end:
        return "ចូលការងារ (ព្រឹក)", "ទាន់ពេល"
    elif shift_morning_in_end < current_time < shift_morning_out_start:
        return "ចូលការងារ (ព្រឹក)", "យឺត / អវត្តមាន"
        
    # ២. ចេញការងារពេលព្រឹក
    elif shift_morning_out_start <= current_time <= shift_morning_out_end:
        return "ចេញការងារ (ព្រឹក)", "ទាន់ពេល"
    elif shift_morning_out_end < current_time < shift_afternoon_in_start:
        return "ចេញការងារ (ព្រឹក)", "យឺត / អវត្តមាន"

    # --- ពិនិត្យវេនរសៀល ---
    # ៣. ចូលការងារពេលរសៀល
    elif shift_afternoon_in_start <= current_time <= shift_afternoon_in_end:
        return "ចូលការងារ (រសៀល)", "ទាន់ពេល"
    elif shift_afternoon_in_end < current_time < shift_afternoon_out_start:
        return "ចូលការងារ (រសៀល)", "យឺត / អវត្តមាន"
        
    # ៤. ចេញការងារពេលរសៀល
    elif shift_afternoon_out_start <= current_time <= shift_afternoon_out_end:
        return "ចេញការងារ (រសៀល)", "ទាន់ពេល"
    
    # ករណីបាញ់រូបចូលក្រៅម៉ោងកំណត់ទាំងស្រុង
    else:
        return "ក្រៅម៉ោងរដ្ឋបាល", "យឺត / អវត្តមាន"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📥 ស្វាគមន៍មកកាន់ប្រព័ន្ធគ្រប់គ្រងវត្តមានរដ្ឋបាលក្រុងសួង!\n"
        "សូមផ្ញើរូបថត Selfie ផ្ទាល់ខ្លួនរបស់អ្នក ដើម្បីចាប់ផ្តើមចុះវត្តមាន។"
    )
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    context.user_data['photo_id'] = photo_file.file_id
    
    location_keyboard = [[{"text": "📍 ផ្ញើទីតាំងបច្ចុប្បន្ន (Share GPS)", "request_location": True}]]
    reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "📸 ទទួលបានរូបថតជោគជ័យ! ជាបន្តសូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើទីតាំង GPS របស់អ្នក។",
        reply_markup=reply_markup
    )
    return LOCATION

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_loc = update.message.location
    now = get_khmer_timezone_now()  # ប្រើម៉ោងខ្មែរពិតប្រាកដ
    
    distance = calculate_distance(user_loc.latitude, user_loc.longitude, OFFICE_LAT, OFFICE_LON)
    
    if distance > ALLOWED_RADIUS_M:
        await update.message.reply_text(
            f"❌ មិនអាចចុះវត្តមានបានទេ! អ្នកស្ថិតនៅចម្ងាយ {int(distance)} ម៉ែត្រ ក្រៅតំបន់សាលាក្រុងសួង (អនុញ្ញាតត្រឹម {ALLOWED_RADIUS_M} ម៉ែត្រ)។",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # គណនាវេន និងស្ថានភាពម៉ោងតាមច្បាប់ថ្មី (៣០ នាទី)
    attendance_type, status_time = check_attendance_shift(now)

    season, quarter, semester = get_khmer_season_info(now)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    user_id = update.message.from_user.id
    username = update.message.from_user.full_name

    # រក្សាទុកក្នុង CSV
    with open(REPORT_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([date_str, time_str, user_id, username, attendance_type, status_time, int(distance), season, now.strftime("%B"), quarter, semester])

    # ឆ្លើយតបទៅមន្ត្រីវិញជាភាសាខ្មែរផ្លូវការ
    await update.message.reply_text(
        f"✅ រដ្ឋបាលក្រុងសួងទទួលបានវត្តមានរបស់អ្នករួចរាល់!\n"
        f"🗓 កាលបរិច្ឆេទ៖ {date_str}\n"
        f"⏰ ម៉ោង (កម្ពុជា)៖ {time_str}\n"
        f"📋 ប្រភេទ៖ {attendance_type}\n"
        f"🎯 ស្ថានភាព៖ {status_time}",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # ផ្ញើបន្តទៅ Group ថ្នាក់ដឹកនាំសាលាក្រុង
    GROUP_ID = "-5126809493"
    try:
        caption = (
            f"📢 វត្តមានមន្ត្រី៖ {username}\n"
            f"⏰ ម៉ោង៖ {time_str} ({attendance_type})\n"
            f"📍 ចម្ងាយ៖ {int(distance)}ម ពីសាលាក្រុង\n"
            f"📌 ស្ថានភាព៖ {status_time}"
        )
        await context.bot.send_photo(chat_id=GROUP_ID, photo=context.user_data['photo_id'], caption=caption)
    except Exception as e:
        print(f"Error sending to group: {e}")

    return ConversationHandler.END

# =========================================================================
# ប្រព័ន្ធចម្រាញ់របាយការណ៍បត់បែនប្រចាំ ថ្ងៃ/សប្តាហ៍/ខែ/ត្រីមាស/ឆមាស/ឆ្នាំ
# =========================================================================
async def get_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text
    if not os.path.exists(REPORT_FILE):
        await update.message.reply_text("❌ មិនទាន់មានទិន្នន័យវត្តមានក្នុងប្រព័ន្ធឡើយ។")
        return

    now = get_khmer_timezone_now()
    today_str = now.strftime("%Y-%m-%d")
    current_year = now.strftime("%Y")
    current_month = now.month
    
    output_filename = f"វត្តមាន_{command.replace('/', '')}_{now.strftime('%Y%m%d')}.csv"
    start_of_week = (now - timedelta(days=7)).date()
    has_data = False

    with open(REPORT_FILE, mode="r", encoding="utf-8-sig") as src, open(output_filename, mode="w", newline="", encoding="utf-8-sig") as dest:
        reader = csv.reader(src)
        writer = csv.writer(dest)
        
        header = next(reader, None)
        if header: 
            writer.writerow(header)
            
        for row in reader:
            row_date_str = row[0]
            try:
                row_date = datetime.strptime(row_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
                
            row_month = int(row_date_str.split("-")[1])
            row_year = row_date_str.split("-")[0]

            if command == "/report_day":
                if row_date_str == today_str:
                    writer.writerow(row)
                    has_data = True
            elif command == "/report_week":
                if row_date >= start_of_week:
                    writer.writerow(row)
                    has_data = True
            elif command == "/report_month":
                if row_year == current_year and row_month == current_month:
                    writer.writerow(row)
                    has_data = True
            elif command == "/report_quarter":
                current_quarter = f"ត្រីមាសទី{(current_month-1)//3 + 1}"
                if row_year == current_year and row[9] == current_quarter:
                    writer.writerow(row)
                    has_data = True
            elif command == "/report_semester":
                current_semester = "ឆមាសទី១" if current_month <= 6 else "ឆមាសទី២"
                if row_year == current_year and row[10] == current_semester:
                    writer.writerow(row)
                    has_data = True
            elif command == "/report_year":
                if row_year == current_year:
                    writer.writerow(row)
                    has_data = True

    if has_data:
        await update.message.reply_text(f"📊 កំពុងរៀបចំ និងផ្ញើរបាយការណ៍ {command} ជូនលោក...")
        await update.message.reply_document(document=open(output_filename, "rb"))
    else:
        await update.message.reply_text(f"ℹ️ មិនមានទិន្នន័យសម្រាប់របាយការណ៍ {command} ក្នុងអំឡុងពេលនេះទេ។")
        
    if os.path.exists(output_filename):
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
    app.add_handler(CommandHandler("report_day", get_report))
    app.add_handler(CommandHandler("report_week", get_report))
    app.add_handler(CommandHandler("report_month", get_report))
    app.add_handler(CommandHandler("report_quarter", get_report))
    app.add_handler(CommandHandler("report_semester", get_report))
    app.add_handler(CommandHandler("report_year", get_report))

    print("🚀 ដំណើរការប្រព័ន្ធគ្រប់គ្រងវត្តមានឆ្លាតវៃ កម្រិតរដ្ឋបាលក្រុងសួង...")
    app.run_polling()

if __name__ == "__main__":
    main()
