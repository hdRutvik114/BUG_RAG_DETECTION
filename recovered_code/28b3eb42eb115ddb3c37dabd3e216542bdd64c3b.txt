import json
import subprocess
import os
from pathlib import Path
from typing import List, Dict, Any

PARSER_JS_PATH = Path(__file__).resolve().parent.parent / "ast_parser.js"

class ASTSlicer:
    def __init__(self):
        self.js_parser_path = str(PARSER_JS_PATH)

    def slice_code(self, code: str, filepath: str = "snippet.js") -> List[Dict[str, Any]]:
        """
        Runs Babel AST parser via Node.js subprocess to slice code into syntactic method boundaries
        and extract AST vectors & complexity metrics.
        """
        payload = json.dumps({"code": code, "filepath": filepath})
        
        try:
            process = subprocess.Popen(
                ["node", self.js_parser_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )
            stdout, stderr = process.communicate(input=payload, timeout=10)
            
            if process.returncode == 0 and stdout.strip():
                try:
                    methods = json.loads(stdout)
                    if isinstance(methods, list) and len(methods) > 0:
                        return methods
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"Babel AST subprocess error: {e}")

        # Fallback Python slicer
        return self._fallback_slice(code, filepath)

    def _fallback_slice(self, code: str, filepath: str) -> List[Dict[str, Any]]:
        lines = code.splitlines()
        if not lines:
            return []

        # Simple method chunking fallback
        chunks = []
        current_chunk = []
        start_line = 1
        current_method = "main_block"

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("function ") or stripped.startswith("const ") or stripped.startswith("export ") or stripped.startswith("async "):
                if current_chunk and len(current_chunk) > 3:
                    chunks.append({
                        "method_name": current_method,
                        "line_number_start": start_line,
                        "line_number_end": idx - 1,
                        "code": "\n".join(current_chunk),
                        "ast_vector": [0.0] * 64,
                        "complexity": 2,
                        "max_depth": 3
                    })
                    current_chunk = []
                    start_line = idx
                if "function " in stripped:
                    current_method = stripped.split("function ")[1].split("(")[0].strip() or "fn"
                elif "=" in stripped:
                    current_method = stripped.split("=")[0].replace("const", "").replace("let", "").replace("export", "").strip() or "fn"

            current_chunk.append(line)

        if current_chunk:
            chunks.append({
                "method_name": current_method,
                "line_number_start": start_line,
                "line_number_end": len(lines),
                "code": "\n".join(current_chunk),
                "ast_vector": [0.0] * 64,
                "complexity": 2,
                "max_depth": 3
            })

        return chunks

ast_slicer = ASTSlicer()
