import re
import unicodedata


NORMALIZE_MAP = {
    "ي": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "أ": "ا",
    "إ": "ا",
    "ؤ": "و",
    "ئ": "ی",
}

FILLERS = [
    "مثلا",
    "خب",
    "یعنی",
    "دیگه",
    "اه",
    "اوه",
    "راستش",
    "آها",
    "خب که",
]

COLLOQUIAL_FIXES = {
    r"\bمی \s*خوام\b": "می‌خوام",
    r"\bنمی \s*خوام\b": "نمی‌خوام",
    r"\bمی \s*تونم\b": "می‌تونم",
    r"\bنمی \s*تونم\b": "نمی‌تونم",
    r"\bمی \s*گم\b": "می‌گم",
    r"\bنمی \s*گم\b": "نمی‌گم",
}


FILLER_PATTERN = re.compile(r"(^|\s|[\،\,\؛\;\!\؟\?])(WORD)(?=($|\s|[\،\,\؛\;\!\؟\?]))")


def normalize_chars(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for src, dst in NORMALIZE_MAP.items():
        text = text.replace(src, dst)
    return text


def remove_fillers(text: str) -> str:
    for filler in FILLERS:
        pattern = FILLER_PATTERN.pattern.replace("WORD", re.escape(filler))
        text = re.sub(pattern, " ", text)
    return text


def apply_colloquial_fixes(text: str) -> str:
    for pattern, replacement in COLLOQUIAL_FIXES.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def clean(raw: str) -> str:
    if not raw:
        return ""
    text = normalize_chars(raw)
    text = remove_fillers(text)
    text = apply_colloquial_fixes(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


__all__ = ["clean"]
