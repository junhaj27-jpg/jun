import os

# Ollama 설정
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL_NAME = "qwen2.5:7b"

# 재시도 및 제약조건 설정
MAX_RETRIES = 3