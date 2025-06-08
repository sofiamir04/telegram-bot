import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from telegram import (
    Update, InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

DATA_FILE = "data.json"
TASKS_FILE = "tasks.json"

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

if not os.path.exists(TASKS_FILE):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    if user_id not in data:
        data[user_id] = {"balance": 0, "withdraws": 0}
        save_data(data)
    buttons = [
        [KeyboardButton("📋 Доступные задания")],
        [KeyboardButton("💰 Мой баланс")],
        [KeyboardButton("💸 Запрос на вывод")],
        [KeyboardButton("📞 Поддержка/связь с разработчиком")],
    ]
    if update.effective_user.id == ADMIN_ID:

        buttons.append([KeyboardButton("➕ Добавить задание")])

    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Это платформа для выполнения заданий онлайн.",
        reply_markup=keyboard
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📋 Доступные задания":
        await show_tasks(update, context)
    elif text == "💰 Мой баланс":
        await show_balance(update, context)
    elif text == "💸 Запрос на вывод":
        await request_withdraw(update, context)
    elif text == "📞 Поддержка/связь с разработчиком":
        await contact_support(update, context)
    elif text == "➕ Добавить задание" and update.effective_user.id == ADMIN_ID:
        await start_add_task(update, context)

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    tasks = load_tasks()
    keyboard = []
    for task_id, task in tasks.items():
        if user_id not in task.get("completed_by", []) and user_id not in task.get("taken_by", []):
            keyboard.append([InlineKeyboardButton(task["title"], callback_data=f"take_{task_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
    await update.message.reply_text(
        "Выберите задание:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    balance = data.get(user_id, {}).get("balance", 0)
    await update.message.reply_text(f"Ваш текущий баланс: {balance} ₸")

async def request_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user_data = data.get(user_id, {})
    balance = user_data.get("balance", 0)
    withdraws = user_data.get("withdraws", 0)

    if (withdraws == 0 and balance < 1000) or (withdraws > 0 and balance < 5000):
        await update.message.reply_text("Недостаточно средств для вывода.")
        return

    await update.message.reply_text("Введите сумму вывода в тенге:")
    context.user_data["awaiting_withdraw_amount"] = True

async def contact_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Для связи с поддержкой напишите @Sofia010821")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "add_task" in context.user_data:
        step = context.user_data["add_task"]["step"]
        if step == "title":
            await ask_task_instruction(update, context)
        elif step == "instruction":
            await ask_task_limit(update, context)
        elif step == "limit":
            await save_new_task(update, context)
        return

    user_id = str(update.effective_user.id)
    data = load_data()

    if context.user_data.get("awaiting_withdraw_amount"):
        try:
            amount = int(update.message.text.strip())
            balance = data[user_id]["balance"]
            withdraws = data[user_id]["withdraws"]

            if (withdraws == 0 and amount < 1000) or (withdraws > 0 and amount < 5000):
                await update.message.reply_text("Минимальная сумма вывода: 1000/5000 тг в зависимости от истории.")
                return

            if amount > balance:
                await update.message.reply_text("У вас недостаточно средств.")
                return

            data[user_id]["balance"] -= amount
            data[user_id]["withdraws"] += 1
            save_data(data)

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"""✉ Запрос на вывод
Пользователь: {user_id}
Баланс: {balance} тг
Сумма вывода: {amount} тг"""
            )
            await update.message.reply_text("Запрос отправлен. Ожидайте подтверждения.")
        except:
            await update.message.reply_text("Ошибка. Введите сумму числом.")
        finally:
            context.user_data["awaiting_withdraw_amount"] = False

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    tasks = load_tasks()

    if query.data == "back":
        await start(update, context)
        return

    if query.data.startswith("take_"):
        task_id = query.data.split("_")[1]
        task = tasks.get(task_id)
        if not task:
            await query.edit_message_text("Задание не найдено.")
            return

        if user_id in task.get("taken_by", []):
            await query.edit_message_text("Вы уже начали это задание.")
            return

        if "limit" in task and len(task.get("taken_by", [])) >= task["limit"]:
            await query.edit_message_text("Лимит по этому заданию исчерпан.")
            return

        task.setdefault("taken_by", []).append(user_id)
        save_tasks(tasks)

        await context.bot.send_message(
            chat_id=user_id,
            text = f"Вы выбрали задание: {task['title']}\nИнструкция: {task['instruction']}\nОтправьте текст или скриншот как отчет."
        )
        context.user_data["current_task"] = task_id

async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if "current_task" not in context.user_data:
        return
    task_id = context.user_data["current_task"]
    tasks = load_tasks()
    task = tasks.get(task_id)
    if not task:
        return

    content = update.message.text or "Без текста"
    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id

    msg = (
    f"✏ Новый отчет от пользователя {user_id}\n"
    f"Задание: {task['title']}\n"
    f"Комментарий: {content}"
)
    await context.bot.send_message(chat_id=REVIEW_CHAT_ID, text=msg)
    if file_id:
        await context.bot.send_photo(chat_id=REVIEW_CHAT_ID, photo=file_id)

    task.setdefault("completed_by", []).append(user_id)
    task["taken_by"].remove(user_id)
    save_tasks(tasks)

    context.user_data.pop("current_task")
    await update.message.reply_text("Ваш отчет отправлен на проверку. Ожидайте.")

async def start_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите заголовок задания:")
    context.user_data["add_task"] = {"step": "title"}

async def ask_task_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["add_task"]["title"] = update.message.text.strip()
    context.user_data["add_task"]["step"] = "instruction"
    await update.message.reply_text("Теперь введите инструкцию к заданию:")

async def ask_task_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["add_task"]["instruction"] = update.message.text.strip()
    context.user_data["add_task"]["step"] = "limit"
    await update.message.reply_text("Введите лимит пользователей (например, 5). Введите 0 для безлимитного задания:")

async def save_new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        limit = int(update.message.text.strip())
    except:
        await update.message.reply_text("Введите число.")
        return

    task_data = context.user_data["add_task"]
    task_data["limit"] = limit

    tasks = load_tasks()
    task_id = str(uuid4())[:8]
    tasks[task_id] = {
        "title": task_data["title"],
        "instruction": task_data["instruction"],
        "limit": limit if limit > 0 else None,
        "taken_by": [],
        "completed_by": []
    }
    save_tasks(tasks)

    await сupdate.message.reply_text("✅ Задание добавлено!")
    context.user_data.pop("add_task", None)
PORT = int(os.environ.get("PORT", 8000))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_http_server():
    server = HTTPServer(('', PORT), Handler)
    print(f"HTTP server running on port {PORT}")
    server.serve_forever()

# Запускаем HTTP-сервер в отдельном потоке, чтобы он не мешал боту
threading.Thread(target=run_http_server, daemon=True).start()
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, report_handler))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    print("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
