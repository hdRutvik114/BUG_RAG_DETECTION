# BugIdentifier System Architecture & Flow Diagrams

Industrial-grade Code-RAG Bug Detection and Automated Program Repair (APR) platform using AST parsing, Comparison-Based Error Mining (Delta-RAG), and Few-Shot In-Context LLM Synthesis.

---

## 1. High-Level System Architecture Diagram

```mermaid
flowchart TD
    subgraph FRONTEND ["React 18 Frontend Dashboard (Port 5173)"]
        UI["GitPortal (Input URL / ZIP / Code Input)"]
        LOGGER["ScanProgressLogger (Real-Time Stepper)"]
        EXPLORER["VulnerabilityExplorer (Monaco Diff Viewer)"]
        OBS["ObservabilityPanel & Summary Metrics"]
    end

    subgraph GATEWAY ["FastAPI API Gateway (Port 8000)"]
        ROUTER["API Router (/api/scan, /api/system)"]
        SCANNER["RepoScanner (Git & ZIP ephemera)"]
    end

    subgraph PARSER ["AST Code Parsing Engine"]
        NODE["Node.js Subprocess (ast_parser.js)"]
        SLICER["ASTSlicer (Method Boundaries)"]
    end

    subgraph ENGINE ["Delta-RAG Gatekeeper & Vector Engine"]
        VEC["120-D AST Vectorizer"]
        DATASET["master dataset.json (3,179 Bug-Fix Pairs)"]
        COSINE["Cosine Similarity Lookup (Local Vector Index)"]
        GATE{"Confidence >= 0.80?"}
    end

    subgraph APR_FRAMEWORK ["Automated Program Repair Framework"]
        PROMPT["Few-Shot In-Context Learning Engine"]
        DELTA["Delta Signature DNA Blueprint"]
        LLM["Generative LLM Engine (Google Gemini / OpenAI)"]
    end

    UI -->|"1. HTTP POST Request"| ROUTER
    ROUTER --> SCANNER
    SCANNER -->|"2. Extract JS/TS Files"| NODE
    NODE --> SLICER
    SLICER -->|"3. Function Chunks"| VEC
    VEC --> COSINE
    DATASET --> COSINE
    COSINE --> GATE
    
    GATE -->|"Similarity < 0.80 (Clean)"| LOGGER
    GATE -->|"Similarity >= 0.80 (Suspicious)"| PROMPT
    
    DATASET -->|"Historical Bug/Fix Pairs"| PROMPT
    DELTA -->|"Structural Blueprint"| PROMPT
    PROMPT --> LLM
    LLM -->|"JSON Diagnostics & Side-by-Side Patch"| EXPLORER
```

---

## 2. Sequence Diagram (User Request to LLM Patch)

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant React as React UI (GitPortal)
    participant API as FastAPI Gateway
    participant Scanner as RepoScanner
    participant Slicer as ASTSlicer (Babel)
    participant DeltaRAG as Delta-RAG Engine
    participant APR as Automated Program Repair Framework
    participant LLM as Generative LLM Engine (Gemini / OpenAI)

    User->>React: Enter Git Repo URL or Paste Code Snippet
    React->>API: POST /api/scan/repository or /api/scan/direct-code
    API->>Scanner: Clone/Extract project into ephemeral directory
    Scanner->>Slicer: Slice source files into standalone function methods
    Slicer-->>DeltaRAG: Return sliced method chunks + AST Vectors
    
    loop For Each Method Chunk
        DeltaRAG->>DeltaRAG: Compute Cosine Similarity against 3,179 dataset pairs
        alt Similarity < 0.80 (Clean Code)
            DeltaRAG-->>API: Mark as Clean ($0.00 LLM Cost)
        else Similarity >= 0.80 (Suspicious Defect)
            DeltaRAG->>APR: Pass Target Code + Historical Pair + Delta Signature
            APR->>LLM: In-Context Learning Prompt (Blueprint + Target Code)
            LLM-->>APR: Return JSON Patch & Explanation
            APR-->>API: Append Vulnerability Diagnostic
        end
    end

    API-->>React: Return JSON ScanResult Payload
    React-->>User: Render Monaco Editor Side-by-Side Diff Explorer
```

---

## 3. Database Schema Blueprint (`dataset.json` & MongoDB)

### Historical Bug-Fix Commit Record (`HistoricalBugFix`)
```json
{
  "_id": "delta_01549",
  "commit_id": "c0c3107334",
  "commit_message": "fix(i18n): localize resources navigation label",
  "project_name": "MartinDelophy/ai-video-editor",
  "file_path": "src/i18n.js",
  "buggy_code_chunk": "const COMMUNITY_LINKS_COPY = { ... }",
  "fixed_code_chunk": "import { I18N_COMPLETION_COPY } from './i18nCompletion.js'; ...",
  "bug_type": "null_pointer",
  "severity": "Medium",
  "explanation": "Missing optional chaining boundary check for undefined navigation label.",
  "ast_vector_120d": [0.0, 0.0, 2.0, 0.0, 1.0, 0.0, 0.12, 0.85, ...],
  "delta_signature": {
    "added_boundary_check": 1,
    "added_await": 0,
    "delta_op_gt": 0,
    "complexity_delta": 2
  },
  "metadata": {
    "language": "JavaScript",
    "framework": "React"
  }
}
```

---

## 4. Architectural Summary Metrics

| Component | Technology | Role / Specification |
| :--- | :--- | :--- |
| **Frontend Dashboard** | React 18 + Vite + Tailwind CSS v4 | Interactive Git portal, Monaco Editor side-by-side diff, live telemetry. |
| **API Gateway** | FastAPI (Python 3.13) + Uvicorn | Async REST routing, CORS middleware, scan background tasks. |
| **Parsing Engine** | Babel Parser (`@babel/parser`) | Node.js subprocess parsing JS/TS code into syntactic method boundaries. |
| **Vector Index** | NumPy + Scikit-Learn TF-IDF | 120-D AST vector matrix & TF-IDF similarity search over 3,179 master pairs. |
| **APR & LLM Engine** | Automated Program Repair Framework & Google Gemini / OpenAI | Few-Shot In-Context Learning guided by structural Delta Signatures. |
