from collections.abc import Callable


YES = {
    "yes",
    "y",
    "haan",
    "han",
    "haa",
    "ji",
    "jee",
    "ji haan",
    "jee haan",
}


def confirm_action(prompt: str, input_fn: Callable[[str], str] = input) -> bool:
    answer = input_fn(prompt)
    if not isinstance(answer, str):
        return False
    return answer.strip().casefold() in YES


def ask_choice(prompt: str, choices: list[str], input_fn: Callable[[str], str] = input) -> str | None:
    lines = [prompt]
    lines.extend(f"{index}. {choice}" for index, choice in enumerate(choices, start=1))
    answer = input_fn("\n".join(lines) + "\n")
    if not isinstance(answer, str):
        return None
    answer = answer.strip()
    if not answer.isdigit():
        return None
    index = int(answer)
    if index < 1 or index > len(choices):
        return None
    return choices[index - 1]
