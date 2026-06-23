from .config import KitConfig, load_config


def build_erc8004_deep_agent(*args, **kwargs):
    from .agent import build_erc8004_deep_agent as _build

    return _build(*args, **kwargs)


__all__ = ["build_erc8004_deep_agent", "KitConfig", "load_config"]
