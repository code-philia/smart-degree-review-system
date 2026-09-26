import re
import unicodedata


LABEL = r"(?P<number>[A-Z]?\d+(?:[.\-]\d+)*)"
FIGURE_CAPTION = re.compile(rf"^\s*(?:图|Figure|Fig\.?)\s*{LABEL}(?:\s+|[、:：.])\s*\S", re.I)
TABLE_CAPTION = re.compile(rf"^\s*(?:表|Table)\s*{LABEL}(?:\s+|[、:：.])\s*\S", re.I)
FIGURE_REFERENCE = re.compile(rf"(?:图|Figure|Fig\.?)\s*{LABEL}", re.I)
TABLE_REFERENCE = re.compile(rf"(?:表|Table)\s*{LABEL}", re.I)
APPENDIX_HEADING = re.compile(r"^\s*附录\s*(?P<number>[A-Z])(?:\s|[:：]|$)", re.I)
APPENDIX_REFERENCE = re.compile(r"附录\s*(?P<number>[A-Z])", re.I)
DOT_LEADER = re.compile(r"(?:\.{2,}|…{2,}|·{2,})\s*\d+\s*$")


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("－", "-")


def normalize_label(value: str) -> str:
    return normalize_text(value).upper().replace("-", ".")


def is_toc_line(text: str) -> bool:
    normalized = normalize_text(text).strip()
    return bool(DOT_LEADER.search(normalized)) or normalized.startswith(("图目录", "表目录", "插图目录"))

