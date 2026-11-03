from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.handlers.media import split_text
from app.services import storage
from app.services.storage import MessageRow, UserRow

router = Router()
router.message.filter(F.from_user.id == settings.ADMIN_ID)
router.callback_query.filter(F.from_user.id == settings.ADMIN_ID)

PAGE_SIZE = 8
PREVIEW_LENGTH = 40
TASHKENT = timezone(timedelta(hours=5))

KIND_LABELS = {
    "voice": "🎙 Ovozli xabar",
    "audio": "🎵 Audio",
    "video_note": "⏺ Dumaloq video",
    "text": "💬 Matn",
    "photo": "🖼 Rasm",
    "video": "🎬 Video",
    "document": "📄 Fayl",
    "sticker": "😀 Stiker",
}
STATUS_LABELS = {
    "ok": "matnga o'girildi",
    "too_big": "fayl juda katta",
    "rate_limit": "navbat to'lgan edi",
    "error": "xatolik yuz berdi",
}


class AdminCallback(CallbackData, prefix="adm"):
    action: str
    user_id: int = 0
    page: int = 0
    log_id: int = 0


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Foydalanuvchilar",
                    callback_data=AdminCallback(action="users").pack(),
                )
            ]
        ]
    )


def _format_time(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M")


def _format_short_time(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(TASHKENT).strftime("%d.%m %H:%M")


def _user_title(user: UserRow) -> str:
    if user.username:
        return f"@{user.username}"
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return full_name or "Username yo'q"


def _kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, f"📎 {kind}")


def _preview(row: MessageRow) -> str:
    text = " ".join((row.transcript or row.content or "").split())
    if len(text) > PREVIEW_LENGTH:
        return f"{text[:PREVIEW_LENGTH]}..."
    return text


def _page_buttons(action: str, page: int, total: int, user_id: int = 0) -> list[InlineKeyboardButton]:
    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=AdminCallback(action=action, user_id=user_id, page=page - 1).pack(),
            )
        )
    if (page + 1) * PAGE_SIZE < total:
        buttons.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=AdminCallback(action=action, user_id=user_id, page=page + 1).pack(),
            )
        )
    return buttons


async def _menu_text() -> str:
    users = await storage.count_users()
    messages = await storage.count_all_messages()
    return f"🛠 Admin panel\n\nFoydalanuvchilar: {users}\nXabarlar: {messages}"


@router.message(Command("admin"))
async def admin_cmd(message: Message) -> None:
    await message.answer(await _menu_text(), reply_markup=admin_menu_keyboard())


@router.callback_query(AdminCallback.filter(F.action == "menu"))
async def show_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(await _menu_text(), reply_markup=admin_menu_keyboard())


@router.callback_query(AdminCallback.filter(F.action == "users"))
async def show_users(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    await callback.answer()
    page = callback_data.page
    total = await storage.count_users()
    users = await storage.list_users(limit=PAGE_SIZE, offset=page * PAGE_SIZE)

    lines = [f"👥 Foydalanuvchilar: {total}", ""]
    rows = []
    for user in users:
        lines.append(f"{_user_title(user)} | ID: {user.id} | {user.message_count} ta xabar")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_user_title(user)} | {user.id}",
                    callback_data=AdminCallback(action="user", user_id=user.id).pack(),
                )
            ]
        )
    if not users:
        lines.append("Hali hech kim botdan foydalanmagan.")

    if nav := _page_buttons("users", page, total):
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=AdminCallback(action="menu").pack())]
    )
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(AdminCallback.filter(F.action == "user"))
async def show_user(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    await callback.answer()
    user = await storage.get_user(callback_data.user_id)
    if user is None:
        await callback.message.edit_text("Foydalanuvchi topilmadi.")
        return

    page = callback_data.page
    messages = await storage.list_messages(user.id, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part) or "-"
    text = (
        f"👤 {_user_title(user)}\n"
        f"ID: {user.id}\n"
        f"Ism: {full_name}\n"
        f"Birinchi marta: {_format_time(user.first_seen)}\n"
        f"Oxirgi marta: {_format_time(user.last_seen)}\n"
        f"Xabarlar: {user.message_count}\n\n"
        "Xabarni ko'rish uchun tanlang:"
    )

    rows = [
        [
            InlineKeyboardButton(
                text=f"{_kind_label(row.kind).split()[0]} {_format_short_time(row.created_at)} {_preview(row)}",
                callback_data=AdminCallback(action="message", log_id=row.id).pack(),
            )
        ]
        for row in messages
    ]
    if nav := _page_buttons("user", page, user.message_count, user_id=user.id):
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=AdminCallback(action="users").pack())]
    )
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(AdminCallback.filter(F.action == "message"))
async def show_message(callback: CallbackQuery, callback_data: AdminCallback, bot: Bot) -> None:
    row = await storage.get_message(callback_data.log_id)
    if row is None:
        await callback.answer("Xabar topilmadi.", show_alert=True)
        return
    await callback.answer()

    admin_chat_id = callback.message.chat.id
    original_note = ""
    try:
        await bot.copy_message(
            chat_id=admin_chat_id,
            from_chat_id=row.chat_id,
            message_id=row.message_id,
        )
    except TelegramBadRequest:
        # The sender may have deleted it or blocked the bot; the saved text is still shown.
        original_note = "\n⚠️ Asl xabar endi mavjud emas."

    header = f"{_kind_label(row.kind)} | {_format_time(row.created_at)}{original_note}"
    if row.status:
        header += f"\nHolat: {STATUS_LABELS.get(row.status, row.status)}"

    body = row.transcript or row.content
    if not body:
        await callback.message.answer(header)
        return
    label = "📝 Matni" if row.transcript else "💬 Mazmuni"
    for chunk in split_text(f"{header}\n\n{label}:\n{body}"):
        await callback.message.answer(chunk)
