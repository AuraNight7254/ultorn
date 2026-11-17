from datetime import datetime

from assistant.skills.get_time import GetTimeSkill
from assistant.skills.open_app import OpenAppSkill
from assistant.skills.open_website import OpenWebsiteSkill


def test_open_app_launches_only_a_configured_target():
    launched = []
    skill = OpenAppSkill(
        apps={"editor": {"aliases": ["text editor"], "target": "editor.exe"}},
        launcher=launched.append,
    )

    result = skill.run(app="TEXT EDITOR")
    unknown = skill.run(app="unknown app")

    assert result.ok is True
    assert result.reply == "Opening editor."
    assert launched == ["editor.exe"]
    assert unknown.ok is False
    assert "won't guess" in unknown.reply


def test_open_website_opens_only_configured_http_urls():
    opened = []
    skill = OpenWebsiteSkill(
        websites={"example": {"aliases": ["example site"], "url": "https://example.com"}},
        opener=lambda url: opened.append(url) or True,
    )

    result = skill.run(website="example site")
    unknown = skill.run(website="unlisted")

    assert result.ok is True
    assert opened == ["https://example.com"]
    assert unknown.ok is False
    assert opened == ["https://example.com"]


def test_open_website_rejects_non_web_schemes():
    skill = OpenWebsiteSkill(
        websites={"unsafe": {"aliases": [], "url": "file:///private.txt"}},
        opener=lambda _: True,
    )

    result = skill.run(website="unsafe")

    assert result.ok is False
    assert "invalid website URL" in result.reply


def test_get_time_returns_local_time():
    skill = GetTimeSkill(clock=lambda: datetime(2026, 11, 17, 9, 5))

    result = skill.run()

    assert result.ok is True
    assert result.reply == "It's 9:05 AM."
