import logging
from state import GraphState
from services.services import feedback_store

logger = logging.getLogger(__name__)


def user_input_node(state: GraphState) -> dict:
    raw = (state["user_input"] or "").strip()
    raw_lower = raw.lower()
    if raw_lower in {"exit", "quit"}:
        return {"command": "exit"}
    if raw_lower == "stats":
        return {"command": "stats"}
    if raw_lower == "learn":
        return {"command": "learn"}
    if raw_lower == "bad":
        return {"command": "bad"}

    # Load blocked variants for this query (zero-result phrasings from prior runs)
    blocked_variants = feedback_store.load_failed_variants(raw)

    # Load prior thumbdowns (user-flagged bad answers for this query)
    prior_thumbdowns: list[dict] = feedback_store.find_thumbdowns_for_query(raw) or []

    # Expand blocked from thumbdown variant history — every reformulation that led
    # to a bad answer is also blocked, matching the agent_query.py pattern.
    existing_blocked: set[str] = set(blocked_variants)
    for td in prior_thumbdowns:
        for v in (td.get("variants") or []):
            vq = (v.get("query") or "").strip()
            if vq and vq not in existing_blocked:
                blocked_variants.append(vq)
                existing_blocked.add(vq)

    if blocked_variants:
        logger.debug(
            "[USER_INPUT] %d blocked variant(s) injected for query: %r",
            len(blocked_variants), raw,
        )
    if prior_thumbdowns:
        logger.debug(
            "[USER_INPUT] %d prior thumbdown record(s) found for query: %r",
            len(prior_thumbdowns), raw,
        )

    return {
        "command": "",
        "blocked_variants": blocked_variants,
        "prior_thumbdowns": prior_thumbdowns,
    }
