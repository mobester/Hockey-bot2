import os
import sqlite3
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from flask import Flask
import asyncio

# Загружаем переменные окружения
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

# Создаем Flask приложение для Railway
app = Flask(__name__)

@app.route('/')
def home():
    return "Хоккейный бот работает!"

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

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
    c.execute('''CREATE TABLE IF NOT EXISTS teams
                 (team_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER,
                  color TEXT,
                  players TEXT)''')
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

# Показываем главное меню
async def show_main_menu(message: types.Message):
    user_id = message.from_user.id
    is_coach_user = is_coach(user_id)
    
    # Создаем клавиатуру
    keyboard = [
        [KeyboardButton(text="📅 Просмотреть события")],
        [KeyboardButton(text="✅ Отметиться на событии")]
    ]
    
    # Кнопки для тренера
    if is_coach_user:
        keyboard.append([KeyboardButton(text="👑 Тренерское меню")])
    
    # Кнопка помощи
    keyboard.append([KeyboardButton(text="ℹ️ Помощь")])
    
    reply_markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    await message.answer("🏒 Добро пожаловать в бот хоккейной команды!", reply_markup=reply_markup)

# Стартовая команда
async def start_command(message: types.Message):
    user = message.from_user
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)", (user.id, user.full_name))
    conn.commit()
    conn.close()
    
    await show_main_menu(message)

# Показываем список событий
async def show_events(message: types.Message):
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("SELECT event_id, date, type FROM events WHERE status = 'open' ORDER BY date DESC")
    events = c.fetchall()
    conn.close()
    
    if not events:
        await message.answer("📭 Нет активных событий")
        return
    
    text = "🏒 Активные события:\n\n"
    for event in events:
        text += f"• {event[2]} {event[1]} (ID: {event[0]})\n"
    
    await message.answer(text)

# Показываем события для отметки
async def show_events_to_mark(message: types.Message):
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("SELECT event_id, date, type FROM events WHERE status = 'open' ORDER BY date DESC")
    events = c.fetchall()
    conn.close()
    
    if not events:
        await message.answer("📭 Нет активных событий для отметки")
        return
    
    # Создаем inline-клавиатуру с событиями
    keyboard = []
    for event in events:
        keyboard.append([InlineKeyboardButton(
            text=f"{event[2]} {event[1]}", 
            callback_data=f"select_event_{event[0]}"
        )])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer("Выберите событие для отметки:", reply_markup=reply_markup)

# Показываем тренерское меню
async def show_coach_menu(message: types.Message):
    keyboard = [
        [InlineKeyboardButton(text="➕ Создать событие", callback_data="create_event")],
        [InlineKeyboardButton(text="👥 Сформировать пятёрки", callback_data="form_teams")],
        [InlineKeyboardButton(text="👑 Назначить тренера", callback_data="set_coach")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer("👑 Тренерское меню:", reply_markup=reply_markup)

# Показываем справку
async def show_help(message: types.Message):
    text = (
        "ℹ️ <b>Как пользоваться ботом</b>\n\n"
        "🏒 <b>Для игроков</b>\n"
        "• Нажмите 'Просмотреть события' чтобы увидеть список\n"
        "• Нажмите 'Отметиться на событии' чтобы выбрать событие и отметить участие\n\n"
        "👑 <b>Для тренера</b>\n"
        "• В тренерском меню можно создать событие, сформировать пятёрки или назначить тренера\n\n"
        "Бот автоматически определяет ваши права на основе назначения тренера"
    )
    await message.answer(text, parse_mode="HTML")

# Создание события (через UI)
async def create_event_start(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📅 Введите дату события (в формате ДД.ММ):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_coach_menu")]
        ])
    )
    # Здесь можно добавить сохранение состояния для ConversationHandler

# Отметка участия в событии
async def select_event(callback: types.CallbackQuery):
    _, event_id = callback.data.split("_")
    event_id = int(event_id)
    
    # Создаем клавиатуру с кнопками отметки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Буду", callback_data=f"mark_{event_id}_1"),
            InlineKeyboardButton(text="❌ Не буду", callback_data=f"mark_{event_id}_0")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_events")]
    ])
    
    await callback.message.edit_text(
        "Подтвердите ваше участие:",
        reply_markup=keyboard
    )

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
            f"Подтвердите ваше участие:\n\n{status_text}",
            reply_markup=callback.message.reply_markup
        )
    except:
        pass  # Если текст не изменился
    
    await callback.answer()
    conn.commit()
    conn.close()

# Обработка нажатий на inline-кнопки
async def handle_callback(callback: types.CallbackQuery):
    data = callback.data
    
    if data.startswith("select_event_"):
        await select_event(callback)
    
    elif data.startswith("mark_"):
        await mark_callback(callback)
    
    elif data == "create_event":
        await create_event_start(callback)
    
    elif data == "back_to_coach_menu":
        await show_coach_menu(callback.message)
    
    elif data == "back_to_events":
        await show_events_to_mark(callback.message)
    
    elif data == "set_coach":
        await set_coach_start(callback)
    
    elif data.startswith("select_coach_"):
        await select_coach(callback)

# Начало процесса назначения тренера
async def set_coach_start(callback: types.CallbackQuery):
    # Получаем список всех пользователей
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("SELECT user_id, name FROM users")
    users = c.fetchall()
    conn.close()
    
    # Создаем клавиатуру с пользователями
    keyboard = []
    for user in users:
        keyboard.append([InlineKeyboardButton(
            text=user[1], 
            callback_data=f"select_coach_{user[0]}"
        )])
    
    keyboard.append([InlineKeyboardButton(
        text="🔙 Назад", 
        callback_data="back_to_coach_menu"
    )])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(
        "Выберите пользователя для назначения тренером:",
        reply_markup=reply_markup
    )

# Выбор пользователя для назначения тренера
async def select_coach(callback: types.CallbackQuery):
    _, user_id = callback.data.split("_")
    user_id = int(user_id)
    
    # Проверяем, является ли отправитель админом группы
    chat_admins = await callback.bot.get_chat_administrators(callback.message.chat.id)
    if not any(admin.user.id == callback.from_user.id for admin in chat_admins):
        await callback.message.edit_text(
            "❌ Только администраторы могут назначать тренера",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="set_coach")]
            ])
        )
        await callback.answer()
        return
    
    # Назначаем тренера
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_coach = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    
    # Получаем имя пользователя
    c.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
    user_name = c.fetchone()[0]
    conn.close()
    
    await callback.message.edit_text(
        f"👑 {user_name} назначен тренером!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_coach_menu")]
        ])
    )
    await callback.answer()

# Обработка нажатий на кнопки главного меню
async def handle_main_menu(message: types.Message):
    text = message.text
    
    if text == "📅 Просмотреть события":
        await show_events(message)
    
    elif text == "✅ Отметиться на событии":
        await show_events_to_mark(message)
    
    elif text == "👑 Тренерское меню":
        if is_coach(message.from_user.id):
            await show_coach_menu(message)
        else:
            await message.answer("❌ У вас нет прав тренера")
    
    elif text == "ℹ️ Помощь":
        await show_help(message)

# Основная функция
async def main():
    init_db()
    
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    
    # Регистрация обработчиков
    dp.message.register(start_command, Command("start"))
    dp.message.register(handle_main_menu, lambda m: m.text in ["📅 Просмотреть события", "✅ Отметиться на событии", "👑 Тренерское меню", "ℹ️ Помощь"])
    dp.callback_query.register(handle_callback)
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Запускаем бота
    asyncio.run(main())
