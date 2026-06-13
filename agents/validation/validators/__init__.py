from collections.abc import Callable
from typing import Any

from agents.validation.validators.arch_validator import validate as validate_arch
from agents.validation.validators.db_validator import validate as validate_db
from agents.validation.validators.erd_validator import validate as validate_erd
from agents.validation.validators.interface_validator import validate as validate_interface
from agents.validation.validators.srs_validator import validate as validate_srs
from agents.validation.validators.ts_validator import validate as validate_ts
from workflow.state import WorkflowState


Validator = Callable[[WorkflowState], list[dict[str, Any]]]

VALIDATORS: dict[str, Validator] = {
    "SRS": validate_srs,
    "INTERFACE": validate_interface,
    "TS": validate_ts,
    "ERD": validate_erd,
    "DB": validate_db,
    "ARCH": validate_arch,
}

__all__ = ["VALIDATORS"]
