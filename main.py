import sys
import os
from pathlib import Path
import uvicorn

# Ensure project root is in sys.path
root_dir = str(Path(__file__).resolve().parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.main import app

if __name__ == "__main__":
    print("Starting BugIdentifier Backend API Server on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
