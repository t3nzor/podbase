from __future__ import annotations

from dataclasses import dataclass

from podbase.transcribe.whisper import WordTiming

DEFAULT_SEGMENT_DURATION = 30.0  # seconds
MIN_SEGMENT_DURATION = 10.0


@dataclass
class TextSegment:
    idx: int
    start_sec: float
    end_sec: float
    text: str


def chunk_words(
    words: list[WordTiming],
    max_duration: float = DEFAULT_SEGMENT_DURATION,
) -> list[TextSegment]:
    """Group word-level timings into fixed-duration segments.

    Breaks at natural boundaries (end of sentence-ish punctuation) when possible,
    otherwise falls back to max_duration.
    """
    if not words:
        return []

    segments: list[TextSegment] = []
    buf_words: list[str] = []
    buf_start: float = words[0].start
    buf_end: float = words[0].end
    idx = 0

    sentence_end_chars = {".", "!", "?", "…"}

    for w in words:
        buf_words.append(w.word)
        buf_end = w.end

        duration = buf_end - buf_start
        ends_sentence = w.word.rstrip()[-1:] in sentence_end_chars if w.word else False

        if (ends_sentence and duration >= MIN_SEGMENT_DURATION) or duration >= max_duration:
            segments.append(
                TextSegment(
                    idx=idx,
                    start_sec=buf_start,
                    end_sec=buf_end,
                    text="".join(buf_words).strip(),
                )
            )
            idx += 1
            buf_words = []
            buf_start = buf_end

    # Flush remaining words
    if buf_words:
        segments.append(
            TextSegment(
                idx=idx,
                start_sec=buf_start,
                end_sec=buf_end,
                text="".join(buf_words).strip(),
            )
        )

    return segments
