# Requirements SLLM Agent

운영용 모듈 패키지입니다. 평가 기능은 포함하지 않으며, TASK1 원자 분해 → TASK2 내부 정규화 → 임베딩 후보 검색 → TASK3 GOLD 생성을 수행합니다.

기본 모델을 Core 프로세스에 다시 적재하지 않고 OpenAI 호환 vLLM의 LoRA 모델을 호출합니다.
vLLM에는 `req-stage1`, `req-stage3` 이름으로 어댑터가 등록되어 있어야 합니다.

```env
LLM_BASE_URL=http://127.0.0.1:8002/v1
LLM_API_KEY=dummy
REQ_STAGE1_SERVED_MODEL=req-stage1
REQ_STAGE3_SERVED_MODEL=req-stage3
REQ_VLLM_CONTEXT_LIMIT=32768
```

```bash
pip install -e .
python -m requirements_gold_agent --input /workspace/test_input/DOC-001_기능전체_입력.json
```

```python
from requirements_gold_agent import RequirementsGenerationService
service = RequirementsGenerationService.get_instance()
service.warmup()
result = service.generate_from_dict(payload, job_id="job-123")
```


## 로컬 단독 실행

압축 해제 후 프로젝트 루트에서 실행합니다.

```bash
cd requirements_gold_agent_v1
pip install -r requirements.txt
python run.py --input examples/input_sample.json --output-dir ./outputs
```

폴더 단위 실행:

```bash
python run.py --input /workspace/test_inputs --output-dir ./outputs --glob "*_기능전체_입력.json"
```

패키지 CLI로도 실행할 수 있습니다.

```bash
python -m requirements_gold_agent --input examples/input_sample.json --output-dir ./outputs
```

editable 설치 후 콘솔 명령으로도 실행할 수 있습니다.

```bash
pip install -e .
requirements-gold-agent --input examples/input_sample.json --output-dir ./outputs
```
