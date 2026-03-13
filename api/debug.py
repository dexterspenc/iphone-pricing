"""api/debug.py — Temporary import-chain diagnostic. DELETE after fix."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/debug")
def debug():
    results = {}

    steps = [
        ("scraper.parser",      "from scraper.parser import parse_caption"),
        ("model.train import",  "from model.train import FEATURES, engineer_features"),
        ("model.predict",       "from model.predict import predict_range"),
        ("api._shared",         "from _shared import build_result"),
    ]

    for name, stmt in steps:
        try:
            exec(stmt, {"__builtins__": __builtins__})
            results[name] = "OK"
        except Exception as e:
            results[name] = f"ERROR: {type(e).__name__}: {e}"
            results["traceback_" + name] = traceback.format_exc()
            break  # stop at first failure

    results["python_version"] = sys.version
    results["sys_path"] = sys.path[:5]
    return results
