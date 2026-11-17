import re
from typing import Any

from assistant.core.logger import ActionLogger
from assistant.core.providers.base import Provider, ProviderError, RateLimitError
from assistant.skills.base import Result, Skill


class Brain:
    def __init__(
        self,
        provider: Provider,
        skills: dict[str, Skill],
        logger: ActionLogger,
        assistant_name: str = "ultron",
    ):
        self.provider = provider
        self.skills = skills
        self.logger = logger
        self.assistant_name = assistant_name

    def process(self, command: str) -> str:
        skill_name = None
        parameters = {}
        confirmed = False
        try:
            decision = self.provider.choose(
                command=command,
                tools=[self._tool_schema(skill) for skill in self.skills.values()],
                system_prompt=self._system_prompt(),
            )
            if decision.tool_name is None:
                reply = _first_sentence(decision.text)
                if not reply:
                    reply = "I couldn't determine a response to that request."
                result = Result(ok=True, reply=reply)
            else:
                skill_name = decision.tool_name
                parameters = decision.arguments or {}
                skill = self.skills.get(skill_name)
                if skill is None or not _valid_parameters(skill.parameters, parameters):
                    result = Result(
                        ok=False,
                        reply="I couldn't safely match that request to an available action.",
                    )
                else:
                    result = skill.run(**parameters)
            self.logger.log(
                raw_command=command,
                skill=skill_name,
                params=parameters,
                confirmed=confirmed,
                result=result,
            )
            return _first_sentence(result.reply)
        except RateLimitError:
            return self._log_provider_error(
                command,
                skill_name,
                parameters,
                confirmed,
                "I'm rate-limited right now; please try again shortly.",
                ok=False,
            )
        except ProviderError as error:
            return self._log_provider_error(
                command,
                skill_name,
                parameters,
                confirmed,
                str(error),
                ok=False,
            )

    def _log_provider_error(self, command, skill_name, parameters, confirmed, reply, ok):
        result = Result(ok=ok, reply=_first_sentence(reply))
        self.logger.log(
            raw_command=command,
            skill=skill_name,
            params=parameters,
            confirmed=confirmed,
            result=result,
        )
        return result.reply

    def _system_prompt(self):
        return (
            f"You are {self.assistant_name}, a concise desktop assistant. "
            "Understand commands in English, Urdu, and Roman Urdu, including mixed language. "
            "Use only the supplied tools for desktop actions. Never invent apps or websites; "
            "if an item is not available in the tool configuration, ask the user to configure it. "
            "Do not suggest or produce shell commands. For non-action replies, answer in one short sentence."
        )

    @staticmethod
    def _tool_schema(skill):
        return {
            "type": "function",
            "function": {
                "name": skill.name,
                "description": skill.description,
                "parameters": skill.parameters,
            },
        }


def _valid_parameters(schema: dict[str, Any], parameters: dict[str, Any]) -> bool:
    if not isinstance(parameters, dict) or schema.get("type") != "object":
        return False
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return False
    if any(key not in properties for key in parameters):
        return False
    if any(key not in parameters for key in schema.get("required", [])):
        return False
    for key, value in parameters.items():
        expected_type = properties[key].get("type")
        if expected_type == "string" and (not isinstance(value, str) or not value.strip()):
            return False
        if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            return False
        if expected_type == "boolean" and not isinstance(value, bool):
            return False
    return True


def _first_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return ""
    return re.split(r"(?<=[.!?؟۔])\s+", normalized, maxsplit=1)[0]
