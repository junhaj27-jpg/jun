from agents.interface_agent.config import *

model = None
processor = None


def load_qwen_vl(model_id: str = MODEL_ID):
    """Qwen2-VL 모델과 프로세서를 로드해 추론 준비 상태로 반환합니다."""
    import importlib.util
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor
    try:
        from transformers import Qwen2VLForConditionalGeneration
    except ImportError:
        Qwen2VLForConditionalGeneration = None

    print(f"Loading model: {model_id}")
    try:
        loaded_processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

        use_cuda = torch.cuda.is_available()
        has_accelerate = importlib.util.find_spec("accelerate") is not None

        if use_cuda:
            dtype = torch.bfloat16
            device_map = "auto" if has_accelerate else None
        else:
            dtype = torch.float32
            device_map = None

        model_cls = Qwen2VLForConditionalGeneration or AutoModelForImageTextToText
        loaded_model = model_cls.from_pretrained(
            model_id,
            torch_dtype=dtype,
            device_map=device_map,
            trust_remote_code=True,
        )
        if use_cuda and device_map is None:
            loaded_model = loaded_model.to("cuda")
        loaded_model.eval()
        return loaded_model, loaded_processor
    except Exception as e:
        raise RuntimeError(
            "Qwen2-VL 모델 로드에 실패했습니다. 인터넷 연결, 모델 다운로드 권한, "
            f"GPU/메모리 상태를 확인하세요. 원인: {e}"
        ) from e


def ensure_model_loaded(model_id: str = MODEL_ID):
    """전역 모델과 프로세서를 최초 호출 시 한 번만 로드합니다."""
    global model, processor
    if model is None or processor is None:
        model, processor = load_qwen_vl(model_id)
    return model, processor


def qwen_generate_text(prompt: str, max_new_tokens: int = 2048) -> str:
    """텍스트 프롬프트를 모델에 전달하고 생성 결과 문자열을 반환합니다."""
    import torch

    loaded_model, loaded_processor = ensure_model_loaded()
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    text = loaded_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = loaded_processor(text=[text], padding=True, return_tensors="pt")

    if torch.cuda.is_available():
        inputs = inputs.to(loaded_model.device)

    with torch.no_grad():
        generated_ids = loaded_model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)

    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    return loaded_processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()


def qwen_analyze_image(image_path: Path, prompt: str, max_new_tokens: int = 2048) -> str:
    """이미지와 프롬프트를 함께 모델에 전달해 화면 분석 결과를 생성합니다."""
    import torch
    from PIL import Image

    loaded_model, loaded_processor = ensure_model_loaded()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": str(image_path)},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    text = loaded_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image = Image.open(image_path).convert("RGB")

    inputs = loaded_processor(
        text=[text],
        images=[image],
        padding=True,
        return_tensors="pt",
    )

    if torch.cuda.is_available():
        inputs = inputs.to(loaded_model.device)

    with torch.no_grad():
        generated_ids = loaded_model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)

    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    return loaded_processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()


def extract_json_from_text(text: str) -> Any:
    """모델 응답에서 JSON 객체 또는 배열 부분만 찾아 파싱합니다."""
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    first_obj = text.find("{")
    first_arr = text.find("[")
    candidates = [i for i in [first_obj, first_arr] if i != -1]
    if not candidates:
        raise ValueError("JSON 시작 문자를 찾지 못했습니다.")

    start = min(candidates)
    end_obj = text.rfind("}")
    end_arr = text.rfind("]")
    end = max(end_obj, end_arr)
    if end == -1:
        raise ValueError("JSON 종료 문자를 찾지 못했습니다.")

    return json.loads(text[start:end + 1])


def parse_or_repair_json(raw: str, context: str, max_new_tokens: int = 1024) -> Any:
    """모델 출력 JSON 파싱에 실패하면 원문 의미를 유지해 JSON 문법만 복구합니다."""
    try:
        return extract_json_from_text(raw)
    except Exception as first_error:
        repair_prompt = f"""
다음 텍스트는 {context}로 생성된 모델 응답이지만 JSON 문법이 깨졌을 수 있습니다.
원문에 없는 업무 내용은 새로 만들지 말고, 원문에 있는 정보만 유지해서 유효한 JSON 하나로 복구하라.
누락된 선택 필드는 빈 문자열, 빈 배열 또는 null로 둔다.
출력이 너무 길면 원문 앞쪽의 핵심 항목만 유지하고 배열 항목 수를 줄여라.
마크다운, 설명, 코드블록 없이 JSON만 출력하라.

[깨진 모델 응답]
{raw[:12000]}
"""
        repaired = qwen_generate_text(repair_prompt, max_new_tokens=max(max_new_tokens, 2048))
        try:
            return extract_json_from_text(repaired)
        except Exception as second_error:
            print("JSON 복구 실패. 원본 출력 일부:")
            print(raw[:1500])
            print("JSON 복구 출력 일부:")
            print(repaired[:1500])
            raise second_error from first_error
