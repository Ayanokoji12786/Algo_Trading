from trading_system.config.schema import SystemConfig


def default_config() -> SystemConfig:
    """The frozen baseline configuration described in Docs/Implementation_Spec.md.

    Returns a fresh instance each call so callers can freely override fields
    via dataclasses.replace() without mutating shared state.
    """
    return SystemConfig()
