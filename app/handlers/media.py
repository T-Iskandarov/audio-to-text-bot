import io
import logging
import sqlite3

from aiogram import Bot, F, Router
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from app.services import storage
from app.services.gemini_stt import GeminiRateLimitError, transcribe

logger = logging.getLogger(__name__)

router = Router()

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_CHUNK_LENGTH = 4000

STATUS_TEXT = "⏳ Eshitilmoqda va matnga o'girilmoqda..."
TOO_BIG_TEXT = "⚠️ Kechirasiz, fayl juda katta. Iltimos, 20 MB dan kichik fayl yuboring."
RATE_LIMIT_TEXT = "Serverda navbat ko'payib ketdi, iltimos 20 soniyadan so'ng qayta yuboring."
ERROR_TEXT = "❌ Matnga o'girishda xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring."


def split_text(text: str, limit: int = MAX_CHUNK_LENGTH) -> list[str]:
    chunks: list[str] = []
    while len(text) > limit:
        # Prefer a paragraph, then a word boundary, so words are not cut in half.
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def get_media_info(message: Message) -> tuple[str, str, int | None]:
    if message.voice:
        voice = message.voice
        return voice.file_id, voice.mime_type or "audio/ogg", voice.file_size
    if message.video_note:
        video_note = message.video_note
        return video_note.file_id, "video/mp4", video_note.file_size
    audio = message.audio
    return audio.file_id, audio.mime_type or "audio/mpeg", audio.file_size


async def record_result(log_id: int | None, status: str, transcript: str | None = None) -> None:
    if log_id is None:
        return
    try:
        await storage.set_result(log_id, status, transcript)
    except sqlite3.Error:
        logger.exception("Could not record transcription result")


@router.message(F.voice | F.audio | F.video_note)
async def handle_media(message: Message, bot: Bot, log_id: int | None = None) -> None:
    file_id, mime_type, file_size = get_media_info(message)

    if file_size is not None and file_size > MAX_FILE_SIZE:
        await record_result(log_id, "too_big")
        await message.reply(TOO_BIG_TEXT)
        return

    status_msg = await message.reply(STATUS_TEXT)

    try:
        async with ChatActionSender.typing(chat_id=message.chat.id, bot=bot):
            file_info = await bot.get_file(file_id)
            buffer = io.BytesIO()
            await bot.download_file(file_info.file_path, destination=buffer)
            text = await transcribe(buffer.getvalue(), mime_type)
    except GeminiRateLimitError:
        logger.warning("Gemini rate limit hit")
        await record_result(log_id, "rate_limit")
        await status_msg.edit_text(RATE_LIMIT_TEXT)
        return
    except Exception:
        logger.exception("Transcription failed")
        await record_result(log_id, "error")
        await status_msg.edit_text(ERROR_TEXT)
        return

    await record_result(log_id, "ok", text)
    first_chunk, *other_chunks = split_text(text)
    await status_msg.edit_text(first_chunk)
    for chunk in other_chunks:
        await message.answer(chunk)
