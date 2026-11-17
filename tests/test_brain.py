import json
from urllib.request import Request

from assistant.core.brain import Brain
from assistant.core.logger import ActionLogger
from assistant.core.providers.base import ModelDecision, RateLimitError
from assistant.core.providers import create_provider
from assistant.core.providers.ollama import OllamaProvider
from assistant.skills.base import Result, Skill


class FakeProvider:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.tools = None

    def choose(self, command, tools, system_prompt):
        self.tools = tools
        if self.error:
            raise self.error
        return self.decision


class FakeSkill(Skill):
    name = "test_action"
    description = "Run a test action."
    parameters = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    risk = "safe"

    def __init__(self):
        self.received = None

    def run(self, **params):
        self.received = params
        return Result(ok=True, reply="Action completed.")


def test_brain_executes_registered_skill_and_logs_action(tmp_path):
    skill = FakeSkill()
    provider = FakeProvider(ModelDecision(tool_name="test_action", arguments={"value": "hello"}))
    logger = ActionLogger(tmp_path / "actions.jsonl")
    brain = Brain(provider, {skill.name: skill}, logger)

    reply = brain.process("do the test action")

    record = json.loads((tmp_path / "actions.jsonl").read_text(encoding="utf-8"))
    assert reply == "Action completed."
    assert skill.received == {"value": "hello"}
    assert record["raw_command"] == "do the test action"
    assert record["skill"] == "test_action"
    assert record["params"] == {"value": "hello"}
    assert record["confirmed"] is False
    assert record["result"]["ok"] is True


def test_brain_rejects_invalid_tool_arguments_without_running_skill(tmp_path):
    skill = FakeSkill()
    provider = FakeProvider(
        ModelDecision(tool_name="test_action", arguments={"value": "hello", "extra": "no"})
    )
    brain = Brain(provider, {skill.name: skill}, ActionLogger(tmp_path / "actions.jsonl"))

    reply = brain.process("run it")

    assert "couldn't safely match" in reply
    assert skill.received is None


def test_brain_returns_friendly_rate_limit_message_and_logs(tmp_path):
    provider = FakeProvider(error=RateLimitError("limited"))
    log_path = tmp_path / "actions.jsonl"
    brain = Brain(provider, {}, ActionLogger(log_path))

    reply = brain.process("hello")

    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert reply == "I'm rate-limited right now; please try again shortly."
    assert record["result"]["ok"] is False


def test_ollama_provider_posts_tool_schemas_and_parses_tool_call(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_time",
                                    "arguments": {},
                                }
                            }
                        ]
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("assistant.core.providers.ollama.urlopen", fake_urlopen)
    provider = OllamaProvider({"model": "llama3.1:8b"})
    tools = [{"type": "function", "function": {"name": "get_time"}}]

    decision = provider.choose("what time is it?", tools, "Be concise.")

    body = json.loads(captured["request"].data.decode("utf-8"))
    assert isinstance(captured["request"], Request)
    assert captured["timeout"] == 60
    assert body["model"] == "llama3.1:8b"
    assert body["tools"] == tools
    assert decision == ModelDecision(tool_name="get_time", arguments={})


def test_provider_is_selected_from_configuration():
    provider = create_provider({"name": "ollama", "model": "llama3.1:8b"})

    assert isinstance(provider, OllamaProvider)
