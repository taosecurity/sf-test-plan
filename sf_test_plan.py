"""sf-test-plan: turn a Markdown test plan into a checklist page. Run: python sf_test_plan.py --help"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sftestplan.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
