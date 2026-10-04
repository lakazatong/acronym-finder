import importlib
import pkgutil


def get_provider(name):
    if not isinstance(name, str):
        raise TypeError("provider name must be a string")

    name = name.lower()

    if not name.isidentifier() or name == "__init__":
        raise ValueError(f"invalid provider name: {name!r}")

    providers = {
        module.name for module in pkgutil.iter_modules(__path__) if not module.ispkg
    }

    if name not in providers:
        available = ", ".join(sorted(providers))
        raise ValueError(
            f"unknown provider '{name}'"
            + (f" (available: {available})" if available else "")
        )

    provider = importlib.import_module(
        f".{name}",
        __name__,
    )

    check = getattr(provider, "check", None)

    if not callable(check):
        raise TypeError(f"provider '{name}' does not define check(name)")

    return provider
