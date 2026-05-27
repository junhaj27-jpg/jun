import base64
import requests
import os
from graph.state import AgentState

def image_generator_node(state: AgentState):
    print("\n==================================================")
    print("[Node] 🎨 Mermaid -> PNG 이미지 변환 및 보고서 최종 조립")
    print("==================================================")
    
    script = state.get("mermaid_script", "")
    report_specs = state.get("report_specs", "")
    
    # 마크다운 래퍼 코드 블록 제거 및 순수 텍스트 정제
    clean_script = script.replace("```mermaid", "").replace("```", "").strip()
    
    if not clean_script:
        print("❌ [오류] 변환할 Mermaid 스크립트가 비어 있습니다.")
        return {"image_path": "변환 실패 (스크립트 없음)"}
        
    try:
        # 1. Mermaid 스크립트를 UTF-8 인코딩 후 Base64 문자열로 변환
        script_bytes = clean_script.encode('utf-8')
        base64_bytes = base64.b64encode(script_bytes)
        base64_string = base64_bytes.decode('utf-8')
        
        # 2. 무료 오픈소스 Mermaid 렌더링 API 호스트 적용
        image_url = f"https://mermaid.ink/img/{base64_string}"
        output_image_path = "output_architecture.png"
        
        # 3. 이미지 다운로드 및 로컬 저장
        response = requests.get(image_url, timeout=15)
        if response.status_code == 200:
            with open(output_image_path, "wb") as f:
                f.write(response.content)
            print(f"✅ 이미지 렌더링 완료 및 로컬 저장 성공: {output_image_path}")
            
            # 4. ★ [하이라이트] 분리되어 있던 명세서(Specs)와 다이어그램 이미지를 하나의 마크다운 리포트로 최종 결합
            final_report_content = (
                f"{report_specs}\n\n"
                f"--- \n\n"
                f"## 📊 3. 시스템 아키텍처 다이어그램\n\n"
                f"### 🖼️ 시각화 아키텍처 뷰 (자동 생성 이미지)\n"
                f"![System Architecture](./{output_image_path})\n\n"
                f"### 📜 원본 Mermaid 소스 코드\n"
                f"```mermaid\n{clean_script}\n```"
            )
            
            final_report_path = "final_architecture_report.md"
            with open(final_report_path, "w", encoding="utf-8") as rf:
                rf.write(final_report_content)
            print(f"🎉 완벽히 조립된 최종 실무 보고서가 생성되었습니다: {final_report_path}")
            
            return {"image_path": output_image_path}
        else:
            print(f"❌ [오류] Mermaid Ink API 응답 에러 (코드: {response.status_code})")
            print(f"❌ RESPONSE: {response})")
            return {"image_path": "변환 실패 (API 에러)"}
            
    except Exception as e:
        print(f"❌ [예외 발생] 이미지 변환 중 알 수 없는 에러: {e}")
        return {"image_path": f"변환 실패 ({str(e)})"}