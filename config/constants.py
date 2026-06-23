from enum import StrEnum


class DocsCode(StrEnum):
    SRS = "SRS"
    INTERFACE = "INTERFACE"
    ERD = "ERD"
    DB = "DB"
    ARCH = "ARCH"
    TS = "TS"


class UpdateYn(StrEnum):
    YES = "Y"
    NO = "N"


class WorkflowStatus(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    RETRY = "RETRY"
    FAILED = "FAILED"
    DONE = "DONE"


class NextAction(StrEnum):
    SUPERVISOR = "SUPERVISOR"
    CONTINUE = "CONTINUE"
    REPLAN = "REPLAN"
    REDUCE = "REDUCE"
    EXPORT = "EXPORT"
    END = "END"


class DocsProgressStatus(StrEnum):
    READY = "READY"
    GENERATING = "GENERATING"
    FAILED = "FAILED"
    DONE = "DONE"


DOCS_CODES = tuple(code.value for code in DocsCode)
UPDATE_YN_VALUES = tuple(value.value for value in UpdateYn)

DOCS_CODE_DB_MAP = {
    DocsCode.SRS.value: "DOC_SRS",
    DocsCode.INTERFACE.value: "DOC_ITF",
    DocsCode.ERD.value: "DOC_ERD",
    DocsCode.DB.value: "DOC_DB",
    DocsCode.ARCH.value: "DOC_ARCH",
    DocsCode.TS.value: "DOC_TS",
}

DB_DOCS_CODE_MAP = {value: key for key, value in DOCS_CODE_DB_MAP.items()}


def normalize_docs_cd(docs_cd: str | DocsCode) -> str:
    value = str(docs_cd or "").strip().upper()
    if value in DOCS_CODES:
        return value
    if value in DB_DOCS_CODE_MAP:
        return DB_DOCS_CODE_MAP[value]

    for prefix in ("DOC_", "DOCS_"):
        if value.startswith(prefix):
            normalized = value.removeprefix(prefix)
            if normalized == "ITF":
                return DocsCode.INTERFACE.value
            if normalized in DOCS_CODES:
                return normalized
    return value

DOCS_PROGRESS_DB_MAP = {
    DocsProgressStatus.READY.value: "PRGRS_PENDING",
    DocsProgressStatus.GENERATING.value: "PRGRS_PROCESSING",
    DocsProgressStatus.DONE.value: "PRGRS_COMPLETED",
    DocsProgressStatus.FAILED.value: "PRGRS_FAILED",
}

DB_DOCS_PROGRESS_MAP = {value: key for key, value in DOCS_PROGRESS_DB_MAP.items()}

FILE_CODE_RFP = "FILE_RFP"
FILE_CODE_MEETING = "FILE_MEETING"
FILE_CODE_REQUIREMENT_JSON = "FILE_REQ_DOC_JSON"
FILE_CODE_INTERFACE_JSON = "FILE_INTERFACE_DOC_JSON"
FILE_CODE_ERD_JSON = "FILE_ERD_DOC_JSON"
FILE_CODE_DB_JSON = "FILE_DB_DOC_JSON"
FILE_CODE_ARCH_JSON = "FILE_ARCH_DOC_JSON"
FILE_CODE_TS_JSON = "FILE_TS_DOC_JSON"
FILE_CODE_GENERATED_DOC = FILE_CODE_REQUIREMENT_JSON

FILE_CODE_DOCUMENT_JSON_MAP = {
    DocsCode.SRS.value: FILE_CODE_REQUIREMENT_JSON,
    DocsCode.INTERFACE.value: FILE_CODE_INTERFACE_JSON,
    DocsCode.ERD.value: FILE_CODE_ERD_JSON,
    DocsCode.DB.value: FILE_CODE_DB_JSON,
    DocsCode.ARCH.value: FILE_CODE_ARCH_JSON,
    DocsCode.TS.value: FILE_CODE_TS_JSON,
}
