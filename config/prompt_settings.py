from pathlib import Path


PROMPT_ROOT = Path("agents")

DOCUMENT_MERGE_PROMPTS = PROMPT_ROOT / "document_merge" / "prompts.py"
REQUIREMENT_GENERATION_PROMPTS = PROMPT_ROOT / "requirement_generation" / "prompts.py"
IMAGE_ANALYSIS_PROMPTS = PROMPT_ROOT / "image_analysis" / "prompts.py"
TEST_SCENARIO_PROMPTS = PROMPT_ROOT / "test_scenario" / "prompts.py"
ARCHITECTURE_ANALYSIS_PROMPTS = PROMPT_ROOT / "architecture_analysis" / "prompts.py"
DATA_STRUCTURE_DESIGN_PROMPTS = PROMPT_ROOT / "data_structure_design" / "prompts.py"


PROMPT_PATHS = {
    "document_merge_agent": DOCUMENT_MERGE_PROMPTS,
    "requirement_generation_agent": REQUIREMENT_GENERATION_PROMPTS,
    "image_analysis_agent": IMAGE_ANALYSIS_PROMPTS,
    "test_scenario_generation_agent": TEST_SCENARIO_PROMPTS,
    "architecture_analysis_agent": ARCHITECTURE_ANALYSIS_PROMPTS,
    "data_structure_design_agent": DATA_STRUCTURE_DESIGN_PROMPTS,
}
