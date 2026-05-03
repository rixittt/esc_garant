from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text='💼 My Deals'), KeyboardButton(text='➕ Create Deal')],
        [KeyboardButton(text='👤 Profile'), KeyboardButton(text='📤 Withdraw')],
        [KeyboardButton(text='📥 Deposit'), KeyboardButton(text='🛠 Support')],
    ]
    if is_admin:
        rows.append([KeyboardButton(text='🏪 Shop'), KeyboardButton(text='🛡 Admin Panel')])
    else:
        rows.append([KeyboardButton(text='🏪 Shop')])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🔎 Find User'), KeyboardButton(text='📊 Users')],
            [KeyboardButton(text='🌐 All Deals'), KeyboardButton(text='💳 Transactions')],
            [KeyboardButton(text='📤 Withdraw Requests')],
            [KeyboardButton(text='⚖️ Disputes'), KeyboardButton(text='📢 Broadcast')],
            [KeyboardButton(text='⚙️ Settings')],
            [KeyboardButton(text='⬅️ User Menu')],
        ],
        resize_keyboard=True,
    )
