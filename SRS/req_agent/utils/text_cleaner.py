import re

def clean_minutes(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"[^\S\n]+|[\x00-\x08\x0b-\x0c\x0e-\x1f\ufeff]", " ", text)
    text = re.sub(r"\[?\d{2}:\d{2}(:\d{2})?\]?", "", text)   # 타임스탬프
    text = re.sub(r"[ \t]+",  " ",    text)
    text = re.sub(r"\n{3,}",  "\n\n", text)
    text = re.sub(r"\.{4,}",  "...",  text)
    return text.strip()