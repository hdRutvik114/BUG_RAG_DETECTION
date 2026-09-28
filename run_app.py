import subprocess
import time
import sys
import os
import signal

def main():
    print("=" * 70)
    print("  BugIdentifier: Code-RAG Bug Tracker & Automated Program Repair")
    print("  Stack: FastAPI (Python 3.13) + React 18 (Vite, Tailwind v4, Monaco)")
    print("=" * 70)

    # 1. Start Backend FastAPI server (scoped reload to backend/ directory to prevent temp scan reloads)
    backend_cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
    print("\n[1/2] Starting Backend API Gateway on http://127.0.0.1:8000...")
    backend_proc = subprocess.Popen(backend_cmd)

    # 2. Start Frontend Vite server
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    print("[2/2] Starting Frontend Vite (Tailwind v4) on http://localhost:5173...")
    frontend_cmd = ["npx", "vite"]
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=frontend_dir, shell=True)

    print("\n" + "=" * 70)
    print("  -> Application Dashboard: http://localhost:5173")
    print("  -> Backend API Swagger Docs: http://127.0.0.1:8000/docs")
    print("=" * 70 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        backend_proc.terminate()
        frontend_proc.terminate()

if __name__ == "__main__":
    main()
