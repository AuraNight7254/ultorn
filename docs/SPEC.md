# VisionX Personal Assistant Specification

## What this is

A voice-controlled desktop assistant, like Siri, that performs daily tasks on the user's
computer:

- Open apps and websites
- Send WhatsApp messages
- Call contacts
- Run coding tasks in projects through Claude Code
- Set reminders

This is personal-use software first. It is also designed to become a product later, so the
implementation must remain clean and configurable.

- Assistant name: `ultron`
- Wake word (Phase 5): `Hey Ultron`
- Both assistant name and wake word come from `config/settings.yaml`, never hardcoded

## VisionX / Ultron naming

The repository and project are currently named Ultron/ultorn. Where the user refers to
`VisionX`, treat that as the overall product/spec name unless explicitly superseded.

## Zero-cost rule

Personal use must cost nothing. Use only free tools, free tiers that do not require a credit
card, or software that runs locally.

| Part | Free choice |
|---|---|
| Brain (LLM) | Groq API free tier (no card needed); Ollama locally as an offline option |
| Speech-to-text | faster-whisper locally; Groq Whisper free tier as a faster option |
| Text-to-speech | Piper or pyttsx3, both local |
| Wake word | openWakeWord, trained on the user's phrase |
| WhatsApp/calls | WhatsApp Desktop deep links and `tel:` links to Phone Link |
| Coding skill | Claude Code on the existing Claude plan |

Free tiers have rate limits. On rate-limit errors, tell the user one short sentence and do
not crash.

## Owner context

- Primary OS: Windows
- Python: 3.11+
- Commands may be English, Urdu, or Roman Urdu mixed with English
- The brain must understand all three language styles

Examples:

- `chrome kholo`
- `Ali ko message bhejo ke main late hoon`

Always check the actual OS at session start and tell the user if it differs from Windows.

## Architecture

Input → speech-to-text → brain → skill → reply (printed now, spoken from Phase 3)

```text
assistant/
  main.py                 # entry point
  core/
    brain.py              # command and skill schemas sent to provider
    providers/            # one file per LLM provider
    registry.py           # auto-discovers skills in skills/
    confirm.py            # confirms risky actions
    logger.py             # appends actions.jsonl entries
  skills/
    base.py               # Skill base class
    open_app.py           # one skill per file
  io/
    text_io.py            # typed input
    stt.py                # speech-to-text
    tts.py                # text-to-speech
    wake.py               # wake word
  config/
    settings.yaml         # name, provider, model, voice, hotkey
    apps.yaml             # app names and aliases
    contacts.yaml         # contact names and aliases
    projects.yaml         # project names and paths
  logs/
  tests/
  .env                    # API keys only
```

## Skill contract

Every skill must define:

- `name`
- `description`
- `parameters` as JSON Schema
- `risk`: `safe` or `confirm`
- `run(**params) -> Result(ok: bool, reply: str)`

The reply must be one short sentence suitable for display or speech.

Adding a skill means adding one file in `skills/`; core code must not require a change.

## Rules

1. The brain is provider-agnostic. Provider and model come from `config/settings.yaml`.
   The default provider is Ollama for the current no-cost implementation. Groq free-tier
   support may be added when a suitable tool-calling model and account limits are verified.
   Ollama, Groq, Anthropic, and OpenAI must remain separable one-provider-per-file.
2. The LLM never runs raw shell commands. It may only call registered skills, and skills may
   act only on allowlisted YAML configuration items.
3. Skills with `risk: "confirm"` include message sending, calls, git push, and deletion.
   Read the action back and wait for an explicit `yes`. If a contact, app, or project is not
   configured, ask the user. Never guess.
4. Secrets live only in `.env`. `.env` and `logs/` are ignored and must never be tracked.
   Ship `.env.example` without real secrets.
5. Every action is logged in `logs/actions.jsonl` with timestamp, raw command, skill,
   params, confirmation state, and result.
6. Replies are short: one sentence.
7. Every skill has tests with external calls mocked. Run `pytest` and pass it before a phase
   is complete.
8. Dependencies are minimal and pinned in `requirements.txt`.
9. Before writing code for a phase, show a short plan and file list and wait for approval.

## Phases

- [ ] 0. Setup: tools, folder, git, specification
- [ ] 1. Text brain, skill system, open_app, open_website, get_time
- [ ] 2. WhatsApp message skill and contacts
- [ ] 3. Voice: push-to-talk, STT, TTS
- [ ] 4. Call skill, coding skill, reminders
- [ ] 5. Wake word, system tray, startup
- [ ] 6. Product preparation

## Skill notes

### WhatsApp

Open this URI:

```text
whatsapp://send?phone=<number without +>&text=<URL-encoded text>
```

WhatsApp Desktop opens with the message typed. Confirm before sending. Do not use unofficial
WhatsApp libraries such as whatsapp-web.js or Baileys.

### Calls

Open a `tel:+923001234567` URI. On Windows this uses Phone Link when a phone is paired.

### Coding

Run Claude Code with the project working directory set to the allowlisted path:

```text
claude -p "<task>" --permission-mode acceptEdits --allowedTools "<scoped list>" --output-format json
```

Reply with the returned result summary. Only push after confirmation. Never use
`--dangerously-skip-permissions`.
