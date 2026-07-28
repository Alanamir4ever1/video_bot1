import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import time
import threading
import subprocess
import shutil

TOKEN = "8874751043:AAE7o4-XhKGdsttEwlkMilx-nqwA-yNBE2I"

bot = telebot.TeleBot(TOKEN)

# ---------- Поиск ffmpeg ----------
def find_ffmpeg():
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path
    possible_paths = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Windows\System32\ffmpeg.exe'
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return None

FFMPEG_PATH = find_ffmpeg()

# ---------- Хранилище ссылок ----------
video_storage = {}
storage_lock = threading.Lock()

def clean_storage():
    while True:
        time.sleep(3600)
        with storage_lock:
            video_storage.clear()

threading.Thread(target=clean_storage, daemon=True).start()

# ---------- Сжатие видео ----------
def compress_video(input_path, output_path, target_mb=48):
    if not FFMPEG_PATH:
        return False
    bitrates = ['1M', '500k', '300k', '200k']
    for br in bitrates:
        try:
            cmd = [
                FFMPEG_PATH,
                '-i', input_path,
                '-c:v', 'libx264',
                '-b:v', br,
                '-c:a', 'aac',
                '-b:a', '128k',
                '-preset', 'fast',
                '-y',
                output_path
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                if size_mb <= target_mb:
                    return True
        except Exception as e:
            print(f"Сжатие с битрейтом {br} не удалось: {e}")
            continue
    return False

# ---------- Скачивание видео (исправленная) ----------
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
        'ffmpeg_location': FFMPEG_PATH,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise Exception("Не удалось получить информацию о видео. Проверьте ссылку.")
            filename = ydl.prepare_filename(info)
            if not filename:
                # если prepare_filename вернул None, ищем вручную
                for f in os.listdir('.'):
                    if f.startswith('video.') and f.endswith('.mp4'):
                        return f
                raise Exception("Файл не найден после загрузки.")
            if not os.path.exists(filename):
                for f in os.listdir('.'):
                    if f.startswith('video.') and f.endswith('.mp4'):
                        filename = f
                        break
            return filename
    except Exception as e:
        raise Exception(f"Ошибка при загрузке видео: {str(e)}")

# ---------- Скачивание аудио (исправленная) ----------
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
        'ffmpeg_location': FFMPEG_PATH,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)  # не скачиваем, только информация
            if info is None:
                raise Exception("Не удалось получить информацию об аудио. Проверьте ссылку.")
            # теперь скачиваем аудио
            ydl.download([url])
            # ищем файл
            for f in os.listdir('.'):
                if f.startswith('audio.') and (f.endswith('.mp3') or f.endswith('.m4a')):
                    return f
            raise Exception("Аудиофайл не найден после загрузки.")
    except Exception as e:
        raise Exception(f"Ошибка при загрузке аудио: {str(e)}")

# ---------- Команда /start ----------
@bot.message_handler(commands=['start', 'help'])
def send_help(message):
    if not FFMPEG_PATH:
        bot.reply_to(
            message,
            "❌ ffmpeg не найден. Убедись, что он установлен."
        )
        return
    bot.reply_to(
        message,
        "🤖 Отправь мне ссылку на видео с YouTube, TikTok, Instagram и др.\n"
        "Если видео больше 50 МБ — я автоматически сожму его.\n"
        "Под видео будет кнопка для извлечения аудио.\n\n"
        "⚠️ Файлы больше 200 МБ могут не сжаться."
    )

# ---------- Обработка ссылок ----------
@bot.message_handler(func=lambda msg: msg.text and (msg.text.startswith('http://') or msg.text.startswith('https://')))
def handle_video_link(message):
    url = message.text.strip()
    if not FFMPEG_PATH:
        bot.reply_to(message, "❌ ffmpeg не найден. Установи его.")
        return

    bot.reply_to(message, "⏳ Начинаю загрузку видео...")

    try:
        video_file = download_video(url)
        size_mb = os.path.getsize(video_file) / (1024 * 1024)

        if size_mb > 50:
            bot.reply_to(message, f"📦 Видео весит {size_mb:.1f} МБ. Начинаю сжатие до 48 МБ...")
            compressed_file = f"compressed_{int(time.time())}_{video_file}"
            if compress_video(video_file, compressed_file):
                os.remove(video_file)
                video_file = compressed_file
                new_size = os.path.getsize(video_file) / (1024 * 1024)
                bot.reply_to(message, f"✅ Сжатие успешно! Новый размер: {new_size:.1f} МБ.")
            else:
                bot.reply_to(message, "❌ Не удалось сжать видео до 50 МБ.")
                os.remove(video_file)
                return

        final_size = os.path.getsize(video_file) / (1024 * 1024)
        if final_size > 50:
            bot.reply_to(message, f"❌ Видео слишком большое ({final_size:.1f} МБ).")
            os.remove(video_file)
            return

        with storage_lock:
            vid = str(int(time.time())) + str(message.chat.id)
            video_storage[vid] = url

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎵 Извлечь аудио", callback_data=f"audio_{vid}"))

        with open(video_file, 'rb') as f:
            bot.send_video(message.chat.id, f, caption="🎬 Видео готово!", reply_markup=markup)

        os.remove(video_file)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка загрузки: {e}")
        for f in os.listdir('.'):
            if f.startswith('video.') or f.startswith('compressed_') or f.startswith('audio.'):
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
            bot.send_message(call.message.chat.id, "❌ Ссылка уже неактивна.")
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
        with storage_lock:
            del video_storage[vid]

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка извлечения аудио: {e}")
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
    print("🤖 Бот запущен. Ожидаю ссылки...")
    bot.infinity_polling()
