# interface_agent

`interface_quick_test.ipynb`의 최신 로직을 Python 모듈로 분리한 패키지입니다.

## 실행

기본 실행은 프로토타입 이미지 1장만 분석합니다.

```powershell
C:\Users\Playdata\miniconda3\envs\nlp_env\python.exe C:\SKN24\final_interface\run_full.py
```

## import 사용

```python
from pathlib import Path
from interface_agent.pipeline import run_ui_design_agent

output_docx_path, requirement_summary, ui_structure, screen_specs = run_ui_design_agent(
    requirement_json_paths=Path("./input"),
    image_paths=Path("./input"),
    output_docx_path=Path("./output/사용자_인터페이스_설계서.docx"),
    max_images=1,
)
```

전체 이미지를 처리하려면 `max_images=None`을 사용합니다.
