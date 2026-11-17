from datetime import datetime

from assistant.skills.get_time import GetTimeSkill
from assistant.skills.open_app import OpenAppSkill
from assistant.skills.open_website import OpenWebsiteSkill
from assistant.skills.send_whatsapp import SendWhatsAppSkill
from assistant.core.contacts import load_contacts


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


def test_send_whatsapp_declined_confirmation_is_handled_in_brain(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: ["علی"]\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    launched = []
    skill = SendWhatsAppSkill(contacts_path, launcher=lambda url: launched.append(url) or True)
    prepared = skill.prepare(contact="Ali", text="Main late hoon")

    assert prepared.status == "ready"
    assert prepared.params["number"] == "+923001234567"


def test_send_whatsapp_launcher_error(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    skill = SendWhatsAppSkill(
        contacts_path,
        launcher=lambda _: (_ for _ in ()).throw(OSError("launch failed")),
        enter_presser=lambda: (_ for _ in ()).throw(AssertionError("Enter must not be pressed")),
    )
    skill.auto_send = True
    skill.send_delay_seconds = 0
    prepared = skill.prepare(contact="Ali", text="Hello")

    result = skill.run(**prepared.params)

    assert result.ok is False
    assert "couldn't open WhatsApp" in result.reply


def test_send_whatsapp_encodes_urdu_text_as_utf8(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "علی":\n    aliases: ["Ali"]\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    opened = []
    skill = SendWhatsAppSkill(contacts_path, launcher=lambda url: opened.append(url) or True)
    prepared = skill.prepare(contact="Ali", text="سلام، میں دیر سے آ رہا ہوں")

    result = skill.run(**prepared.params)

    assert result.ok is True
    assert opened[0].startswith("whatsapp://send?phone=923001234567&text=")
    assert "%20" in opened[0]
    assert "%D8" in opened[0]
    assert "press Send" in result.reply
    assert "sent" not in result.reply.casefold()


def test_send_whatsapp_missing_contacts_yaml(tmp_path):
    skill = SendWhatsAppSkill(tmp_path / "contacts.yaml")

    prepared = skill.prepare(contact="Ali", text="Hello")

    assert prepared.status == "missing"
    assert "contacts.example.yaml" in prepared.reply


def test_invalid_number_in_contacts_yaml(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "03001234567"\n',
        encoding="utf-8",
    )

    try:
        load_contacts(contacts_path)
    except ValueError as error:
        assert "invalid E.164" in str(error)
    else:
        raise AssertionError("Expected invalid E.164 number")


def test_two_contacts_with_same_alias(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n'
        '  "Ali One":\n'
        '    aliases: ["Ali"]\n'
        '    number: "+923001111111"\n'
        '  "Ali Two":\n'
        '    aliases: ["Ali"]\n'
        '    number: "+923002222222"\n',
        encoding="utf-8",
    )
    skill = SendWhatsAppSkill(contacts_path)

    prepared = skill.prepare(contact="Ali", text="Hello")

    assert prepared.status == "ambiguous"
    assert len(prepared.candidates) == 2


def test_send_whatsapp_empty_text(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    skill = SendWhatsAppSkill(contacts_path)

    prepared = skill.prepare(contact="Ali", text="   ")

    assert prepared.status == "error"
    assert "cannot be empty" in prepared.reply


def test_auto_send_off_does_not_check_window(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    presses = []
    skill = SendWhatsAppSkill(
        contacts_path,
        launcher=lambda _: True,
        window_details=lambda: ("WhatsApp.Root", "WhatsApp"),
        enter_presser=lambda: presses.append(True),
        sleeper=lambda _: None,
    )
    skill.auto_send = False
    prepared = skill.prepare(contact="Ali", text="Hello")

    result = skill.run(**prepared.params)

    assert result.reply == "WhatsApp was opened with the message ready; press Send."
    assert result.auto_send_attempted is False
    assert presses == []


def test_auto_send_wrong_foreground_window_logs_details(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    presses = []
    skill = SendWhatsAppSkill(
        contacts_path,
        launcher=lambda _: True,
        window_details=lambda: ("chrome.exe", "Google Chrome"),
        enter_presser=lambda: presses.append(True),
        sleeper=lambda _: None,
    )
    skill.auto_send = True
    skill.send_delay_seconds = 0
    prepared = skill.prepare(contact="Ali", text="Hello")

    result = skill.run(**prepared.params)

    assert result.auto_send_attempted is True
    assert result.auto_send_window_check_passed is False
    assert result.foreground_process == "chrome.exe"
    assert result.foreground_title == "Google Chrome"
    assert "needs you to press Send" in result.reply
    assert presses == []


def test_auto_send_library_missing_needs_manual_send(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "+923001234567"\n',
        encoding="utf-8",
    )

    def missing_library():
        raise ImportError("pywinauto is not installed")

    skill = SendWhatsAppSkill(
        contacts_path,
        launcher=lambda _: True,
        window_details=lambda: ("WhatsApp.Root", "WhatsApp"),
        enter_presser=missing_library,
        sleeper=lambda _: None,
    )
    skill.auto_send = True
    skill.send_delay_seconds = 0
    prepared = skill.prepare(contact="Ali", text="Hello")

    result = skill.run(**prepared.params)

    assert result.auto_send_attempted is True
    assert result.auto_send_window_check_passed is True
    assert result.reply == "The message is typed but needs you to press Send."


def test_auto_send_presses_enter_once_on_matching_window(tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    contacts_path.write_text(
        'contacts:\n  "Ali":\n    aliases: []\n    number: "+923001234567"\n',
        encoding="utf-8",
    )
    presses = []
    skill = SendWhatsAppSkill(
        contacts_path,
        launcher=lambda _: True,
        window_details=lambda: ("WhatsApp.Root", "WhatsApp"),
        enter_presser=lambda: presses.append(True),
        sleeper=lambda _: None,
    )
    skill.auto_send = True
    skill.send_delay_seconds = 0
    prepared = skill.prepare(contact="Ali", text="Hello")

    result = skill.run(**prepared.params)

    assert presses == [True]
    assert result.reply == "Enter pressed in WhatsApp."
    assert result.auto_send_attempted is True
    assert result.auto_send_window_check_passed is True
