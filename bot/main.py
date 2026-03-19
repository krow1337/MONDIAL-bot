import asyncio
import logging
import sqlite3
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8666560798:AAERpn353BmLAucNeSLI7d4cnxBB3hdHb3M"
WALLET_ADDRESS = "UQAGonDQgytakpGpKuoT8E00yXQN7mugl2cKJzKb_0HjqXIF"
CRYPTO_TOKEN = "552832:AAPr6hpSVHxlz0oxqrlGvhgKTDivpzZjNa4"

# ========== СОЗДАЁМ BOT ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== СОЗДАЁМ CRYPTO BOT ==========
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ========== БАЗА ДАННЫХ ==========
db_path = "../database"
if not os.path.exists(db_path):
    os.makedirs(db_path)
conn = sqlite3.connect(os.path.join(db_path, "mondial.db"))
cursor = conn.cursor()

# Создаём таблицы
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    role TEXT DEFAULT 'buyer',
    positive_reviews INTEGER DEFAULT 0,
    negative_reviews INTEGER DEFAULT 0,
    total_deals INTEGER DEFAULT 0,
    total_amount REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS deals (
    deal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER,
    buyer_id INTEGER,
    item TEXT,
    quantity TEXT,
    amount REAL,
    status TEXT DEFAULT 'waiting',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ========== СОСТОЯНИЯ ==========
class DealStates(StatesGroup):
    waiting_item = State()
    waiting_buyer_id = State()

class AMLStates(StatesGroup):
    waiting_reviews = State()
    waiting_deals = State()
    waiting_amount = State()

# ========== КОМАНДА START ==========
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "no_username"
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                  (user_id, username))
    conn.commit()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Продавец", callback_data="role_seller")],
        [InlineKeyboardButton(text="🛒 Покупатель", callback_data="role_buyer")],
        [InlineKeyboardButton(text="📋 Мои сделки", callback_data="my_deals")]
    ])
    
    await message.answer(
        "👋 Добро пожаловать в MONDIAL — безопасный гарант-бот!\n\n"
        "Выберите роль:",
        reply_markup=keyboard
    )

# ========== КОМАНДА AML ==========
@dp.message(Command("AML"))
async def cmd_aml(message: types.Message):
    user_id = message.from_user.id
    
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or user[0] != "seller":
        await message.answer("❌ Эта команда доступна только продавцам!")
        return
    
    cursor.execute("""
        SELECT positive_reviews, negative_reviews, total_deals, total_amount 
        FROM users WHERE user_id = ?
    """, (user_id,))
    stats = cursor.fetchone()
    
    text = (
        f"📊 *Ваша статистика продавца*\n\n"
        f"⭐ Положительные отзывы: *{stats[0]}*\n"
        f"👎 Отрицательные отзывы: *{stats[1]}*\n"
        f"📦 Всего сделок: *{stats[2]}*\n"
        f"💰 Сумма сделок: *{stats[3]:,.0f} ₽*\n\n"
        f"⚙️ *Управление:*"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить отзывы", callback_data="aml_edit_reviews")],
        [InlineKeyboardButton(text="✏️ Изменить сделки", callback_data="aml_edit_deals")],
        [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data="aml_edit_amount")],
        [InlineKeyboardButton(text="❌ Сбросить всё", callback_data="aml_reset")]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ========== ОБРАБОТКА AML КНОПОК ==========
@dp.callback_query(lambda c: c.data.startswith("aml_"))
async def aml_buttons(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data
    
    if action == "aml_edit_reviews":
        await callback.message.edit_text(
            "✏️ Введите новые значения в формате:\n"
            "`положительные | отрицательные`\n\n"
            "Пример: `15 | 3`"
        )
        await state.set_state(AMLStates.waiting_reviews)
    
    elif action == "aml_edit_deals":
        await callback.message.edit_text(
            "✏️ Введите новое количество завершённых сделок:"
        )
        await state.set_state(AMLStates.waiting_deals)
    
    elif action == "aml_edit_amount":
        await callback.message.edit_text(
            "✏️ Введите новую общую сумму в рублях:"
        )
        await state.set_state(AMLStates.waiting_amount)
    
    elif action == "aml_reset":
        user_id = callback.from_user.id
        cursor.execute("""
            UPDATE users 
            SET positive_reviews = 0, negative_reviews = 0, 
                total_deals = 0, total_amount = 0 
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        await callback.message.edit_text("✅ Статистика сброшена!")
        await cmd_aml(callback.message)

# ========== ОБРАБОТКА ВВОДА ДЛЯ AML ==========
@dp.message(AMLStates.waiting_reviews)
async def process_reviews(message: types.Message, state: FSMContext):
    try:
        pos, neg = map(int, message.text.split("|"))
        user_id = message.from_user.id
        cursor.execute("""
            UPDATE users 
            SET positive_reviews = ?, negative_reviews = ? 
            WHERE user_id = ?
        """, (pos, neg, user_id))
        conn.commit()
        await message.answer("✅ Отзывы обновлены!")
        await state.clear()
        await cmd_aml(message)
    except:
        await message.answer("❌ Неверный формат. Используйте: `15 | 3`")

@dp.message(AMLStates.waiting_deals)
async def process_deals(message: types.Message, state: FSMContext):
    try:
        deals = int(message.text)
        user_id = message.from_user.id
        cursor.execute("UPDATE users SET total_deals = ? WHERE user_id = ?", 
                      (deals, user_id))
        conn.commit()
        await message.answer("✅ Количество сделок обновлено!")
        await state.clear()
        await cmd_aml(message)
    except:
        await message.answer("❌ Введите число!")

@dp.message(AMLStates.waiting_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", ""))
        user_id = message.from_user.id
        cursor.execute("UPDATE users SET total_amount = ? WHERE user_id = ?", 
                      (amount, user_id))
        conn.commit()
        await message.answer("✅ Сумма обновлена!")
        await state.clear()
        await cmd_aml(message)
    except:
        await message.answer("❌ Введите число!")

# ========== ВЫБОР РОЛИ ==========
@dp.callback_query(lambda c: c.data.startswith("role_"))
async def process_role(callback: types.CallbackQuery):
    role = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
    conn.commit()
    
    if role == "seller":
        text = "✅ Вы выбрали роль: 👤 Продавец"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Создать сделку", callback_data="create_deal")],
            [InlineKeyboardButton(text="📋 Мои сделки", callback_data="my_deals")],
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="go_to_aml")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    else:
        text = f"✅ Вы выбрали роль: 🛒 Покупатель\n\n🆔 Ваш Telegram ID: `{user_id}`\nПередайте его продавцу для создания сделки."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

# ========== ВОЗВРАТ В ГЛАВНОЕ МЕНЮ ==========
@dp.callback_query(lambda c: c.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Продавец", callback_data="role_seller")],
        [InlineKeyboardButton(text="🛒 Покупатель", callback_data="role_buyer")],
        [InlineKeyboardButton(text="📋 Мои сделки", callback_data="my_deals")]
    ])
    
    await callback.message.edit_text(
        "👋 Добро пожаловать в MONDIAL — безопасный гарант-бот!\n\n"
        "Выберите роль:",
        reply_markup=keyboard
    )

# ========== МОИ СДЕЛКИ ==========
@dp.callback_query(lambda c: c.data == "my_deals")
async def my_deals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cursor.execute("SELECT deal_id, item, amount, status FROM deals WHERE seller_id = ? OR buyer_id = ?", (user_id, user_id))
    deals = cursor.fetchall()
    
    if not deals:
        await callback.message.answer("📭 У вас пока нет сделок.")
        return
    
    text = "📋 *Ваши сделки:*\n\n"
    for deal in deals:
        status_text = {
            "waiting": "⏳ Ожидает",
            "active": "✅ Активна",
            "paid": "💰 Оплачено",
            "completed": "✔️ Завершена",
            "cancelled": "❌ Отменена"
        }.get(deal[3], deal[3])
        
        text += f"🔹 #{deal[0]} — {deal[1]} — {deal[2]:,.0f} ₽ — {status_text}\n"
    
    await callback.message.answer(text, parse_mode="Markdown")

# ========== ПЕРЕХОД К AML ==========
@dp.callback_query(lambda c: c.data == "go_to_aml")
async def go_to_aml(callback: types.CallbackQuery):
    await cmd_aml(callback.message)

# ========== СОЗДАНИЕ СДЕЛКИ ==========
@dp.callback_query(lambda c: c.data == "create_deal")
async def create_deal_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📦 Введите данные сделки в формате:\n"
        "`Название  Количество  Цена в рублях`\n\n"
        "Пример: `iPhone 13  1 шт  60000`"
    )
    await state.set_state(DealStates.waiting_item)

@dp.message(DealStates.waiting_item)
async def process_deal_item(message: types.Message, state: FSMContext):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) != 3:
            raise ValueError
        await state.update_data(item=parts[0], quantity=parts[1], amount=float(parts[2]))
        await message.answer("🆔 Введите Telegram ID покупателя:")
        await state.set_state(DealStates.waiting_buyer_id)
    except:
        await message.answer("❌ Неверный формат. Используйте: `Товар | Количество | Цена`")

@dp.message(DealStates.waiting_buyer_id)
async def process_buyer_id(message: types.Message, state: FSMContext):
    try:
        buyer_id = int(message.text)
        data = await state.get_data()
        
        cursor.execute("""
            INSERT INTO deals (seller_id, buyer_id, item, quantity, amount, status)
            VALUES (?, ?, ?, ?, ?, 'waiting')
        """, (message.from_user.id, buyer_id, data['item'], data['quantity'], data['amount']))
        conn.commit()
        deal_id = cursor.lastrowid
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{deal_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{deal_id}")]
        ])
        
        # Получаем статистику продавца
        cursor.execute("""
            SELECT positive_reviews, negative_reviews, total_deals, total_amount 
            FROM users WHERE user_id = ?
        """, (message.from_user.id,))
        seller_stats = cursor.fetchone()
        
        # Отправляем запрос покупателю со статистикой продавца
        await bot.send_message(
            buyer_id,
            f"🔔 *Продавец @{message.from_user.username} предлагает сделку:*\n\n"
            f"📦 Товар: {data['item']}\n"
            f"🔢 Количество: {data['quantity']}\n"
            f"💰 Сумма: {data['amount']:,.0f} ₽\n\n"
            f"📊 *Статистика продавца:*\n"
            f"⭐ Положительные отзывы: {seller_stats[0]}\n"
            f"👎 Отрицательные отзывы: {seller_stats[1]}\n"
            f"📦 Всего сделок: {seller_stats[2]}\n"
            f"💰 Сумма сделок: {seller_stats[3]:,.0f} ₽",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await message.answer("✅ Запрос отправлен покупателю!")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# ========== ПРИНЯТИЕ СДЕЛКИ ==========
@dp.callback_query(lambda c: c.data.startswith("accept_"))
async def accept_deal(callback: types.CallbackQuery):
    deal_id = int(callback.data.split("_")[1])
    
    cursor.execute("SELECT seller_id, item, amount FROM deals WHERE deal_id = ?", (deal_id,))
    deal = cursor.fetchone()
    
    cursor.execute("UPDATE deals SET status = 'active' WHERE deal_id = ?", (deal_id,))
    conn.commit()
    
    await callback.message.edit_text("✅ Сделка подтверждена!")
    
    # Кнопки выбора способа оплаты
    choice_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Crypto Bot", callback_data=f"pay_crypto_{deal_id}")],
        [InlineKeyboardButton(text="💸 Прямой перевод", callback_data=f"pay_manual_{deal_id}")],
        [InlineKeyboardButton(text="❌ Отменить сделку", callback_data=f"cancel_{deal_id}")]
    ])
    
    await callback.message.answer(
        f"💳 *Выберите способ оплаты для сделки #{deal_id}*\n\n"
        f"💰 Сумма: *{deal[2]} USDT*\n"
        f"📦 Товар: {deal[1]}\n\n"
        f"• Crypto Bot — автоматическая проверка\n"
        f"• Прямой перевод — на кошелёк гаранта",
        reply_markup=choice_keyboard,
        parse_mode="Markdown"
    )
    
    # Получаем статистику покупателя
    cursor.execute("""
        SELECT positive_reviews, negative_reviews, total_deals, total_amount 
        FROM users WHERE user_id = ?
    """, (callback.from_user.id,))
    buyer_stats = cursor.fetchone()
    
    # Отправляем продавцу уведомление со статистикой покупателя
    await bot.send_message(
        deal[0],
        f"✅ *Покупатель принял сделку #{deal_id}!*\n\n"
        f"📊 *Статистика покупателя:*\n"
        f"⭐ Положительные отзывы: {buyer_stats[0]}\n"
        f"👎 Отрицательные отзывы: {buyer_stats[1]}\n"
        f"📦 Всего сделок: {buyer_stats[2]}\n"
        f"💰 Сумма сделок: {buyer_stats[3]:,.0f} ₽\n\n"
        f"📌 Выберите способ оплаты.",
        parse_mode="Markdown"
    )

# ========== ВЫБОР CRYPTO BOT ==========
@dp.callback_query(lambda c: c.data.startswith("pay_crypto_"))
async def pay_crypto(callback: types.CallbackQuery):
    deal_id = int(callback.data.split("_")[2])
    
    cursor.execute("SELECT seller_id, item, amount FROM deals WHERE deal_id = ?", (deal_id,))
    deal = cursor.fetchone()
    
    try:
        # Создаём счёт в Crypto Bot
        invoice = await cp.create_invoice(
            amount=deal[2],
            asset="USDT",
            description=f"Оплата сделки #{deal_id}",
            payload=str(deal_id)
        )
        
        # Кнопки для оплаты
        payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить через Crypto Bot", url=invoice.pay_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment_{deal_id}")],
            [InlineKeyboardButton(text="❌ Отменить сделку", callback_data=f"cancel_{deal_id}")]
        ])
        
        await callback.message.edit_text(
            f"💳 *Оплата через Crypto Bot*\n\n"
            f"💰 Сумма: *{deal[2]} USDT*\n"
            f"📦 Товар: {deal[1]}\n\n"
            f"🔗 Нажмите кнопку ниже для оплаты",
            reply_markup=payment_keyboard,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

# ========== ПРОВЕРКА ОПЛАТЫ CRYPTO BOT ==========
@dp.callback_query(lambda c: c.data.startswith("check_payment_"))
async def check_payment(callback: types.CallbackQuery):
    deal_id = int(callback.data.split("_")[2])
    
    try:
        # Получаем счета по номеру сделки
        invoices = await cp.get_invoices(payload=str(deal_id))
        
        if not invoices:
            await callback.answer("❌ Счёт не найден", show_alert=True)
            return
        
        invoice = invoices[0]
        
        if invoice.status == "paid":
            cursor.execute("UPDATE deals SET status = 'paid' WHERE deal_id = ?", (deal_id,))
            conn.commit()
            
            await callback.message.edit_text("✅ Оплата подтверждена! Ожидайте перевода от гаранта.")
            
            cursor.execute("SELECT seller_id FROM deals WHERE deal_id = ?", (deal_id,))
            seller_id = cursor.fetchone()[0]
            
            await bot.send_message(
                seller_id,
                f"💰 Покупатель оплатил сделку #{deal_id} через Crypto Bot!"
            )
        elif invoice.status == "active":
            await callback.answer("⏳ Ожидание оплаты", show_alert=True)
        else:
            await callback.answer("❌ Счёт не найден или истёк", show_alert=True)
            
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# ========== ВЫБОР ПРЯМОГО ПЕРЕВОДА ==========
@dp.callback_query(lambda c: c.data.startswith("pay_manual_"))
async def pay_manual(callback: types.CallbackQuery):
    deal_id = int(callback.data.split("_")[2])
    
    cursor.execute("SELECT amount FROM deals WHERE deal_id = ?", (deal_id,))
    deal = cursor.fetchone()
    
    payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{deal_id}")],
        [InlineKeyboardButton(text="❌ Отменить сделку", callback_data=f"cancel_{deal_id}")]
    ])
    
    await callback.message.edit_text(
        f"💸 *Прямой перевод*\n\n"
        f"💰 Сумма: *{deal[0]} USDT*\n\n"
        f"📤 Отправьте {deal[0]} USDT (сеть TON) на кошелёк:\n"
        f"`{WALLET_ADDRESS}`\n\n"
        f"⚠️ *ВАЖНО!*\n"
        f"• Только сеть *TON*\n"
        f"• Другие сети = потеря средств\n\n"
        f"✅ После отправки нажмите кнопку ниже",
        reply_markup=payment_keyboard,
        parse_mode="Markdown"
    )

# ========== ОТКЛОНЕНИЕ СДЕЛКИ ==========
@dp.callback_query(lambda c: c.data.startswith("reject_"))
async def reject_deal(callback: types.CallbackQuery):
    deal_id = int(callback.data.split("_")[1])
    cursor.execute("UPDATE deals SET status = 'cancelled' WHERE deal_id = ?", (deal_id,))
    conn.commit()
    await callback.message.edit_text("❌ Сделка отклонена.")

# ========== ОТМЕНА СДЕЛКИ ==========
@dp.callback_query(lambda c: c.data.startswith("cancel_"))
async def cancel_deal(callback: types.CallbackQuery):
    deal_id = int(callback.data.split("_")[1])
    cursor.execute("UPDATE deals SET status = 'cancelled' WHERE deal_id = ?", (deal_id,))
    conn.commit()
    await callback.message.edit_text("❌ Сделка отменена.")

# ========== ПОДТВЕРЖДЕНИЕ РУЧНОЙ ОПЛАТЫ ==========
@dp.callback_query(lambda c: c.data.startswith("paid_"))
async def paid_deal(callback: types.CallbackQuery):
    deal_id = int(callback.data.split("_")[1])
    
    cursor.execute("SELECT seller_id, amount FROM deals WHERE deal_id = ?", (deal_id,))
    deal = cursor.fetchone()
    
    cursor.execute("UPDATE deals SET status = 'paid' WHERE deal_id = ?", (deal_id,))
    conn.commit()
    
    await callback.message.edit_text("✅ Оплата подтверждена. Ожидайте перевода от гаранта.")
    
    await bot.send_message(
        deal[0],
        f"💰 Покупатель оплатил сделку #{deal_id}!\n"
        f"Сумма: {deal[1]:,.0f} USDT"
    )

# ========== ЗАПУСК ==========
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Бот MONDIAL запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())