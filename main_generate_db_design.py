from workflows.db_design_workflow import compile_database_design_graph


def main():
    app = compile_database_design_graph()
    result = app.invoke({
        "use_rag": True,
    })

    if result.get("status") != "VALID":
        raise RuntimeError(f"DB 설계서 생성 실패: {result.get('validation_errors', [])}")

    print("[완료] DB 설계 JSON:", result.get("output_json_path"))
    print("[완료] DB 설계서:", result.get("database_design_docx_path"))


if __name__ == "__main__":
    main()
