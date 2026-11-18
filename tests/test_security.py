import subprocess
import sys
from pathlib import Path


def test_source_audit_passes_current_checkout():
    subprocess.run([sys.executable, "scripts/audit_public_files.py"], check=True)


def test_static_audit_detects_forbidden_import_in_either_form():
    sys.path.insert(0, str(Path("scripts").resolve()))
    try:
        from audit_public_files import inspect_python

        sdk = "Meta" + "Trader5"
        assert inspect_python(f"import {sdk}")
        assert inspect_python(f"from {sdk} import something")
        assert not inspect_python("from decimal import Decimal")
    finally:
        sys.path.pop(0)
