import asyncio
import time
from collections import deque
from types import TracebackType


class GeminiRateLimiter:
    """Queues callers so Gemini sees at most `rpm` requests a minute and `concurrency` at once."""

    def __init__(self, rpm: int, concurrency: int, window: float = 60.0) -> None:
        self._rpm = rpm
        self._window = window
        self._started: deque[float] = deque()
        self._slot_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(concurrency)

    async def _wait_for_slot(self) -> None:
        # Held while sleeping, so waiters keep their arrival order.
        async with self._slot_lock:
            now = time.monotonic()
            while self._started and now - self._started[0] >= self._window:
                self._started.popleft()
            if len(self._started) >= self._rpm:
                await asyncio.sleep(self._window - (now - self._started.popleft()))
            self._started.append(time.monotonic())

    async def __aenter__(self) -> None:
        await self._semaphore.acquire()
        try:
            await self._wait_for_slot()
        except BaseException:
            self._semaphore.release()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._semaphore.release()
