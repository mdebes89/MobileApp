"""Generation pipeline: research -> outline -> write -> validate -> TTS -> finalize.

The chapter arc is MANDATORY and in this exact order:
  1. world_before  - the world BEFORE the topic existed (indirect dependencies, conditions)
  2. origin        - ORIGIN of the topic (when/where it first appeared)
  3. evolution     - chronological EVOLUTION across historical eras
  4. challenges    - current-day CHALLENGES
  5. perspective   - future PERSPECTIVE
"""
import asyncio
import io
import json
import logging
import re
import struct
import wave
from dataclasses import dataclass, field
from typing import Any

from app import mistral_client, ratelimit
from app.config import get_settings
from app.normalize import slugify

log = logging.getLogger(__name__)

ARC_SECTIONS = ["world_before", "origin", "evolution", "challenges", "perspective"]

CHAPTER_COUNTS = {10: (3, 4), 30: (7, 8), 60: (12, 16)}
WORDS_PER_MINUTE = 150
TARGET_SAMPLE_RATE = 44100
TTS_CHUNK_LIMIT = 5000

PLACEHOLDER_PATTERNS = [
    re.compile(r"\[.*?\]", re.IGNORECASE),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\blorem ipsum\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\[insert[^]]*\]", re.IGNORECASE),
]


@dataclass
class OutlineChapter:
    position: int
    arc_section: str
    title: str
    summary: str = ""
    target_words: int = 0


@dataclass
class Outline:
    title: str
    chapters: list[OutlineChapter] = field(default_factory=list)


@dataclass
class ChapterResult:
    position: int
    arc_section: str
    title: str
    text: str
    audio: bytes | None = None
    duration_seconds: int | None = None


def target_word_count(length_minutes: int) -> int:
    return WORDS_PER_MINUTE * length_minutes


def chapter_count_for(length_minutes: int) -> int:
    lo, hi = CHAPTER_COUNTS[length_minutes]
    return lo


def split_word_budget(total_words: int, num_chapters: int) -> list[int]:
    base = total_words // num_chapters
    remainder = total_words - base * num_chapters
    return [base + (1 if i < remainder else 0) for i in range(num_chapters)]


async def research_topic(topic: str, language: str) -> str:
    """Step a: web-search-grounded fact gathering about origins and full history."""
    sys = (
        "You are a meticulous research historian. Use web search to gather verified facts. "
        "Report the topic's origins, indirect dependencies, enabling conditions, and its full "
        "chronological history through the present day. Include approximate dates and places. "
        f"Write in {language}. Do not invent facts; flag uncertainty explicitly."
    )
    usr = (
        f"Topic: {topic}\n\n"
        "Gate 1 - topic validation: state clearly whether this topic is a real, well-defined subject with a "
        "meaningful history. If it is too vague, nonsensical, or has no meaningful history, say exactly: "
        "REJECT_TOPIC and give a one-sentence reason.\n\n"
        "Then produce structured research notes covering: (1) the world before this topic existed, including "
        "indirect dependencies and enabling conditions; (2) its origin; (3) chronological eras of evolution; "
        "(4) present-day challenges; (5) plausible future trajectory."
    )
    content = await mistral_client.chat_completion(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
    )
    if re.search(r"^\s*REJECT_TOPIC", content, re.IGNORECASE | re.MULTILINE):
        raise ValueError(f"topic rejected during research: {topic}")
    return content


async def build_outline(topic: str, research: str, length_minutes: int, language: str) -> Outline:
    """Step b: mandatory five-part arc outline with chapter counts by length."""
    n = chapter_count_for(length_minutes)
    budget = split_word_budget(target_word_count(length_minutes), n)
    settings = get_settings()
    sys = (
        "You are an audiobook architect. Design chapter outlines with a strict narrative arc. "
        f"Write titles and summaries in {language}."
    )
    usr = (
        f"Topic: {topic}\n\nResearch notes:\n{research}\n\n"
        f"Design an audiobook with exactly {n} chapters following this MANDATORY arc order:\n"
        "1) world_before: the world BEFORE the topic existed - indirect dependencies and conditions that led to it\n"
        "2) origin: when/where the topic first appeared and what made it possible\n"
        "3) evolution: chronological evolution across historical eras\n"
        "4) challenges: current-day challenges\n"
        "5) perspective: future perspective\n\n"
        "Every section must be represented, in this exact order; 'evolution' may span multiple chapters "
        f"({n} chapters total). Respond in JSON only:\n"
        '{"title": "<audiobook title>", "chapters": [{"arc_section": "world_before|origin|evolution|challenges|perspective", '
        '"title": "<chapter title>", "summary": "<2-3 sentence summary>"}]}'
    )
    raw = await mistral_client.chat_completion(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}], json_mode=True
    )
    data = _parse_json(raw)
    outline = Outline(title=data.get("title", topic).strip())
    for i, ch in enumerate(data.get("chapters", [])[:n]):
        outline.chapters.append(
            OutlineChapter(
                position=i,
                arc_section=ch.get("arc_section", ARC_SECTIONS[2]),
                title=str(ch.get("title", f"Chapter {i + 1}")).strip(),
                summary=ch.get("summary", ""),
                target_words=budget[i],
            )
        )
    if not outline.chapters:
        raise ValueError("empty outline")
    _validate_arc_order(outline.chapters)
    return outline


def _validate_arc_order(chapters: list[OutlineChapter]) -> None:
    """The arc order must be non-decreasing in the mandated section sequence."""
    rank = {s: i for i, s in enumerate(ARC_SECTIONS)}
    last = -1
    for ch in chapters:
        if ch.arc_section not in rank:
            raise ValueError(f"unknown arc section: {ch.arc_section}")
        r = rank[ch.arc_section]
        if r < last:
            raise ValueError("chapters violate the mandatory arc order")
        last = r


async def write_chapter(
    topic: str, outline: Outline, chapter: OutlineChapter, prev_title: str | None, language: str
) -> str:
    """Step c: narration-ready spoken prose with natural transitions."""
    sys = (
        "You are a professional audiobook narrator-writer. Write complete, narration-ready prose. "
        "Spoken style: no markdown decorations, no headings, no bullet lists. Numbers must be written "
        "for reading aloud. Natural spoken transitions. Do not include the chapter title in the text."
    )
    ctx = (
        f"Audiobook title: {outline.title}. Previous chapter: {prev_title or 'none (this is the first chapter)'}. "
        f"Narrate in {language}."
    )
    usr = (
        f"{ctx}\nTopic: {topic}\nChapter {chapter.position + 1} of {len(outline.chapters)} "
        f"(arc: {chapter.arc_section}): {chapter.title}\nSummary: {chapter.summary}\n"
        f"Target length: about {chapter.target_words} words ("
        f"{chapter.arc_section} of the arc). "
        "Open with a transition from the previous chapter where applicable, then write the full chapter as "
        "flowing paragraphs separated by blank lines."
    )
    return await mistral_client.chat_completion([{"role": "system", "content": sys}, {"role": "user", "content": usr}])


async def validate_chapter(topic: str, outline: Outline, chapter: OutlineChapter, text: str, language: str) -> dict:
    """Step d: separate validation pass. Returns {"valid": bool, "issues": [...]}."""
    sys = (
        "You are a strict audiobook QA editor. Judge only what you are asked; be conservative about "
        "statements concerning real, identifiable people."
    )
    usr = (
        f"Topic: {topic}\nArc position {chapter.position + 1} of {len(outline.chapters)} "
        f"({chapter.arc_section}): {chapter.title}\n\nChapter text:\n{text}\n\nCheck:\n"
        "1) Topic relevance including indirect dependencies.\n"
        "2) Strict arc conformance for this chapter's arc section.\n"
        "3) No placeholder text and no missing paragraphs (the text must be substantial, not truncated).\n"
        "4) No defamation: statements about real identifiable people must be neutral or clearly framed as contested.\n"
        'Respond in JSON only: {"valid": true|false, "issues": ["..."]}'
    )
    raw = await mistral_client.chat_completion(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}], json_mode=True
    )
    try:
        data = _parse_json(raw)
    except ValueError:
        return {"valid": False, "issues": ["validator produced unparseable output"]}
    valid = bool(data.get("valid"))
    issues = [str(i) for i in data.get("issues", [])]
    if not valid and not issues:
        issues = ["validator reported invalid without specifics"]
    return {"valid": valid, "issues": issues}


def has_placeholder_text(text: str) -> bool:
    return any(p.search(text) for p in PLACEHOLDER_PATTERNS)


async def synthesize_chapter_audio(text: str, voice: str, language: str) -> tuple[bytes, int]:
    """Step e: chunked TTS, WAV concat, resample to 44.1 kHz 16-bit mono, MP3 encode."""
    settings = get_settings()
    voice_id = settings.tts_voice_id(voice)
    chunks = chunk_text_for_tts(text, settings.mistral_tts_chunk_chars)
    wav_parts: list[bytes] = []
    for idx, chunk in enumerate(chunks):
        for attempt in range(3):
            try:
                wav_parts.append(await mistral_client.text_to_speech(chunk, voice_id, response_format="wav"))
                break
            except (mistral_client.MistralError, ratelimit.RateLimitExceeded) as exc:
                if attempt == 2:
                    raise
                log.warning("TTS chunk %d failed (%s); retrying", idx, exc)
                await asyncio.sleep(2**attempt)
    combined = concatenate_wav(wav_parts, target_rate=TARGET_SAMPLE_RATE, channels=1, sample_width=2)
    duration = wav_duration_seconds(combined)
    mp3 = encode_mp3(combined)
    return mp3, duration


def chunk_text_for_tts(text: str, limit: int = TTS_CHUNK_LIMIT) -> list[str]:
    """Split on paragraph boundaries under ~5000 chars per request."""
    if len(text) <= limit:
        return [text] if text.strip() else []
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > limit:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[.!?])\s+", para)
            sub = ""
            for s in sentences:
                if len(sub) + len(s) + 1 > limit:
                    if sub:
                        chunks.append(sub)
                    sub = s
                else:
                    sub = f"{sub} {s}".strip()
            current = sub
        elif len(current) + len(para) + 2 > limit:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}".strip()
    if current.strip():
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def _read_wav_frames(data: bytes) -> tuple[bytes, int, int, int]:
    """Return (frames, sample_rate, channels, sample_width) from a WAV byte string."""
    with wave.open(io.BytesIO(data), "rb") as w:
        return (
            w.readframes(w.getnframes()),
            w.getframerate(),
            w.getnchannels(),
            w.getsampwidth(),
        )


def concatenate_wav(parts: list[bytes], target_rate: int, channels: int, sample_width: int) -> bytes:
    """Concatenate WAV chunks, resampling to target_rate, as 16-bit mono WAV."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w_out:
        w_out.setnchannels(channels)
        w_out.setsampwidth(sample_width)
        w_out.setframerate(target_rate)
        for part in parts:
            frames, rate, nch, width = _read_wav_frames(part)
            frames = _to_mono(frames, nch, width)
            if rate != target_rate:
                frames = _resample(frames, rate, target_rate, width)
            w_out.writeframes(frames)
    return out.getvalue()


def _to_mono(frames: bytes, channels: int, sample_width: int) -> bytes:
    if channels == 1:
        return frames
    if sample_width != 2:
        raise ValueError(f"unsupported sample width: {sample_width}")
    count = len(frames) // (channels * 2)
    vals = struct.unpack(f"<{count * channels}h", frames)
    mono = [sum(vals[i * channels : (i + 1) * channels]) // channels for i in range(count)]
    return struct.pack(f"<{count}h", *mono)


def _resample(frames: bytes, src_rate: int, dst_rate: int, sample_width: int) -> bytes:
    if sample_width != 2:
        raise ValueError(f"unsupported sample width: {sample_width}")
    import audioop

    return audioop.ratecv(frames, 2, 1, src_rate, dst_rate, None)[0]


def wav_duration_seconds(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return max(1, int(round(w.getnframes() / float(w.getframerate()))))


def verify_audio_header(data: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.getnframes() > 0
    except Exception:
        return False


def encode_mp3(wav_bytes: bytes) -> bytes:
    import lameenc

    frames, rate, _, width = _read_wav_frames(wav_bytes)
    if width != 2:
        raise ValueError("MP3 encode expects 16-bit PCM")
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(96)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(frames)) + bytes(encoder.flush())


def chapter_object_key(normalized_topic: str, position: int, title: str, ext: str = "mp3") -> str:
    return f"{normalized_topic.replace(' ', '-')}-chapter-{position + 1:02d}-{slugify(title)}.{ext}"


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise ValueError(f"unparseable model output: {text[:200]}")
