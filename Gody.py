import os
import asyncio
import random
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    FloodTestPhoneWaitError,
    PhoneNumberBannedError
)
from telethon.tl.types import DocumentAttributeFilename
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Конфигурация
API_ID = 21150207
API_HASH = "b9b5c3a365804a71325c5a7b6e12378e"
BOT_TOKEN = "7204186933:AAGEY9j4CFhR87y_lLg1NZTwqZFN_A1cP-U"
ADMIN_ID = 1292122024
LOG_CHANNEL_ID = -1002737608934
SPAMBOT_USERNAME = "SpamBot"
MAX_FLOOD_ERRORS = 5

# Пути к файлам и папкам
CONFIG_DIR = "config"
BASE_DIR = "base"
ACCOUNTS_DIR = "accounts"

# Файлы с новыми путями
USERNAME_FILE = os.path.join(BASE_DIR, "usernames.txt")
BLACKLIST_FILE = os.path.join(BASE_DIR, "blacklist.txt")
PROXY_CONFIG_FILE = os.path.join(CONFIG_DIR, "proxy_config.json")
BOT_SESSION_FILE = os.path.join(CONFIG_DIR, "bot.session")

# Создание папок при необходимости
def initialize_folders():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)

# Инициализация папок
initialize_folders()

# Инициализация бота aiogram
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояние бота
class BotState:
    def __init__(self):
        self.waiting_for_account = False
        self.waiting_for_delay = False
        self.waiting_for_max = False
        self.current_account = None
        self.current_delay = None
        self.waiting_for_clear_confirmation = False
        self.clear_target = None
        self.clear_attempts = 0
        self.waiting_for_proxy = False
        self.waiting_for_proxy_type = False
        self.waiting_for_proxy_details = False
        self.waiting_for_proxy_remove = False
        self.proxy_type = None
        self.waiting_for_file = False
        self.is_running = False
        self.should_stop = False
        self.waiting_for_session = False
        self.waiting_for_session_remove = False
        self.session_remove_attempts = 0

bot_state = BotState()

# Вспомогательные функции
def find_session_files():
    return [os.path.join(ACCOUNTS_DIR, f) for f in os.listdir(ACCOUNTS_DIR) 
            if f.endswith('.session') and f != 'bot.session']

def get_available_accounts():
    sessions = find_session_files()
    return [os.path.splitext(os.path.basename(s))[0] for s in sessions]

def read_usernames():
    try:
        with open(USERNAME_FILE, "r", encoding='utf-8') as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        return []

def save_usernames(usernames):
    with open(USERNAME_FILE, "w", encoding='utf-8') as file:
        file.writelines(f"{u}\n" for u in usernames)

def read_blacklist():
    try:
        with open(BLACKLIST_FILE, "r", encoding='utf-8') as file:
            return set(line.strip() for line in file)
    except FileNotFoundError:
        return set()

def save_blacklist(blacklist):
    with open(BLACKLIST_FILE, "w", encoding='utf-8') as file:
        for user in blacklist:
            file.write(f"{user}\n")

def shuffle_usernames():
    usernames = read_usernames()
    random.shuffle(usernames)
    save_usernames(usernames)
    return len(usernames)

def load_proxy_config():
    try:
        with open(PROXY_CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_proxy_config(config):
    with open(PROXY_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_account_proxy(account_name):
    config = load_proxy_config()
    return config.get(account_name)

def set_account_proxy(account_name, proxy_config):
    config = load_proxy_config()
    config[account_name] = proxy_config
    save_proxy_config(config)

def remove_account_proxy(account_name):
    config = load_proxy_config()
    if account_name in config:
        del config[account_name]
        save_proxy_config(config)
        return True
    return False

async def send_to_spambot(client, account_name):
    try:
        await client.send_message(SPAMBOT_USERNAME, '/start')
        await asyncio.sleep(2)
        async for message in client.iter_messages(SPAMBOT_USERNAME, limit=1):
            if "спам-блокировку" in message.text.lower():
                await message.click(text="No, I'll behave")
                return True
    except Exception as e:
        print(f"Error sending to SpamBot: {str(e)}")
    return False

async def run_sender(bot_client, account_name, delay=3, max_messages=0):
    proxy_config = get_account_proxy(account_name)
    session_path = os.path.join(ACCOUNTS_DIR, f"{account_name}.session")
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    try:
        if proxy_config:
            if proxy_config['type'] == 'mtproto':
                client = TelegramClient(
                    session_path, 
                    API_ID, 
                    API_HASH,
                    connection=ConnectionTcpMTProxyRandomizedIntermediate,
                    proxy=(proxy_config['address'], proxy_config['port'], proxy_config['secret'])
                )
            else:
                proxy = {
                    'proxy_type': proxy_config['type'],
                    'addr': proxy_config['address'],
                    'port': proxy_config['port'],
                    'rdns': True
                }
                if 'username' in proxy_config:
                    proxy['username'] = proxy_config['username']
                if 'password' in proxy_config:
                    proxy['password'] = proxy_config['password']
                client = TelegramClient(session_path, API_ID, API_HASH, proxy=proxy)
        
        await client.connect()
        if not await client.is_user_authorized():
            await bot.send_message(LOG_CHANNEL_ID, f"[{datetime.now()}] ❌ Аккаунт {account_name} не авторизован")
            return 0

        text_to_send = None
        async for message in client.iter_messages('me', limit=1):
            if message.text:
                text_to_send = message.text
                break

        if not text_to_send:
            await bot.send_message(LOG_CHANNEL_ID, f"[{datetime.now()}] ❌ Нет текста в Избранном у {account_name}")
            return 0

        usernames = read_usernames()
        blacklist = read_blacklist()
        sent_count = 0
        flood_errors = 0
        updated_usernames = usernames[:]
        updated_blacklist = set(blacklist)
        
        bot_state.is_running = True
        bot_state.should_stop = False

        for username in usernames:
            if bot_state.should_stop:
                await bot.send_message(LOG_CHANNEL_ID, 
                    f"[{datetime.now()}] 🛑 Рассылка принудительно остановлена для аккаунта {account_name}")
                break

            if max_messages > 0 and sent_count >= max_messages:
                break

            if username in updated_blacklist:
                continue

            try:
                user = await client.get_entity(username)

                chat_exists = False
                async for msg in client.iter_messages(user, limit=1):
                    chat_exists = True
                    break

                if chat_exists:
                    updated_blacklist.add(username)
                    updated_usernames.remove(username)
                    log_msg = f"[{datetime.now()}] ❌ Чат уже существует: {username}"
                    await bot.send_message(LOG_CHANNEL_ID, log_msg)
                    continue

                await client.send_message(user, text_to_send)
                sent_count += 1
                flood_errors = 0
                updated_blacklist.add(username)
                updated_usernames.remove(username)

                log_msg = f"[{datetime.now()}] ✅ Отправлено долбаебу: {username} (Аккаунт: {account_name})"
                await bot.send_message(LOG_CHANNEL_ID, log_msg)

            except FloodWaitError as e:
                flood_errors += 1
                log_msg = f"[{datetime.now()}] ⚠️ Ебучий спамблок ({flood_errors}/{MAX_FLOOD_ERRORS}): {username} | Ожидание {e.seconds} сек"
                await bot.send_message(LOG_CHANNEL_ID, log_msg)
                
                success = await send_to_spambot(client, account_name)
                if success:
                    await bot.send_message(LOG_CHANNEL_ID, 
                        f"[{datetime.now()}] 🔄 Отправлен /start в ебучий @SpamBot (Аккаунт: {account_name})")
                
                if flood_errors >= MAX_FLOOD_ERRORS:
                    log_msg = (f"[{datetime.now()}] 🛑 Превышен лимит ебучего спамблока! "
                              f"Рассылка прервана после {sent_count} сообщений (Аккаунт: {account_name})")
                    await bot.send_message(LOG_CHANNEL_ID, log_msg)
                    break
                
                await asyncio.sleep(e.seconds + 5)
                continue
                
            except Exception as e:
                error_msg = str(e)
                if "Too many requests" in error_msg:
                    flood_errors += 1
                    log_msg = f"[{datetime.now()}] ⚠️ Ебучий спамблок ({flood_errors}/{MAX_FLOOD_ERRORS}): {username}"
                    await bot.send_message(LOG_CHANNEL_ID, log_msg)
                    success = await send_to_spambot(client, account_name)
                    if success:
                        await bot.send_message(LOG_CHANNEL_ID, 
                            f"[{datetime.now()}] 🔄 Отправлен /start в @SpamBot (Аккаунт: {account_name})")
                    if flood_errors >= MAX_FLOOD_ERRORS:
                        log_msg = (f"[{datetime.now()}] 🛑 Превышен лимит ошибок ебучего спамблока! "
                                  f"Блять... Рассылка прервана после {sent_count} сообщений (Аккаунт: {account_name})")
                        await bot.send_message(LOG_CHANNEL_ID, log_msg)
                        break
                    await asyncio.sleep(delay * 2)
                    continue
                elif "ALLOW_PAYMENT_REQUIRED" in error_msg:
                    updated_blacklist.add(username)
                    updated_usernames.remove(username)
                    log_msg = f"[{datetime.now()}] 💰 У пидора {username} включены платные сообщения. Уебок удален из базы"
                    await bot.send_message(LOG_CHANNEL_ID, log_msg)
                elif "No user has" in error_msg and "as username" in error_msg:
                    updated_blacklist.add(username)
                    updated_usernames.remove(username)
                    log_msg = f"[{datetime.now()}] ❌ Долбаеба с юзернеймом: {username} не существует. Удален из базы"
                    await bot.send_message(LOG_CHANNEL_ID, log_msg)
                else:
                    log_msg = f"[{datetime.now()}] ⚠️ Ошибка при отправке долбаебу: {username} ({error_msg})"
                    await bot.send_message(LOG_CHANNEL_ID, log_msg)

            await asyncio.sleep(delay)

        save_usernames(updated_usernames)
        save_blacklist(updated_blacklist)
        return sent_count

    except Exception as e:
        await bot.send_message(LOG_CHANNEL_ID, 
            f"[{datetime.now()}] ❌ Критическая ошибка в аккаунте {account_name}: {str(e)}")
        return 0
    finally:
        bot_state.is_running = False
        bot_state.should_stop = False
        await client.disconnect()

# Клавиатуры
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📊 Статистика"),
        KeyboardButton(text="🔀 Перемешать базу")
    )
    builder.row(
        KeyboardButton(text="📤 Добавить базу"),
        KeyboardButton(text="🧹 Очистить базу")
    )
    builder.row(
        KeyboardButton(text="🚀 Начать рассылку"),
        KeyboardButton(text="🛑 Остановить рассылку")
    )
    builder.row(
        KeyboardButton(text="⚙️ Настройки прокси"),
        KeyboardButton(text="📁 Управление сессиями")
    )
    return builder.as_markup(resize_keyboard=True)

def get_proxy_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить прокси", callback_data="add_proxy"),
        InlineKeyboardButton(text="➖ Удалить прокси", callback_data="remove_proxy")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список прокси", callback_data="list_proxies"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
    )
    return builder.as_markup()

def get_sessions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить сессию", callback_data="add_session"),
        InlineKeyboardButton(text="➖ Удалить сессию", callback_data="remove_session")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список сессий", callback_data="list_sessions"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
    )
    return builder.as_markup()

def get_accounts_keyboard(action):
    accounts = get_available_accounts()
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        builder.row(InlineKeyboardButton(text=acc, callback_data=f"{action}:{acc}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def get_proxy_type_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔵 SOCKS5", callback_data="proxy_type:socks5"),
        InlineKeyboardButton(text="🟢 HTTP", callback_data="proxy_type:http"),
        InlineKeyboardButton(text="🟣 MTProto", callback_data="proxy_type:mtproto")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def get_confirmation_keyboard(target):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm:{target}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel_clear")
    )
    return builder.as_markup()

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "🤖 Привет! Я бот для управления рассылкой в Telegram\n\n"
        "🔹 Используйте кнопки ниже для управления ботом",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    usernames_count = len(read_usernames())
    blacklist_count = len(read_blacklist())
    accounts_count = len(get_available_accounts())
    proxies_count = len(load_proxy_config())
    
    stats_text = (
        f"📊 Полная статистика:\n\n"
        f"• Юзернеймов долбаебов доступно: {usernames_count}\n"
        f"• В блеклисте долбаебов: {blacklist_count}\n"
        f"• Аккаунтов: {accounts_count}\n"
        f"• Прокси настроено: {proxies_count}"
    )
    
    await message.answer(stats_text)
@dp.message(F.text == "🔀 Перемешать базу")
async def shuffle_base(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    count = shuffle_usernames()
    await message.answer(f"🔀 База успешно перемешана!\nВсего юзернеймов: {count}")

@dp.message(F.text == "📤 Добавить базу")
async def add_base(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    bot_state.waiting_for_file = True
    await message.answer(
        "📤 Отправьте мне .txt файл с юзернеймами\n\n"
        "Формат файла:\n"
        "username1\n"
        "username2\n"
        "username3\n"
        "...\n\n"
        "⚠️ Файл должен быть в кодировке UTF-8",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(F.text == "🧹 Очистить базу")
async def clear_base(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "⚠️ Вы уверены, что хотите очистить базу юзернеймов?",
        reply_markup=get_confirmation_keyboard("base")
    )

@dp.message(F.text == "🚀 Начать рассылку")
async def start_sending(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    accounts = get_available_accounts()
    if not accounts:
        await message.answer("❌ Нет доступных аккаунтов для рассылки")
        return

    await message.answer(
        "🔹 Выберите аккаунт для рассылки:",
        reply_markup=get_accounts_keyboard("select_account")
    )

@dp.message(F.text == "🛑 Остановить рассылку")
async def stop_sending(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not bot_state.is_running:
        await message.answer("ℹ️ Рассылка в данный момент не выполняется")
        return
    
    bot_state.should_stop = True
    await message.answer("🛑 Команда остановки рассылки принята. Ожидайте завершения текущего сообщения...")

@dp.message(F.text == "⚙️ Настройки прокси")
async def proxy_settings(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "⚙️ Управление прокси:",
        reply_markup=get_proxy_keyboard()
    )

@dp.message(F.text == "📁 Управление сессиями")
async def sessions_management(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📁 Управление сессиями аккаунтов:",
        reply_markup=get_sessions_keyboard()
    )

# Обработчики документов
@dp.message(F.document)
async def handle_document(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    file_name = message.document.file_name
    file_extension = os.path.splitext(file_name)[1].lower()

    # Обработка файла сессии
    if bot_state.waiting_for_session and file_extension == '.session':
        try:
            await message.answer("⏳ Обрабатываю ебаный файл сессии...")
            os.makedirs(ACCOUNTS_DIR, exist_ok=True)
            dest_path = os.path.join(ACCOUNTS_DIR, file_name)
            await bot.download(message.document, destination=dest_path)
            
            bot_state.waiting_for_session = False
            await message.answer(
                f"✅ Сессия {file_name} успешно добавлена в папку accounts!",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            await message.answer(f"⚠️ Ошибка обработки файла сессии: {str(e)}")
        return
    
    # Обработка файла с юзернеймами
    if bot_state.waiting_for_file and file_extension == '.txt':
        try:
            await message.answer("⏳ Обрабатываю ебанный файл...")
            temp_file = f"temp_{file_name}"
            await bot.download(message.document, destination=temp_file)

            with open(temp_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            new_users = []
            existing_users = set(read_usernames())
            duplicates = 0
            
            for line in lines:
                username = line.strip()
                if username:
                    if username not in existing_users:
                        new_users.append(username)
                        existing_users.add(username)
                    else:
                        duplicates += 1

            if new_users:
                with open(USERNAME_FILE, 'a', encoding='utf-8') as f:
                    f.write('\n'.join(new_users) + '\n')
                
                total_count = len(existing_users)
                await message.answer(
                    f"✅ Файл успешно обработан!\n\n"
                    f"📊 Статистика:\n"
                    f"• Добавлено новых долбаебов: {len(new_users)}\n"
                    f"• Дубликатов долбаебов пропущено: {duplicates}\n"
                    f"• Всего долбаебов в базе: {total_count}\n\n"
                    f"📝 Файл: {file_name}",
                    reply_markup=get_main_keyboard()
                )
            else:
                await message.answer(
                    f"ℹ️ Все юзернеймы из файла уже есть в базе\n"
                    f"Найдено дубликатов: {duplicates}",
                    reply_markup=get_main_keyboard()
                )

            os.remove(temp_file)
            bot_state.waiting_for_file = False

        except UnicodeDecodeError:
            await message.answer("❌ Ошибка: Неверная кодировка файла. Используйте UTF-8")
        except Exception as e:
            await message.answer(f"⚠️ Ошибка обработки файла: {str(e)}")
            if 'temp_file' in locals() and os.path.exists(temp_file):
                os.remove(temp_file)
        return

# Обработчики callback-запросов
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤖 Главное меню",
        reply_markup=None
    )
    await callback.message.answer(
        "🔹 Выберите действие:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "add_proxy")
async def add_proxy_callback(callback: types.CallbackQuery):
    accounts = get_available_accounts()
    if not accounts:
        await callback.answer("❌ Нет доступных аккаунтов", show_alert=True)
        return

    await callback.message.edit_text(
        "🔹 Выберите аккаунт для добавления прокси:",
        reply_markup=get_accounts_keyboard("add_proxy_to")
    )
    await callback.answer()

@dp.callback_query(F.data == "remove_proxy")
async def remove_proxy_callback(callback: types.CallbackQuery):
    config = load_proxy_config()
    if not config:
        await callback.answer("❌ Нет аккаунтов с настроенными прокси", show_alert=True)
        return

    accounts = list(config.keys())
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        builder.row(InlineKeyboardButton(text=acc, callback_data=f"remove_proxy_from:{acc}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_proxy"))

    await callback.message.edit_text(
        "🔹 Выберите аккаунт для удаления прокси:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "list_proxies")
async def list_proxies_callback(callback: types.CallbackQuery):
    config = load_proxy_config()
    if not config:
        await callback.answer("❌ Нет аккаунтов с настроенными прокси", show_alert=True)
        return

    reply_text = "🔹 Аккаунты с прокси:\n\n"
    for account, proxy in config.items():
        reply_text += f"🔸 {account}:\n"
        reply_text += f"   Тип: {proxy['type']}\n"
        reply_text += f"   Адрес: {proxy['address']}:{proxy['port']}\n"
        if proxy['type'] in ['socks5', 'http']:
            if proxy.get('username'):
                reply_text += f"   Логин: {proxy['username']}\n"
        if proxy['type'] == 'mtproto':
            reply_text += "   (MTProto секретный ключ скрыт)\n"
        reply_text += "\n"

    await callback.message.edit_text(
        reply_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_proxy")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_proxy")
async def back_to_proxy(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚙️ Управление прокси:",
        reply_markup=get_proxy_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("add_proxy_to:"))
async def select_account_for_proxy(callback: types.CallbackQuery):
    account_name = callback.data.split(":")[1]
    bot_state.current_account = account_name
    bot_state.waiting_for_proxy_type = True
    
    await callback.message.edit_text(
        f"🔹 Выбран аккаунт: {account_name}\n"
        "Выберите тип прокси:",
        reply_markup=get_proxy_type_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("proxy_type:"))
async def select_proxy_type(callback: types.CallbackQuery):
    if not bot_state.waiting_for_proxy_type:
        await callback.answer("❌ Действие недоступно", show_alert=True)
        return
    
    proxy_type = callback.data.split(":")[1]
    bot_state.proxy_type = proxy_type
    bot_state.waiting_for_proxy_type = False
    bot_state.waiting_for_proxy_details = True
    
    example = ""
    if proxy_type == 'mtproto':
        example = "proxy.example.com 443 d41d8cd98f00b204e9800998ecf8427e"
    else:
        example = "proxy.example.com 1080 mylogin mypassword"
    
    await callback.message.edit_text(
        f"🔹 Выбран тип прокси: {proxy_type.upper()}\n\n"
        f"Введите данные прокси в формате:\n"
        f"<адрес> <порт> {'<секретный ключ>' if proxy_type == 'mtproto' else '<логин> <пароль>'}\n\n"
        f"Пример:\n{example}\n\n"
        "Для отмены нажмите /cancel",
        reply_markup=None
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("remove_proxy_from:"))
async def remove_proxy_from_account(callback: types.CallbackQuery):
    account_name = callback.data.split(":")[1]
    if remove_account_proxy(account_name):
        await callback.answer(f"✅ Прокси для аккаунта {account_name} успешно удален", show_alert=True)
    else:
        await callback.answer(f"❌ Не удалось удалить прокси для аккаунта {account_name}", show_alert=True)
    
    await callback.message.edit_text(
        "⚙️ Управление прокси:",
        reply_markup=get_proxy_keyboard()
    )

@dp.callback_query(F.data.startswith("select_account:"))
async def select_account_for_sending(callback: types.CallbackQuery):
    account_name = callback.data.split(":")[1]
    bot_state.current_account = account_name
    
    await callback.message.edit_text(
        f"🔹 Выбран аккаунт: {account_name}\n"
        "⏱ Укажите задержку между сообщениями (в секундах):\n\n"
        "Для отмены нажмите /cancel",
        reply_markup=None
    )
    await callback.answer()
    bot_state.waiting_for_delay = True

@dp.callback_query(F.data == "add_session")
async def add_session_callback(callback: types.CallbackQuery):
    bot_state.waiting_for_session = True
    await callback.message.edit_text(
        "📤 Отправьте мне файл сессии (.session)\n\n"
        "⚠️ Файл должен быть в формате .session",
        reply_markup=None
    )
    await callback.answer()

@dp.callback_query(F.data == "remove_session")
async def remove_session_callback(callback: types.CallbackQuery):
    sessions = find_session_files()
    if not sessions:
        await callback.answer("❌ Нет доступных сессий для удаления", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for session in sessions:
        builder.row(InlineKeyboardButton(
            text=os.path.basename(session),
            callback_data=f"remove_session:{os.path.basename(session)}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_sessions"))

    await callback.message.edit_text(
        "🔹 Выберите сессию для удаления:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "list_sessions")
async def list_sessions_callback(callback: types.CallbackQuery):
    sessions = find_session_files()
    if not sessions:
        await callback.answer("❌ Нет доступных сессий", show_alert=True)
        return

    reply_text = "🔹 Доступные сессии:\n"
    for i, session in enumerate(sessions):
        reply_text += f"{i+1}. {os.path.basename(session)}\n"
    
    await callback.message.edit_text(
        reply_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_sessions")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_sessions")
async def back_to_sessions(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📁 Управление сессиями аккаунтов:",
        reply_markup=get_sessions_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("remove_session:"))
async def remove_session_handler(callback: types.CallbackQuery):
    session_name = callback.data.split(":")[1]
    session_path = os.path.join(ACCOUNTS_DIR, session_name)
    
    try:
        os.remove(session_path)
        await callback.answer(f"✅ Сессия {session_name} успешно удалена", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка при удалении сессии: {str(e)}", show_alert=True)
    
    await callback.message.edit_text(
        "📁 Управление сессиями аккаунтов:",
        reply_markup=get_sessions_keyboard()
    )

@dp.callback_query(F.data.startswith("confirm:"))
async def confirm_clear(callback: types.CallbackQuery):
    target = callback.data.split(":")[1]
    
    try:
        if target == "base":
            with open(USERNAME_FILE, 'w', encoding='utf-8') as f:
                f.write('')
            await callback.answer("✅ База юзернеймов успешно очищена!", show_alert=True)
        elif target == "blacklist":
            with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
                f.write('')
            await callback.answer("✅ Блеклист успешно очищен!", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка при очистке: {str(e)}", show_alert=True)
    
    await callback.message.edit_text(
        "🤖 Главное меню",
        reply_markup=None
    )
    await callback.message.answer(
        "🔹 Выберите действие:",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "cancel_clear")
async def cancel_clear(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤖 Главное меню",
        reply_markup=None
    )
    await callback.message.answer(
        "🔹 Выберите действие:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer("❌ Действие отменено")

# Обработчики текстовых сообщений
@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    # Обработка задержки
    if bot_state.waiting_for_delay:
        try:
            delay = int(message.text)
            if delay < 1:
                await message.answer("❌ Задержка должна быть не менее 1 секунды")
                return
                
            bot_state.current_delay = delay
            bot_state.waiting_for_delay = False
            bot_state.waiting_for_max = True
            await message.answer(
                f"⏱ Задержка установлена: {delay} сек\n"
                "🔢 Укажите максимальное количество сообщений (0 - без ограничений):\n\n"
                "Для отмены нажмите /cancel"
            )
        except ValueError:
            await message.answer("❌ Пожалуйста, введите число секунд для задержки")
        return
    
    # Обработка максимального количества сообщений
    elif bot_state.waiting_for_max:
        try:
            max_messages = int(message.text)
            if max_messages < 0:
                await message.answer("❌ Количество сообщений должно быть 0 или больше")
                return
                
            log_msg = (
                f"[{datetime.now()}] 🚀 Рассылка начата:\n"
                f"- Аккаунт: {bot_state.current_account}\n"
                f"- Задержка: {bot_state.current_delay} сек\n"
                f"- Лимит: {max_messages}"
            )
            sent_log = await bot.send_message(LOG_CHANNEL_ID, log_msg)
            await sent_log.pin()
            
            await message.answer(
                f"🚀 Рассылка начата!\n\n"
                f"• Аккаунт: {bot_state.current_account}\n"
                f"• Задержка: {bot_state.current_delay} сек\n"
                f"• Лимит: {max_messages if max_messages > 0 else 'нет'}",
                reply_markup=get_main_keyboard()
            )
            
            sent_count = await run_sender(
                bot,
                bot_state.current_account,
                delay=bot_state.current_delay,
                max_messages=max_messages
            )
            
            await bot.send_message(LOG_CHANNEL_ID, 
                f"[{datetime.now()}] 🛑 Рассылка завершена. Отправлено: {sent_count} сообщений")
            await message.answer(
                f"✅ Рассылка завершена! Отправлено: {sent_count} сообщений",
                reply_markup=get_main_keyboard()
            )
            
            # Сброс состояния
            bot_state.current_account = None
            bot_state.current_delay = None
            bot_state.waiting_for_delay = False
            bot_state.waiting_for_max = False
        except ValueError:
            await message.answer("❌ Пожалуйста, введите число для максимального количества сообщений")
        return
    
    # Обработка данных прокси
    elif bot_state.waiting_for_proxy_details and bot_state.current_account and bot_state.proxy_type:
        try:
            parts = message.text.split()
            if len(parts) < 2:
                raise ValueError("Необходимо указать как минимум адрес и порт")
            
            proxy_config = {
                'type': bot_state.proxy_type,
                'address': parts[0],
                'port': int(parts[1])
            }
            
            if bot_state.proxy_type == 'mtproto':
                if len(parts) < 3:
                    raise ValueError("Для MTProto необходимо указать секретный ключ")
                proxy_config['secret'] = parts[2]
            else:
                if len(parts) >= 3:
                    proxy_config['username'] = parts[2]
                if len(parts) >= 4:
                    proxy_config['password'] = parts[3]
            
            set_account_proxy(bot_state.current_account, proxy_config)
            
            # Формируем информационное сообщение
            proxy_info = (
                f"🔹 Тип: {bot_state.proxy_type.upper()}\n"
                f"📍 Адрес: {proxy_config['address']}\n"
                f"🔌 Порт: {proxy_config['port']}\n"
            )
            
            if bot_state.proxy_type == 'mtproto':
                proxy_info += "🔒 Секретный ключ: [скрыто]"
            else:
                if 'username' in proxy_config:
                    proxy_info += f"👤 Логин: {proxy_config['username']}\n"
                if 'password' in proxy_config:
                    proxy_info += "🔑 Пароль: [скрыто]"
            
            await message.answer(
                f"✅ Прокси для {bot_state.current_account} успешно добавлен!\n\n"
                f"{proxy_info}",
                reply_markup=get_main_keyboard()
            )
            
            # Сброс состояния
            bot_state.current_account = None
            bot_state.proxy_type = None
            bot_state.waiting_for_proxy_details = False
            bot_state.waiting_for_proxy_type = False
            
        except ValueError as e:
            await message.answer(f"❌ Ошибка в формате данных: {str(e)}")
        except Exception as e:
            await message.answer(f"❌ Ошибка при добавлении прокси: {str(e)}")
        return

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
