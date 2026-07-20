"""Central tracing policy for all instrumented workflow nodes and services.

Every module-level ``instrument_namespace`` hook delegates selection, naming,
input shaping, and output shaping to this file. The resulting LangChain run is
shared by Langfuse, LangSmith, and Phoenix.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import inspect
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar, cast

from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.runnables.config import var_child_runnable_config

from app_workflow.config import (
    _EXCLUDED_ARGUMENTS,
    _MAX_COLLECTION_ITEMS,
    _MAX_TEXT_CHARS,
)


F = TypeVar("F", bound=Callable[..., Any])
InputBuilder = Callable[[Mapping[str, Any]], Any]
OutputBuilder = Callable[[Any], Any]

@dataclass(frozen=True)
class TraceSpec:
    """Central input/output policy for one trace or a group of traces."""

    input_builder: InputBuilder
    output_builder: OutputBuilder


def _include_argument(name: str) -> bool:
    normalized = name.lower()
    if normalized in _EXCLUDED_ARGUMENTS:
        return False
    return not normalized.endswith(("_client", "_handler"))


def _type_name(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _summarize(value: Any, *, depth: int = 0) -> Any:
    """Make trace data useful and bounded without changing application data."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= _MAX_TEXT_CHARS:
            return value
        return {
            "preview": value[:_MAX_TEXT_CHARS],
            "character_count": len(value),
            "truncated": True,
        }
    if isinstance(value, Path):
        return str(value)
    if depth >= 3:
        return {"type": _type_name(value)}
    if isinstance(value, Mapping):
        items = list(value.items())
        summarized = {
            str(key): _summarize(item, depth=depth + 1)
            for key, item in items[:_MAX_COLLECTION_ITEMS]
        }
        if len(items) > _MAX_COLLECTION_ITEMS:
            summarized["_trace_summary"] = {
                "item_count": len(items),
                "truncated": True,
            }
        return summarized
    if isinstance(value, (list, tuple, set, frozenset)):
        values = list(value)
        return {
            "item_count": len(values),
            "items": [
                _summarize(item, depth=depth + 1)
                for item in values[:_MAX_COLLECTION_ITEMS]
            ],
            "truncated": len(values) > _MAX_COLLECTION_ITEMS,
        }

    shape = getattr(value, "shape", None)
    if shape is not None:
        return {
            "type": _type_name(value),
            "shape": list(shape),
            "dtype": str(getattr(value, "dtype", "unknown")),
        }

    # Service objects belong in the trace, but as identity/configuration rather
    # than a serialized object graph which may contain credentials or clients.
    summary: dict[str, Any] = {"type": _type_name(value)}
    for attribute in ("model_name", "collection_name", "name", "timeout"):
        try:
            attribute_value = getattr(value, attribute, None)
        except Exception:
            continue
        if isinstance(attribute_value, (str, int, float, bool)):
            summary[attribute] = attribute_value
    return summary


def _default_input(arguments: Mapping[str, Any]) -> Any:
    return {
        name: _summarize(value)
        for name, value in arguments.items()
        if _include_argument(name)
    }


def _default_output(result: Any) -> Any:
    if result is None:
        return {"status": "completed"}
    return _summarize(result)


def _selected_input(*names: str) -> InputBuilder:
    def build(arguments: Mapping[str, Any]) -> Any:
        return {
            name: _summarize(arguments[name])
            for name in names
            if name in arguments and _include_argument(name)
        }

    return build


def _collection_output(result: Any) -> Any:
    if result is None:
        return {"status": "completed"}
    if isinstance(result, Mapping):
        return {
            "field_count": len(result),
            "fields": list(result.keys())[:_MAX_COLLECTION_ITEMS],
            "value": _summarize(result),
        }
    if isinstance(result, (list, tuple, set, frozenset)):
        return {
            "item_count": len(result),
            "items": _summarize(result)["items"],
        }
    return _default_output(result)


def _verdict_output(result: Any) -> Any:
    if not isinstance(result, Mapping):
        return _default_output(result)
    keys = (
        "verdict",
        "overall_reason",
        "relevant",
        "fabricated_claims",
        "dropped_claims",
        "lost_relevant_information",
    )
    return {key: _summarize(result[key]) for key in keys if key in result}


def _llm_output(result: Any) -> Any:
    return {
        "ok": getattr(result, "ok", None),
        "content": _summarize(getattr(result, "content", "")),
        "error_kind": str(getattr(result, "error_kind", "")) or None,
        "status_code": getattr(result, "status_code", None),
        "error_message": _summarize(getattr(result, "error_message", "")),
    }


_DEFAULT_SPEC = TraceSpec(_default_input, _default_output)

# Exact policies for operations whose useful trace contract is well-defined.
_TRACE_SPECS: dict[str, TraceSpec] = {
    "Embeddings / EmbeddingManager.generate_embedding": TraceSpec(
        _selected_input("text", "batch_size", "show_progress"), _default_output
    ),
    "Embeddings / EmbeddingManager.cosine_similarity": TraceSpec(
        _selected_input("vec_a", "vec_b"), _default_output
    ),
    "Retriever / RAGRetriever.retrieve": TraceSpec(
        _selected_input("query", "top_k", "score_threshold"), _collection_output
    ),
    "Retriever / RAGRetriever.retrieve_separate": TraceSpec(
        _selected_input(
            "query",
            "top_k",
            "top_l",
            "doc_score_threshold",
            "learned_score_threshold",
        ),
        _collection_output,
    ),
    "Retriever / RAGRetriever._query_collection": TraceSpec(
        _selected_input("query_embedding", "collection", "top_k"),
        _collection_output,
    ),
    "Vector Store / VectorStore.add_document": TraceSpec(
        _selected_input("documents", "embeddings"), _default_output
    ),
    "Vector Store / VectorStore.add_documents_in_batches": TraceSpec(
        _selected_input("documents", "embeddings", "batch_size"), _default_output
    ),
    "LLM Caller / llm_invoke": TraceSpec(
        _selected_input("llm", "messages", "tools", "caller_tag"), _llm_output
    ),
    "LLM Caller / _invoke_once": TraceSpec(
        _selected_input("llm", "messages", "tools", "caller_tag"), _llm_output
    ),
    "Validation / validate_retrieval": TraceSpec(
        _selected_input("query", "chunks"), _verdict_output
    ),
    "Validation / validate_merge": TraceSpec(
        _selected_input("source_chunks", "merged_chunk"), _verdict_output
    ),
    "Validation / validate_redundancy": TraceSpec(
        _selected_input("window_chunks", "groups"), _verdict_output
    ),
    "Validation / validate_lbc": TraceSpec(
        _selected_input("query", "original_chunk", "compressed_chunk"),
        _verdict_output,
    ),
    "LLM Output Repair / fix_llm_output": TraceSpec(
        _selected_input("expected_output", "raw_response", "correct", "llm"),
        _collection_output,
    ),
    "Feedback Store / FeedbackStore.log": TraceSpec(
        _selected_input(
            "query",
            "answer",
            "sources",
            "quality",
            "document_retrieved_chunks",
            "learned_qa_retrieved_chunks",
            "retrieved_chunks",
            "request_id",
            "variants",
        ),
        _default_output,
    ),
    "Feedback Store / FeedbackStore.mark_last_bad": TraceSpec(
        _selected_input("feedback", "variants"),
        _default_output,
    ),
    "Self Learning / SelfLearner.run_distillation": TraceSpec(
        _selected_input("batch_size"), _default_output
    ),
    "Self Learning / SelfLearner._generate_qa_pairs": TraceSpec(
        _selected_input("interaction"), _collection_output
    ),
}

# Group policies cover all current and future traced helpers in these modules.
_GROUP_SPECS: dict[str, TraceSpec] = {
    "Database": TraceSpec(_default_input, _default_output),
    "Learned QA Store": TraceSpec(_default_input, _collection_output),
    "Query Variants": TraceSpec(_default_input, _collection_output),
    "Retrieval Node": TraceSpec(_default_input, _collection_output),
    "Retrieval Validation Node": TraceSpec(_default_input, _collection_output),
    "Deduplication and Merge": TraceSpec(_default_input, _collection_output),
    "NAC Compression": TraceSpec(_default_input, _collection_output),
    "DC Compression": TraceSpec(_default_input, _collection_output),
    "LBC Compression": TraceSpec(_default_input, _collection_output),
    "Draft Generation Node": TraceSpec(_default_input, _collection_output),
    "Answer Generation Node": TraceSpec(_default_input, _collection_output),
    "Answer Quality Node": TraceSpec(_default_input, _verdict_output),
    "Workflow Routing": TraceSpec(_default_input, _default_output),
}


def _trace_spec(name: str) -> TraceSpec:
    exact = _TRACE_SPECS.get(name)
    if exact is not None:
        return exact
    group = name.partition(" / ")[0]
    return _GROUP_SPECS.get(group, _DEFAULT_SPEC)


def traced_operation(name: str) -> Callable[[F], F]:
    """Trace a function using its centrally registered input/output policy."""

    spec = _trace_spec(name)

    def decorate(func: F) -> F:
        if getattr(func, "__workflow_traced__", False):
            return func

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = inspect.signature(func).bind_partial(*args, **kwargs)
            trace_input = spec.input_builder(bound.arguments)
            actual_result: list[Any] = []

            config = kwargs.get("config")
            if config is None:
                try:
                    config = var_child_runnable_config.get()
                except LookupError:
                    config = None

            def execute(_trace_input: Any) -> Any:
                result = func(*args, **kwargs)
                actual_result.append(result)
                try:
                    return spec.output_builder(result)
                except Exception as exc:
                    # Observability must never make a successful app operation fail.
                    return {
                        "status": "completed",
                        "trace_output_error": f"{type(exc).__name__}: {exc}",
                    }

            RunnableLambda(execute, name=name).invoke(
                trace_input,
                config=cast(RunnableConfig | None, config),
            )
            return actual_result[0]

        setattr(wrapper, "__workflow_traced__", True)
        setattr(wrapper, "__trace_name__", name)
        return cast(F, wrapper)

    return decorate


def instrument_namespace(
    namespace: dict[str, Any],
    group: str,
    *,
    exclude: set[str] | None = None,
) -> None:
    """Apply the central tracing policy to functions defined by a module."""

    module_name = str(namespace.get("__name__", ""))
    skipped = exclude or set()
    for symbol, value in list(namespace.items()):
        if symbol in skipped or symbol.startswith("__"):
            continue
        if inspect.isfunction(value) and value.__module__ == module_name:
            namespace[symbol] = traced_operation(f"{group} / {symbol}")(value)
            continue
        if not inspect.isclass(value) or value.__module__ != module_name:
            continue
        for method_name, descriptor in list(vars(value).items()):
            if method_name in skipped or method_name.startswith("__"):
                continue
            trace_name = f"{group} / {value.__name__}.{method_name}"
            if isinstance(descriptor, staticmethod):
                setattr(
                    value,
                    method_name,
                    staticmethod(traced_operation(trace_name)(descriptor.__func__)),
                )
            elif isinstance(descriptor, classmethod):
                setattr(
                    value,
                    method_name,
                    classmethod(traced_operation(trace_name)(descriptor.__func__)),
                )
            elif inspect.isfunction(descriptor):
                setattr(value, method_name, traced_operation(trace_name)(descriptor))
