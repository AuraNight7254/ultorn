# GitHub Copilot Instructions: VisionX / Ultron

## Project

Build a clean, configurable, zero-cost personal desktop assistant for Windows. The assistant
name is `ultron` and the wake word is `Hey Ultron`, but both must come from
`assistant/config/settings.yaml`, not source code.

## Development rules

- Python 3.11+.
- Use Windows paths and behavior in Windows-specific code.
- `config/settings.yaml` controls assistant name, provider, model, voice, and hotkey.
- `config/apps.yaml`, `config/contacts.yaml`, and `config/projects.yaml` are allowlists.
- Provider and model must remain configurable and provider-agnostic.
- Ollama is the current local default. Future Groq, Anthropic, and OpenAI providers must be
  separate files in `assistant/core/providers/`.
- Never send raw shell commands to an LLM.
- An LLM may only call registered skills.
- Skills may only act on allowlisted configuration entries.
- Confirm all risky actions (`confirm`) and wait for an explicit yes.
- Ask for configuration rather than guessing missing apps, contacts, or projects.
- Never commit secrets, logs, virtual environments, or Python caches.
- Keep dependencies pinned and minimal.
- Reply in one short sentence.
- Add mock-based tests for every skill and run `pytest`.
- Do not add a paid dependency or service without stopping to ask first.

## Architecture

```text
Input -> STT -> Brain -> Skill -> Reply
```

Core modules:

- `assistant/main.py`
- `assistant/core/brain.py`
- `assistant/core/providers/`
- `assistant/core/registry.py`
- `assistant/core/confirm.py`
- `assistant/core/logger.py`
- `assistant/skills/base.py`
- `assistant/io/text_io.py`
- `assistant/io/stt.py`
- `assistant/io/tts.py`
- `assistant/io/wake.py`
- `assistant/config/settings.yaml`
- `assistant/config/apps.yaml`
- `assistant/config/contacts.yaml`
- `assistant/config/projects.yaml`

## Skill contract

```python
class Skill:
    name: str
    description: str
    parameters: dict  # JSON Schema
    risk: str         # "safe" or "confirm"

    def run(self, **params):
        return Result(ok=bool, reply="One short sentence")
```

Add a skill by adding one file under `assistant/skills/`. Do not modify core registration code.

## Current phase

Phase 1 is complete: text input, provider-agnostic brain, Ollama provider, automatic skill
registry, `open_app`, `open_website`, and `get_time`.

Before implementing later phases, show a short plan and file list and wait for approval.

Before a phase is complete:

1. Run `pytest`.
2. Confirm external calls are mocked.
3. Confirm `.env` and `logs/` are ignored.
4. Log timestamp, raw command, skill, params, confirmation state, and result.
