# MASTER PROJECT GUIDE & DOCUMENTATION
## BugIdentifier: Code-RAG Bug Tracker & Automated Program Repair (APR) Platform

---

## 1. HIGH-LEVEL OVERVIEW & PURPOSE

### What is BugIdentifier?
**BugIdentifier** is an industrial-grade Automated Program Repair (APR) and bug detection web application built for JavaScript and TypeScript (MERN stack) codebases. It combines static Abstract Syntax Tree (AST) analysis, Comparison-Based Error Mining (Delta-RAG), and Generative Large Language Models (LLMs) to automatically detect code defects, display side-by-side diffs, and apply verifiable patches.

### The Problem It Solves
1. **Traditional Linters (ESLint, SonarQube)**: Rely on rigid keyword regex rules. They fail to catch dynamic logic errors, unhandled async promise rejections, and null pointer boundary bugs.
2. **Generic LLMs (Blind AI Prompts)**: Sending raw source code to an LLM without structural context causes "hallucinations"—where the model invents non-existent variable names or rewrites healthy code.
3. **High Token Costs**: Sending every single line of code to an LLM is extremely expensive.

### The Solution: Comparison-Based Error Mining (Delta-RAG)
BugIdentifier shifts the bug detection paradigm:
- It slices monolithic source files into standalone method/function boundaries using a Babel AST parser.
- Converts each function into a **120-Dimensional AST Geometry Vector**.
- Performs a fast similarity lookup against a pre-computed dataset of **3,179 historical bug-fix commit pairs** (6,358 code snippets).
- Uses a **Confidence Gatekeeper**: If code similarity is low, it is marked **Clean ($0.00 LLM Cost)**. If similarity is high, the engine extracts the **Delta Signature (Transformation DNA)** of past fixes and feeds it as a blueprint to the **Generative LLM Engine** for accurate patch synthesis.

---

## 2. COMPLETE PROJECT FILE & DIRECTORY STRUCTURE

Here is every directory and file in the codebase and its exact role:

```
new bug/
├── backend/                             # Python FastAPI Backend & Engine Core
│   ├── dataset.json                     # MASTER DATASET: 3,179 Bug-Fix Pairs (17.61 MB)
│   ├── main.py                          # FastAPI API Gateway & Endpoint Router
│   ├── __init__.py                      # Package Initializer
│   ├── core/                            # Core Pipeline Engines
│   │   ├── config.py                    # Environment (.env) & Path Configuration
│   │   ├── db.py                        # DatabaseManager (MongoDB Atlas & Local Store)
│   │   ├── delta_rag.py                 # DeltaRAGEngine (NumPy Vectors & Cosine Lookup)
│   │   ├── repo_scanner.py              # RepoScanner (Git Checkout & ZIP Extractor)
│   │   ├── repair_agent.py              # In-Context LLM Repair Framework (Gemini / OpenAI)
│   │   ├── ast_slicer.py                # ASTSlicer (Spawns Babel AST Node Process)
│   │   └── __init__.py                  # Core Package Initializer
│   └── tools/                           # Consolidated ML & Vectorizer Utilities
│       ├── Bug claude 2/                # Iteration 1 Tools (ast_vectorizer, miner.py)
│       ├── bugdataneone/                # Iteration 2 Tools (mine_github_mern.py)
│       └── claude3/                     # Iteration 3 Tools (llm_providers.py)
├── frontend/                            # React 18 + Vite + Tailwind CSS v4 Client
│   ├── index.html                       # HTML Entry Point
│   ├── package.json                     # Frontend NPM Dependencies
│   ├── vite.config.js                   # Vite Configuration & Backend Proxy (/api)
│   ├── dist/                            # Production Compiled Web Bundle
│   └── src/                             # Source Code
│       ├── App.jsx                      # Main React Application & State Machine
│       ├── main.jsx                     # React Root Entry & ErrorBoundary Component
│       ├── index.css                    # Tailwind CSS v4 Core Stylesheet
│       └── components/                  # UI Components
│           ├── Navbar.jsx               # Header & Live API Connection Status Pill
│           ├── GitPortal.jsx            # Input Form (GitHub URL, ZIP Upload, Snippet)
│           ├── ScanProgressLogger.jsx   # Real-Time 11-Step Progress Stepper
│           ├── VulnerabilityExplorer.jsx# Monaco Editor Side-by-Side Code Diff Viewer
│           ├── SummaryAndImprovements.jsx# Overview Cards & Impact Metrics
│           ├── ObservabilityPanel.jsx   # Telemetry & Performance Charts
│           ├── DiagnosticReportModal.jsx# Export Markdown Diagnostic Report Modal
│           └── DirectCodeModal.jsx      # Code Snippet Input Modal
├── refer.txt                            # Original System Specification Blueprint
├── diagram.md                           # System Architecture Diagrams & Sequence Flow
├── run_app.py                           # Master App Launcher (Starts FastAPI & Vite)
└── PROJECT_REPORT_AND_PPT_GUIDE.md      # This Master Documentation Guide
```

---

## 3. WHAT IS STORED IN THE DATABASE

The application uses a **Local Embedded Store** ([`backend/dataset.json`](file:///c:/Users/YATIRAJ/OneDrive/Desktop/new%20bug/backend/dataset.json), 17.61 MB) for offline high-speed indexing, with optional synchronization to **MongoDB Atlas** (`historical_bug_fixes` collection).

### Master Dataset Metrics
- **Total Historical Bug-Fix Pairs**: **3,179 commit pairs**
- **Total Code Snippets**: **6,358 snippets** (3,179 "Before" Buggy Code + 3,179 "After" Fixed Patches)
- **Top Sources**: Mined from `vercel/next.js`, `prisma/prisma`, `vitejs/vite`, `babel/babel`, `eslint/eslint`, `webpack/webpack`, and MERN stack repos.

### Defect Categories in Dataset
1. **Null Pointer & Unhandled Access** (657 records)
2. **Logic & State Errors** (721 records)
3. **Async / Promise Rejections** (393 records)
4. **Security Vulnerabilities** (389 records)
5. **Type & API Misuse** (390 records)
6. **Exception & Performance Issues** (209 records)
7. **Off-by-One Loop Boundaries** (49 records)

### JSON Structure of Each Stored Record
```json
{
  "_id": "delta_01549",
  "commit_id": "c0c3107334",
  "commit_message": "fix(i18n): localize resources navigation label",
  "project_name": "MartinDelophy/ai-video-editor",
  "file_path": "src/i18n.js",
  "buggy_code_chunk": "const COMMUNITY_LINKS_COPY = { ... };",
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
  }
}
```

---

## 4. END-TO-END STEP-BY-STEP WORKFLOW

```
[1. User Input] ➔ [2. Ephemeral Checkout] ➔ [3. File Selection] ➔ [4. Babel AST Slicing]
                                                                        │
[8. Monaco UI Diff]  [7. Generative LLM Engine]  [6. Delta-RAG Lookup]  [5. AST Vectorization]
```

### Step 1: User Input Submission
The user accesses `http://localhost:5173` and submits:
- A **GitHub Repository URL** (e.g. `https://github.com/owner/repository`)
- A **ZIP Archive** containing a JavaScript/TypeScript project
- Or pastes a **Direct Code Snippet** into `GitPortal.jsx`.

### Step 2: Ephemeral Checkout & Extraction
FastAPI's `/api/scan/repository` endpoint triggers `RepoScanner`:
- Creates a unique `scan_id` (e.g., `scan_cbb0964a`).
- Clones or extracts the code into an isolated temporary folder (`temp_scans/scan_cbb0964a`).

### Step 3: Source File Selection
- Walks the directory and filters only relevant `.js`, `.jsx`, `.ts`, `.tsx` source files.
- Excludes `node_modules`, build targets (`dist/`, `build/`), configuration files, and minified bundles.

### Step 4: Babel AST Parsing & Syntactic Slicing
- `ASTSlicer` passes each source file into a Node.js subprocess running `@babel/parser` (`ast_parser.js`).
- Parses the AST tree to locate clean function and method boundaries, slicing whole files into independent method chunks.

### Step 5: Feature Extraction & Vector Representation
For each sliced method chunk, `delta_rag.py` computes:
1. **120-D AST Geometry Vector**: Captures node counts, nesting depth, and control flow geometry.
2. **Static Metrics**: Detects unhandled `async/await`, missing `try/catch`, null dereference patterns, and loop boundaries (`i <= length`).

### Step 6: Delta-RAG Similarity Search & Gatekeeper Filter
- The computed AST vector is queried against the 3,179 dataset records in RAM using normalized **Cosine Similarity**:
  $$\text{Similarity}(A, B) = \frac{A \cdot B}{\|A\| \|B\|}$$
- **Confidence Gatekeeper**:
  - `Similarity < 0.50`: Classified as **Clean Code** (Logged and skipped \(\rightarrow\) **$0.00 LLM Cost**).
  - `Similarity >= 0.50`: Flagged as **Suspicious Defect**.

### Step 7: Evidence & Delta Signature Retrieval
When a method is flagged as suspicious, the system retrieves:
- Historical **Buggy Code** ("Before" commit).
- Historical **Fixed Patch** ("After" commit).
- **Delta Signature (\(\Delta\))**: Transformation DNA (`added_boundary_check: 1`, `added_await: 0`).

### Step 8: Automated Program Repair & LLM Synthesis
The **In-Context LLM Repair Module** (`repair_agent.py`) formulates a Few-Shot In-Context Prompt feeding Google Gemini / OpenAI:
- **Input**: Target Suspicious Code + Matched Historical Pair + Delta Transformation Signature Blueprint.
- **Output**: Strict JSON payload containing defect presence, bug type, severity level, technical explanation, and the exact refactored patch.

### Step 9: Interactive React Dashboard & Monaco Diff Display
FastAPI returns the `ScanResult` JSON payload to the React UI:
- `VulnerabilityExplorer.jsx` displays:
  - **File Tree Navigator**: Visualizing clean vs defect-flagged files.
  - **Monaco Editor Diff**: Showing side-by-side highlighted code diffs (User Code vs Refactored Patch).
  - **1-Click Action**: "Accept and Apply Patch" button to write the fix back to source code.

---

## 5. EXACT IN-CONTEXT PROMPT TEMPLATE

This is the exact prompt sent to the LLM by `repair_agent.py`:

```text
You are an elite code analyzer and automated program repair assistant.
Your task is to analyze the target code and determine if a software bug is present, then generate a patch.

You are provided with a historical bug pattern and fix transformation blueprint as a REFERENCE for the defect type:
### REFERENCE DEFECT TYPE: {bug_type}
### REFERENCE BLUEPRINT:
{delta_signature}

### TARGET USER CODE TO ANALYSE:
```javascript
{target_code}
```

CRITICAL INSTRUCTIONS:
1. Determine if the TARGET USER CODE actually contains a defect or logic error. If the code is already correct and healthy, set "is_bug_present": false.
2. If a bug IS present, generate a clean, refactored version of the TARGET USER CODE that resolves the defect.
3. CRITICAL: The "suggested_fix_code" MUST be the exact modified version of the TARGET USER CODE. Keep the function name, parameter names, and surrounding logic identical to the TARGET USER CODE. NEVER output code or function names from other projects.

Output your response strictly as valid JSON with these keys:
{
  "is_bug_present": true,
  "bug_type": "string describing defect",
  "severity_level": "Critical" | "Major" | "Minor",
  "explanation": "concise explanation of the bug and fix applied to the target code",
  "suggested_fix_code": "the exact refactored target code"
}
```

---

## 6. POWERPOINT (PPT) SLIDE-BY-SLIDE PRESENTATION OUTLINE

Ready-to-use 10-slide outline for your project presentation:

| Slide | Slide Title | Key Content & Talking Points |
| :--- | :--- | :--- |
| **Slide 1** | **Title Slide** | **BugIdentifier**: Code-RAG Bug Tracker & Automated Program Repair Platform.<br>Sub-heading: Structural AST Geometry Vectors & Few-Shot LLM Synthesis. |
| **Slide 2** | **Problem Statement** | • Static linters miss dynamic logic & async bugs.<br>• Generic LLMs hallucinate variable names without structural context.<br>• Sending clean code to LLMs wastes API costs. |
| **Slide 3** | **Core Innovation (Delta-RAG)** | • Slices code into method boundaries via Babel AST parser.<br>• Matches code using **120-D AST Geometry Vectors**.<br>• Extracts **Delta Signature (Transformation DNA)** as an LLM repair blueprint. |
| **Slide 4** | **Tech Stack & Architecture** | • **Frontend**: React 18, Vite, Tailwind v4, Monaco Editor, Lucide Icons.<br>• **Backend**: FastAPI, Python 3.13, Uvicorn.<br>• **Engine**: Babel AST Parser, NumPy, Scikit-Learn, Gemini/OpenAI. |
| **Slide 5** | **The Delta Signature (\(\Delta\))** | • Concept: Difference between "Before" (buggy) and "After" (fixed) commits.<br>• Features: `added_boundary_check`, `added_await`, `complexity_delta`. |
| **Slide 6** | **Master Dataset Breakdown** | • **3,179 Master Bug-Fix Pairs** (6,358 code snippets).<br>• Mined from Next.js, Prisma, Vite, Vue, Babel, ESLint, Webpack. |
| **Slide 7** | **End-to-End Pipeline** | Visual 7-step pipeline: User Input \(\rightarrow\) Git Checkout \(\rightarrow\) Babel Slicing \(\rightarrow\) AST Vector Lookup \(\rightarrow\) Gatekeeper \(\rightarrow\) LLM Synthesis \(\rightarrow\) Monaco Diff. |
| **Slide 8** | **Key Features & UX** | • Confidence Gatekeeper ($0 cost on clean code).<br>• Monaco Side-by-Side Diff Viewer.<br>• 1-Click "Accept & Apply Patch" button. |
| **Slide 9** | **Results & Verification** | • Sub-second vector search over 3,179 pairs.<br>• 0 Vite compilation errors.<br>• 100% verified FastAPI REST endpoints. |
| **Slide 10**| **Conclusion & Future Scope** | • Industrial-grade APR platform combining static AST geometry with LLMs.<br>• Future: Multi-language support (Python/Go/Java) and VS Code extension. |
