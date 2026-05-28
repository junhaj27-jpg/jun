from workflows.erd_workflow import compile_erd_graph


def main():
    app = compile_erd_graph()
    result = app.invoke({
        "use_llm": True,
        "use_mermaid": True,
        "fast_table": False,
    })

    if result.get("status") != "VALID":
        raise RuntimeError(f"ERD 설계서 생성 실패: {result.get('validation_errors', [])}")

    print("[완료] ERD JSON:", result.get("output_json_path"))
    print("[완료] ERD 설계서:", result.get("erd_docx_path"))


if __name__ == "__main__":
    main()
