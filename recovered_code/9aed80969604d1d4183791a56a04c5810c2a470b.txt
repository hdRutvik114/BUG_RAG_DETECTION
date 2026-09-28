import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.core.config import settings

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.is_connected = False
        self.local_storage: Dict[str, Dict[str, Any]] = {
            "scans": {},
            "historical_dataset": {},
            "delta_signatures": {}
        }
        self._init_connection()

    def _init_connection(self):
        if PYMONGO_AVAILABLE and settings.mongodb_uri:
            try:
                self.client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=2000)
                self.client.admin.command('ping')
                self.db = self.client[settings.mongodb_db_name]
                self.is_connected = True
                print("Connected successfully to MongoDB Atlas.")
            except Exception as e:
                print(f"MongoDB Atlas connection failed: {e}. Using resilient local store.")
                self.is_connected = False
        else:
            print("Running in Local Embedded Store mode (offline ready).")
            self.is_connected = False

    def save_scan_result(self, scan_id: str, scan_data: Dict[str, Any]) -> str:
        scan_data["updated_at"] = datetime.utcnow().isoformat()
        if self.is_connected and self.db is not None:
            try:
                self.db.scans.update_one({"scan_id": scan_id}, {"$set": scan_data}, upsert=True)
            except Exception as e:
                print(f"Error saving to MongoDB: {e}")
        self.local_storage["scans"][scan_id] = scan_data
        return scan_id

    def get_scan_result(self, scan_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            try:
                res = self.db.scans.find_one({"scan_id": scan_id}, {"_id": 0})
                if res:
                    return res
            except Exception as e:
                print(f"Error reading from MongoDB: {e}")
        return self.local_storage["scans"].get(scan_id)

    def save_historical_dataset(self, records: List[Dict[str, Any]]):
        if self.is_connected and self.db is not None:
            try:
                if self.db.historical_bug_fixes.count_documents({}) == 0 and records:
                    self.db.historical_bug_fixes.insert_many(records)
            except Exception as e:
                print(f"Error caching dataset to MongoDB: {e}")
        for r in records:
            key = str(r.get("pair_id", r.get("commit_id", len(self.local_storage["historical_dataset"]))))
            self.local_storage["historical_dataset"][key] = r

    def get_dataset_records(self) -> List[Dict[str, Any]]:
        return list(self.local_storage["historical_dataset"].values())

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_mongodb_connected": self.is_connected,
            "engine": "MongoDB Atlas Vector Search" if self.is_connected else "Local Hybrid Vector Index",
            "active_scans_count": len(self.local_storage["scans"]),
            "historical_records_count": len(self.local_storage["historical_dataset"])
        }

db_manager = DatabaseManager()
