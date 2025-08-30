import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

# Загружаем переменные окружения
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
    c.execute('''CREATE TABLE IF NOT EXISTS teams
                 (team_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER,
                  color TEXT,
                  players TEXT)''')
    conn.commit()
    conn.close()

# Показываем главное меню
async def show_main_menu(message: types.Message):
    # Убедимся, что база данных инициализирована
    init_db()
    
    user_id = message.from_user.id
    
    # Безопасно проверяем статус тренера
    try:
        is_coach_user = is_coach(user_id)
    except Exception as e:
        # Логируем ошибку в консоль (для администратора)
        print(f"ERROR checking coach status for user {user_id}: {str(e)}")
        # Для пользователя показываем понятное сообщение
        await message.answer("⚠️ Ошибка проверки прав. Попробуйте позже.")
        is_coach_user = False
    
    # Теперь переменная точно существует
    await message.answer(f"DEBUG: Ваш user_id: {user_id}, is_coach: {is_coach_user}")
    
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
    
    # ОБРАБОТКА НОВОЙ КНОПКИ
    elif text == "👑 Назначить первого тренера":
        # Проверяем права администратора
        chat_admins = await message.bot.get_chat_administrators(message.chat.id)
        if not any(admin.user.id == message.from_user.id for admin in chat_admins):
            await message.answer("❌ Только администраторы могут назначать тренера")
            return
        
        await message.answer(
            "❗ Чтобы назначить тренера, ответьте на сообщение игрока командой /set_coach\n\n"
            "Пример:\n"
            "1. Ответьте на сообщение игрока\n"
            "2. Напишите: /set_coach"
        )
    
    elif text == "ℹ️ Помощь":
        await show_help(message)

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
    
    text = "🏒 <b>Активные события:</b>\n\n"
    for event in events:
        text += f"• <b>{event[2]}</b> {event[1]} (ID: {event[0]})\n"
    
    await message.answer(text, parse_mode="HTML")

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
    await message.answer("👑 <b>Тренерское меню:</b>", reply_markup=reply_markup, parse_mode="HTML")

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
    status_text = "✅ <b>Будут:</b>\n" + "\n".join(players) if players else "Пока никто не отметил участие"
    
    try:
        await callback.message.edit_text(
            f"Подтвердите ваше участие:\n\n{status_text}",
            reply_markup=callback.message.reply_markup,
            parse_mode="HTML"
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
        f"👑 <b>{user_name}</b> назначен тренером!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_coach_menu")]
        ]),
        parse_mode="HTML"
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
        f"🏒 <b>{event_type} {date}</b>\n"
        "Кто будет? Нажмите кнопку ниже:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    
    # Сохраняем ID сообщения
    c.execute("UPDATE events SET group_msg_id = ? WHERE event_id = ?", 
             (msg.message_id, event_id))
    conn.commit()
    conn.close()

# Формирование пятёрок (тренер)
async def form_teams_start(message: types.Message):
    if not is_coach(message.from_user.id):
        await message.answer("❌ Только тренер может формировать команды")
        return
    
    conn = sqlite3.connect('hockey.db')
    c = conn.cursor()
    c.execute("SELECT event_id, date, type FROM events WHERE status = 'open' ORDER BY event_id DESC LIMIT 1")
    event = c.fetchone()
    
    if not event:
        await message.answer("❗ Нет активных событий для формирования команд")
        return
    
    # Получаем список участников
    c.execute('''SELECT u.user_id, u.name FROM participants p
                 JOIN users u ON p.user_id = u.user_id
                 WHERE p.event_id = ?''', (event[0],))
    players = c.fetchall()
    
    if len(players) < 5:
        await message.answer(f"❗ Недостаточно игроков! Есть {len(players)}, нужно минимум 5")
        return
    
    # Распределяем игроков на одну пятёрку (упрощенная версия)
    import random
    random.shuffle(players)
    team = [p[1] for p in players[:5]]
    
    # Сохраняем в БД
    c.execute("INSERT INTO teams (event_id, color, players) VALUES (?, ?, ?)",
             (event[0], "Красная", ",".join(team)))
    conn.commit()
    conn.close()
    
    # Отправляем результат
    result = "🏒 <b>Сформирована пятёрка:</b>\n\n"
    result += "• <b>Красная:</b>\n" + "\n".join(f"  {i+1}. {p}" for i, p in enumerate(team))
    
    await message.answer(result, parse_mode="HTML")

# Создание события через UI
async def create_event_start(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📅 Введите дату события (в формате ДД.ММ):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_coach_menu")]
        ])
    )

# Основная функция
async def main():
    init_db()
    
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    
    # Регистрация обработчиков
    dp.message.register(start_command, Command("start"))
    dp.message.register(handle_main_menu, lambda m: m.text in ["📅 Просмотреть события", "✅ Отметиться на событии", "👑 Тренерское меню", "ℹ️ Помощь"])
    dp.message.register(create_event, Command("create_event"))
    dp.message.register(form_teams_start, Command("form_teams"))
    dp.callback_query.register(handle_callback)
    
    # ЗАПУСК БОТА (КРИТИЧЕСКИ ВАЖНО!)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
