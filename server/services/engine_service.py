from inkmoment.engines import get_engine
from server.services.dependency_service import configure_runtime_model_cache
from server.services.llm_service import ensure_ark_key_loaded


def require_engine(engine: str, state_store, logger) -> None:
    """Validate engine dependencies before a job enters the expensive scan stage."""
    configure_runtime_model_cache(state_store)
    selected_engine = get_engine(engine)
    if selected_engine.requires_llm_model:
        ensure_ark_key_loaded()
    selected_engine.prewarm(logger)
