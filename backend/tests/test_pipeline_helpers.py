import io
import struct
import wave

import pytest

from app.pipeline import (
    ARC_SECTIONS,
    OutlineChapter,
    _validate_arc_order,
    chapter_count_for,
    chapter_object_key,
    chunk_text_for_tts,
    concatenate_wav,
    encode_mp3,
    has_placeholder_text,
    split_word_budget,
    target_word_count,
    verify_audio_header,
    wav_duration_seconds,
)


def _wav_bytes(rate=24000, seconds=0.5, channels=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", 0) for _ in range(int(rate * seconds)))
        w.writeframes(frames)
    return buf.getvalue()


class TestWordBudget:
    def test_10min(self):
        assert target_word_count(10) == 1500

    def test_30min(self):
        assert target_word_count(30) == 4500

    def test_60min(self):
        assert target_word_count(60) == 9000

    def test_split_sums(self):
        for total in (1500, 4500, 9000):
            for n in (3, 7, 12):
                parts = split_word_budget(total, n)
                assert sum(parts) == total
                assert max(parts) - min(parts) <= 1


class TestChapterCounts:
    def test_counts(self):
        assert chapter_count_for(10) == 3
        assert chapter_count_for(30) == 7
        assert chapter_count_for(60) == 12


def _ch(pos, arc):
    return OutlineChapter(position=pos, arc_section=arc, title=f"c{pos}")


class TestArcOrder:
    def test_valid_full_arc(self):
        _validate_arc_order([_ch(0, "world_before"), _ch(1, "origin"), _ch(2, "evolution"), _ch(3, "challenges"), _ch(4, "perspective")])

    def test_evolution_spans_multiple(self):
        _validate_arc_order(
            [_ch(0, "world_before"), _ch(1, "origin"), _ch(2, "evolution"), _ch(3, "evolution"), _ch(4, "challenges"), _ch(5, "perspective")]
        )

    def test_out_of_order_rejected(self):
        with pytest.raises(ValueError):
            _validate_arc_order([_ch(0, "origin"), _ch(1, "world_before")])

    def test_unknown_section_rejected(self):
        with pytest.raises(ValueError):
            _validate_arc_order([_ch(0, "bogus")])

    def test_arc_sections_mandatory_order(self):
        assert ARC_SECTIONS == ["world_before", "origin", "evolution", "challenges", "perspective"]


class TestPlaceholders:
    def test_clean_text(self):
        assert not has_placeholder_text("The earliest bricks date to seven thousand BCE.")

    def test_brackets(self):
        assert has_placeholder_text("He said [something] once.")

    def test_todo(self):
        assert has_placeholder_text("We will TODO later.")

    def test_insert(self):
        assert has_placeholder_text("Please [insert date here].")


class TestTTSChunking:
    def test_short_text_single_chunk(self):
        assert chunk_text_for_tts("Hello world") == ["Hello world"]

    def test_split_on_paragraph_boundaries(self):
        paras = ["A" * 100 for _ in range(100)]
        text = "\n\n".join(paras)
        chunks = chunk_text_for_tts(text, limit=450)
        assert all(len(c) <= 450 for c in chunks)
        assert "".join(c.replace("\n\n", "") for c in chunks) == "".join(paras)

    def test_huge_paragraph_split_on_sentences(self):
        para = " ".join("Sentence number one here." for _ in range(500))
        chunks = chunk_text_for_tts(para, limit=400)
        assert all(len(c) <= 400 for c in chunks)
        assert " ".join(chunks).replace("  ", " ") == para


class TestAudioProcessing:
    def test_concat_resamples_to_44100(self):
        parts = [_wav_bytes(rate=24000), _wav_bytes(rate=24000)]
        out = concatenate_wav(parts, target_rate=44100, channels=1, sample_width=2)
        with wave.open(io.BytesIO(out)) as w:
            assert w.getframerate() == 44100
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getnframes() > 0

    def test_mixed_rates_concat(self):
        parts = [_wav_bytes(rate=24000), _wav_bytes(rate=44100)]
        out = concatenate_wav(parts, target_rate=44100, channels=1, sample_width=2)
        assert verify_audio_header(out)

    def test_stereo_to_mono(self):
        parts = [_wav_bytes(rate=24000, channels=2)]
        out = concatenate_wav(parts, target_rate=44100, channels=1, sample_width=2)
        with wave.open(io.BytesIO(out)) as w:
            assert w.getnchannels() == 1

    def test_verify_header_rejects_garbage(self):
        assert not verify_audio_header(b"not audio at all")

    def test_duration(self):
        out = concatenate_wav([_wav_bytes(rate=24000, seconds=1.0)], target_rate=44100, channels=1, sample_width=2)
        assert wav_duration_seconds(out) == 1

    def test_mp3_encode(self):
        wav = concatenate_wav([_wav_bytes(rate=24000, seconds=1.0)], target_rate=44100, channels=1, sample_width=2)
        mp3 = encode_mp3(wav)
        assert mp3[:3] == b"ID3" or mp3[0] == 0xFF


class TestObjectKeys:
    def test_chapter_key_format(self):
        key = chapter_object_key("coffee", 2, "The World Before Coffee")
        assert key == "coffee-chapter-03-the-world-before-coffee.mp3"

    def test_first_chapter_is_01(self):
        assert "chapter-01" in chapter_object_key("tea", 0, "x")

    def test_two_digit_sequence(self):
        assert "chapter-10" in chapter_object_key("tea", 9, "x")
        assert "chapter-16" in chapter_object_key("tea", 15, "x")
