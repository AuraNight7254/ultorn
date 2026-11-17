import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from assistant.core.providers.base import ModelDecision, ProviderError, RateLimitError


class GroqProvider:
    provider_name = "groq"

    def __init__(self, settings):
        self.model = settings.get("model")
        self.base_url = settings.get("base_url", "https://api.groq.com/openai/v1").rstrip("/")
        self.timeout = settings.get("timeout", 60)
        self.api_key = settings.get("api_key") or os.environ.get("GROQ_API_KEY")

    def choose(self, command, tools, system_prompt):
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY is not configured.")
        if not self.model:
            raise ProviderError("Groq model is not configured.")

        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": command},
            ],
            "tools": tools,
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise RateLimitError("Groq is rate-limited; please try again shortly.") from error
            raise ProviderError(f"Groq returned HTTP {error.code}: {error.reason}.") from error
        except (URLError, TimeoutError) as error:
            raise ProviderError("I couldn't reach Groq; please check your connection.") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("Groq returned an invalid response.") from error

        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("Groq returned an invalid response.") from error

        tool_calls = message.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            raise ProviderError("Groq returned invalid tool calls.")
        if len(tool_calls) > 1:
            raise ProviderError("The model requested multiple actions; please ask for one action at a time.")
        if tool_calls:
            try:
                function = tool_calls[0]["function"]
                name = function["name"]
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise ProviderError("Groq returned an invalid tool call.") from error
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise ProviderError("Groq returned an invalid tool call.")
            return ModelDecision(tool_name=name, arguments=arguments)

        content = message.get("content", "")
        if not isinstance(content, str):
            raise ProviderError("Groq returned an invalid response.")
        return ModelDecision(text=content)
