import json
import io
from urllib.request import Request
from urllib.error import HTTPError

from assistant.core.brain import Brain
from assistant.core.logger import ActionLogger
from assistant.core.providers.base import ModelDecision, ProviderError, RateLimitError
from assistant.core.providers import create_provider
from assistant.core.providers.ollama import OllamaProvider
from assistant.core.providers.groq import GroqProvider
from assistant.core.confirm import confirm_action
from assistant.core.registry import discover_skills
from assistant.skills.base import Result, Skill
from assistant.skills.send_whatsapp import SendWhatsAppSkill


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


def test_confirm_action_accepts_only_explicit_yes():
    assert confirm_action("Confirm? ", lambda _: "yes") is True
    assert confirm_action("Confirm? ", lambda _: "haan") is True
    assert confirm_action("Confirm? ", lambda _: "maybe") is False
    assert confirm_action("Confirm? ", lambda _: "") is False


def test_action_logger_writes_valid_json_lines(tmp_path):
    log_path = tmp_path / "actions.jsonl"
    logger = ActionLogger(log_path)
    logger.log("hello", "get_time", {}, False, Result(ok=True, reply="It's 1:00 PM."))
    logger.log("unknown", None, {}, False, Result(ok=False, reply="Not configured."))

    lines = log_path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 2
    assert records[0]["raw_command"] == "hello"
    assert records[0]["confirmed"] is False
    assert records[1]["skill"] is None


def test_registry_auto_discovers_phase_one_skills():
    skills = discover_skills()

    assert set(skills) == {"get_time", "open_app", "open_website", "send_whatsapp"}


def test_groq_provider_maps_http_429_to_rate_limit(monkeypatch):
    provider = GroqProvider({"model": "test-tool-model"})
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("assistant.core.providers.groq.urlopen", fake_urlopen)

    try:
        provider.choose("hello", [], "Be concise.")
    except RateLimitError as error:
        assert str(error) == "Groq is rate-limited; please try again shortly."
    else:
        raise AssertionError("Expected Groq rate-limit handling")


def test_groq_provider_explains_403_without_exposing_api_key(monkeypatch):
    api_key = "gsk_test_key_for_redaction"
    monkeypatch.setenv("GROQ_API_KEY", api_key)
    body = json.dumps(
        {
            "error": {
                "message": f"Key {api_key} cannot access this model.",
                "code": "model_access_denied",
            }
        }
    ).encode("utf-8")
    provider = GroqProvider({"model": "openai/gpt-oss-20b"})

    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(body),
        )

    monkeypatch.setattr("assistant.core.providers.groq.urlopen", fake_urlopen)

    try:
        provider.choose("open chrome", [], "Be concise.")
    except ProviderError as error:
        assert "openai/gpt-oss-20b" in str(error)
        assert "model_access_denied" not in str(error)
        assert api_key not in str(error)
        assert "cannot access this model" in str(error)
    else:
        raise AssertionError("Expected a Groq 403 provider error")


def test_groq_provider_reads_dotenv_and_posts_local_tool_schema(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text('GROQ_API_KEY="test-key"\n', encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "get_time",
                                            "arguments": "{}",
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("assistant.core.providers.groq.urlopen", fake_urlopen)
    provider = GroqProvider(
        {"model": "llama-3.3-70b-versatile"},
        env_path=env_path,
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Get local time.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    decision = provider.choose("what time is it?", tools, "Be concise.")

    request, timeout = calls[0]
    request_body = json.loads(request.data.decode("utf-8"))
    assert len(calls) == 1
    assert timeout == 60
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request_body["model"] == "llama-3.3-70b-versatile"
    assert request_body["tools"] == tools
    assert decision == ModelDecision(tool_name="get_time", arguments={})


def test_groq_provider_environment_key_overrides_dotenv(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("GROQ_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "environment-key")
    provider = GroqProvider({"model": "test-model"}, env_path=env_path)

    assert provider._read_api_key() == "environment-key"


def test_groq_provider_without_key_returns_provider_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    provider = GroqProvider(
        {"model": "test-model"},
        env_path=tmp_path / "missing.env",
    )

    try:
        provider.choose("hello", [], "Be concise.")
    except ProviderError as error:
        assert str(error) == "GROQ_API_KEY is not configured in .env."
    else:
        raise AssertionError("Expected a missing Groq key error")


def test_provider_is_selected_from_groq_or_ollama_configuration():
    groq = create_provider(
        {"name": "groq", "model": "llama-3.3-70b-versatile"}
    )
    ollama = create_provider({"name": "ollama", "model": "llama3.1:8b"})

    assert isinstance(groq, GroqProvider)
    assert isinstance(ollama, OllamaProvider)


def test_brain_declines_whatsapp_confirmation(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: ["علی"]\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    launched = []
    skill = SendWhatsAppSkill(contacts_path, launcher=lambda url: launched.append(url) or True)
    provider = FakeProvider(
        ModelDecision(
            tool_name="send_whatsapp",
            arguments={"contact": "Ali", "text": "Main late hoon"},
        )
    )
    brain = Brain(
        provider,
        {skill.name: skill},
        ActionLogger(tmp_path / "actions.jsonl"),
        confirm_fn=lambda prompt: False,
    )

    reply = brain.process("Ali ko message bhejo")

    assert reply == "The WhatsApp message was declined."
    assert launched == []


def test_brain_asks_which_contact_for_alias_ambiguity(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n'
        '  "Ali One":\n'
        '    aliases: ["Ali"]\n'
        '    number: "+923001111111"\n'
        '  "Ali Two":\n'
        '    aliases: ["Ali"]\n'
        '    number: "+923002222222"\n',
        encoding="utf-8",
    )
    skill = SendWhatsAppSkill(contacts_path, launcher=lambda _: True)
    provider = FakeProvider(
        ModelDecision(
            tool_name="send_whatsapp",
            arguments={"contact": "Ali", "text": "Hello"},
        )
    )
    choice_calls = []
    brain = Brain(
        provider,
        {skill.name: skill},
        ActionLogger(tmp_path / "actions.jsonl"),
        confirm_fn=lambda prompt: True,
        choice_fn=lambda prompt, choices: (
            choice_calls.append((prompt, choices)) or "Ali Two (+923002222222)"
        ),
    )

    reply = brain.process("Ali ko message bhejo")

    assert "press Send" in reply
    assert choice_calls[0][0] == "Which one?"
    assert len(choice_calls[0][1]) == 2


def test_brain_declined_confirmation_auto_send_on_never_presses_enter(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    presses = []
    skill = SendWhatsAppSkill(
        contacts_path,
        launcher=lambda _: True,
        window_details=lambda: ("WhatsApp.Root", "WhatsApp"),
        enter_presser=lambda: presses.append(True),
        sleeper=lambda _: None,
    )
    skill.auto_send = True
    provider = FakeProvider(
        ModelDecision(
            tool_name="send_whatsapp",
            arguments={"contact": "Ali", "text": "Hello"},
        )
    )
    brain = Brain(
        provider,
        {skill.name: skill},
        ActionLogger(tmp_path / "actions.jsonl"),
        confirm_fn=lambda prompt: False,
    )

    reply = brain.process("Ali ko message bhejo")

    assert reply == "The WhatsApp message was declined."
    assert presses == []
