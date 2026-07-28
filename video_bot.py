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

# ---------- Сжатие ----------
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
        except Exception:
            continue
    return False

# ---------- Надёжная загрузка YouTube ----------
def download_video(url):
    ydl_opts = {
        'outtmpl': 'video.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'noplaylist': True,
        'ffmpeg_location': FFMPEG_PATH,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        time.sleep(1)
        # Ищем любой файл, который начинается с 'video.'
        for f in os.listdir('.'):
            if f.startswith('video.') and os.path.getsize(f) > 1000:
                return f
        raise Exception("Файл не найден")
    except Exception as e:
        raise Exception(f"Ошибка: {str(e)}")

# ---------- Аудио ----------
def download_audio(url):
    ydl_opts = {
        'outtmpl': 'audio.%(ext)s',
        'format': 'bestaudio',
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
            ydl.download([url])
        time.sleep(1)
        for f in os.listdir('.'):
            if f.startswith('audio.') and (f.endswith('.mp3') or f.endswith('.m4a')):
                return f
        raise Exception("Аудио не найдено")
    except Exception as e:
        raise Exception(f"Ошибка аудио: {str(e)}")

# ---------- Команды ----------
@bot.message_handler(commands=['start', 'help'])
def send_help(message):
    bot.reply_to(
        message,
        "🤖 Отправь ссылку на видео с YouTube, TikTok, Instagram.\n"
        "Если видео > 50 МБ — сожму.\n"
        "Под видео будет кнопка для аудио."
    )

@bot.message_handler(func=lambda msg: msg.text and (msg.text.startswith('http://') or msg.text.startswith('https://')))
def handle_video_link(message):
    url = message.text.strip()
    bot.reply_to(message, "⏳ Загружаю видео...")
    try:
        video_file = download_video(url)
        size_mb = os.path.getsize(video_file) / (1024 * 1024)

        if size_mb > 50:
            bot.reply_to(message, f"📦 {size_mb:.1f} МБ. Сжимаю...")
            compressed = f"compressed_{int(time.time())}_{video_file}"
            if compress_video(video_file, compressed):
                os.remove(video_file)
                video_file = compressed
                bot.reply_to(message, f"✅ Сжато!")
            else:
                bot.reply_to(message, "❌ Не удалось сжать.")
                os.remove(video_file)
                return

        with storage_lock:
            vid = str(int(time.time())) + str(message.chat.id)
            video_storage[vid] = url

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎵 Аудио", callback_data=f"audio_{vid}"))

        with open(video_file, 'rb') as f:
            bot.send_video(message.chat.id, f, caption="🎬 Видео готово!", reply_markup=markup)

        os.remove(video_file)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        for f in os.listdir('.'):
            if f.startswith('video.') or f.startswith('compressed_') or f.startswith('audio.'):
                try:
                    os.remove(f)
                except:
                    pass

# ---------- Аудио по кнопке ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith('audio_'))
def handle_audio_callback(call):
    bot.answer_callback_query(call.id, "⏳ Извлекаю аудио...")
    vid = call.data.split('_')[1]
    with storage_lock:
        url = video_storage.get(vid)
        if not url:
            bot.send_message(call.message.chat.id, "❌ Ссылка устарела.")
            return

    try:
        audio_file = download_audio(url)
        with open(audio_file, 'rb') as f:
            bot.send_audio(call.message.chat.id, f, caption="🎵 Аудио готово!")
        os.remove(audio_file)
        with storage_lock:
            del video_storage[vid]
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка: {e}")
        for f in os.listdir('.'):
            if f.startswith('audio.'):
                try:
                    os.remove(f)
                except:
                    pass

@bot.message_handler(func=lambda msg: True)
def unknown_message(message):
    bot.reply_to(message, "❌ Отправь ссылку (http:// или https://).")

if __name__ == "__main__":
    print("🤖 Бот запущен.")
    bot.infinity_polling()
