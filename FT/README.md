# RFP 요구사항 명세서 생성 Fine-tuning Model

공공기관 제안요청서(RFP)의 기능 요구사항(FUR/SFR)을 입력받아  
검수 가능한 최종 요구사항 명세서 JSON을 자동 생성하는 멀티태스킹 Fine-tuning 모델입니다.

본 프로젝트는 SDLC 산출물 작성 에이전트의 **요구사항 정의 단계**에 적용하기 위한 모델로,  
RFP 문서 안에 섞여 있는 복수 요구사항, 예외조건, 참고문구를 의미 기반으로 분해하고  
중복·부분중복·상하위 관계를 판단하여 표준화된 요구사항 명세서를 생성하는 것을 목표로 합니다.

---

## 1. 프로젝트 목적

RFP의 기능 요구사항 문단에는 여러 수행 행위와 조건이 하나의 문장 또는 항목 안에 혼재되어 있습니다.

예를 들어 하나의 FUR 안에 다음과 같은 내용이 동시에 포함될 수 있습니다.

- 등록 / 수정 / 삭제 / 조회
- 권한 조건
- 외부 시스템 연계
- 대시보드 조회
- 알림 제공
- 통계 및 리포트 생성
- 표준 준수 조건
- 검수 기준이 다른 기능

본 모델은 이러한 요구사항을 다음 단계로 처리합니다.

1. 독립 요구사항 단위로 의미 기반 분해
2. 같은 FUR 내부의 유사 요구사항 정규화 및 병합
3. 문서 전체 범위에서 중복, 부분중복, 상위·하위 관계 판단
4. 최종 요구사항 명세서 JSON 생성

---

## 2. 주요 기능

- RFP 기능 요구사항 JSON 입력 처리
- FUR/SFR 단위의 독립 요구사항 분해
- 과분해 방지 및 의미 기반 결합
- 요구사항명 / 상세내용 / 수행행위 표준화
- 문서 전체 범위의 중복 제거
- 부분중복 및 상하위 관계 판단
- 최종 GOLD 요구사항 명세서 생성
- source, source_task2_ids, source_atomic_ids 기반 추적성 제공
- LoRA Adapter 기반 운영 적용
- 요구사항 생성 에이전트에만 파인튜닝 Adapter 선택 적용

---

## 3. 입력 / 출력 구조

### Input

```json
{
  "document_id": "DOC-001",
  "document_name": "RFP 기능 요구사항",
  "functional_requirements": [
    {
      "requirement_id": "FUR-001",
      "requirement_name": "통합 게시판 관리",
      "requirement_type": "기능",
      "requirement_definition": "공지사항과 문의 게시글을 통합 관리한다.",
      "requirement_detail": "공지사항, FAQ, 문의 게시글을 등록·수정·삭제·조회할 수 있어야 한다."
    }
  ],
  "scope_reference_requirements": []
}
```

### Output

```json
{
  "output_type": "GOLD_REQUIREMENT_SPECIFICATION",
  "document_id": "DOC-001",
  "gold_requirement_specification": [
    {
      "requirement_id": "GOLD-001",
      "requirement_type": "기능",
      "action_type": "관리",
      "requirement_name": "통합 게시판 콘텐츠 관리 기능",
      "requirement_detail": "공지사항, FAQ, 문의 게시글을 등록·수정·삭제·조회할 수 있어야 한다.",
      "source": ["FUR-001"],
      "source_task2_ids": ["T2-001"],
      "source_atomic_ids": ["FUR-001::A-001"],
      "processing_type": "KEPT"
    }
  ]
}
```

---

## 4. 학습 개요

| 항목 | 내용 |
|---|---|
| 기반 모델 | `Qwen/Qwen3-VL-8B-Instruct` |
| 학습 방식 | QLoRA 기반 LoRA Adapter 미세조정 |
| 양자화 | 4bit NF4 + double quant + bfloat16 compute |
| 파인튜닝 대상 | 요구사항 생성 Agent |
| 원천 데이터 | RFP 기능 요구사항 문서 21개 |
| 원본 요구사항 규모 | FUR/SFR 290건 |
| 데이터셋 형식 | ChatML JSONL / Parquet |
| 실행 환경 | RunPod GPU A100 기반 |
| 저장 형식 | Hugging Face PEFT LoRA Adapter |

---

## 5. Fine-tuning Task 구조

본 모델은 요구사항 생성을 하나의 단일 생성 문제가 아니라  
단계별 판단이 필요한 멀티태스킹 문제로 정의합니다.

### TASK 1. 독립 요구사항 분해

RFP의 각 기능 요구사항 내부에서 여러 수행 행위가 섞여 있는 경우,  
검수 가능한 독립 요구사항 단위로 분해합니다.

예시:

```text
공지사항, FAQ, 문의 게시글을 등록·수정·삭제·조회할 수 있어야 한다.
```

출력 예시:

```json
{
  "atomic_requirements": [
    {
      "atomic_id": "FUR-001::A-001",
      "action_type": "관리",
      "output_name": "통합 게시판 콘텐츠 관리 기능"
    }
  ]
}
```

---

### TASK 2. Local 정규화 / 병합

같은 FUR 내부에서 생성된 독립 요구사항 후보를 대상으로  
중복, 과분해, 표현 차이를 정리하고 요구사항명과 상세내용을 표준화합니다.

주요 역할:

- 유사 독립 요구사항 결합
- 과분해된 항목 재병합
- 수행행위 표준화
- 요구사항명 정규화
- 상세내용 문장화

---

### TASK 3. Global 중복 제거 / 최종화

문서 전체 요구사항 후보를 대상으로  
중복, 부분중복, 상위·하위 관계를 판단하여 최종 GOLD 요구사항 명세서를 생성합니다.

주요 역할:

- 문서 전체 범위의 중복 제거
- 부분중복 판단
- 상위·하위 관계 판단
- 관련은 있지만 검수 기준이 다른 요구사항 분리
- 최종 요구사항 ID 생성
- source 계보 유지

---

## 6. 학습 단계 설계

Fine-tuning은 커리큘럼 학습 방식으로 구성됩니다.

### Stage 1. Core 학습

Task1, Task2, Task3 AUX 데이터를 혼합하여 학습합니다.

| 항목 | 내용 |
|---|---|
| 학습 데이터 | Task1 + Task2 + Task3 AUX |
| 역할 | 분해, 정규화, 짧은 관계판정 기초 학습 |
| 입력 길이 | 약 1만 토큰 이하 |
| 권장 GPU | 24GB 이상 |
| 저장 Adapter | Stage1 Core Adapter |

Task3 AUX는 문서 전체가 아니라  
2~8개 Task2 후보 그룹을 대상으로 관계 판정을 학습하는 보조 데이터입니다.

---

### Stage 2. Gold Finalizer 학습

Stage1 Adapter를 이어서 학습하여  
문서 전체 범위의 최종 요구사항 생성 패턴을 학습합니다.

| 항목 | 내용 |
|---|---|
| 학습 데이터 | Task3 문서 전체 Primary |
| 역할 | 전역 중복 제거, 의미 병합, 상하위 판단, 최종 요구사항 명세서 생성 |
| 입력 길이 | 최대 약 11만 토큰 |
| 권장 GPU | 80GB 이상 |
| 저장 Adapter | Gold Finalizer Adapter |

---

## 7. 학습 데이터 요약

| 구분 | 수량 | 의미 |
|---|---:|---|
| RFP 문서 | 21개 | 문서 단위 |
| 원본 기능 요구사항 | 290건 | FUR/SFR 단위 |
| Task1 | 1,843건 | 기능 수행 행위 의미·검수 기준으로 분해된 최소 기능 단위 |
| Task2 | 1,381건 | FUR 내부 결합·문체 정규화 결과 |
| Task3 | 1,165건 | 문서 전체 전역 중복·부분중복·상하위 병합 결과 |

---

## 8. 학습 Row 구성

| Stage | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| Stage 1 Core | 2,190 | 459 | 477 | 3,126 |
| Stage 2 Gold Finalizer | 15 | 3 | 3 | 21 |

---

## 9. Hyperparameter

| 항목 | Stage 1 | Stage 2 |
|---|---|---|
| 기반 모델 | Qwen/Qwen3-VL-8B-Instruct | Qwen/Qwen3-VL-8B-Instruct + Stage1 Adapter |
| 학습 방식 | QLoRA | QLoRA 누적 학습 |
| 양자화 | 4bit NF4 + double quant + bf16 compute | 4bit NF4 + double quant + bf16 compute |
| LoRA r | 16 | 16 |
| LoRA alpha | 32 | 32 |
| LoRA dropout | 0.05 | 0.05 |
| Epoch | 2 | 5 |
| Gradient Accumulation | 8 | 1 |
| 역할 | 분해·정규화·기초 관계판정 | 문서 전체 범위 검토 |

Stage 1은 표본 수가 많기 때문에 비교적 안정적인 업데이트가 가능하지만,  
Stage 2는 문서 전체 학습 row 수가 적어 과적합 위험이 큽니다.

따라서 특정 문서의 요구사항명, source ID, JSON 배열 순서, 문장 표현에 과적합되지 않도록  
Stage 2의 epoch는 낮게 유지하였습니다.

---

## 10. 학습 적용 후 요구사항 생성 결과

테스트 문서 기준으로 요구사항 수는 다음과 같이 변화했습니다.

| 문서 | 입력 요구사항 수 | TASK1 | TASK2 | TASK3 | 변화 |
|---|---:|---:|---:|---:|---|
| DOC-001 | 17 | 152 | 122 | 99 | 17 → 152 → 122 → 99 |
| DOC-003 | 10 | 27 | 27 | 19 | 10 → 27 → 27 → 19 |
| DOC-021 | 12 | 64 | 51 | 25 | 12 → 64 → 51 → 25 |

이를 통해 모델이 원본 FUR/SFR을 독립 요구사항 후보로 확장한 뒤,  
정규화 및 전역 병합을 통해 최종 요구사항 명세서 수준으로 압축하는 흐름을 확인할 수 있습니다.

---

## 11. 평가 방식

파인튜닝 모델의 출력은 ChatGPT 5.5 기반 정답 요구사항 명세서와 비교하여 평가했습니다.

요구사항 생성은 정답 문장을 그대로 복사하는 문제가 아니라  
동일 의미를 다른 문장 구조로 재작성하는 추상적 생성 문제입니다.

따라서 표면 일치 지표와 의미 기반 지표를 함께 사용했습니다.

| 지표 | 설명 |
|---|---|
| Semantic Precision / Recall / F1 | 예측 요구사항과 정답 요구사항을 임베딩하여 cosine similarity 0.8 이상에서 1:1 매칭 |
| ROUGE-1 | 단어 단위 1-Gram 겹침 정도 |
| ROUGE-2 | 연속된 두 단어 2-Gram 겹침 정도 |
| ROUGE-L | LCS 기반 문장 구조 유사도 |
| BLEU-4 | 생성 문장이 정답 문장에 포함되는 정도 |
| Token-F1 | 토큰 단위 표면 일치도 |
| 평균 매칭 코사인 | 매칭된 예측-정답 쌍의 평균 의미 유사도 |

---

## 12. 의미론적 평가 결과

| 문서 | 예측 | 정답 | Semantic Precision | Semantic Recall | Semantic F1 |
|---|---:|---:|---:|---:|---:|
| DOC-001 | 99 | 136 | 1.00 | 0.7279 | 0.8426 |
| DOC-003 | 19 | 20 | 1.00 | 0.9500 | 0.9744 |
| DOC-021 | 25 | 28 | 1.00 | 0.8929 | 0.9434 |
| Macro Average | - | - | 1.00 | 0.8569 | 0.9201 |

### 해석

- 모든 테스트 문서에서 Semantic Precision이 1.00으로 측정되었습니다.
- 이는 정답에 없는 요구사항을 불필요하게 생성하지 않았다는 의미입니다.
- 평균 Semantic Recall은 0.8569로, 정답 요구사항의 약 86%를 포착했습니다.
- 평균 Semantic F1은 0.9201로 측정되었습니다.
- 일부 문서에서는 예측 수가 정답 수보다 적어 누락 경향이 확인되었습니다.

---

## 13. 텍스트 생성 평가 결과

| 문서 | ROUGE-1 | ROUGE-2 | ROUGE-L | BLEU-4 | Token-F1 | 평균 매칭 코사인 |
|---|---:|---:|---:|---:|---:|---:|
| DOC-001 | 0.3929 | 0.1740 | 0.3735 | 0.0760 | 0.3929 | 0.9479 |
| DOC-003 | 0.4252 | 0.2330 | 0.4068 | 0.1063 | 0.4252 | 0.9533 |
| DOC-021 | 0.2960 | 0.1099 | 0.2760 | 0.0243 | 0.2960 | 0.9351 |
| Average | 0.3714 | 0.1723 | 0.3521 | 0.0689 | 0.3714 | 0.9454 |

### 해석

ROUGE와 BLEU 같은 표면 일치 지표는 낮은 편입니다.  
그러나 매칭된 요구사항 쌍의 평균 코사인 유사도는 0.9454로 높게 측정되었습니다.

이는 모델이 정답과 동일한 의미를 유지하면서도  
다른 어휘와 문장 구조로 요구사항을 재작성하고 있음을 의미합니다.

따라서 본 모델의 성능 평가는 표면 일치 지표보다  
Semantic F1과 평균 매칭 코사인을 중심으로 해석하는 것이 적절합니다.

---

## 14. 모델 저장 및 운영 방식

| 항목 | 설명 |
|---|---|
| 기반 모델 | `Qwen/Qwen3-VL-8B-Instruct` |
| Stage1 Adapter | `req-qwen3vl-stage1-core` |
| Stage2 / Gold Adapter | `req-qwen3vl-stage2-gold` 또는 기존 stage3 repo alias |
| 저장 형식 | Hugging Face LoRA / PEFT Adapter |
| 운영 패키지 | `requirements-gold-agent` |
| 운영 방식 | Base Model + Adapter 로드 후 요구사항 생성 요청에서 Adapter 활성화 |

---

## 15. 모델 로드 예시

```python
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration
from peft import PeftModel
import torch
import os

BASE_MODEL_REPO = "Qwen/Qwen3-VL-8B-Instruct"
STAGE1_ADAPTER_REPO = "jaehoony/req-qwen3vl-stage1-core"
STAGE2_GOLD_ADAPTER_REPO = "jaehoony/req-qwen3vl-stage2-gold"

HF_TOKEN = os.environ.get("HF_TOKEN")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16
)

processor = AutoProcessor.from_pretrained(
    BASE_MODEL_REPO,
    token=HF_TOKEN,
    trust_remote_code=True
)

base_model = Qwen3VLForConditionalGeneration.from_pretrained(
    BASE_MODEL_REPO,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
    token=HF_TOKEN,
    trust_remote_code=True
)

model = PeftModel.from_pretrained(
    base_model,
    STAGE1_ADAPTER_REPO,
    adapter_name="stage1",
    token=HF_TOKEN
)

model.load_adapter(
    STAGE2_GOLD_ADAPTER_REPO,
    adapter_name="stage2_gold",
    token=HF_TOKEN
)

model.eval()
```

---

## 16. 운영 적용 방식

운영 환경에서는 전체 모델을 여러 개 두지 않고,  
Qwen3-VL 기반 모델 1개에 LoRA Adapter를 붙이는 방식으로 운영합니다.

요구사항 생성 에이전트에서는 Adapter를 활성화하고,  
그 외 산출물 생성 에이전트에서는 Adapter를 비활성화하여 기본 모델을 사용할 수 있습니다.

| 요청 유형 | Adapter | 결과 |
|---|---|---|
| 요구사항 생성 에이전트 | ON | Fine-tuning 적용 |
| 나머지 산출물 에이전트 | OFF | 기본 모델 사용 |

예시:

```python
# 요구사항 생성: Adapter ON
out = model.generate(...)

# 기타 산출물 생성: Adapter OFF
with model.disable_adapter():
    out = model.generate(...)
```

---

## 17. 프로젝트 활용 방안

본 모델은 SDLC 산출물 작성 에이전트의 요구사항 정의 단계에 적용할 수 있습니다.

주요 활용 시나리오는 다음과 같습니다.

1. RFP 업로드
2. 기능 요구사항 JSON 추출
3. 요구사항 생성 Agent 호출
4. Task1 독립 요구사항 분해
5. Task2 Local 정규화
6. Task3 Global 중복 제거 및 최종화
7. 최종 요구사항 명세서 JSON 생성
8. 사용자 요구사항 명세서 DOCX / Excel / JSON 산출물 생성

---

## 18. 종합 평가

본 모델은 테스트 문서 기준으로 높은 의미 정밀도와 의미 충실성을 보였습니다.

### 장점

- 정답에 없는 요구사항을 거의 생성하지 않음
- Semantic Precision 1.00 달성
- 평균 Semantic F1 0.9201
- 평균 매칭 코사인 0.9454
- 요구사항 source 계보 유지
- JSON 구조화 출력 가능
- LoRA Adapter 기반으로 운영 적용 용이

### 개선 필요 사항

- 일부 문서에서 정답 요구사항 누락 발생
- DOC-001처럼 입력 범위가 넓은 문서에서 재현율 저하
- 문서 전체 Task3 학습 데이터 수가 적어 추가 데이터 확보 필요
- 운영 시 RAG 검증 또는 누락 보강 단계 필요

---

## 19. 향후 개선 방향

- Task3 문서 전체 학습 데이터 추가 확보
- 긴 입력 문서에 대한 동적 청크 전략 개선
- 재현율 향상을 위한 누락 검증 Agent 추가
- source coverage 검증 로직 강화
- 중복 제거 결과에 대한 relation_decisions 로그 고도화
- H200 기반 장문 추론 및 운영 테스트
- 요구사항명 / 상세내용 문체 표준화 규칙 보강
- RAG 기반 법령·지침 검증 단계 연계


