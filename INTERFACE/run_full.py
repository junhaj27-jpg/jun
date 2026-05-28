import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

from interface_agent.pipeline import run_ui_design_agent
from interface_agent.config import INPUT_DIR, OUTPUT_DOCX_PATH


if __name__ == "__main__":
    run_ui_design_agent(
        requirement_json_paths=INPUT_DIR,
        image_paths=INPUT_DIR,
        output_docx_path=OUTPUT_DOCX_PATH,
        max_images=1,
    )
