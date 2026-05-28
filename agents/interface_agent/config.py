import json
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()

INPUT_DIR = Path(os.getenv("INTERFACE_INPUT_DIR", "./data/interface"))
REQUIREMENT_DIR = Path(os.getenv("INTERFACE_REQUIREMENT_DIR", str(INPUT_DIR / "requirements")))
PROTOTYPE_DIR = Path(os.getenv("INTERFACE_PROTOTYPE_DIR", str(INPUT_DIR / "prototypes")))
OUTPUT_DIR = Path(os.getenv("INTERFACE_OUTPUT_DIR", "./output/interface"))
WORK_DIR = Path(os.getenv("INTERFACE_WORK_DIR", "./json_temp/interface"))

SUPPORTED_REQUIREMENT_JSON_EXTS = {".json"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

MODEL_ID = os.getenv("INTERFACE_VLM_MODEL_ID", "Qwen/Qwen2-VL-2B-Instruct")

MAX_NEW_TOKENS_SCREEN = int(os.getenv("INTERFACE_MAX_NEW_TOKENS_SCREEN", "1536"))
MAX_NEW_TOKENS_FINAL = int(os.getenv("INTERFACE_MAX_NEW_TOKENS_FINAL", "1024"))

OUTPUT_DOCX_PATH = Path(
    os.getenv(
        "INTERFACE_OUTPUT_DOCX_PATH",
        str(OUTPUT_DIR / "사용자 인터페이스 설계서.docx"),
    )
)
