import json
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

INPUT_DIR = Path("./input")
OUTPUT_DIR = Path("./output")
WORK_DIR = Path("./work")

SUPPORTED_REQUIREMENT_JSON_EXTS = {".json"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

MODEL_ID = "Qwen/Qwen2-VL-2B-Instruct"

MAX_NEW_TOKENS_SCREEN = 1536
MAX_NEW_TOKENS_FINAL = 1024

OUTPUT_DOCX_PATH = OUTPUT_DIR / "사용자_인터페이스_설계서.docx"
