import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 1. Sub-query generation flow
ENABLE_SUB_QUERY_GENERATION = True
ENABLE_QUERY_VARIANTS_OUTPUT_FIX = True

# 2. Retrieval deduplication/merge and its LLM output repair
ENABLE_RETRIEVAL_DEDUP_MERGE = True
ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX = True

ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION = True
ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION_OUTPUT_FIX = True

# 3. Retrieval validation and its LLM output repair
ENABLE_RETRIEVAL_VALIDATION = True
ENABLE_RETRIEVAL_VALIDATION_OUTPUT_FIX = True

# 4. Compression stages, their validators, and their LLM output repair
ENABLE_NAC_COMPRESSION = True
ENABLE_DC_COMPRESSION = True
ENABLE_LBC_COMPRESSION = True
ENABLE_COMPRESSION_VALIDATION = True   
ENABLE_COMPRESSION_OUTPUT_FIX = True

# 5. Answer draft creation (disabled = generate final answer directly)
ENABLE_ANSWER_DRAFT_CREATION = True

# 6. Answer quality check (only applies when draft creation is enabled)
ENABLE_ANSWER_QUALITY_CHECK = True
ENABLE_ANSWER_QUALITY_OUTPUT_FIX = True

# 7. Automatic distillation
ENABLE_AUTO_DISTILLATION = False

# 8. QA-pair generation and its LLM output repair
ENABLE_QA_PAIR_GENERATION = True
ENABLE_QA_PAIR_OUTPUT_FIX = True

# 9. Global LLM output repair across the overall implementation
ENABLE_GLOBAL_LLM_OUTPUT_FIX = True

# 10. Observability/tracing toggles
ENABLE_PHOENIX_TRACING = False
ENABLE_LANGFUSE_TRACING = True

_EXCLUDED_ARGUMENTS = {"self", "cls", "config", "callbacks", "client", "handler"}
_MAX_TEXT_CHARS = 2_000
_MAX_COLLECTION_ITEMS = 20


# CONSTANTS
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

VECTOR_STORE_PATH = str(_PROJECT_ROOT / "data" / "vector_store")
# SEARCH_ROOTS = [
#     _PROJECT_ROOT / "data" / "pdfs",
#     _PROJECT_ROOT / "data" / "textfiles",
#     _PROJECT_ROOT / "data" / "csv",
#     _PROJECT_ROOT / "data" / "word",
#     _PROJECT_ROOT / "data" / "html",
#     _PROJECT_ROOT / "data" / "json",
#     _PROJECT_ROOT / "data",
# ]
JSON_DIR = _PROJECT_ROOT / "data" / "json"
COLLECTION_NAME = "documents"
LEARNED_COLLECTION = "learned_qa"
MAX_TOTAL_RETRIEVALS = 5
RETRIEVAL_TOP_K = 4
RETRIEVAL_TOP_L = 4
LEARN_EVERY_N = 5
PAD_TOKENS = int(os.getenv("PAD_TOKENS", "0"))
MERGE_SIMILARITY_THRESHOLD = 0.90
PRE_RETRIEVAL_SIM_THRESHOLD = 0.95
BRANCH_BUDGET_FOR_SHORT_QUESTIONS = 2
BRANCH_BUDGET_FOR_MEDIUM_QUESTIONS = 2
BRANCH_BUDGET_FOR_CONJUNCTION_QUESTIONS = 3
BRANCH_BUDGET_SHORT_WORD_COUNT = 4
BRANCH_BUDGET_MEDIUM_WORD_COUNT = 8
BRANCH_BUDGET_CONJUNCTION_KEYWORDS = [
    "and", "or", "both", "versus", "vs", "compare",
    "difference", "how", "why", "explain", "list", "describe", "contrast",
]
LBC_MIN_RETENTION_RATIO = 0.35
DC_WINDOW_SIZE = 3
LLM_RESPONSE_RETRY_LIMIT = 3
LLM_RATE_LIMIT_MAX_ATTEMPTS = 3
LLM_RATE_LIMIT_BACKOFF_BASE_SECONDS = 1.0
LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS = 30.0
LLM_RATE_LIMIT_MAX_DELAY_SECONDS = 1800.0
MIN_COOLDOWN_TIME = 0.0
MAX_COOLDOWN_TIME = 30.0
MIN_FEEDBACK_LEN = 10
_JSON_REPAIR_TRIES = 2
# UNSTRUCTURED_EXT = {".pdf", ".txt", ".doc", ".docx", ".html", ".htm"}
# TABULAR_EXT     = {".csv", ".xls", ".xlsx"}
# SUPPORTED_EXT   = UNSTRUCTURED_EXT | TABULAR_EXT | {".json"}
# CHUNK_SIZE = 1000
# CHUNK_OVERLAP = 200
# BATCH_SIZE = 512
# MIN_CHUNK_CHARS = 150
MIN_SIMILARITY = 0.5
DOCUMENTS_MIN_SIMILARITY = 0.53
LEARNED_QA_MIN_SIMILARITY = 0.57
MIN_ANSWER_LENGTH = 50
COMPRESS_MIN_TOKENS = 500
LLM_RESPONSE_TIMEOUT_SECONDS = 150
RETRIEVAL_TIMEOUT_SECONDS = 10
EMBEDDING_ENCODING_TIMEOUT_SECONDS = 5
