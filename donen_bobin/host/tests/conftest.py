import sys
from pathlib import Path

HOST = Path(__file__).resolve().parents[1]
REPO_KOKU = HOST.parents[1]
for yol in (HOST, REPO_KOKU):
    if str(yol) not in sys.path:
        sys.path.insert(0, str(yol))
