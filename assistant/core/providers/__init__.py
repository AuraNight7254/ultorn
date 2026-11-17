import importlib
import inspect
import pkgutil


def create_provider(settings):
    provider_name = settings.get("name")
    matches = []
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if (
                candidate.__module__ == module.__name__
                and getattr(candidate, "provider_name", None) == provider_name
            ):
                matches.append(candidate)

    if len(matches) != 1:
        if not matches:
            raise ValueError(f"Provider '{provider_name}' is not available.")
        raise ValueError(f"Provider '{provider_name}' is registered more than once.")
    return matches[0](settings)