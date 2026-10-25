import re
import unicodedata

_ALNUM = re.compile(r"[^a-z0-9]+")

_STOPWORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or",
    "the", "to", "with", "its", "is", "are", "was", "were", "be", "been",
}


def normalize_topic(topic: str) -> str:
    """Lowercase, trim, strip punctuation, drop stopwords and single letters."""
    if not topic:
        return ""
    text = unicodedata.normalize("NFKD", topic)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _ALNUM.sub(" ", text.lower()).strip()
    words = []
    for w in text.split():
        if w.isdigit():
            words.append(w)
        elif len(w) >= 2 and w not in _STOPWORDS:
            words.append(w)
    return " ".join(words)


def cache_key(normalized_topic: str, length_minutes: int, voice: str, language: str) -> str:
    return f"{normalized_topic}|{length_minutes}|{voice.lower()}|{language.lower()}"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _ALNUM.sub("-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", text)
