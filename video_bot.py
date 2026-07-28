import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import time
import threading

TOKEN = "8874751043:AAE7o4-XhKGdsttEwlkMilx-nqwA-yNBE2I"  # замени на токен от @BotFather

bot = telebot.TeleBot(TOKEN)

# Хранилище ссылок для кнопок (временное)
video_storage = {}
storage_lock = threading.Lock()

# Очистка старых записей (раз в час)
def clean_storage():
    while True:
        time.sleep(3600)
        with storage_lock:
            video_storage.clear()

threading.Thread(target=clean_storage, daemon=True).start()

# ---------- Проверка ffmpeg ----------
def check_ffmpeg():
    import subprocess
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except:
        return False

# ---------- Скачивание видео ----------
def download_video(url):
    ydl_opts = {
        'outtmpl': 'video.%(ext)s',
        'format': 'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'noplaylist': True,
        'ffmpeg_location': None,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                for f in os.listdir('.'):
                    if f.startswith('video.') and f.endswith('.mp4'):
                        filename = f
                        break
            return filename
    except Exception as e:
        raise e

# ---------- Скачивание аудио ----------
def download_audio(url):
    ydl_opts = {
        'outtmpl': 'audio.%(ext)s',
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'noplaylist': True,
        'ffmpeg_location': None,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # у mp3 расширение .mp3, а не .m4a
            base, _ = os.path.splitext(filename)
            if not os.path.exists(filename):
                for f in os.listdir('.'):
                    if f.startswith('audio.') and (f.endswith('.mp3') or f.endswith('.m4a')):
                        filename = f
                        break
            return filename
    except Exception as e:
        raise e

# ---------- Команда /start ----------
@bot.message_handler(commands=['start', 'help'])
def send_help(message):
    if not check_ffmpeg():
        bot.reply_to(
            message,
            "⚠️ Для работы бота требуется **ffmpeg**.\n"
            "Установи его и добавь в PATH."
        )
        return
    bot.reply_to(
        message,
        "🤖 Отправь мне ссылку на видео с YouTube, TikTok, Instagram и др.\n"
        "Я скачаю видео со звуком, а под ним будет кнопка для извлечения аудио.\n\n"
        "⚠️ Файлы больше 50 МБ не отправляются."
    )

# ---------- Обработка ссылок ----------
@bot.message_handler(func=lambda msg: msg.text and (msg.text.startswith('http://') or msg.text.startswith('https://')))
def handle_video_link(message):
    url = message.text.strip()
    if not check_ffmpeg():
        bot.reply_to(message, "❌ ffmpeg не найден. Установи его.")
        return

    bot.reply_to(message, "⏳ Начинаю загрузку видео...")

    try:
        video_file = download_video(url)
        size = os.path.getsize(video_file)
        if size > 50 * 1024 * 1024:
            bot.reply_to(message, f"❌ Видео слишком большое ({size/1024/1024:.1f} МБ).")
            os.remove(video_file)
            return

        # Сохраняем ссылку для кнопки
        with storage_lock:
            vid = str(int(time.time())) + str(message.chat.id)
            video_storage[vid] = url

        # Отправляем видео с кнопкой
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎵 Извлечь аудио", callback_data=f"audio_{vid}"))

        with open(video_file, 'rb') as f:
            bot.send_video(message.chat.id, f, caption="🎬 Видео готово!", reply_markup=markup)

        os.remove(video_file)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка загрузки: {e}")
        # удаляем временные файлы
        for f in os.listdir('.'):
            if f.startswith('video.') or f.startswith('audio.'):
                try:
                    os.remove(f)
                except:
                    pass

# ---------- Колбэк для извлечения аудио ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith('audio_'))
def handle_audio_callback(call):
    bot.answer_callback_query(call.id, "⏳ Извлекаю аудио...")

    vid = call.data.split('_')[1]
    with storage_lock:
        url = video_storage.get(vid)
        if not url:
            bot.send_message(call.message.chat.id, "❌ Ссылка уже неактивна. Попробуй отправить видео заново.")
            return

    try:
        audio_file = download_audio(url)
        size = os.path.getsize(audio_file)
        if size > 50 * 1024 * 1024:
            bot.send_message(call.message.chat.id, f"❌ Аудио слишком большое ({size/1024/1024:.1f} МБ).")
            os.remove(audio_file)
            return

        with open(audio_file, 'rb') as f:
            bot.send_audio(call.message.chat.id, f, caption="🎵 Аудио готово!")

        os.remove(audio_file)

        # удаляем ссылку из хранилища
        with storage_lock:
            del video_storage[vid]

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка извлечения аудио: {e}")
        # удаляем временные файлы
        for f in os.listdir('.'):
            if f.startswith('audio.'):
                try:
                    os.remove(f)
                except:
                    pass

# ---------- Обработка других сообщений ----------
@bot.message_handler(func=lambda msg: True)
def unknown_message(message):
    bot.reply_to(message, "❌ Отправь ссылку на видео (начинается с http:// или https://).")

# ---------- Запуск ----------
if __name__ == "__main__":
    print("🤖 Бот для скачивания видео и аудио запущен.")
    bot.infinity_polling()