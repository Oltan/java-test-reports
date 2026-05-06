import os
import subprocess
import tempfile

DOORS_PATH = r"C:\Program Files\IBM\DOORS\9.7\bin\doors.exe"
DRY_RUN_ENV = "DRY_RUN"
DRY_RUN_TRUE_VALUES = {"1", "true", "yes", "on"}
DOORS_DRY_RUN_RESULT_ENV = "DOORS_DRY_RUN_RESULT"


def is_dry_run_enabled():
    return os.getenv(DRY_RUN_ENV, "false").lower() in DRY_RUN_TRUE_VALUES


def is_doors_available():
    if is_dry_run_enabled():
        return True
    return os.path.exists(DOORS_PATH)


def run_doors_dxl(script_content: str):
    """Run DXL script via doors.exe. Returns (returncode, stdout, stderr)."""
    if is_dry_run_enabled():
        if os.getenv(DOORS_DRY_RUN_RESULT_ENV, "success").lower() == "failure":
            return 1, "", "DOORS dry-run failure requested"
        return 0, "DOORS dry-run export completed", ""

    if not is_doors_available():
        return -1, "", "DOORS not available on this system"

    with tempfile.NamedTemporaryFile(suffix=".dxl", mode="w", delete=False) as f:
        f.write(script_content)
        f.flush()
        result = subprocess.run(
            [DOORS_PATH, "-b", f.name],
            capture_output=True, text=True, timeout=60
        )
    return result.returncode, result.stdout, result.stderr
