import importlib
import inspect
import pkgutil

import assistant.skills
from assistant.skills.base import Skill


def discover_skills():
    discovered = {}
    for module_info in pkgutil.iter_modules(assistant.skills.__path__):
        module = importlib.import_module(f"{assistant.skills.__name__}.{module_info.name}")
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if (
                candidate is not Skill
                and issubclass(candidate, Skill)
                and candidate.__module__ == module.__name__
                and not inspect.isabstract(candidate)
            ):
                skill = candidate()
                if skill.name in discovered:
                    raise ValueError(f"Duplicate skill name: {skill.name}.")
                discovered[skill.name] = skill
    return discovered
