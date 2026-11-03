import asyncio
import io
import logging

from google import genai
from google.genai import errors, types

from app.config import settings
from app.middlewares.throttling import GeminiRateLimiter
from app.services.silence import is_silent

logger = logging.getLogger(__name__)

NO_SPEECH_TEXT = "[Ovozli xabarda nutq aniqlanmadi]"

SYSTEM_PROMPT = (
    "Sen professional stenograf va muharrirsan. Yuborilgan audio yoki video xabar ichidagi "
    "nutqni eshitib, uni aniq va ravon o'zbek lotin alifbosida matnga o'girib ber. "
    "Qoidalar: 1. Shevada yoki ruscha-o'zbekcha aralash aytilgan so'zlarni kontekstni buzmagan "
    "holda tushunarli qilib yoz. 2. Tinish belgilarini joy-joyiga qo'y. 3. O'zingdan hech qanday "
    "kirish yoki izoh so'zi qo'shma, faqat inson gapirgan nutqning o'zini qaytar. 4. Hech qachon "
    "so'z to'qima va taxmin qilma: faqat aniq eshitilgan so'zlarni yoz. Agar faylda jimlik, "
    f"shovqin yoki musiqa bo'lib, inson nutqi aniq eshitilmasa, faqat '{NO_SPEECH_TEXT}' deb "
    "javob ber."
)
USER_PROMPT = "Ushbu media fayldagi barcha gaplarni matnga o'girib ber."

# Inline parts are base64-encoded and a request is capped at 20 MB, so larger media goes via the Files API.
INLINE_LIMIT_BYTES = 14 * 1024 * 1024
FILE_POLL_SECONDS = 2.0
FILE_POLL_ATTEMPTS = 60

# Retired model, per-model quota or overload: another model may still answer.
FALLBACK_STATUS_CODES = {404, 429, 500, 502, 503, 504}


class GeminiRateLimitError(Exception):
    """Gemini answered 429 Resource Exhausted."""


class GeminiEmptyResponseError(Exception):
    """Gemini returned no text, for example because the response was blocked."""


client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())
limiter = GeminiRateLimiter(rpm=settings.GEMINI_RPM, concurrency=settings.GEMINI_CONCURRENCY)


async def _upload(media_bytes: bytes, mime_type: str) -> types.File:
    uploaded = await client.aio.files.upload(
        file=io.BytesIO(media_bytes),
        config=types.UploadFileConfig(mime_type=mime_type),
    )
    for _ in range(FILE_POLL_ATTEMPTS):
        if uploaded.state != types.FileState.PROCESSING:
            break
        await asyncio.sleep(FILE_POLL_SECONDS)
        uploaded = await client.aio.files.get(name=uploaded.name)
    if uploaded.state != types.FileState.ACTIVE:
        await client.aio.files.delete(name=uploaded.name)
        raise RuntimeError(f"Gemini could not process the upload: {uploaded.state}")
    return uploaded


async def _generate_with_model(model: str, media_part: types.Part) -> str:
    async with asyncio.timeout(settings.GEMINI_TIMEOUT_SECONDS):
        response = await client.aio.models.generate_content(
            model=model,
            contents=[media_part, USER_PROMPT],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
            ),
        )
    text = (response.text or "").strip()
    if not text:
        raise GeminiEmptyResponseError(str(response.prompt_feedback))
    return text


async def _generate(media_part: types.Part) -> str:
    models = [settings.GEMINI_MODEL, *settings.GEMINI_FALLBACK_MODELS]
    for model in models[:-1]:
        try:
            return await _generate_with_model(model, media_part)
        except errors.APIError as exc:
            if exc.code not in FALLBACK_STATUS_CODES:
                raise
            logger.warning("Gemini model %s failed with %s, trying the next one", model, exc.code)
        except TimeoutError:
            logger.warning("Gemini model %s timed out, trying the next one", model)
    return await _generate_with_model(models[-1], media_part)


async def transcribe(media_bytes: bytes, mime_type: str) -> str:
    # Gemini tends to invent speech for pure silence, so it never gets to see it.
    if await asyncio.to_thread(is_silent, media_bytes):
        return NO_SPEECH_TEXT

    try:
        async with limiter:
            if len(media_bytes) <= INLINE_LIMIT_BYTES:
                return await _generate(types.Part.from_bytes(data=media_bytes, mime_type=mime_type))

            uploaded = await _upload(media_bytes, mime_type)
            try:
                return await _generate(
                    types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime_type)
                )
            finally:
                await client.aio.files.delete(name=uploaded.name)
    except errors.APIError as exc:
        if exc.code == 429:
            raise GeminiRateLimitError from exc
        raise
