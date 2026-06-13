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
