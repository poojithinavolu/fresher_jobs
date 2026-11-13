"""Consolidated unit tests for company interview research & agentic pipeline."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from company_search.test_dynamic_agentic import TestDynamicAgenticPipeline

if __name__ == "__main__":
    unittest.main()
