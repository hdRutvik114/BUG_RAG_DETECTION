import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# Automatically load environment variables from .env file
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

CSV_PATH = BASE_DIR / "binary_bug_detection_dataset.csv"

class Settings(BaseModel):
    app_name: str = "BugIdentifier: Code-RAG Bug Tracker & Repair"
    csv_path: str = str(CSV_PATH)
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", 0.80))
    mongodb_uri: str = os.getenv("MONGODB_URI", "")
    mongodb_db_name: str = os.getenv("MONGODB_DB_NAME", "bugidentifier_db")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    temp_dir: str = str(BASE_DIR / "temp_scans")

settings = Settings()
os.makedirs(settings.temp_dir, exist_ok=True)
