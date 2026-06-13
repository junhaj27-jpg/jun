import re


def clean_meeting_minutes(text: str) -> str:
    """
    LLM 생성 회의록 Markdown 정제
    """

    # 줄바꿈 통일
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Markdown 헤더 제거
    # ## 제목 -> 제목
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)

    # Markdown 굵게 제거
    # **텍스트** -> 텍스트
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

    # Markdown 구분선 제거
    text = re.sub(r"^\s*-{3,}\s*$", "", text, flags=re.MULTILINE)

    # 연속 공백 정리
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 연속 개행 정리
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()