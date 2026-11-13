"""Forwarder to test_filter_engine.py for backward compatibility."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_filter_engine import (
    test_experience_filtering,
    test_title_blacklist,
    test_company_blacklist,
    test_date_freshness,
    test_categorization,
    test_full_pipeline_evaluation,
)

if __name__ == "__main__":
    print("\nRunning Fresher Job Scraper Test Suite (tests/test_filter.py)...")
    test_experience_filtering()
    test_title_blacklist()
    test_company_blacklist()
    test_date_freshness()
    test_categorization()
    test_full_pipeline_evaluation()
    print("\nALL FILTER TESTS PASSED SUCCESSFULLY!\n")
