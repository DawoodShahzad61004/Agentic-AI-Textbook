# Bugs

Numbered bug records for the Langflow learning project. Bugs are numbered sequentially
(`BUG-NNN`) and IDs are never reused.

---

### BUG-001 · Docker cannot pull Langflow image — `lookup auth.docker.io: no such host`

| Field | Detail |
|---|---|
| **Issue** | `docker run langflowai/langflow:latest` failed to download the image with a DNS lookup error. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Environment (Docker Desktop / WSL2), not project code |
| **Description** | First run of `docker run -p 7860:7860 langflowai/langflow:latest` reported `Unable to find image locally` (normal), then failed with `lookup auth.docker.io: no such host`. Docker could not resolve Docker Hub's auth/registry hosts. |
| **Root Cause** | Not Langflow and not a missing image. Windows host DNS actually resolved fine (`nslookup auth.docker.io` and `registry-1.docker.io` both returned addresses, and `curl https://auth.docker.io/token` succeeded), so the failure was stale DNS state inside Docker Desktop's internal WSL2/Linux VM rather than on the host. |
| **Solution** | Quit Docker Desktop completely, then `ipconfig /flushdns` and `wsl --shutdown` (Admin), restart Docker Desktop, and retry `docker pull hello-world` then `docker pull langflowai/langflow:latest`. If it recurs, pin explicit DNS (`{"dns":["1.1.1.1","8.8.8.8"]}`) in Docker Engine settings. The pull subsequently succeeded. Ultimately superseded by moving off Docker entirely — see ADR-001. |
| **Date Resolved** | 2026-07-23 |

---

### BUG-002 · Langflow container exits on startup — `Username and password must be set`

| Field | Detail |
|---|---|
| **Issue** | After the image pulled successfully, the Langflow container shut down immediately instead of serving on port 7860. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | Environment (Docker container config), not project code |
| **Description** | Container logs ended with `Missing credentials: username=langflow, password=not set` followed by `ValueError: Username and password must be set`. The PyTorch and CORS lines in the same log were only warnings and did not cause the shutdown. |
| **Root Cause** | The current `langflowai/langflow:latest` image ships with login enabled by default and refuses to start without superuser credentials. The failed container also still owned the name `langflow`, blocking a clean re-run. |
| **Solution** | `docker rm langflow`, then start with auth env vars: `-e LANGFLOW_AUTO_LOGIN=false -e LANGFLOW_SUPERUSER=langflow -e LANGFLOW_SUPERUSER_PASSWORD="<strong-password>"` (the legacy default password `langflow` is rejected). For a private local experiment, `-e LANGFLOW_AUTO_LOGIN=true` bypasses the login screen. See Research topic 4. Superseded in practice by the local install (ADR-001). |
| **Date Resolved** | 2026-07-23 |

---

### BUG-003 · `python3.14 uv venv` fails — `can't open file '...\uv'`

| Field | Detail |
|---|---|
| **Issue** | Attempt to create a virtual environment errored with a file-not-found on `uv`. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | Environment (shell command), not project code |
| **Description** | Running `python3.14 uv venv` produced `can't open file 'C:\Users\LOQ\Desktop\Projects\Langflow-learning-project\uv': [Errno 2] No such file or directory`. |
| **Root Cause** | `python3.14 uv venv` tells Python to *execute a script file named `uv`*, so Python searched for `.\uv` and failed. `uv` is a standalone tool, not a Python script argument. |
| **Solution** | Invoke `uv` directly: `uv venv .venv --python 3.12` then `.\.venv\Scripts\Activate.ps1`. See ADR-003 for the Python version choice. |
| **Date Resolved** | 2026-07-23 |

---

### BUG-004 · `uv install langflow` — `unrecognized subcommand 'install'`

| Field | Detail |
|---|---|
| **Issue** | Package install command rejected by `uv`. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | Environment (shell command), not project code |
| **Description** | `uv install langflow` returned `error: unrecognized subcommand 'install'` with the hint `a similar subcommand exists: 'uv pip install'`. |
| **Root Cause** | `uv` has no top-level `install`; package installation goes through the pip-compatible interface. |
| **Solution** | Use `uv pip install langflow` (later pinned — see BUG-005 and ADR-002). |
| **Date Resolved** | 2026-07-23 |

---

### BUG-005 · `litellm==1.93.0` fails to build on Windows — `link.exe not found`

| Field | Detail |
|---|---|
| **Issue** | `uv pip install langflow` (which resolves langflow 1.11.0) failed while building `litellm==1.93.0` from source. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Environment (dependency build), not project code |
| **Description** | Resolution pulled `litellm==1.93.0` (via `langflow 1.11.0` → `langflow-base[complete] 0.11.0`). The wheel build ran `maturin`, auto-installed a temporary Rust toolchain, began compiling the pyo3 native crates, then failed: `error: linker link.exe not found` / `the msvc targets depend on the msvc linker but link.exe was not found`. |
| **Root Cause** | LiteLLM 1.93.0 ships Linux wheels but **no `win_amd64` wheel**, so Windows falls back to compiling the Rust/pyo3 `python-bridge` from source, which requires the MSVC C++ linker (`link.exe`) from Visual Studio Build Tools — not installed. This was the real blocker; the earlier suspicion that Python 3.14 was at fault was a red herring (the failure reproduced on 3.12 too). |
| **Solution** | Pin an older Langflow release that depends on a LiteLLM version with a prebuilt Windows wheel: `uv pip install --only-binary=litellm "langflow==1.10.2"`, which resolves `litellm==1.91.4` and installs cleanly with no compiler needed. Alternative (heavier): install Microsoft C++ Build Tools with the "Desktop development with C++" workload and build 1.11.0. See ADR-002 and Research topic 3. |
| **Date Resolved** | 2026-07-23 |

---

### BUG-006 · Live Groq API key committed in plaintext across generated flow exports

| Field | Detail |
|---|---|
| **Issue** | Several generated `flows/*.json` exports (the `LangGraph RAG Pipeline` family) carried a real Groq API key (`<redacted>`) baked into `GroqModel` node `api_key` values, staged for commit. |
| **Found Date** | 2026-07-27 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `flows/1.json`–`flows/9.json`, `flows/LangGraph RAG Pipeline.json` |
| **Description** | The Custom-Component/flow generator wrote a live credential straight into node template values instead of a placeholder, so every exported snapshot of the pipeline carried the real key in plaintext JSON. |
| **Root Cause** | The generator script's Groq node config used the working key from the local dev session instead of a placeholder string or `load_from_db` reference. |
| **Solution** | Redacted every occurrence to `"---"` before finalizing the commit (the `f8bb1cf` "API removed" commit already contains only the redacted value). Recommended follow-up: rotate the exposed key (it did reach git history in `f8bb1cf` before redaction if `git log -p` is ever consulted) and switch the field to Langflow's global-variable mechanism (`value: "GROQ_API_KEY"`, `load_from_db: true`) so future exports never carry a live secret at all. |
| **Date Resolved** | 2026-07-27 |

---

### BUG-007 · Fresh import fails Playground pre-flight — "is missing Knowledge" / "is missing Memory Base"

| Field | Detail |
|---|---|
| **Issue** | Re-importing `flows/LangGraph RAG Pipeline.json` into a clean Langflow instance failed Langflow's pre-run validation: `Knowledge · documents is missing Knowledge`, `Knowledge · learned_qa is missing Knowledge`, `Memory Base (feedback + prior turns) is missing Memory Base` — despite every node being wired correctly. |
| **Found Date** | 2026-07-27 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | `flows/LangGraph RAG Pipeline.json` (Knowledge and Memory Base nodes) |
| **Description** | The `knowledge_base` / `memory_base` dropdown fields are `required` and were empty on import, which Langflow's pre-flight "required, visible, no value, no incoming edge" check flags before a run can start. |
| **Root Cause** | `Knowledge` and `Memory Base` selections are per-user resources living in the Langflow instance's own storage (`~/.langflow/knowledge_bases/<user>/<kb_name>/`, and a DB row scoped to the current flow ID for Memory Base) — not something a flow JSON export can carry. A fresh import always starts with these fields blank (see Research topic 5). |
| **Solution** | Pre-filled the `knowledge_base` dropdown *values* (`documents`, `learned_qa`) in the generator so only matching Knowledge Bases need to be created and the dropdown auto-resolves; removed the `Memory Base` node entirely (ADR-008) rather than requiring one to be created and attached to the workflow on every fresh import. |
| **Date Resolved** | 2026-07-27 |

---

### BUG-008 · Hugging Face Inference API embeddings — SSRF-blocked DNS resolution

| Field | Detail |
|---|---|
| **Issue** | Running the flow raised `ValueError: SSRF Protection: DNS resolution failed for api-inference.huggingface.co: [Errno 11001] getaddrinfo failed`. |
| **Found Date** | 2026-07-27 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | Environment (Windows DNS configuration), not project code |
| **Description** | The Hugging Face Inference API embeddings component could not resolve `api-inference.huggingface.co`. `nslookup api-inference.huggingface.co` and `nslookup router.huggingface.co` both timed out against the configured DNS server (`gpon.net`, `fe80::1` — the router). |
| **Root Cause** | The Windows network adapter's only DNS server was the router, which was not resolving external hostnames at all; unrelated to Langflow, the flow, or Hugging Face. |
| **Solution** | Set the adapter's DNS servers to public resolvers (`1.1.1.1` / `8.8.8.8`) via Settings → Network & Internet → DNS server assignment, or `Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses ("1.1.1.1","8.8.8.8")`, then `ipconfig /flushdns`. In the flow itself, the remote Hugging Face Inference API node was subsequently replaced by a different embeddings provider rather than relying on that endpoint. |
| **Date Resolved** | 2026-07-27 |

---

### BUG-009 · Embeddings node with a required, empty API key aborts the run before any Chat Output builds

| Field | Detail |
|---|---|
| **Issue** | Playground runs showed a fleeting "AI" bubble at the top of the chat history, then reverted to showing only the user's message, with no red-bordered node in the canvas. |
| **Found Date** | 2026-07-27 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `flows/LangGraph RAG Pipeline.json` (embeddings node feeding `generate_query_variants`) |
| **Description** | Reproduced headlessly via `Graph.async_start()`: the run aborted with `lfx.exceptions.component.ComponentBuildError: Error building Component Google Generative AI Embeddings: API Key is required`, raised while building `generate_query_variants`'s embeddings dependency — i.e. on the second vertex of the run, long before any Chat Output could be reached. |
| **Root Cause** | Two compounding facts: (1) the standalone embeddings component's `api_key` field is `required` and was empty; (2) wiring the optional `embeddings` handle to *any* embeddings node makes that node a hard build dependency even though the input itself is declared optional — an unconfigured node on an optional input still blocks the run once an edge exists. |
| **Solution** | Either supply a real API key for the connected embeddings provider, or delete the embeddings node and its edges — every consumer (`generate_query_variants`, `dedup_merge_documents`, `dedup_merge_learned_qa`) already falls back to token-overlap similarity when no embeddings model is connected (covered by the test suite in the flow-generation session). |
| **Date Resolved** | 2026-07-27 |

---

### BUG-010 · `generate_draft` never runs — every query silently falls through to `no_context_answer`

| Field | Detail |
|---|---|
| **Issue** | With no red error node and a flow that "looked" correct, every Playground query routed to `no_context_answer` instead of `generate_draft`, even though the `documents` Knowledge Base held 106 ingested chunks. |
| **Found Date** | 2026-07-27 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `flows/LangGraph RAG Pipeline.json` (`retrieve` and `combine_tracks` components) |
| **Description** | Two independent causes compounded. (a) `retrieve`'s per-track similarity floors (`DOCUMENTS_MIN_SIMILARITY = 0.53`, `LEARNED_QA_MIN_SIMILARITY = 0.57`) were compared directly against the `Knowledge` node's `_score` field, which is a Chroma *distance* in roughly `[-2, 0]` (closer to `0` is better), not a `[0, 1]` similarity — so `_score >= 0.53` was false for every row and `retrieve` accepted zero chunks every time (see Research topic 6). (b) Separately, `combine_tracks` had several conditional outputs (`to_draft`, `to_answer`, `to_retry`, `to_no_context`) wired alongside other routers into the same downstream input fields; Langflow built an inactive branch's vertex before the active branch had populated it, surfacing as `generate_draft has not been built yet` (see Research topic 7). |
| **Root Cause** | (a) a similarity-vs-distance sign/scale mismatch between the ported Memora thresholds and the `Knowledge` node's native score convention; (b) multiple conditional-router outputs converging on one input field, which is a build-order hazard in Langflow's dependency resolution. |
| **Solution** | (a) convert `similarity = 1 + _score` (Chroma's negated-distance score), clamped to `[0, 1]`, before applying the threshold; if no row in a populated ranked search clears the fixed model-specific floor, retain its two best rows rather than incorrectly treating the Knowledge Base as empty. (b) collapsed the routing to one deterministic path — `combine_tracks.to_draft → generate_draft → check_answer_quality.to_answer → generate_answer` — removing the retry back-edges into `generate_query_variants` in the process (ADR-009). |
| **Date Resolved** | 2026-07-27 |

---

### BUG-011 · Local MiniLM label did not match the component implementation

| Field | Detail |
|---|---|
| **Issue** | A later edit intended to switch the embeddings provider to a local, keyless `sentence-transformers/all-MiniLM-L6-v2` model (confirmed working in a standalone smoke test: 384-dimensional normalized vectors, no network, no key). The node was renamed "Local MiniLM Embeddings" and its `model_name` field set to `sentence-transformers/all-MiniLM-L6-v2`. This most plausibly reproduces the persistent "no answer / vanishing AI bubble" symptom reported after that edit. |
| **Found Date** | 2026-07-27 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | `flows/LangGraph RAG Pipeline.json` — node displayed as "Local MiniLM Embeddings" |
| **Description** | Verified directly against the exported JSON: the node's `type` is still `"Google Generative AI Embeddings"` (`module: lfx.components.google.google_generative_ai_embeddings.GoogleGenerativeAIEmbeddingsComponent`), with `template.api_key.value == ""` (required, empty) and `template.model_name.value == "sentence-transformers/all-MiniLM-L6-v2"` — a Hugging Face model id being sent to Google's embeddings API, which will not recognize it even if a key were supplied. |
| **Root Cause** | Editing a node's display label and one field value does not change its underlying component `type`/module — those are independent in a Langflow export. The edit changed what the node is *called* and *configured with*, not what code actually runs, so it still hits the same class of failure as BUG-009 (required empty `api_key`), now compounded by an invalid `model_name` for the provider it actually is. |
| **Solution** | Replaced the runtime code with `langchain_huggingface.HuggingFaceEmbeddings`, configured for `sentence-transformers/all-MiniLM-L6-v2`, `local_files_only=True`, and normalized output. Removed the unused remote Hugging Face inference node. A smoke test produced normalized 384-dimensional vectors, and `Graph.from_payload` validated the updated component. |
| **Date Resolved** | 2026-07-27 |

---
