import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Ensure project root is in sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.core.config import settings

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    QDRANT_SDK_AVAILABLE = True
except ImportError:
    QDRANT_SDK_AVAILABLE = False


class QdrantVectorStoreManager:
    """
    Qdrant Online Cloud / Self-Hosted Vector Store Gateway
    Stores 120-D AST vectors and historical Delta-RAG bug repair blueprints.
    Ready to connect when QDRANT_URL and QDRANT_API_KEY environment variables are supplied.
    """

    def __init__(self):
        self.client = None
        self.is_connected = False
        self.collection_name = settings.qdrant_collection_name
        self.vector_dim = 120
        self._init_connection()

    def _init_connection(self):
        """
        Attempts lazy connection to Qdrant Cloud or local cluster if URL is supplied.
        Gracefully defaults to offline mode when credentials are omitted.
        """
        if QDRANT_SDK_AVAILABLE and settings.qdrant_url:
            try:
                self.client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                    timeout=5.0
                )
                # Verify server connectivity
                self.client.get_collections()
                self.is_connected = True
                print(f"[Qdrant] Connected successfully to Qdrant Cloud at {settings.qdrant_url}")
                self.ensure_collection()
            except Exception as e:
                print(f"[Qdrant] Connection to Qdrant Cloud deferred: {e}. Ready to connect when active.")
                self.is_connected = False
        else:
            if not QDRANT_SDK_AVAILABLE:
                print("[Qdrant] qdrant-client package not installed (optional). Install via 'pip install qdrant-client' to enable.")
            else:
                print("[Qdrant] Standby mode. Provide QDRANT_URL in environment to enable Online Vector Storage.")
            self.is_connected = False

    def ensure_collection(self, vector_size: int = 120):
        """
        Ensures the target Delta-RAG vector collection exists with Cosine distance metric.
        """
        if not self.is_connected or not self.client:
            return False

        try:
            collections = [c.name for c in self.client.get_collections().collections]
            if self.collection_name not in collections:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                print(f"[Qdrant] Created collection '{self.collection_name}' (vector size: {vector_size})")
            return True
        except Exception as e:
            print(f"[Qdrant] Failed to ensure collection '{self.collection_name}': {e}")
            return False

    def upsert_delta_pair(self, pair_id: int, vector: List[float], payload: Dict[str, Any]) -> bool:
        """
        Upserts a single 120-D AST vector and its associated bug-fix blueprint into Qdrant.
        """
        if not self.is_connected or not self.client:
            return False

        try:
            # Padding/truncating vector to target dimension
            if len(vector) < self.vector_dim:
                vector = vector + [0.0] * (self.vector_dim - len(vector))
            elif len(vector) > self.vector_dim:
                vector = vector[:self.vector_dim]

            point = models.PointStruct(
                id=int(pair_id),
                vector=[float(v) for v in vector],
                payload=payload
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            return True
        except Exception as e:
            print(f"[Qdrant] Error upserting vector point #{pair_id}: {e}")
            return False

    def batch_upsert_pairs(self, records: List[Dict[str, Any]]) -> int:
        """
        Batch upserts historical dataset records into Qdrant Cloud.
        """
        if not self.is_connected or not self.client or not records:
            return 0

        points = []
        for r in records:
            pid = r.get("pair_id", 0)
            ast_vec = r.get("buggy_ast", [])
            if not ast_vec:
                continue

            if len(ast_vec) < self.vector_dim:
                ast_vec = ast_vec + [0.0] * (self.vector_dim - len(ast_vec))
            else:
                ast_vec = ast_vec[:self.vector_dim]

            payload = {
                "pair_id": pid,
                "project_name": r.get("project_name", ""),
                "bug_type": r.get("bug_type", ""),
                "severity": r.get("severity", ""),
                "commit_id": r.get("commit_id", ""),
                "commit_message": r.get("commit_message", ""),
                "buggy_code": r.get("buggy_code", ""),
                "fixed_code": r.get("fixed_code", ""),
                "delta_signature": r.get("delta_signature", {})
            }

            points.append(models.PointStruct(
                id=int(pid),
                vector=[float(v) for v in ast_vec],
                payload=payload
            ))

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            print(f"[Qdrant] Successfully batch indexed {len(points)} vectors to Qdrant Cloud.")
            return len(points)
        except Exception as e:
            print(f"[Qdrant] Batch upsert error: {e}")
            return 0

    def search_similar_delta_vectors(
        self,
        query_vector: List[float],
        limit: int = 5,
        score_threshold: float = 0.80
    ) -> List[Dict[str, Any]]:
        """
        Performs Cosine Similarity vector search on Qdrant Cloud.
        Returns matched historical bug-fix blueprints above score_threshold.
        """
        if not self.is_connected or not self.client:
            return []

        try:
            if len(query_vector) < self.vector_dim:
                query_vector = query_vector + [0.0] * (self.vector_dim - len(query_vector))
            else:
                query_vector = query_vector[:self.vector_dim]

            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=[float(v) for v in query_vector],
                limit=limit,
                score_threshold=score_threshold
            )

            results = []
            for hit in search_result:
                res_payload = hit.payload or {}
                res_payload["qdrant_score"] = float(hit.score)
                results.append(res_payload)

            return results
        except Exception as e:
            print(f"[Qdrant] Search query error: {e}")
            return []

    def get_status(self) -> Dict[str, Any]:
        """
        Returns status telemetry for system health endpoints.
        """
        return {
            "qdrant_sdk_installed": QDRANT_SDK_AVAILABLE,
            "is_connected": self.is_connected,
            "url": settings.qdrant_url if settings.qdrant_url else "Not configured (standby)",
            "collection_name": self.collection_name,
            "vector_dimension": self.vector_dim
        }


# Global singleton instance for easy import across backend modules
qdrant_manager = QdrantVectorStoreManager()
