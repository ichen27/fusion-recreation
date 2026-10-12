"""Run independent dependency-free probe suites from any checkout."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
for directory in sorted((root / "experiments").iterdir()):
    if directory.is_dir() and list(directory.glob("test_*.py")):
        print("\nTesting " + directory.name, flush=True)
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-v"], cwd=directory, check=True)
