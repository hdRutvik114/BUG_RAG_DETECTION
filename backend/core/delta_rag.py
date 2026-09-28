import os
import ast
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from backend.core.config import settings
from backend.core.db import db_manager
from backend.core.qdrant_db import qdrant_manager

class DeltaRAGEngine:
    def __init__(self):
        self.pairs: Dict[int, Dict[str, Any]] = {}
        self.buggy_ast_matrix = None
        self.buggy_code_corpus: List[str] = []
        self.pair_id_index_map: List[int] = []
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
        self.is_indexed = False
        self._load_dataset()

    def _extract_delta_signature(self, buggy_code: str, fixed_code: str, buggy_ast: List[float], fixed_ast: List[float]) -> Dict[str, Any]:
        buggy_guards = sum(buggy_code.count(x) for x in ['if (', 'if(', '?.', '=== null', '!== null', '=== undefined', '!== undefined', 'typeof', 'length >', 'length ==='])
        fixed_guards = sum(fixed_code.count(x) for x in ['if (', 'if(', '?.', '=== null', '!== null', '=== undefined', '!== undefined', 'typeof', 'length >', 'length ==='])
        added_boundary_check = max(0, fixed_guards - buggy_guards)

        buggy_async = buggy_code.count('await') + buggy_code.count('async') + buggy_code.count('Promise')
        fixed_async = fixed_code.count('await') + fixed_code.count('async') + fixed_code.count('Promise')
        added_await = max(0, fixed_async - buggy_async)

        buggy_ops = sum(buggy_code.count(op) for op in ['>', '<', '>=', '<=', '===', '!==', '==', '!='])
        fixed_ops = sum(fixed_code.count(op) for op in ['>', '<', '>=', '<=', '===', '!==', '==', '!='])
        delta_op_gt = fixed_ops - buggy_ops

        complexity_delta = len(fixed_code.splitlines()) - len(buggy_code.splitlines())

        return {
            "added_boundary_check": int(added_boundary_check),
            "added_await": int(added_await),
            "delta_op_gt": int(delta_op_gt),
            "complexity_delta": int(complexity_delta)
        }

    def _load_dataset(self):
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dataset.json")
        records_to_save = []
        ast_vectors_list = []
        code_snippets_list = []
        pair_ids = []

        if os.path.exists(json_path):
            print(f"Loading master dataset from JSON at {json_path}...")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    records_to_save = json.load(f)
                
                for record in records_to_save:
                    pid = int(record.get("pair_id", record.get("id", len(self.pairs) + 1)))
                    b_ast = record.get("ast_vector_120d", record.get("ast_vector", [0.0]*64))
                    if len(b_ast) < 64:
                        b_ast = b_ast + [0.0] * (64 - len(b_ast))
                    elif len(b_ast) > 64:
                        b_ast = b_ast[:64]
                    record["ast_vector_120d"] = b_ast

                    self.pairs[pid] = record
                    ast_vectors_list.append(b_ast)
                    code_snippets_list.append(str(record.get("buggy_code_chunk", record.get("buggy_code", ""))))
                    pair_ids.append(pid)

                if ast_vectors_list:
                    self.buggy_ast_matrix = np.array(ast_vectors_list, dtype=np.float32)
                    norms = np.linalg.norm(self.buggy_ast_matrix, axis=1, keepdims=True)
                    norms[norms == 0] = 1e-10
                    self.buggy_ast_matrix = self.buggy_ast_matrix / norms

                    self.buggy_code_corpus = code_snippets_list
                    self.pair_id_index_map = pair_ids

                    self.tfidf_vectorizer = TfidfVectorizer(
                        token_pattern=r'(?u)\b\w+\b|[\+\-\*\/\=\<\>\!\&\|\?\:\.\,]',
                        max_features=1500,
                        ngram_range=(1, 2)
                    )
                    self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.buggy_code_corpus)

                    self.is_indexed = True
                    db_manager.save_historical_dataset(records_to_save)
                    print(f"Successfully indexed {len(self.pairs)} master historical bug-fix records from dataset.json!")
                    return
            except Exception as e:
                print(f"Error loading dataset.json: {e}")

        if not os.path.exists(settings.csv_path):
            print(f"Warning: Dataset CSV not found at {settings.csv_path}")
            return

        print(f"Loading historical bug-fix dataset from {settings.csv_path}...")
        df = pd.read_csv(settings.csv_path)

        grouped = df.groupby('pair_id')
        records_to_save = []
        ast_vectors_list = []
        code_snippets_list = []
        pair_ids = []

        for pair_id, group in grouped:
            buggy_row = group[group['is_bug'] == 1]
            fixed_row = group[group['is_bug'] == 0]

            if buggy_row.empty or fixed_row.empty:
                continue

            bug_data = buggy_row.iloc[0]
            fix_data = fixed_row.iloc[0]

            try:
                b_ast = ast.literal_eval(str(bug_data['ast_vector']))
            except Exception:
                b_ast = [0.0] * 64

            try:
                f_ast = ast.literal_eval(str(fix_data['ast_vector']))
            except Exception:
                f_ast = [0.0] * 64

            if len(b_ast) < 64:
                b_ast = b_ast + [0.0] * (64 - len(b_ast))
            elif len(b_ast) > 64:
                b_ast = b_ast[:64]

            if len(f_ast) < 64:
                f_ast = f_ast + [0.0] * (64 - len(f_ast))
            elif len(f_ast) > 64:
                f_ast = f_ast[:64]

            delta_sig = self._extract_delta_signature(
                str(bug_data['code']), str(fix_data['code']), b_ast, f_ast
            )

            commit_msg = str(bug_data.get('bug_description', ''))
            if not commit_msg or commit_msg == 'nan':
                commit_msg = f"Fix {bug_data.get('bug_type', 'defect')} in {bug_data.get('file_path', 'source')}"

            pair_record = {
                "pair_id": int(pair_id),
                "commit_id": str(bug_data.get('commit_hash', f"c_{pair_id}")),
                "commit_message": commit_msg,
                "project_name": str(bug_data.get('repository', 'open-source-repo')),
                "file_path": str(bug_data.get('file_path', 'index.js')),
                "bug_type": str(bug_data.get('bug_type', 'Logic Error')),
                "severity": str(bug_data.get('severity', 'Major')).capitalize(),
                "buggy_code_chunk": str(bug_data['code']),
                "fixed_code_chunk": str(fix_data['code']),
                "ast_vector_120d": b_ast,
                "delta_signature": delta_sig,
                "root_cause": str(bug_data.get('root_cause', '')),
                "fix_description": str(bug_data.get('fix_description', '')),
                "language": str(bug_data.get('language', 'JavaScript')),
                "gemini_confidence": float(bug_data.get('gemini_confidence', 0.9))
            }

            self.pairs[int(pair_id)] = pair_record
            records_to_save.append(pair_record)

            ast_vectors_list.append(b_ast)
            code_snippets_list.append(str(bug_data['code']))
            pair_ids.append(int(pair_id))

        if ast_vectors_list:
            self.buggy_ast_matrix = np.array(ast_vectors_list, dtype=np.float32)
            norms = np.linalg.norm(self.buggy_ast_matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1e-10
            self.buggy_ast_matrix = self.buggy_ast_matrix / norms

            self.buggy_code_corpus = code_snippets_list
            self.pair_id_index_map = pair_ids

            self.tfidf_vectorizer = TfidfVectorizer(
                token_pattern=r'(?u)\b\w+\b|[\+\-\*\/\=\<\>\!\&\|\?\:\.\,]',
                max_features=1500,
                ngram_range=(1, 2)
            )
            self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.buggy_code_corpus)

            self.is_indexed = True
            db_manager.save_historical_dataset(records_to_save)
            print(f"Successfully indexed {len(self.pairs)} historical bug-fix pairs with Delta Signatures!")

    def _compute_structural_defect_score(self, code: str) -> float:
        """
        Detects structural code anomalies:
        - Unhandled async promises (.then vs await, missing catch)
        - Potential boundary / null dereference
        - State mutation patterns
        - Array index off-by-one loops (<= length)
        """
        score = 0.0
        # Check for unhandled async or un-awaited promises
        if ("fetch(" in code or "axios." in code or "api." in code or "authenticate(" in code) and ("await " not in code and ".then(" not in code):
            score += 0.25
        if ("async " in code) and ("try {" not in code and ".catch(" not in code):
            score += 0.15

        # Check for loop index off-by-one (e.g. i <= items.length)
        if "<=" in code and ".length" in code:
            score += 0.30

        # Check for state mutation in hooks / reducers
        if ("useSelector" in code or "useDispatch" in code) and ("useEffect" in code) and (".map(" in code) and ("if (" not in code and "&&" not in code):
            score += 0.25

        # Check for direct deep property access without optional chaining / null guard
        if (".profile." in code or ".user." in code or ".data.items" in code) and ("?." not in code and "if (" not in code):
            score += 0.20

        return min(0.35, score)

    def match_code_chunk(
        self,
        target_ast_vector: List[float],
        target_code: str,
        threshold: Optional[float] = None
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Learned Confidence Gatekeeper:
        - Evaluates hybrid similarity (AST structural geometry + code token patterns + structural defect signals)
        - Scaled appropriately so realistic structural anomalies reach the verification gate.
        """
        effective_threshold = threshold if threshold is not None else float(settings.similarity_threshold)

        # 0. Query Online Qdrant Cloud Store if connected
        if qdrant_manager.is_connected:
            q_results = qdrant_manager.search_similar_delta_vectors(target_ast_vector, limit=1, score_threshold=effective_threshold)
            if q_results:
                matched_pair = q_results[0]
                q_score = matched_pair.get("qdrant_score", 0.92)
                return True, round(q_score, 4), matched_pair

        if not self.is_indexed or len(self.pair_id_index_map) == 0:
            return False, 0.0, {}

        # 1. AST Structural Similarity
        t_ast = np.array(target_ast_vector[:64], dtype=np.float32)
        if len(t_ast) < 64:
            t_ast = np.pad(t_ast, (0, 64 - len(t_ast)))
        t_norm = np.linalg.norm(t_ast)
        if t_norm > 0:
            t_ast_norm = t_ast / t_norm
            ast_sims = np.dot(self.buggy_ast_matrix, t_ast_norm)
        else:
            ast_sims = np.zeros(len(self.pair_id_index_map))

        # 2. Token / Semantic Similarity
        try:
            t_tfidf = self.tfidf_vectorizer.transform([target_code])
            text_sims = cosine_similarity(t_tfidf, self.tfidf_matrix)[0]
        except Exception:
            text_sims = np.zeros(len(self.pair_id_index_map))

        # 3. Hybrid Cognition Score
        hybrid_scores = 0.40 * ast_sims + 0.60 * text_sims
        best_idx = int(np.argmax(hybrid_scores))
        raw_best_score = float(hybrid_scores[best_idx])

        # 4. Calibrated Confidence Scaling & Defect Signal Fusion
        defect_bonus = self._compute_structural_defect_score(target_code)
        
        # Calibrate raw similarity: in text-code RAG, raw TF-IDF peak of ~0.35-0.5 represents a strong structural match
        calibrated_score = (raw_best_score * 1.5) + defect_bonus
        calibrated_score = max(0.05, min(0.98, calibrated_score))

        matched_pair_id = self.pair_id_index_map[best_idx]
        matched_pair = self.pairs.get(matched_pair_id, {})

        is_suspicious = calibrated_score >= effective_threshold

        return is_suspicious, round(calibrated_score, 4), matched_pair

    def get_dataset_stats(self) -> Dict[str, Any]:
        if not self.pairs:
            return {"total_pairs": 0, "bug_types": {}, "severities": {}, "top_repositories": []}

        bug_types = {}
        severities = {}
        repos = {}
        total_boundary_checks = 0
        total_await_fixes = 0

        for p in self.pairs.values():
            bt = p.get('bug_type', 'Unknown')
            sev = p.get('severity', 'Major')
            rep = p.get('project_name', 'Unknown')
            bug_types[bt] = bug_types.get(bt, 0) + 1
            severities[sev] = severities.get(sev, 0) + 1
            repos[rep] = repos.get(rep, 0) + 1

            sig = p.get('delta_signature', {})
            total_boundary_checks += sig.get('added_boundary_check', 0)
            total_await_fixes += sig.get('added_await', 0)

        sorted_repos = sorted([{"name": k, "count": v} for k, v in repos.items()], key=lambda x: x["count"], reverse=True)[:5]

        return {
            "total_pairs": len(self.pairs),
            "total_samples": len(self.pairs) * 2,
            "bug_types": bug_types,
            "severities": severities,
            "top_repositories": sorted_repos,
            "delta_metrics": {
                "total_boundary_check_fixes": total_boundary_checks,
                "total_async_await_fixes": total_await_fixes
            }
        }

delta_rag_engine = DeltaRAGEngine()
