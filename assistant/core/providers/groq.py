import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from assistant.core.providers.base import ModelDecision, ProviderError, RateLimitError


class GroqProvider:
    provider_name = "groq"

    def __init__(self, settings, env_path: Path | None = None):
        self.model = settings.get("model")
        self.base_url = settings.get("base_url", "https://api.groq.com/openai/v1").rstrip("/")
        self.timeout = settings.get("timeout", 60)
        self.env_path = (
            Path(env_path)
            if env_path is not None
            else Path(__file__).resolve().parents[3] / ".env"
        )

    def choose(self, command, tools, system_prompt):
        api_key = self._read_api_key()
        if not api_key:
            raise ProviderError("GROQ_API_KEY is not configured in .env.")
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
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ultron/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_data = response.read()
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                if status != 200:
                    response_body = self._sanitize_error_body(response_data, api_key)
                    detail = response_body or "empty response body"
                    raise ProviderError(f"Groq returned HTTP {status}: {detail}")
                payload = json.loads(response_data.decode("utf-8"))
        except HTTPError as error:
            response_body = self._read_error_body(error, api_key)
            if error.code == 429:
                message = "Groq is rate-limited; please try again shortly."
                if response_body:
                    message = f"Groq is rate-limited (HTTP 429): {response_body}"
                raise RateLimitError(message) from error
            detail = response_body or str(error.reason)
            raise ProviderError(
                f"Groq returned HTTP {error.code}: {detail}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise ProviderError("I couldn't reach Groq; please check your connection.") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("Groq returned an invalid response.") from error

        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("Groq returned an invalid response.") from error
        if not isinstance(message, dict):
            raise ProviderError("Groq returned an invalid response.")

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

    @staticmethod
    def _read_error_body(error: HTTPError, api_key: str) -> str:
        try:
            response_body = error.read()
        except OSError:
            return ""
        return GroqProvider._sanitize_error_body(response_body, api_key)

    @staticmethod
    def _sanitize_error_body(response_body: bytes, api_key: str) -> str:
        response_body = response_body.decode("utf-8", errors="replace")
        if api_key:
            response_body = response_body.replace(api_key, "[redacted]")
        return response_body[:300]

    def _read_api_key(self) -> str | None:
        environment_key = os.environ.get("GROQ_API_KEY")
        if environment_key and environment_key.strip():
            return environment_key.strip()
        try:
            with self.env_path.open(encoding="utf-8") as env_file:
                for line in env_file:
                    entry = line.strip()
                    if not entry or entry.startswith("#") or "=" not in entry:
                        continue
                    name, value = entry.split("=", 1)
                    if name.strip() == "GROQ_API_KEY":
                        return value.strip().strip("\"'")
        except FileNotFoundError:
            return None
        except OSError as error:
            raise ProviderError("I couldn't read the Groq API key from .env.") from error
        return None
