from app.normalize import cache_key, normalize_topic, slugify


class TestNormalizeTopic:
    def test_lowercase_and_trim(self):
        assert normalize_topic("  Coffee  ") == "coffee"

    def test_punctuation_removed(self):
        assert normalize_topic("Paper! (a history)") == "paper history"

    def test_mixed_case(self):
        assert normalize_topic("Bricks") == "bricks"
        assert normalize_topic("CoFfEe") == "coffee"

    def test_dedup_variants(self):
        """All of these represent the same topic and must normalize identically."""
        variants = ["Coffee", "  coffee  ", "coffee!", "coffee?!"]
        normalized = {normalize_topic(v) for v in variants}
        assert normalized == {"coffee"}

    def test_dedup_multiword(self):
        a = normalize_topic("The Silk Road!")
        b = normalize_topic("  silk   road  ")
        assert a == b == "silk road"

    def test_strips_accents(self):
        assert normalize_topic("Café") == "cafe"

    def test_drops_short_words(self):
        assert normalize_topic("a of the tea") == "tea"

    def test_empty_and_garbage(self):
        assert normalize_topic("") == ""
        assert normalize_topic("!!! ???") == ""
        assert normalize_topic("a") == ""

    def test_numbers_kept(self):
        assert normalize_topic("World War 2") == "world war 2"

    def test_stopwords_dropped(self):
        assert normalize_topic("The History of Coffee") == "history coffee"


class TestCacheKey:
    def test_basic_key(self):
        assert cache_key("coffee", 10, "male", "en") == "coffee|10|male|en"

    def test_voice_and_language_normalized(self):
        assert cache_key("coffee", 10, "MALE", "EN") == "coffee|10|male|en"

    def test_distinct_lengths(self):
        keys = {cache_key("coffee", m, "male", "en") for m in (10, 30, 60)}
        assert len(keys) == 3

    def test_distinct_voices(self):
        assert cache_key("coffee", 10, "male", "en") != cache_key("coffee", 10, "female", "en")

    def test_distinct_languages(self):
        assert cache_key("coffee", 10, "male", "en") != cache_key("coffee", 10, "male", "fr")

    def test_full_dedup_identity(self):
        """(normalized topic + length + voice + language) is the dedup identity."""
        k1 = cache_key(normalize_topic("Coffee!"), 30, "female", "EN")
        k2 = cache_key(normalize_topic("  coffee "), 30, "female", "en")
        assert k1 == k2

    def test_different_topics_differ(self):
        assert cache_key("coffee", 10, "male", "en") != cache_key("tea", 10, "male", "en")


class TestSlugify:
    def test_kebab(self):
        assert slugify("The World Before Coffee!") == "the-world-before-coffee"

    def test_collapses_dashes(self):
        assert slugify("a -- b") == "a-b"
