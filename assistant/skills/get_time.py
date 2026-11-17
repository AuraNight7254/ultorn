from datetime import datetime
from typing import Callable

from assistant.skills.base import Result, Skill


class GetTimeSkill(Skill):
    name = "get_time"
    description = "Tell the user the current local time."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    risk = "safe"

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now().astimezone()):
        self.clock = clock

    def run(self, **params) -> Result:
        now = self.clock()
        return Result(ok=True, reply=f"It's {now.strftime('%I:%M %p').lstrip('0')}.")
