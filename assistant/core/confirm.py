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
