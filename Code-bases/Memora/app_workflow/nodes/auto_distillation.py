import logging
from state import GraphState
from app_workflow.services.services import self_learner
from app_workflow.services.switches import get_switches

logger = logging.getLogger(__name__)


def auto_distillation(state: GraphState, config=None) -> dict:
    logger.info("[AUTO_DISTILLATION] threshold reached — running distillation")
    self_learner.run_distillation(config=config, switches=get_switches(state))
    return {}
