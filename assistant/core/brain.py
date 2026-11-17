import re
from typing import Any

from assistant.core.logger import ActionLogger
from assistant.core.providers.base import Provider, ProviderError, RateLimitError
from assistant.core.confirm import ask_choice, confirm_action
from assistant.skills.base import PreparedAction, Result, Skill


class Brain:
    def __init__(
        self,
        provider: Provider,
        skills: dict[str, Skill],
        logger: ActionLogger,
        assistant_name: str = "ultron",
        confirm_fn=confirm_action,
        choice_fn=ask_choice,
    ):
        self.provider = provider
        self.skills = skills
        self.logger = logger
        self.assistant_name = assistant_name
        self.confirm_fn = confirm_fn
        self.choice_fn = choice_fn

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
                    prepared = skill.prepare(**parameters)
                    if prepared.status == "ambiguous":
                        choices = [
                            f"{candidate['name']} ({candidate['number']})"
                            for candidate in prepared.candidates
                        ]
                        selected = self.choice_fn(
                            "Which one?",
                            choices,
                        )
                        if selected is None:
                            result = Result(ok=False, reply="No contact was selected.")
                        else:
                            selected_candidate = next(
                                candidate
                                for candidate in prepared.candidates
                                if f"{candidate['name']} ({candidate['number']})" == selected
                            )
                            prepared = skill.prepare(
                                **parameters,
                                contact_choice=selected_candidate["name"],
                            )
                            result, confirmed = self._execute_prepared(
                                skill,
                                prepared,
                                parameters,
                            )
                    elif prepared.status != "ready":
                        result = Result(ok=False, reply=prepared.reply)
                    else:
                        result, confirmed = self._execute_prepared(skill, prepared, parameters)
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

    def _execute_prepared(
        self,
        skill: Skill,
        prepared: PreparedAction,
        original_parameters: dict[str, Any],
    ) -> tuple[Result, bool]:
        if prepared.status == "ambiguous":
            return Result(ok=False, reply=prepared.reply), False
        if prepared.status != "ready":
            return Result(ok=False, reply=prepared.reply), False

        if skill.risk == "confirm":
            prompt_params = prepared.params or original_parameters
            prompt = (
                f"Send '{prompt_params['text']}' to "
                f"{prompt_params['name']} ({prompt_params['number']})?"
            )
            if not self.confirm_fn(prompt):
                return Result(ok=False, reply="The WhatsApp message was declined."), False
            return skill.run(**(prepared.params or original_parameters)), True

        return skill.run(**(prepared.params or original_parameters)), False

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
            "Keep WhatsApp message text in the user's original language and wording. "
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
