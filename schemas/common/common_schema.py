from typing import Literal


DocsCode = Literal["SRS", "INTERFACE", "ERD", "DB", "ARCH", "TS"]
UpdateYn = Literal["Y", "N"]
WorkflowStatus = Literal["READY", "RUNNING", "RETRY", "FAILED", "DONE"]
NextAction = Literal["SUPERVISOR", "CONTINUE", "REPLAN", "REDUCE", "EXPORT", "END"]
