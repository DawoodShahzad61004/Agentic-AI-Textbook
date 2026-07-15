import os
from phoenix.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor


def setup_phoenix_tracing():
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:4317")
    project_name = os.getenv("PHOENIX_PROJECT_NAME", "rag-work")

    register(
        project_name=project_name,
        endpoint=endpoint,
        auto_instrument=True,
    )

    LangChainInstrumentor().instrument()