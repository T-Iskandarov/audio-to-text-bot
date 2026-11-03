import logging
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.services import storage

logger = logging.getLogger(__name__)


class TrackingMiddleware(BaseMiddleware):
    """Records every incoming message for the admin panel and passes its row id on as `log_id`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["log_id"] = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
            try:
                data["log_id"] = await storage.log_message(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    chat_id=event.chat.id,
                    message_id=event.message_id,
                    kind=event.content_type.value,
                    content=event.text or event.caption,
                )
            except sqlite3.Error:
                # A broken log must not stop transcription.
                logger.exception("Could not record message")
        return await handler(event, data)
