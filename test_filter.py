"""
Backward-compatibility entry point for tests/test_filter_engine.py.
Delegates directly to the consolidated test suite in tests/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS_DIR = ROOT / "tests"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from tests.test_filter_engine import (
    test_experience_filtering,
    test_title_blacklist,
    test_company_blacklist,
    test_date_freshness,
    test_categorization,
    test_full_pipeline_evaluation,
)

if __name__ == "__main__":
    import runpy
    target = Path(__file__).resolve().parent / "tests" / "test_filter_engine.py"
    runpy.run_path(str(target), run_name="__main__")
