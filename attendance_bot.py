import os
import csv
from datetime import datetime, timedelta
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

# ម៉ោងចូលការងារ (ម៉ោង ០៧:០០ ព្រឹក)
WORK_START_HOUR = 7
WORK_START_MIN = 0

# ឈ្មោះឯកសាររក្សាទុកទិន្នន័យ
REPORT_FILE = "attendance_records.csv"

# ស្ថានភាពសម្រាប់ Conversation
PHOTO, LOCATION = range(2)

# បង្កើតឯកសារ CSV បើមិនទាន់មាន
if not os.path.exists(REPORT_FILE):
    with open(REPORT_FILE, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["កាលបរិច្ឆេទ", "ម៉ោង", "ID មន្ត្រី", "ឈ្មោះគណនី", "ស្ថានភាពម៉ោង", "ចម្ងាយ(ម៉ែត្រ)", "រដូវកាល", "ខែ", "ត្រីមាស", "ឆមាស"])

def get_khmer_season_info(dt):
    month = dt.month
    year = dt.year
    
    # កំណត់រដូវកាល
    season = "រដូវវស្សា" if 5 <= month <= 10 else "រដូវប្រាំង"
    
    # កំណត់ត្រីមាស
    quarter = f"ត្រីមាសទី{(month-1)//3 + 1}"
    
    # កំណត់ឆមាស
    semester = "ឆមាសទី១" if month <= 6 else "ឆមាសទី២"
    
    return season, quarter, semester

def calculate_distance(lat1, lon1, lat2, lon2):
    from math import radians, cos, sin, asin, sqrt
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000  # កាំផែនដីជាម៉ែត្រ
    return c * r

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📥 ស្វាគមន៍មកកាន់ប្រព័ន្ធគ្រប់គ្រងវត្តមានរដ្ឋបាលក្រុងសួង!\n"
        "សូមផ្ញើរូបថត Selfie ផ្ទាល់ខ្លួនរបស់អ្នក ដើម្បីចាប់ផ្តើមចុះវត្តមាន។"
    )
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    context.user_data['photo_id'] = photo_file.file_id
    
    # បង្កើតប៊ូតុងស្នើសុំទីតាំង
    location_keyboard = [[{"text": "📍 ផ្ញើទីតាំងបច្ចុប្បន្ន (Share GPS)", "request_location": True}]]
    reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "📸 ទទួលបានរូបថតជោគជ័យ! ជាបន្តសូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើទីតាំង GPS របស់អ្នក។",
        reply_markup=reply_markup
    )
    return LOCATION

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_loc = update.message.location
    now = datetime.now()
    
    distance = calculate_distance(user_loc.latitude, user_loc.longitude, OFFICE_LAT, OFFICE_LON)
    
    if distance > ALLOWED_RADIUS_M:
        await update.message.reply_text(
            f"❌ មិនអាចចុះវត្តមានបានទេ! អ្នកស្ថិតនៅចម្ងាយ {int(distance)} ម៉ែត្រ ក្រៅតំបន់សាលាក្រុងសួង (អនុញ្ញាតត្រឹម {ALLOWED_RADIUS_M} ម៉ែត្រ)។",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # គណនាស្ថានភាពមកទាន់ ឬយឺត
    status_time = "ទាន់ពេល"
    if now.hour > WORK_START_HOUR or (now.hour == WORK_START_HOUR and now.minute > WORK_START_MIN):
        diff_mins = (now.hour - WORK_START_HOUR) * 60 + (now.minute - WORK_START_MIN)
        status_time = f"យឺត {diff_mins} នាទី"

    season, quarter, semester = get_khmer_season_info(now)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    user_id = update.message.from_user.id
    username = update.message.from_user.full_name

    # រក្សាទុកក្នុង CSV
    with open(REPORT_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([date_str, time_str, user_id, username, status_time, int(distance), season, now.strftime("%B"), quarter, semester])

    await update.message.reply_text(
        f"✅ ចុះវត្តមានជោគជ័យ!\n🗓 កាលបរិច្ឆេទ៖ {date_str}\n⏰ ម៉ោង៖ {time_str}\n🎯 ស្ថានភាព៖ {status_time}",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # ផ្ញើបន្តទៅ Group ថ្នាក់ដឹកនាំ (បើមាន GROUP_ID)
    GROUP_ID = "-4756534568"  # ដាក់ ID ក្រុមរបស់លោកនៅទីនេះ
    try:
        caption = f"📢 វត្តមានមន្ត្រី៖ {username}\n⏰ ម៉ោង៖ {time_str}\n📍 ចម្ងាយ៖ {int(distance)}ម ពីសាលាក្រុង\n📌 ស្ថានភាព៖ {status_time}"
        await context.bot.send_photo(chat_id=GROUP_ID, photo=context.user_data['photo_id'], caption=caption)
    except Exception as e:
        print(f"Error sending to group: {e}")

    return ConversationHandler.END

# =========================================================================
# ផ្នែកកូដថ្មីសម្រាប់ទាញរបាយការណ៍ (ចម្រាញ់តាម Daily, Weekly, Monthly...)
# =========================================================================
async def get_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text
    if not os.path.exists(REPORT_FILE):
        await update.message.reply_text("❌ មិនទាន់មានទិន្នន័យវត្តមានក្នុងប្រព័ន្ធឡើយ។")
        return

    now = datetime.now()
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
                if row_year == current_year and row[8] == current_quarter:
                    writer.writerow(row)
                    has_data = True
            elif command == "/report_semester":
                current_semester = "ឆមាសទី១" if current_month <= 6 else "ឆមាសទី២"
                if row_year == current_year and row[9] == current_semester:
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
    
    # ចុះឈ្មោះពាក្យបញ្ជាទាញរបាយការណ៍ទាំងអស់
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
