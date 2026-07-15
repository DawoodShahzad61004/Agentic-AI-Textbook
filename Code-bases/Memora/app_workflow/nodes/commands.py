import logging
from state import GraphState
from app_workflow.services import services
from app_workflow.services.services import feedback_store, learned_collection, self_learner
from app_workflow.config import ENABLE_AUTO_DISTILLATION, LEARN_EVERY_N, MIN_FEEDBACK_LEN

logger = logging.getLogger(__name__)


def cmd_stats(state: GraphState) -> dict:
    total = feedback_store.count()
    good = feedback_store.count_good()
    learned = learned_collection.count()
    print(f"\n  Total interactions logged : {total}")
    print(f"  Successful (OK quality)   : {good}")
    print(f"  Learned QA pairs in store : {learned}")
    if ENABLE_AUTO_DISTILLATION:
        next_n = LEARN_EVERY_N - (good % LEARN_EVERY_N) if good > 0 else LEARN_EVERY_N
        print(f"  Next distillation at      : {next_n} more good interaction(s)\n")
    else:
        print("  Automatic distillation    : disabled\n")
    return {}


def cmd_learn(state: GraphState, config=None) -> dict:
    print("Forcing distillation now…")
    added = self_learner.run_distillation(config=config)
    print(f"Added {added} QA pair(s) to learned_qa.\n")
    return {}


def cmd_bad(state: GraphState) -> dict:
    feedback = (state.get("user_feedback") or "").strip()  # type: ignore[attr-defined]
    # Pass the variants captured during the previous answer run so that the
    # thumbdown entry records which chunks each reformulation retrieved.
    variants = list(services.last_variants_with_chunks)
    ok = feedback_store.mark_last_bad(feedback=feedback, variants=variants)
    if not ok:
        print("Nothing to flag yet.\n")
        return {}
    if feedback and len(feedback) >= MIN_FEEDBACK_LEN:
        print("Last answer flagged as bad and persisted to user_thumbdowns.json.\n")
    elif feedback:
        print(
            f"Last answer flagged as bad. Feedback too short"
            f" (<{MIN_FEEDBACK_LEN} chars) — not persisted.\n"
        )
    else:
        print("Last answer flagged as bad. No feedback provided.\n")
    return {}


def cmd_exit(state: GraphState) -> dict:
    logger.info("[EXIT] User requested exit.")
    print("Goodbye!")
    raise SystemExit(0)
