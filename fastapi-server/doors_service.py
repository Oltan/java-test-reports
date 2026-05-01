import os
import subprocess
import tempfile

DOORS_PATH = r"C:\Program Files\IBM\DOORS\9.7\bin\doors.exe"


def is_doors_available():
    return os.path.exists(DOORS_PATH)


def run_doors_dxl(script_content: str):
    """Run DXL script via doors.exe. Returns (returncode, stdout, stderr)."""
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