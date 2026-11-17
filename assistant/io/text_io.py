def read_command(assistant_name: str) -> str | None:
    command = input(f"{assistant_name}> ").strip()
    return command or None
