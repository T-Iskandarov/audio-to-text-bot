from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.config import settings
from app.handlers.admin import admin_menu_keyboard

router = Router()

WELCOME_TEXT = (
    "🎙 Menga ovozli xabar, audio fayl yoki dumaloq video yuboring.\n"
    "Men uni o'zbek lotin alifbosida toza matnga o'girib beraman."
)
HELP_TEXT = (
    "Qanday ishlataman?\n"
    "Ovozli xabar, audio fayl yoki dumaloq videoni shu yerga yuboring yoki boshqa chatdan "
    "uzating. Bir necha soniyada matnini olasiz.\n\n"
    "Fayl hajmi 20 MB dan oshmasligi kerak."
)


@router.message(CommandStart())
async def start_cmd(message: Message) -> None:
    is_admin = message.from_user and message.from_user.id == settings.ADMIN_ID
    await message.answer(WELCOME_TEXT, reply_markup=admin_menu_keyboard() if is_admin else None)


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(HELP_TEXT)
