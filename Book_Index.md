# Self-Learning Agentic RAG System
### A Step-by-Step Guide to Learn and Create

---

## Table of Contents

---

### **Preface**
- How to read this book
- Prerequisites (Python, basic ML familiarity)
- The project you will build by the end
- Companion source files and repository layout
- Conventions used (callouts, console traces, code listings, definition boxes)

---

## **PART I — FOUNDATIONS**

### Chapter 1 — Why RAG? The Problem with Plain LLMs
1.1 What Large Language Models actually are (decoder-only Transformers in one diagram)
1.2 Tokens, embeddings, attention, and the "predict the next token" objective
1.3 Why the output is a probability distribution — the seed of the hallucination problem
1.4 The hallucination problem — concrete examples
1.5 Knowledge cutoffs and stale information
1.6 Proprietary and private data — the data the model never saw
1.7 Why prompt engineering alone is not enough (and why it pairs *with* RAG, not against it)
1.8 Why fine-tuning alone is not enough — cost, data, frequency, and the citations problem
1.9 Where RAG fits in the landscape — what it fixes and what it does not fix

### Chapter 2 — Anatomy of a Retrieval-Augmented Generation System
2.1 The two pipelines: ingestion (offline) and retrieval (online)
2.2 The library cataloguer and the librarian — the working analogy
2.3 The five-step retrieval flow — embed → search → augment → generate → return
2.4 Core components at a glance — loader, splitter, embedder, vector DB, retriever, generator
2.5 A minimal RAG in ~40 lines of code
2.6 Limits of "traditional" RAG — the case for something smarter

### Chapter 3 — Setting Up Your Development Environment
3.1 Checking if your laptop is RAG-ready (CPU, RAM, GPU, storage)
3.2 Python versions and why 3.10–3.12 is the sweet spot
3.3 Virtual environments: `venv` vs `uv` vs `conda`
3.4 Installing the core stack — `langchain`, `langchain-groq`, `langchain-unstructured`, `langgraph`, `chromadb`, `sentence-transformers`
3.5 Pinned versions and why they matter (a tour of `requirements.txt`)
3.6 Managing API keys with `.env` and `python-dotenv`
3.7 Common install errors (PyTorch missing, `libmagic`, Windows `.venv` locks) and how to fix them
3.8 Verifying the install — a 5-minute smoke test

---

## **PART II — BUILDING THE INGESTION PIPELINE**

### Chapter 4 — The Document Structure
4.1 What a `Document` object really is
4.2 `page_content` vs `metadata` — and why metadata matters
4.3 Enriching metadata (source, page, timestamp, author, doc-type)
4.4 Why clean metadata pays dividends downstream

### Chapter 5 — Data Loading From Multiple Sources
5.1 Text files with `TextLoader`
5.2 PDFs with `PyPDFLoader` vs `PyMuPDFLoader` — speed and fidelity tradeoffs
5.3 Directory loading with `DirectoryLoader` and glob patterns
5.4 The `UnstructuredLoader` — one loader, many formats
5.5 Tabular data: CSV, Excel, TSV — converting to JSON for uniform ingestion
5.6 HTML, Markdown, DOCX, and JSON
5.7 Handling messy and scanned PDFs (OCR fallbacks)
5.8 Building a unified file-discovery helper across multiple data roots

### Chapter 6 — When RAG Is the Wrong Tool: The Two-Track Problem
6.1 The CSV-stats trap — why "give me the average age" can't be answered by similarity search
6.2 Semantic retrieval vs aggregation — a fundamental mismatch
6.3 The two-track architecture — RAG for prose, pandas for structured data
6.4 Routing the user's query to the right track
6.5 LLM-generated pandas code as a sandboxed tool
6.6 When to keep CSVs in RAG anyway (lookups, narrow joins, denormalized rows)

### Chapter 7 — Chunking Strategies
7.1 Why chunk at all? Context windows and retrieval precision
7.2 Fixed-size chunking
7.3 `RecursiveCharacterTextSplitter` — the sensible default
7.4 Choosing `chunk_size` and `chunk_overlap` (1000 / 200 and when to deviate)
7.5 Chars vs tokens — why "1000 chars ≈ 250 tokens" and when the ratio breaks
7.6 Semantic chunking — splitting by meaning, not characters
7.7 Markdown-aware and code-aware splitters
7.8 Document-structure-aware chunking (headers, sections)
7.9 Chunk hygiene — stripping boilerplate, deduplication, length filters
7.10 Experimenting: how chunking choices visibly change retrieval quality

### Chapter 8 — Embeddings Deep Dive
8.1 Dense vectors as compressed meaning
8.2 How sentence-transformers produce a 384-d vector
8.3 Where the model comes from — Hugging Face Hub and local caching
8.4 Open-source vs paid embedding models (MiniLM, BGE, OpenAI `text-embedding-3`, Cohere, Voyage)
8.5 Cost, dimensionality, and quality tradeoffs
8.6 Batching embeddings for speed without crashing memory
8.7 Caching and reusing embeddings
8.8 Evaluating an embedding model on your own data
8.9 Building the `EmbeddingManager` class — generation, normalization, cosine similarity
8.10 Why vectors are L2-normalized and what `||v|| = 1.0` actually means

### Chapter 9 — Vector Databases
9.1 What a vector DB actually stores
9.2 Cosine similarity, L2 distance, dot product — pick one
9.3 ChromaDB for local development
9.4 Alternatives: FAISS, Pinecone, Weaviate, Qdrant, Milvus, Typesense — when to use which
9.5 Collections, IDs, metadata filters
9.6 Persistence: saving the store to disk and reloading
9.7 Building the `VectorStore` class with batched inserts
9.8 Backups, migrations, and versioning your index

### Chapter 10 — Putting Ingestion Together: `ingest.py`
10.1 File discovery across multiple roots
10.2 Avoiding double-ingestion — why a parent root that contains your child roots will silently duplicate every chunk
10.3 Routing each file to the right loader
10.4 Splitting, embedding, and persisting in one run
10.5 Logging, progress bars, and idempotency
10.6 Re-running ingestion without duplicating entries

---

## **PART III — BUILDING THE RETRIEVAL PIPELINE**

### Chapter 11 — Query Retrieval Fundamentals
11.1 From question to query embedding
11.2 Similarity search mechanics, step by step
11.3 Top-k selection, score thresholds, and `MIN_SIMILARITY` heuristics
11.4 Distance-to-score conversion (`1 − distance`) and what scores actually mean (0.7+ strong, 0.4–0.7 related, <0.2 unrelated)
11.5 Building the `RAGRetriever` class
11.6 Inspecting what came back — scores, sources, previews
11.7 Why the retriever caches its last chunks (and who consumes that cache)

### Chapter 12 — Advanced Retrieval Techniques
12.1 The upgrade ladder — cosine → MMR → BM25 hybrid → cross-encoder rerank
12.2 Hybrid search — dense + sparse (BM25) combined
12.3 Reciprocal Rank Fusion (RRF) — merging ranked lists from multiple methods
12.4 Maximum Marginal Relevance (MMR) for diversity
12.5 Reranking with cross-encoders (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
12.6 Metadata filtering and hybrid filters
12.7 Multi-query retrieval — rephrasing for coverage
12.8 HyDE — hypothetical document embeddings
12.9 Parent–child / small-to-big retrieval
12.10 Contextual compression — extracting only relevant sentences from chunks

### Chapter 13 — Generating Answers with an LLM
13.1 The augmentation step — prompt + context + question
13.2 Choosing a hosted LLM (Groq, OpenAI, Anthropic, local via Ollama)
13.3 Groq with `langchain-groq` — fast and cheap for dev (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`)
13.4 A simple RAG answer function end-to-end
13.5 Model names, deprecations, and staying current
13.6 Temperature, max_tokens, and other generation knobs
13.7 Handling API errors, rate limits, and retries (Groq 6K TPM wall, `BadRequestError` parsing)
13.8 Advanced answer formatting — sources, confidence, previews
13.9 Streaming, citations, and conversational history (the enhanced pipeline)

### Chapter 13B — Centralized LLM Invocation and Error Handling
13B.1 Why every LLM call should flow through one wrapper — the case for `llm_caller.py`
13B.2 The `LLMResult` dataclass and the `LLMErrorKind` enum
13B.3 The Groq error taxonomy — `BadRequestError`, `RateLimitError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `UnprocessableEntityError`, `InternalServerError`, `APIConnectionError`, `APITimeoutError`, `APIStatusError`
13B.4 The `tool_use_failed` recovery path — extracting the assistant's draft from a malformed function-call payload via `_strip_function_suffix`
13B.5 Custom OpenAI-compatible endpoints — `CUSTOM_API_BASE`, `CUSTOM_API_KEY`, and `_normalize_openai_base_url`
13B.6 The tolerant HTTP client — `build_tolerant_http_client` with retry and timeout policy
13B.7 The `caller_tag` parameter — grep-friendly trace lines for every call site
13B.8 Transient vs permanent errors — which kinds the agent loop should retry
13B.9 Why `llm.invoke(...)` is never called directly outside `llm_caller.py`
13B.10 Multiple LLM roles — one client per job (`llm`, `judge_llm`, `json_fix_llm`, `llm_tool`, `merge_llm`) in `llm_setup.py`
13B.11 Why the answer-generation LLM should not be the answer-quality judge — bias, calibration, and cost
13B.12 The dedicated `json_fix_llm` — decoupling repair calls from the primary model to protect its rate limit
13B.13 Tiered SLM/LLM architecture — small model for judges/repairs, large model for generation
13B.14 Provider-routing options — Groq, Custom OpenAI-compatible endpoint, Hugging Face Inference Providers Router, and why Google Colab was evaluated and rejected
13B.15 The provider-consolidation timeline — from split (`ChatGroq` + custom + HF router) to unified custom-endpoint, and when to walk it back
13B.16 The `ChatGroq` + HF-style model path pitfall — `model_not_found` HTTP 404 when the client and the model string come from different provider families
13B.17 HF Inference Providers Router under sustained load — HTTP 402 and how it inflates latency
13B.18 Retry with capped exponential backoff — `LLM_RATE_LIMIT_MAX_ATTEMPTS`, `_BACKOFF_BASE_SECONDS`, `_BACKOFF_MAX_SECONDS`, `_BACKOFF_JITTER_SECONDS`, `_MAX_DELAY_SECONDS`
13B.19 The `LLMRateLimitAbortError` — when to stop retrying and surface the failure

### Chapter 14 — Prompt Engineering for RAG
14.1 Anatomy of a good prompt — role, instruction, context, constraints
14.2 Zero-shot, one-shot, few-shot prompting
14.3 Chain-of-Thought and self-consistency
14.4 ReAct — reasoning + acting
14.5 The grounded-answer prompt template for RAG
14.6 Reducing hallucination through prompt constraints ("answer only from context")
14.7 Citation-aware prompts and the `[Source: filename]` convention
14.8 Controlling tone, length, and output format (JSON, Markdown)
14.9 Why word-count caps are honored as suggestions, not rules
14.10 Debugging a bad prompt
14.11 The Conservative-Grounding Prompt Pattern — a reusable template that forbids inference beyond the provided context, applied identically to answer, draft, and answer-from-draft prompts
14.12 Structure for reliable structured-output LLM calls — role → schema → constraint hierarchy → worked example → "return ONLY JSON" reminder placed last
14.13 Advanced reasoning prompts — Tree of Thoughts, Step-Back, and Socratic prompting
14.14 Multi-stage prompting — prompt chaining and meta prompting
14.15 Delimiter techniques — separating instructions, context, examples, and user input safely
14.16 Persona + constraint hybrids — combining role prompting with explicit behavioral boundaries

---

## **PART IV — FROM RAG TO AGENTIC RAG**

### Chapter 15 — What "Agentic" Really Means
15.1 The fixed pipeline limitation of traditional RAG
15.2 Definition — autonomous agents making dynamic retrieval decisions
15.3 The four agent decisions: *when*, *what*, *where*, and *how many times* to retrieve
15.4 Agentic RAG vs traditional RAG — a visual comparison
15.5 When you actually need an agent (and when you don't)

### Chapter 16 — Designing the Agent Loop
16.1 The reasoning loop: decide → retrieve → evaluate → answer
16.2 Why tool-calling is the core primitive
16.3 Iteration caps and termination conditions (`MAX_ITERATIONS`, `MAX_TOTAL_RETRIEVALS`, `MAX_TOOL_CALLS_PER_ITERATION`)
16.4 Short-term memory within a session
16.5 The minimal agent in pseudocode

### Chapter 17 — Tool Use and Function Calling
17.1 What a "tool" is from the LLM's perspective
17.2 Writing tool schemas (JSON Schema style)
17.3 Hiding server-side parameters from the LLM (the `context` injection pattern)
17.4 Why exposing `context` in the tool schema causes Groq 400 `tool_use_failed` errors
17.5 Building `tools.py` — `retrieve_documents` and `check_answer_quality`
17.6 Multi-tool calls in a single turn
17.7 Safety: validating and sandboxing tool inputs

### Chapter 18 — Implementing the Agent with `llm.invoke(tools=…)`
18.1 `response.content` vs `response.tool_calls` — the two shapes of a reply
18.2 Executing tool calls in your loop
18.3 Feeding tool results back as `role: "tool"` messages
18.4 Injecting real retrieved context into quality checks — and the `args`-mutation bug that leaks it back into history
18.5 Exit conditions and safeguarding against infinite loops
18.6 Writing `agent_query.py`
18.7 From open loop to phase state machine — the RETRIEVE → COMPRESS → CAQ pipeline
18.8 Synthetic-injection — what to do when the LLM skips a required phase
  - 18.8.1 LLM emits final answer without retrieving — inject retrieve + compress + CAQ and re-emit
  - 18.8.2 LLM calls CAQ but skips compression — inject `compress_context` first, then proceed
  - 18.8.3 The user-role nudge after synthetic injections — getting the model to re-emit cleanly
18.9 Message-list scrubbing without breaking the assistant↔`tool_call_id` pairing
18.10 The `_judge` sidecar message — keeping validator output retrievable but out of the live retrieval surface
18.11 Token-usage accounting per iteration — accumulating `total_prompt_tokens` and `total_completion_tokens`

### Chapter 19 — Orchestration with LangGraph
19.1 Why graph-based orchestration — the case against ever-growing `agent_query.py` loops
19.2 Nodes, edges, and conditional edges — the three primitives
19.3 The `GraphState` TypedDict — declaring every field the graph will ever touch
19.4 `Annotated[list[dict], operator.add]` — reducers for fan-out/fan-in fields
19.5 `NotRequired[…]` — fields that may or may not appear in a given run
19.6 A minimal decide → retrieve → generate workflow
19.7 Conditional edges and routing functions — moving control flow out of nodes
19.8 Visualizing the graph with `app.get_graph().draw_mermaid_png()` — `rag_graph.png`
19.9 Debugging a LangGraph flow — node-level logging, state snapshots, recursion limits
19.10 When LangGraph helps and when an imperative loop is enough
19.11 Non-barrier fan-in — the default behavior where a join node fires once per incoming edge
19.12 The `defer=True` flag — registering a node as a true fan-in barrier that waits for all predecessors
19.13 Reducer semantics revisited — how `Annotated[list, operator.add]` combines with `defer=True` to guarantee ordered, complete input

### Chapter 19B — Porting the Agent to a LangGraph State Machine
19B.1 The migration plan — from `agent_query.py` loop to a node-per-phase graph
19B.2 One module per node — `user_input.py`, `query_variants.py`, `retrieve.py`, `validate_retrieval.py`, `dedup_merge.py`, `nac.py`, `dc.py`, `lbc.py`, `combine_tracks.py`, `generate_draft.py`, `check_answer_quality.py`, `generate_answer.py`, `no_context_answer.py`, `commands.py`, `auto_distillation.py`
19B.3 The `graph.py` module — assembling nodes, edges, and entry/exit points
19B.4 The `state.py` schema — every field the graph reads or writes, in one place
19B.5 The `routes.py` module — every conditional-edge function gathered together
19B.6 The `services/` layer — `llm_caller.py`, `llm_setup.py`, `logger_config.py`, `prompts.py`, `embedding_manager`, `validators.py`, `fix_llm_output.py`
19B.7 The `user_input_node` and `route_user_input` — handling `bad`, `stats`, `learn`, `exit` commands as graph entry points
19B.8 Fan-out — letting two independent retrievals run in parallel from a single START
19B.9 Fan-in via reducer-typed list fields — accumulating chunks from parallel branches
19B.10 The `combine_tracks` node — merging document and learned_qa outputs at the join point (registered with `defer=True` to force barrier semantics)
19B.11 The draft / quality-check / final-answer routing — when to retry vs. when to return
19B.12 Maintaining both pipelines side-by-side — keeping `agent_query.py` working while the LangGraph version stabilizes
19B.13 The node-vs-service architectural boundary — what belongs in a `nodes/` module vs. a `services/` module
19B.14 Circular imports across `nodes/` — how mixed absolute/relative import styles load the same module under two identities, and how to detect it

### Chapter 20 — Quality Control and Self-Correction
20.1 The check_answer_quality heuristic — red-flag refusal phrases, length floor, meaningful-overlap counting
20.2 Why heuristic groundedness checks are brittle (the magic 15-word stop-list threshold)
20.3 LLM-as-judge evaluation — and why the judge should *not* be the same call that produced the answer
20.4 Retry strategies — rephrase, expand, broaden
20.5 Confidence scoring — and why LLM-self-reported confidence is not evidence
20.6 Graceful degradation when nothing useful is retrieved
20.7 Beyond OK/INSUFFICIENT — the structured multi-verdict judge (`GROUNDED` / `PARTIALLY_FABRICATED` / `OVERCLAIMED` / `OFF_TOPIC` / `UNKNOWN`) with per-verdict routing
20.8 Semantic-extension blindness — why binary judges pass answers that add plausible-sounding but ungrounded content
20.9 Two-stage answer generation — `generate_draft` → `generate_answer` where the draft is *synthesis input*, not the final answer
20.10 The missing-gate bug — running the quality check on the draft while the actual final answer bypasses it, and the fix
20.11 Fabrication under repair — when the JSON-repair tier invents plausible values for inputs with no real answer data

### Chapter 20B — Structured Output Reliability with `fix_llm_output.py`
20B.1 The thirty failure modes — prefix prose, code fences, function-call wrappers, Python literals, escaped strings, comments, trailing commas, single quotes, unquoted keys, truncated JSON, multiple candidates, hallucinated reasoning, XML-instead-of-JSON, infinite repetition, and more
20B.2 The layered repair pipeline — preprocess → balanced-extract → `json.loads` → `json_repair` → Pydantic validation
20B.3 Preprocessing — `_strip_code_fences`, `_strip_blockquotes`, `_unwrap_function_call`, `_strip_json_comments`, `_fix_python_literals`, thinking-preamble stripping
20B.4 Balanced top-level JSON extraction (`_extract_balanced_json`) — bracket-counting that respects string literals
20B.5 `json_repair` as the tolerant fallback — when permissive parsing helps and when it should be distrusted
20B.6 Project-specific Pydantic schemas — `merge`, `dc_scan`, `redundancy_judge`, `retrieval_judge`, `merge_judge`, `lbc_compress`, `lbc_judge`, `distill_qa`
20B.7 The `correct=False` vs `correct=True` modes — strict validation vs aggressive recovery
20B.8 The empty-fallback principle — returning `[]` for list schemas, `{}` for object schemas on hard failure
20B.9 The Outlines framework — `outlines.from_openai(llm.root_client, MODEL)` for compliant servers
20B.10 Why `response_format: json_schema` only works on Groq's structured-output-supported models
20B.11 Test harness — `test_output_fixes.py` and the catalogue of malformed inputs

### Chapter 21 — Answer-Relevance Verification (Separate From Groundedness)
21.1 The three distinct failure modes — topic drift, question-type mismatch, hallucination
21.2 Why pure cosine similarity between query and answer is the wrong tool — high-similarity-wrong-answer and low-similarity-correct-answer cases
21.3 The two-stage gate — similarity smoke-test + LLM judge
21.4 Designing the relevance rubric (`RELEVANT` / `PARTIAL` / `IRRELEVANT` + one-sentence reason)
21.5 Tuning the cosine threshold from your own `interactions.jsonl` distribution
21.6 What to do when relevance fails — retry vs admit gap
21.7 Keeping relevance separate from groundedness in the agent loop

### Chapter 22 — Observability: Building a Full Dry-Run Trace
22.1 Why observable agents beat "magic" agents
22.2 Step-numbered console output across the entire pipeline
22.3 Logging the embedding step — model, shape, first-8-vals, L2 norm
22.4 Per-retrieval logging — score-ranked docs, source filenames, content previews
22.5 Serializing the messages list — what the LLM actually sees on each turn
22.6 Per-iteration tool-call logs (which tool, which args, which result)
22.7 The chunks-vs-retrieval-calls counting bug — and how to fix it
22.8 The `[CONTEXT SIZE @ iter N]` telemetry block — messages, chars, ~tokens, real prompt tokens
22.9 The `[CTXSIZE]` greppable log line for offline analysis
22.10 Reading a real dry-run trace from start to finish
22.11 Turning trace output on and off cleanly

### Chapter 22B — Semantic Compression of Retrieved Context
22B.1 Why retrieved chunks are redundant by design — and why that wastes tokens
22B.2 The three-stage compression hierarchy: NAC → DC → LBC
22B.3 Neighbor-Aware Compression (NAC) — merging adjacent chunks from the same source
  - 22B.3.1 Detecting neighbor runs via `chunk_seq` metadata
  - 22B.3.2 The NAC merge prompt and validate-merge loop
  - 22B.3.3 Retry-with-feedback when the LLM merge is unfaithful
22B.4 Deduplication Compression (DC) — removing cross-chunk redundancy
  - 22B.4.1 The sliding-window scanner and the `_DC_SCAN_PROMPT`
  - 22B.4.2 The redundancy judge and `validate_redundancy`
  - 22B.4.3 The intra-chunk group bug and the cross-chunk guard fix
  - 22B.4.4 Bracket-counting JSON extraction — why greedy regex fails with trailing prose
  - 22B.4.5 Verdict deduplication and out-of-range index guards
22B.5 LLM-Based Compression (LBC) — query-focused sentence-level filtering
  - 22B.5.1 The `_LBC_COMPRESS_PROMPT` and the `__IRRELEVANT__` sentinel
  - 22B.5.2 `LBC_MIN_RETENTION_RATIO` — guarding against over-compression
  - 22B.5.3 `validate_lbc` — detecting fabricated and dropped claims
22B.6 Building `validators.py` — four LLM-as-judge validators
  - 22B.6.1 `validate_retrieval` — PASS / PARTIAL / FAIL per chunk
  - 22B.6.2 `validate_merge` — FAITHFUL / UNFAITHFUL with fabricated and dropped claims
  - 22B.6.3 `validate_redundancy` — CONFIRMED / REJECTED per redundancy group
  - 22B.6.4 `validate_lbc` — SAFE / OVER_COMPRESSED / FABRICATED
22B.7 Extracting compression into its own module — building `context_compression.py`
22B.8 The `compress_context` tool — exposing compression to the agent as a callable phase
22B.9 Wiring `context_compression.py` into `agent_query.py` and the agent state machine
22B.10 Measuring the token savings — before and after compression telemetry
22B.11 Known failure modes and tuning knobs (`DC_WINDOW_SIZE`, `LBC_MIN_RETENTION_RATIO`, `MERGE_SIMILARITY_THRESHOLD`)

### Chapter 22C — Two-Track Parallel Compression in the LangGraph Rewrite
22C.1 Why split into two tracks — document chunks and learned_qa chunks have different characteristics
22C.2 The state-schema split — `retrieved_document_chunks`, `retrieved_learned_qa_chunks`, and downstream parallel fields
22C.3 The document track — NAC → DC → LBC (full pipeline for noisy source chunks)
22C.4 The learned_qa track — DC → LBC (NAC skipped; distilled chunks have no sequence to merge)
22C.5 Extracting each stage into its own node file — `nac.py`, `dc.py`, `lbc.py`, `dedup_merge.py`, `combine_tracks.py`
22C.6 The per-stage `execute_X` / `validate_X` pattern — separating action from judgement
22C.7 Per-stage routing functions in `routes.py` — `route_nac_documents_to_validator`, `route_dc_documents_to_validator`, `route_dc_learned_qa_to_validator`
22C.8 Fan-out from `query_variants` → `retrieve` — letting both tracks run concurrently
22C.9 Fan-in at `combine_tracks` — assembling `compressed_docs` with learned_qa precedence
22C.10 The conflict-resolution header — "LEARNED QA — HIGH PRIORITY" placed before "DOCUMENT — SECONDARY"
22C.11 The `_THIN` log separator and per-track telemetry — keeping two parallel streams readable

---

## **PART V — TOKENS, CONTEXT, AND MODEL CHOICE**

### Chapter 23 — The Token Budget — What Actually Fits in Your Context Window
23.1 What a context window is and what it includes (system prompt + history + tool results + user query + reserved output)
23.2 Total window vs *actually usable* input — the 128K → ~120K reality
23.3 A worked token budget for a 6-iteration agentic RAG run
23.4 How tool results inflate context fast — ~1,250 tokens per top-k=5 retrieval
23.5 Reading real numbers — the `total_prompt_tokens` and `total_completion_tokens` log lines

### Chapter 24 — Long-Context Performance and the Failure Cliff
24.1 The "lost in the middle" problem — why models attend to start and end, not middle
24.2 Empirical zones for an 8B model — ≤16K green, 16–32K yellow, >32K red
24.3 Where the rules start being ignored — the ~1.8K-token instruction-following ceiling on `llama-3.1-8b-instant`
24.4 Hallucination vs instruction drift vs runaway loops — three distinct failure modes
24.5 Designing a stress test — three runs at increasing context sizes, same query

### Chapter 25 — Why Small Models Struggle With Agentic Loops
25.1 Parameter count as "working-memory capacity"
25.2 Attention dilution as the conversation grows
25.3 Instruction following is learned behavior, not a hard rule engine
25.4 No explicit state tracking — the model has to count tool calls by re-reading history
25.5 The text-vs-code mode-flip failure — when procedural prompts produce Python instead of JSON
25.6 When to upgrade to a 70B model and what changes

### Chapter 26 — Prompt Engineering for Small Models in Long Loops
26.1 Section ordering matters — role/rules first, contextual injections middle, PROCESS last (closest to the user message)
26.2 The before-and-after of `_BASE_SYSTEM_PROMPT` → `_ROLE_AND_RULES` + `_PROCESS_INSTRUCTIONS` split
26.3 Strengthening "do NOT batch tool calls" with explicit numbered process steps
26.4 Compressing blocked-variants and thumbdown sections — token-cost math
26.5 Capping how many prior-failure records to inject (most recent 1–2)
26.6 Shorter tool schema descriptions reclaim instruction-following budget
26.7 Demonstration over description — replacing procedure with worked input/output examples (the JSON-not-Python fix)
26.8 Adding negative instructions ("Do NOT write Python code") when small models drift

### Chapter 27 — Agent State Engineering Beyond the System Prompt
27.1 Why "remind the model from the system prompt" stops working at scale
27.2 Injecting retrieval state into every tool result (`[Retrieval N/5] Queries tried so far: …`)
27.3 The per-iteration state-summary user message — a soft reminder placed close to generation
27.4 Hard filters at the tool layer — refusing repeated/blocked queries before the LLM sees them
27.5 Compressing tool results before appending to history — the 60% token-cost cut
27.6 The single-source-of-truth principle for agent state

---

## **PART VI — THE SELF-LEARNING LAYER**

### Chapter 28 — What "Self-Learning" Actually Means
28.1 The honest truth — agentic ≠ self-learning
28.2 Why the LLM's weights never change in your app
28.3 Three real paths to self-improvement
  - 28.3.1 Memory injection (easiest)
  - 28.3.2 Fine-tuning on accumulated interactions (moderate)
  - 28.3.3 RLHF / DPO (research-grade)
28.4 Why the memory-injection path is the right choice for most projects
28.5 Dangers of unchecked self-learning (reinforcing hallucinations, memory pollution)

### Chapter 29 — Capturing Interactions: The Feedback Store
29.1 What to log — query, answer, sources, chunks, quality signal
29.2 JSONL as a lightweight ledger (`interactions.jsonl`)
29.3 Implicit vs explicit feedback (agent quality check vs user thumbs)
29.4 Building `feedback_store.py`
29.5 Privacy, PII, and what NOT to log

### Chapter 30 — Learning From Failure, Part 1: Failed Query Variants
30.1 The problem — the agent keeps re-trying phrasings that retrieved zero chunks
30.2 The blocklist file — `failed_variants.json` keyed by normalized query
30.3 Recording every failing reformulation, not just the user-flagged one
30.4 Soft prompt injection vs hard tool-layer filtering — and why filtering wins
30.5 Walkthrough — building the load/save helpers and wiring them into `run_agent`
30.6 Verifying it works — observing the agent skip a previously-failing query

### Chapter 31 — Learning From Failure, Part 2: User Thumbdowns
31.1 The richer signal — when the answer was technically grounded but still wrong
31.2 The `bad` command and the `MIN_FEEDBACK_LEN` threshold
31.3 What to capture per thumbdown — original query, every variant tried, chunks each retrieved, the user's own feedback
31.4 Persisting to `user_thumbdowns.json`
31.5 Looking up prior thumbdowns by normalized query
31.6 Injecting a `USER-FLAGGED PRIOR FAILURE` block into the system prompt
31.7 Worked example — the "ASD" disambiguation case (autism vs Adjustable Speed Drive)
31.8 Content-vs-presentation feedback — the conflation problem and how to classify
31.9 Why "not structured enough" feedback can't help retrieval
31.10 Exact matching vs fuzzy/semantic matching for query lookup

### Chapter 32 — Learning From Success: The Distillation Engine
32.1 The principle — learn only from *validated* interactions
32.2 Synthetic Q&A pair generation from verified triples
32.3 Strict grounding in source chunks — no new facts invented
32.4 The distillation prompt, line by line
32.5 Deduplication with SHA-256 stable IDs
32.6 Building `self_learner.py`
32.7 Triggering: "every N good interactions" vs time-based vs manual (`learn` command)

### Chapter 33 — Hybrid Retrieval Over Documents and Learned Memory
33.1 Two collections, one retriever
33.2 Merging, deduplicating, and re-ranking across collections
33.3 Weighting learned memory vs raw documents
33.4 Updating `retriever.py` for hybrid behaviour
33.5 Watching the learned collection grow over time
33.6 Hybrid single-pool retrieval vs two-track parallel retrieval — the design choice and its trade-offs
33.7 Distance-metric consistency across collections — why both must use the same metric or scores stop being comparable
33.8 Per-collection score thresholds — `DOCUMENTS_MIN_SIMILARITY` vs `LEARNED_QA_MIN_SIMILARITY` and why one number is not enough
33.9 Per-collection top-k — `RETRIEVAL_TOP_K` for documents, `RETRIEVAL_TOP_L` for learned_qa

### Chapter 34 — Chunk-Level Deduplication and Merging During Retrieval
34.1 Why retrievals across iterations produce near-duplicate chunks
34.2 The `MERGE_SIMILARITY_THRESHOLD` knob — choosing 0.85 vs 0.88 vs 0.92
34.3 Cosine similarity at retrieval time — comparing only new chunks against the existing pool
34.4 Greedy/star-shaped merging vs single-link clustering — what your code actually does
34.5 The `_merge_similar_chunks` LLM merge step — JSON output, fence stripping, fallbacks
34.6 The mutation-during-iteration bug — why drops must be deferred to a single pass at the end
34.7 Re-embedding merged chunks so they can participate in future merges
34.8 Telemetry — logging near-misses to tune the threshold empirically

### Chapter 35 — Interactive Session: CLI Commands for Learning
35.1 The `bad` command — interactive feedback prompt and persistence
35.2 The `stats` command — visibility into learning progress
35.3 The `learn` command — forcing a distillation pass
35.4 The `/save`, `/correct`, `/forget` pattern (alternative design)
35.5 User-friendly logging and progress messages

### Chapter 36 — Evaluating Whether Self-Learning Actually Works
36.1 Baseline accuracy before learning kicks in
36.2 Building a fixed evaluation set of questions
36.3 Driving repeated runs with `run_batch.py` — `stdin` monkey-patching, fixture lists, and reusing `agent_query.main()`
36.4 Measuring answer quality over time
36.5 Detecting memory drift and regression
36.6 When to manually review and prune the learned collection
36.7 Comparing to research benchmarks (Self-RAG, Pistis-RAG, RAGAS)

### Chapter 36B — Feature-Flag-Driven Development for RAG Pipelines
36B.1 Why every pipeline stage needs a kill-switch — incremental rollout, A/B testing, and ablation
36B.2 The `config.py` flag catalogue — `ENABLE_SUB_QUERY_GENERATION`, `ENABLE_RETRIEVAL_DEDUP_MERGE`, `ENABLE_RETRIEVAL_VALIDATION`, `ENABLE_NAC_COMPRESSION`, `ENABLE_DC_COMPRESSION`, `ENABLE_LBC_COMPRESSION`, `ENABLE_COMPRESSION_VALIDATION`, `ENABLE_ANSWER_DRAFT_CREATION`, `ENABLE_ANSWER_QUALITY_CHECK`, `ENABLE_AUTO_DISTILLATION`, `ENABLE_QA_PAIR_GENERATION`, `ENABLE_GLOBAL_LLM_OUTPUT_FIX`
36B.3 Per-stage output-fix flags — `ENABLE_*_OUTPUT_FIX` as an independent layer on top of `ENABLE_GLOBAL_LLM_OUTPUT_FIX`
36B.4 Building an "all flags true" baseline run
36B.5 Disabling one subsystem at a time — the `All_flags_True_except_*` dry-run methodology
36B.6 The post-retrieval-separation dry run — comparing chunks before and after track-split refactoring
36B.7 Cross-run diffing — `new_log.txt` vs `old_log.txt` for regression hunting
36B.8 What to flag-gate vs what to hard-wire — a heuristic

### Chapter 36C — Evidence-Based Retrieval Tuning From Production Logs
36C.1 Why hand-picked thresholds fail — the retrieval knobs that need real-data calibration
36C.2 The A/B log-comparison methodology — running the same query set under two configurations and diffing the retrieved-chunk sets
36C.3 Choosing `RETRIEVAL_TOP_K` (documents) and `RETRIEVAL_TOP_L` (learned_qa) from observed score distributions, not defaults
36C.4 Choosing `DOCUMENTS_MIN_SIMILARITY` and `LEARNED_QA_MIN_SIMILARITY` — the precision/recall trade-off per collection
36C.5 Detecting silent regressions — when a "cleanup" refactor changes retrieval outputs without changing tests
36C.6 Building a repeatable tuning loop — fixture query set + timestamped log capture + diff scripts

---

## **PART VII — PRODUCTION, DEPLOYMENT, AND BEYOND**

### Chapter 37 — Evaluation Frameworks for RAG
37.1 Retrieval metrics — recall@k, precision@k, MRR, nDCG
37.2 Generation metrics — faithfulness, answer relevancy, context precision
37.3 RAGAS, TruLens, DeepEval — tools of the trade
37.4 Building a lightweight in-house evaluator
37.5 Human evaluation: when automation isn't enough

### Chapter 38 — Observability Platforms and Debugging
38.1 Why print-statements stop scaling — trace granularity, cross-run comparison, and shareable evidence
38.2 The three vantage points — application logs, LLM-call traces, and framework-level spans
38.3 Structured logging across the pipeline — the `logger_config.py` module, per-file `getLogger(__name__)`, and level routing
38.4 The Python `logging` hierarchy in a multi-module project — parent/child loggers, propagation, and level inheritance
38.5 Bridging Python `logging` into distributed traces — the `_TracingHandler` pattern that mirrors log records onto active spans
38.6 OpenTelemetry, OpenInference, and OpenInference Semantic Conventions — the fundamentals every backend implements
38.7 Arize Phoenix as primary — self-hosted deployment under a no-data-egress constraint
38.8 The `phoenix_tracing.py` bootstrap — `TracerProvider`, span exporter, LangChain instrumentation
38.9 Why `opentelemetry.trace.get_current_span()` sometimes returns a non-recording span — and how to guard for it
38.10 LangSmith in parallel — a second backend with a hosted UI for team review
38.11 The LangSmith UI's rendering surface — where custom run events appear (and where they silently do not)
38.12 Langfuse as a third backend — the callback-based tracing model, contrasted with Phoenix/LangSmith ambient instrumentation
38.13 Explicit `config` threading through the entire LLM call chain — required for Langfuse's `CallbackHandler` to receive anything
38.14 The Langfuse-evicts-Phoenix bug — how a third-party library silently replaces the global `TracerProvider`'s span exporter, and how to detect and fix it
38.15 Windows console encoding failures — `UnicodeEncodeError` on cp1252 for non-ASCII trace payloads and the safe-encoding wrapper
38.16 The main-CLI-never-initialized-tracing regression — a checklist for entry-point audits
38.17 Langfuse Scores, Datasets, and Annotations — when they help and when they duplicate what Phoenix/LangSmith already track
38.18 Choosing between the three — a decision matrix: hosted vs self-hosted, callback vs ambient, UI vs API-first
38.19 Debugging retrieval failures
38.20 Debugging LangGraph flows that don't terminate — recursion limits, state snapshots, node-level breakpoints

### Chapter 39 — Performance and Cost Optimization
39.1 Batching embeddings — sweet-spot batch sizes
39.2 Caching at every layer (embeddings, retrieval, LLM responses)
39.3 Reducing token usage in prompts
39.4 Picking cheaper models for cheap steps
39.5 Async and parallel retrieval
39.6 Index compression and quantization
39.7 Thread-based per-call timeouts — `ThreadPoolExecutor.submit(...) + future.result(timeout=N)` as the portable pattern for wrapping a blocking LLM call
39.8 Semaphores vs FIFO queue for LLM-call serialization under concurrent load — throughput vs fairness
39.9 Exponential backoff with jitter as an architectural pattern — not just a reliability feature (retry economics, thundering-herd avoidance)
39.10 The GPU-driver failure fallback — falling back to CPU embeddings when NVIDIA Code 43 is detected
39.11 The `merge_llm` / `judge_llm` / `json_fix_llm` split — routing cheap operations to a smaller model
39.12 Latency budgeting in a multi-stage pipeline — where the seconds actually go

### Chapter 40 — Security and Safety
40.1 Prompt injection — how attackers hide instructions in documents
40.2 Data exfiltration via tool misuse
40.3 Input validation and output sanitization
40.4 PII detection and redaction
40.5 Rate limiting and abuse prevention
40.6 Auditing what the agent has "learned" — and how to forget on demand

### Chapter 41 — Deployment
41.1 Wrapping the agent in a FastAPI service — `api.py`, `lifespan`, and graceful shutdown
41.2 Running two pipelines side by side — LangChain on port 8000, LangGraph on port 8001
41.3 The endpoint surface — `POST /query`, `POST /bad`, `GET /stats`, `POST /learn`, `GET /health`
41.4 Request/response Pydantic models — `QueryRequest`, `QueryResponse`, and the LangChain vs LangGraph response-shape difference
41.5 Postman setup for parallel-pipeline testing — one collection, two environments
41.6 Streaming responses to the client
41.7 Persistent vector stores in production (managed vs self-hosted)
41.8 Stateless web frontends and session handling
41.9 Containerization with Docker
41.10 Scaling — replicas, load balancing, shared index
41.11 CI/CD for RAG systems
41.12 From JSONL ledger to MongoDB — when file-based feedback storage stops scaling
41.13 MongoDB replica sets and why multi-document transactions require them
41.14 `DuplicateKeyError` as an idempotency guard for LangGraph node retries — safer than a check-then-insert race
41.15 Migration path — copying `interactions.jsonl`, `failed_variants.json`, and `user_thumbdowns.json` into MongoDB collections without losing history

### Chapter 42 — Advanced Topics and Extensions
42.1 Multi-modal RAG — images, tables, audio
42.2 GraphRAG — knowledge graphs as the retrieval substrate
42.3 Multi-agent systems — planner, researcher, critic
42.4 Long-term user memory vs shared organization memory
42.5 Fine-tuning a small model on your distilled dataset — and what the *Continual Harness* framework adds on top of a static distillation pass
42.6 Moving from memory injection to true weight-level learning — the SEAL framework (Zweiger et al., NeurIPS 2025): self-edits, ReSTEM, LoRA-based inner loop, and the catastrophic-forgetting caveat
42.7 Self-RAG and reflection-token approaches
42.8 Semantic / fuzzy matching for thumbdown lookup (beyond normalized exact match)
42.9 Process Reward Models for agents — what *ToolPRMBench* measures and how it would apply to the retrieve/compress/draft/judge phases
42.10 Where our memory-injection loop stops and weight-level self-adaptation begins — an honest map of the gap

### Chapter 43 — The Finished Project — Recap and Roadmap
43.1 What you built, file by file
43.2 Architecture diagram of the complete system (`rag_graph.png` — the rendered LangGraph)
43.3 The three failure-memory mechanisms working together (`failed_variants`, `user_thumbdowns`, `learned_qa`)
43.4 Documentation discipline — keeping `Architecture.md`, `Status.md`, `Decisions.md`, `Bugs.md`, and `Research.md` in sync with the code
43.5 Architecture Decision Records (ADRs) — the `Decisions.md` ledger and how to write a new one
43.6 The structured bug catalogue — `Bugs.md` with `BUG-XXX` IDs, severity, root cause, and status
43.7 The chronological status log — `Status.md` as a write-once-per-week development diary
43.8 Known limitations and honest tradeoffs
43.9 Ten enhancement ideas, ranked by effort
43.10 Turning the project into a portfolio piece
43.11 Talking about this system in an interview

---

## **APPENDICES**

- **Appendix A** — Full Source Code Listings
  - LangChain pipeline (`app/`): `ingest.py`, `embedding_manager.py`, `vector_store.py`, `retriever.py`, `tools.py`, `llm_caller.py`, `llm_setup.py`, `fix_llm_output.py`, `context_compression.py`, `agent_query.py`, `validators.py`, `feedback_store.py`, `self_learner.py`, `learned_qa_store.py`, `query.py`, `run_batch.py`, `api.py`, `test_llm_caller.py`, `test_output_fixes.py`
  - LangGraph pipeline (`app_workflow/`): `main.py`, `api.py`, `graph.py`, `state.py`, `routes.py`, `config.py`, and the node modules — `user_input.py`, `commands.py`, `query_variants.py`, `retrieve.py`, `validate_retrieval.py`, `dedup_merge.py`, `nac.py`, `dc.py`, `lbc.py`, `combine_tracks.py`, `generate_draft.py`, `check_answer_quality.py`, `generate_answer.py`, `no_context_answer.py`, `auto_distillation.py`
  - Services (`app_workflow/services/`): `llm_setup.py`, `llm_caller.py`, `fix_llm_output.py`, `validators.py`, `logger_config.py`, `prompts.py`, `services.py`, `phoenix_tracing.py`, `langfuse_tracing.py`, `trace_events.py`
- **Appendix B** — Full Annotated Dry-Run Trace (every step from question to answer for one real query, including embedding logs, compression telemetry, per-iteration context-size telemetry, the `[CTXSIZE]` greppable lines, and Phoenix + LangSmith span IDs)
- **Appendix C** — Bug Catalogue
  - Pre-refactor bugs: the `args`-mutation context leak, the tuple-vs-string return bug in `tools.py`, the JSON-vs-Python merge-output bug, the fence-stripping bug, the parent-root double-ingestion bug, the intra-chunk DC group bug, the greedy-regex JSON extraction bug, the verdict-deduplication bug, the redundancy-judge subject-misidentification bug, the DC judge emitting Python instead of JSON, the Outlines + Groq `json_schema`-unsupported-model failure, the `tool_use_failed` recovery path, the chunk-merge JSON-escaping bug with Windows backslash paths, the assistant↔`tool_call_id` pairing break during message scrubbing, the LLM-skips-compress-and-CAQ phase-bypass attempts
  - Behavioral / judge bugs (BUG-001 – BUG-010): tool-call overflow silently drops requests, retrieval judge over-lenient on bibliography chunks, DC redundancy judge false positives, LBC over-expansion, `check_answer_quality` blind to semantic extension, no schema awareness for data-interpretation questions, near-synonym-loop enforcement, self-reported confidence, exact-string thumbdown matching, weak coverage checker for multi-part queries
  - Fatal-cause / environment bugs (BUG-F001 – BUG-F010+): the merge JSON escaping bug on Windows paths, `OPENAI_BASE_URL` resolved before `load_dotenv()`, `CUSTOM_API_BASE` double-appending `/chat/completions`, local server returning `function.arguments` as dict, DC silent JSON-parse failure, DC judge Python output, `compression.py` shadowing Python 3.14 stdlib module, early COMPRESS trigger blocking multi-query retrieval, `json-repair` missing from `requirements.txt`, inconsistent source-path formatting polluting `learned_qa`
  - Late-refactor bugs (BUG-057 – BUG-076): NVIDIA GPU Code 43 fallback, LLM-repair-tier fabricates JSON, wrong balanced-JSON candidate selection, `combine_tracks` fan-in non-barrier, `generate_answer` returns draft verbatim, `ChatGroq` + HF-path `model_not_found` 404, HF Router HTTP 402 under load, LBC fabricates from citation-only sources, DC deletes before `validate_redundancy` can reject, missing quality gate after `generate-answer-from-draft`, Phoenix never initialized in CLI entry point, `_TracingHandler` filters DEBUG before spans see it, `get_current_span()` returns non-recording span, LangSmith UI cannot render custom events, Windows cp1252 crash on trace payloads, circular import via mixed absolute/relative styles, Langfuse `CallbackHandler` was a no-op without `config` threading, Langfuse evicts Phoenix span exporter from global `TracerProvider`
- **Appendix D** — Data Files and Reference Outputs (`interactions.jsonl`, `failed_variants.json`, `user_thumbdowns.json`, `learned_qa` collection, `rag_graph.png`, `langchain_api_*_debug.log`, `langgraph_api_*_debug.log`, `new_log.txt`, `old_log.txt`)
- **Appendix E** — Three-Run Stress Test Tables (token counts, query lists, where the model breaks) — plus the `All_flags_True`, `All_flags_True_except_*`, `Post-retrieval-separation` flag-ablation runs
- **Appendix F** — Troubleshooting Cookbook (common errors and fixes)
- **Appendix G** — Glossary of terms (agent, chunk, embedding, RAG, distillation, ReAct, hybrid retrieval, thumbdown, variant, groundedness, relevance, MMR, RRF, NAC, DC, LBC, GraphState, fan-out/fan-in, reducer-typed field, `defer=True` barrier, non-barrier fan-in, multi-verdict judge, Conservative-Grounding Prompt Pattern, `MERGE_SIMILARITY_THRESHOLD`, `LBC_MIN_RETENTION_RATIO`, `DC_WINDOW_SIZE`, `RETRIEVAL_TOP_K`, `RETRIEVAL_TOP_L`, `DOCUMENTS_MIN_SIMILARITY`, `LEARNED_QA_MIN_SIMILARITY`, `LLM_RATE_LIMIT_*`, ambient vs callback tracing, `OpenInference`, `TracerProvider`, span exporter, self-edit, ReSTEM, LoRA, catastrophic forgetting, PRM, …)
- **Appendix H** — Recommended Reading and Video Resources
  - Foundational: original RAG paper (Lewis et al., 2020), Attention Is All You Need
  - Compression & context management: contextual compression papers
  - Self-improvement / weight-level adaptation: **SEAL — Self-Adapting Language Models** (Zweiger, Pari, Guo, Akyürek, Kim, Agrawal — NeurIPS 2025, arXiv:2506.10943), *Continual Harness: Online Adaptation for Self-Improving Foundation Agents*, Deductive Closure Training (Akyürek et al., 2024)
  - Process reward for agents: **ToolPRMBench**
  - Structured decoding: Outlines, Guidance, `json_repair` library
  - Framework docs: LangGraph, LangSmith, Arize Phoenix, Langfuse, OpenInference Semantic Conventions
- **Appendix I** — Comparison Tables — Vector DBs, Embedding Models, LLM Providers, Tracing Backends (Phoenix vs LangSmith vs Langfuse: self-hosting, egress, callback vs ambient, UI-render surface)
- **Appendix J** — Suggested Exercises and Project Extensions
- **Appendix K** — Architecture Decision Records (the full `Decisions.md` ledger — ADR-001 embedding model, ADR-002 vector store, ADR-003 classic-to-agentic, ADR-007 NAC→DC→LBC pipeline, ADR-010 four-phase state machine, ADR-012 split system prompt, ADR-013 thumbdown persistence, ADR-020 `check_answer_quality` removal from tool schema, ADR-053 evidence-based threshold tuning, ADR-054 HF Router adoption, ADR-055 dedicated `json_fix_llm`, ADR-056 multi-verdict quality judge, ADR-057 `combine_tracks` with `defer=True`, ADR-058 draft-as-synthesis-input, ADR-059 Conservative-Grounding Prompt Pattern, ADR-060 LLM backend consolidation, ADR-061 direct JSON list for query variants, ADR-062 full backend consolidation, ADR-063 Phoenix as primary observability backend, ADR-064 `_TracingHandler` logging bridge, ADR-065 divergent `llm_setup` between pipelines, ADR-066 Langfuse as third tracing backend, ADR-067 explicit `config` threading — and the ~50 others)
- **Appendix L** — API Endpoints Reference (the contents of `API_ENDPOINTS.txt`: dual-port LangChain/LangGraph setup, request/response shapes, Postman recipes)
- **Appendix M** — Concurrency and Rate-Limiting Patterns Cookbook — `ThreadPoolExecutor` timeout wrapper, semaphore-guarded LLM calls, FIFO-queue serializer, capped exponential backoff with jitter, `LLMRateLimitAbortError` handling
- **Appendix N** — The Five LLM Roles Reference — `llm`, `judge_llm`, `json_fix_llm`, `llm_tool`, `merge_llm`: what each does, which provider serves it in the current build, and how to swap

---

*End of Index*
