from podbase.transcribe.chunk import TextSegment, chunk_words
from podbase.transcribe.whisper import WordTiming


def _make_words(n: int, start: float = 0.0, dur: float = 0.5) -> list[WordTiming]:
    """Create n sequential words starting at `start`."""
    words = []
    for i in range(n):
        s = start + i * dur
        words.append(WordTiming(word=f"word{i} ", start=s, end=s + dur))
    return words


class TestChunkWords:
    def test_empty_input(self) -> None:
        assert chunk_words([]) == []

    def test_single_segment(self) -> None:
        words = _make_words(5, start=0.0, dur=1.0)
        segs = chunk_words(words, max_duration=60.0)
        assert len(segs) == 1
        assert segs[0].idx == 0
        assert segs[0].start_sec == 0.0
        assert segs[0].end_sec == 5.0
        assert "word0" in segs[0].text

    def test_splits_at_max_duration(self) -> None:
        # 20 words at 2s each = 40s total, max_duration=30 -> 2 segments
        words = _make_words(20, start=0.0, dur=2.0)
        segs = chunk_words(words, max_duration=30.0)
        assert len(segs) == 2
        assert segs[0].idx == 0
        assert segs[1].idx == 1

    def test_splits_at_sentence_boundary(self) -> None:
        # Create words where one ends with a period
        words = [
            WordTiming(word="hello ", start=0.0, end=1.0),
            WordTiming(word="world. ", start=1.0, end=2.0),
            WordTiming(word="next ", start=2.0, end=15.0),
            WordTiming(word="sentence ", start=15.0, end=16.0),
        ]
        # max_duration=60, min_duration=10 -> should split at "world." since 2s < 10s min
        segs = chunk_words(words, max_duration=60.0)
        # With min_duration=10, it won't split at 2s mark
        assert len(segs) == 1

    def test_segment_indices_are_sequential(self) -> None:
        words = _make_words(50, start=0.0, dur=1.0)
        segs = chunk_words(words, max_duration=15.0)
        for i, seg in enumerate(segs):
            assert seg.idx == i

    def test_text_is_joined(self) -> None:
        words = [
            WordTiming(word="foo ", start=0.0, end=1.0),
            WordTiming(word="bar ", start=1.0, end=2.0),
            WordTiming(word="baz ", start=2.0, end=3.0),
        ]
        segs = chunk_words(words, max_duration=60.0)
        assert "foo" in segs[0].text
        assert "bar" in segs[0].text
        assert "baz" in segs[0].text
