import logging

from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)


def get_langfuse_handler() -> CallbackHandler:
    handler = CallbackHandler()
    logger.info("Langfuse tracing handler initialized.")
    return handler
