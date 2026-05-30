from inkmoment.engines import get_engine
from server.services.dependency_service import configure_runtime_model_cache


def require_engine(engine: str, state_store, logger) -> None:
    """Validate engine dependencies before a job enters the expensive scan stage."""
    configure_runtime_model_cache(state_store)
    get_engine(engine).prewarm(logger)
