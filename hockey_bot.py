import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Получаем токен из переменной окружения
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, name TEXT, is_coach INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (event_id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, status TEXT DEFAULT 'open', group_msg_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS participants
                 (event_id INTEGER, user_id INTEGER,
                 FOREIGN KEY(event_id) REFERENCES events(event_id),
                 FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    conn.commit()
    conn.close()

# Регистрация пользователя
async def start_command(message: types.Message):
    user = message.from_user
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)", (user.id, user.full_name))
    conn.commit()
    conn.close()
    await message.answer(f"✅ {user.full_name}, вы зарегистрированы! Используйте /help")

# Справка по командам
async def help_command(message: types.Message):
    text = (
        "🏒 *Команды для игроков*\n"
        "/mark — отметить участие в тренировке\n\n"
        "👑 *Команды для тренера*\n"
        "/set\\_coach — назначить тренера \\(админ\\)\n"
        "/create\\_event ДД\\.ММ Тип — создать событие\n"
        "/form\\_teams — сформировать пятёрки"
    )
    await message.answer(text, parse_mode="MarkdownV2")

# Назначение тренера (только для админа группы)
async def set_coach(message: types.Message):
    # Проверяем, является ли отправитель админом группы
    chat_admins = await message.bot.get_chat_administrators(message.chat.id)
    if not any(admin.user.id == message.from_user.id for admin in chat_admins):
        await message.answer("❌ Только администраторы могут назначать тренера")
        return
    
    # Назначаем тренера
    target_user = message.reply_to_message.from_user if message.reply_to_message else None
    if not target_user:
        await message.answer("❗ Ответьте на сообщение игрока, чтобы назначить его тренером")
        return
    
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_coach = 1 WHERE user_id = ?", (target_user.id,))
    conn.commit()
    conn.close()
    
    await message.answer(f"👑 {target_user.full_name} назначен тренером!")

# Создание события (тренер)
async def create_event(message: types.Message):
    if not is_coach(message.from_user.id):
        await message.answer("❌ Только тренер может создавать события")
        return
    
    try:
        _, date, event_type = message.text.split(maxsplit=2)
    except:
        await message.answer(
            "📌 Используйте формат:\n/create_event ДД.ММ Тип\n"
            "Пример: /create_event 25.10 Тренировка"
        )
        return
    
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    
    # Создаем событие
    c.execute("INSERT INTO events (date, type) VALUES (?, ?)", (date, event_type))
    event_id = c.lastrowid
    
    # Создаем сообщение в чате
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Буду", callback_data=f"mark_{event_id}_1"),
         InlineKeyboardButton(text="❌ Не буду", callback_data=f"mark_{event_id}_0")]
    ])
    
    msg = await message.answer(
        f"🏒 {event_type} {date}\n"
        "Кто будет? Нажмите кнопку ниже:",
        reply_markup=keyboard
    )
    
    # Сохраняем ID сообщения
    c.execute("UPDATE events SET group_msg_id = ? WHERE event_id = ?", 
             (msg.message_id, event_id))
    conn.commit()
    conn.close()

# Проверка, является ли пользователь тренером
def is_coach(user_id):
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("SELECT is_coach FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] == 1 if result else False

# Отметка участия
async def mark_callback(callback: types.CallbackQuery):
    _, event_id, status = callback.data.split("_")
    event_id, status = int(event_id), int(status)
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    
    # Удаляем старую отметку
    c.execute("DELETE FROM participants WHERE event_id = ? AND user_id = ?", 
             (event_id, user_id))
    
    # Добавляем новую при подтверждении
    if status == 1:
        c.execute("INSERT INTO participants (event_id, user_id) VALUES (?, ?)", 
                 (event_id, user_id))
    
    # Получаем список участников
    c.execute('''SELECT u.name FROM participants p
                 JOIN users u ON p.user_id = u.user_id
                 WHERE p.event_id = ?''', (event_id,))
    players = [row[0] for row in c.fetchall()]
    
    # Обновляем сообщение
    status_text = "✅ Будут:\n" + "\n".join(players) if players else "Пока никто не отметил участие"
    
    try:
        await callback.message.edit_text(
            f"{callback.message.text.split('Кто будет?')[0]}"
            f"Кто будет?\n\n{status_text}",
            reply_markup=callback.message.reply_markup
        )
    except:
        pass  # Если текст не изменился
    
    await callback.answer()
    conn.commit()
    conn.close()

# Основная функция
async def main():
    init_db()
    
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    
    # Регистрация обработчиков
    dp.message.register(start_command, Command("start"))
    dp.message.register(help_command, Command("help"))
    dp.message.register(set_coach, Command("set_coach"))
    dp.message.register(create_event, Command("create_event"))
    dp.callback_query.register(mark_callback, lambda c: c.data.startswith('mark_'))
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

# Запускаем веб-сервер в отдельном потоке
import threading
def run_server():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_server, daemon=True).start()
