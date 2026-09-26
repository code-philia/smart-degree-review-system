import re
import unicodedata


LABEL = r"(?P<number>(?:[A-Z]\.?)?\d+(?:[.\-]\d+)*)"
FIGURE_CAPTION = re.compile(rf"^\s*(?:图|Figure|Fig\.?)\s*{LABEL}(?:\s+|[、:：.])\s*\S", re.I)
TABLE_CAPTION = re.compile(rf"^\s*(?:表|Table)\s*{LABEL}(?:\s+|[、:：.])\s*\S", re.I)
FIGURE_REFERENCE = re.compile(rf"(?:图|Figure|Fig\.?)\s*{LABEL}", re.I)
TABLE_REFERENCE = re.compile(rf"(?:表|Table)\s*{LABEL}", re.I)
APPENDIX_HEADING = re.compile(r"^\s*附录\s*(?P<number>[A-Z])(?:\s|[:：]|$)", re.I)
APPENDIX_REFERENCE = re.compile(r"附录\s*(?P<number>[A-Z])", re.I)
APPENDIX_QUALIFIER = re.compile(r"附录\s*(?P<number>[A-Z])\s*$", re.I)
APPENDIX_NARRATIVE = re.compile(
    r"^(?:介绍|展示|讨论|描述|给出|包含|列出|参见|详见|可见|说明了|"
    r"使用了|分析了|在|中(?:的|有|给)|里(?:的|有)|所(?:示|述)|是|有|将|为|"
    r"见(?:图|表))"
)
DOT_LEADER = re.compile(r"(?:\.{2,}|…{2,}|·{2,})\s*\d+\s*$")


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("－", "-")


def normalize_label(value: str) -> str:
    return normalize_text(value).upper().replace("-", ".")


def is_toc_line(text: str) -> bool:
    normalized = normalize_text(text).strip()
    return bool(DOT_LEADER.search(normalized)) or normalized.startswith(("图目录", "表目录", "插图目录"))



def is_appendix_heading(text: str, match: re.Match) -> bool:
    """Treat only a short standalone title as a heading, not a body sentence."""
    tail = text[match.end():].strip()
    return (len(text.strip()) <= 80 and
            not re.search(r"[。；;，,]", tail) and
            not APPENDIX_NARRATIVE.match(tail))
