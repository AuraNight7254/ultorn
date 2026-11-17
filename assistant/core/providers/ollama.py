import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from assistant.core.providers.base import ModelDecision, ProviderError, RateLimitError


class OllamaProvider:
    provider_name = "ollama"

    def __init__(self, settings):
        self.model = settings.get("model", "llama3.1:8b")
        self.base_url = settings.get("base_url", "http://localhost:11434").rstrip("/")
        self.timeout = settings.get("timeout", 60)

    def choose(self, command, tools, system_prompt):
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": command},
            ],
            "tools": tools,
            "stream": False,
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise RateLimitError("Ollama is rate-limited; please try again shortly.") from error
            raise ProviderError(f"Ollama returned HTTP {error.code}: {error.reason}.") from error
        except (URLError, TimeoutError) as error:
            raise ProviderError(
                "I couldn't reach Ollama; check that it is running and the configured model is installed."
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("Ollama returned an invalid response.") from error

        try:
            message = payload["message"]
        except (KeyError, TypeError) as error:
            raise ProviderError("Ollama returned an invalid response.") from error
        if not isinstance(message, dict):
            raise ProviderError("Ollama returned an invalid response.")

        tool_calls = message.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            raise ProviderError("Ollama returned invalid tool calls.")
        if len(tool_calls) > 1:
            raise ProviderError("The model requested multiple actions; please ask for one action at a time.")
        if tool_calls:
            try:
                function = tool_calls[0]["function"]
                name = function["name"]
                arguments = function.get("arguments", {})
            except (KeyError, TypeError) as error:
                raise ProviderError("Ollama returned an invalid tool call.") from error
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise ProviderError("Ollama returned an invalid tool call.")
            return ModelDecision(tool_name=name, arguments=arguments)

        content = message.get("content", "")
        if not isinstance(content, str):
            raise ProviderError("Ollama returned an invalid response.")
        return ModelDecision(text=content)
