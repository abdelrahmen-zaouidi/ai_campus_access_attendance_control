import os
import sys

# Ensure the repository root (where app.py lives) is importable when pytest
# collects tests from the tests/ directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
