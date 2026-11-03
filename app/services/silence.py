import io
import logging

import av
import numpy as np

logger = logging.getLogger(__name__)

# About -50 dBFS, below anything audible as speech. Peak-based so quiet speech is never dropped.
SILENCE_PEAK = 0.003


def _frame_peak(samples: np.ndarray) -> float:
    if np.issubdtype(samples.dtype, np.integer):
        return float(np.abs(samples.astype(np.float64)).max()) / np.iinfo(samples.dtype).max
    return float(np.abs(samples).max())


def is_silent(media_bytes: bytes) -> bool:
    """True if the media has no audio or only silence. Undecodable media counts as not silent."""
    try:
        with av.open(io.BytesIO(media_bytes)) as container:
            if not container.streams.audio:
                return True
            for frame in container.decode(audio=0):
                samples = frame.to_ndarray()
                if samples.size and _frame_peak(samples) >= SILENCE_PEAK:
                    return False
    except av.FFmpegError:
        logger.warning("Could not decode media for the silence check", exc_info=True)
        return False
    return True
