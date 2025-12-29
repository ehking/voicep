import os
import re
import unicodedata
from typing import Iterable, List, Optional

from loguru import logger

from .settings import settings

NORMALIZE_MAP = {
    "ي": "ی",
    "ئ": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "أ": "ا",
    "إ": "ا",
    "ؤ": "و",
    "ٱ": "ا",
    "ٰ": "",
    "‍": "",
    "ـ": "",
}

FILLERS = {
    "مثلا",
    "خب",
    "یعنی",
    "دیگه",
    "اه",
    "اوه",
    "راستش",
    "آها",
    "مثلا",
    "خب که",
}

CLITIC_EXCEPTIONS = {"پرتو", "آذربایجان", "گفتوگو"}
CLITIC_SUFFIXES = ["تو", "شو", "مو", "مون", "تون", "شون", "رو", "و"]
PERSIAN_LETTERS = re.compile(r"^[آ-ی]+$", re.UNICODE)
TATWEEL_PATTERN = re.compile(r"\u0640+")
COMBINING_MARKS = re.compile(r"[\u064b-\u065f\u0610-\u061a]")
MULTISPACE_PATTERN = re.compile(r"\s+")
FILLER_PATTERN = re.compile(r"(^|\s|[\،\,\؛\;\!\؟\?])(WORD)(?=($|\s|[\،\,\؛\;\!\؟\?]))")

CONFUSION_MAP = {
    "غشنگ": "قشنگ",
    "غشنگه": "قشنگه",
    "غشنگی": "قشنگی",
    "میخوا": "می‌خوام",
    "می خوام": "می‌خوام",
    "میخوام": "می‌خوام",
    "نمیدونم": "نمی‌دونم",
    "نمیدون": "نمی‌دونم",
    "نمیدنم": "نمی‌دونم",
    "ایسر": "عشق",
    "ایسرچه": "عشقت",
    "ایسره": "عشقه",
    "عشقر": "عشق",
    "حسرت": "حسرت",
    "هرروز": "هر روز",
}

KNOWN_GOOD_WORDS = {
    "عشق",
    "لبخند",
    "دل",
    "زندگی",
    "هر",
    "هر",
    "روز",
    "شب",
    "هرروز",
    "هرشب",
    "فاطمه",
    "قشنگ",
    "خونه",
    "نمی‌خوام",
    "می‌خندم",
    "نمی‌دونم",
    "می‌خوام",
    "دوستت",
    "دارم",
    "دوست",
    "احساس",
    "خیلی",
    "زیبا",
    "هستی",
    "می‌خندی",
    "آروم",
}


# Optional MLM
_MLM_PIPELINE = None
if settings.USE_MLM_CORRECTION:
    import importlib.util

    if importlib.util.find_spec("transformers") is not None:
        from transformers import AutoModelForMaskedLM, AutoTokenizer, pipeline

        model_name = os.environ.get("PERSIAN_MLM_MODEL", "HooshvareLab/bert-fa-zwnj-base")
        try:  # pragma: no cover - optional dependency
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForMaskedLM.from_pretrained(model_name)
            _MLM_PIPELINE = pipeline("fill-mask", model=model, tokenizer=tokenizer, top_k=5)
            logger.info(f"Loaded MLM model for correction: {model_name}")
        except Exception as exc:  # pragma: no cover - optional
            logger.warning(f"MLM correction requested but model unavailable: {exc}")
            _MLM_PIPELINE = None
    else:
        logger.warning("MLM correction requested but transformers is not installed")


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    without_marks = COMBINING_MARKS.sub("", without_marks)
    return unicodedata.normalize("NFC", without_marks)


def _normalize_chars(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for src, dst in NORMALIZE_MAP.items():
        text = text.replace(src, dst)
    text = TATWEEL_PATTERN.sub("", text)
    text = _strip_diacritics(text)
    return text


def _remove_fillers(text: str) -> str:
    for filler in FILLERS:
        pattern = FILLER_PATTERN.pattern.replace("WORD", re.escape(filler))
        text = re.sub(pattern, " ", text)
    return text


def _split_clitics(text: str) -> str:
    def replacer(match: re.Match) -> str:
        base, suffix = match.group(1), match.group(2)
        if base in CLITIC_EXCEPTIONS:
            return match.group(0)
        if len(base) <= 2:
            return match.group(0)
        spacer = " "
        suffix_token = "و" if suffix == "و" else suffix
        return f"{base}{spacer}{suffix_token}"

    pattern = re.compile(r"\b([آ-ی]{2,}?)(" + "|".join(CLITIC_SUFFIXES) + r")\b")
    return re.sub(pattern, replacer, text)


def _is_low_quality_token(token: str) -> bool:
    if not token:
        return False
    persian_ratio = sum(1 for ch in token if "آ" <= ch <= "ی") / max(len(token), 1)
    if persian_ratio < 0.6:
        return True
    if re.search(r"[A-Za-z0-9]", token):
        return True
    if not PERSIAN_LETTERS.match(token) and len(token) > 4:
        return True
    if token.count("ه") + token.count("ع") > len(token):
        return True
    return False


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _replace_confusions(tokens: Iterable[str]) -> List[str]:
    cleaned_tokens: List[str] = []
    for tok in tokens:
        base = tok
        lower = tok.strip()
        replacement: Optional[str] = None
        if lower in CONFUSION_MAP:
            replacement = CONFUSION_MAP[lower]
        elif _is_low_quality_token(lower):
            best_word = None
            best_score = 10
            for candidate in KNOWN_GOOD_WORDS.union(CONFUSION_MAP.values()):
                dist = _levenshtein(lower, candidate)
                if dist < best_score:
                    best_score = dist
                    best_word = candidate
            if best_word and best_score <= 2:
                replacement = best_word
        cleaned_tokens.append(replacement or base)
    return cleaned_tokens


def _mlm_correct(tokens: List[str]) -> List[str]:
    if not _MLM_PIPELINE:
        return tokens
    corrected = tokens[:]
    for idx, tok in enumerate(tokens):
        if not _is_low_quality_token(tok):
            continue
        context_start = max(0, idx - 5)
        context_end = min(len(tokens), idx + 6)
        context = tokens[context_start:context_end]
        mask_index = idx - context_start
        context[mask_index] = _MLM_PIPELINE.tokenizer.mask_token
        sentence = " ".join(context)
        try:  # pragma: no cover - optional path
            predictions = _MLM_PIPELINE(sentence)
        except Exception as exc:
            logger.debug(f"MLM correction failed for token '{tok}': {exc}")
            continue
        for candidate in predictions:
            token_str = candidate.get("token_str", "").strip()
            if token_str and PERSIAN_LETTERS.match(token_str) and 1 <= len(token_str) <= max(8, len(tok) + 2):
                corrected[idx] = token_str
                break
    return corrected


def normalize_text(raw: str) -> str:
    if not raw:
        return ""
    text = _normalize_chars(raw)
    text = _remove_fillers(text)
    text = MULTISPACE_PATTERN.sub(" ", text)
    return text.strip()


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = normalize_text(raw)
    text = _split_clitics(text)
    tokens = text.split()
    tokens = _replace_confusions(tokens)
    if settings.USE_MLM_CORRECTION:
        tokens = _mlm_correct(tokens)
    final_text = " ".join(tokens)
    final_text = MULTISPACE_PATTERN.sub(" ", final_text)
    return final_text.strip()


__all__ = ["normalize_text", "clean_text"]
