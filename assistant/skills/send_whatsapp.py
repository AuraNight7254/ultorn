from pathlib import Path
from urllib.parse import quote
import os
import webbrowser
import ctypes
import time

from assistant.core.contacts import find_contacts, load_contacts
from assistant.skills.base import PreparedAction, Result, Skill


def open_whatsapp_link(url: str) -> bool:
    if os.name == "nt":
        os.startfile(url)
        return True
    return webbrowser.open(url)


def get_foreground_window_details() -> tuple[str, str]:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return "", ""

    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, title_buffer, length + 1)

    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_handle = ctypes.windll.kernel32.OpenProcess(
        0x0400 | 0x0010,
        False,
        pid.value,
    )
    process_name = ""
    if process_handle:
        image_buffer = ctypes.create_unicode_buffer(260)
        size = ctypes.c_ulong(260)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
            process_handle,
            0,
            image_buffer,
            ctypes.byref(size),
        ):
            process_name = os.path.basename(image_buffer.value)
        ctypes.windll.kernel32.CloseHandle(process_handle)
    return process_name, title_buffer.value


def press_enter_in_foreground_window() -> None:
    try:
        from pywinauto import Desktop
    except ImportError as error:
        raise ImportError("pywinauto is not installed.") from error

    import ctypes

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        raise OSError("No foreground window is available.")
    window = Desktop(backend="uia").window(handle=hwnd)
    window.set_focus()
    window.type_keys("{ENTER}")


class SendWhatsAppSkill(Skill):
    name = "send_whatsapp"
    description = "Prepare and open a WhatsApp message for a configured contact."
    parameters = {
        "type": "object",
        "properties": {
            "contact": {"type": "string", "description": "Configured contact name or alias."},
            "text": {"type": "string", "description": "Message text preserving the user's language."},
        },
        "required": ["contact", "text"],
        "additionalProperties": False,
    }
    risk = "confirm"

    def __init__(
        self,
        contacts_path: Path | None = None,
        launcher=open_whatsapp_link,
        window_details=get_foreground_window_details,
        enter_presser=press_enter_in_foreground_window,
        sleeper=time.sleep,
    ):
        self.contacts_path = contacts_path
        self.launcher = launcher
        self.window_details = window_details
        self.enter_presser = enter_presser
        self.sleeper = sleeper
        self.auto_send = False
        self.send_delay_seconds = 3

    def prepare(self, **params) -> PreparedAction:
        contact_name = params.get("contact")
        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            return PreparedAction(status="error", reply="The WhatsApp message text cannot be empty.")
        if not isinstance(contact_name, str) or not contact_name.strip():
            return PreparedAction(status="missing", reply="Which contact should receive the WhatsApp message?")

        try:
            contacts = load_contacts(self.contacts_path)
        except FileNotFoundError:
            return PreparedAction(
                status="missing",
                reply="contacts.yaml is missing; copy config/contacts.example.yaml to config/contacts.yaml.",
            )
        except (OSError, ValueError) as error:
            return PreparedAction(status="error", reply=f"{error}")

        matches = find_contacts(contact_name, contacts)
        if not matches:
            return PreparedAction(
                status="missing",
                reply=f"I don't have {contact_name} configured; add the contact to config/contacts.yaml.",
            )

        selected_name = params.get("contact_choice")
        if len(matches) > 1 and not selected_name:
            candidates = tuple(
                {"name": contact.name, "number": contact.number}
                for contact in matches
            )
            return PreparedAction(status="ambiguous", candidates=candidates)
        if len(matches) > 1:
            matches = [contact for contact in matches if contact.name == selected_name]
        if len(matches) != 1:
            return PreparedAction(status="missing", reply="No contact was selected.")

        contact = matches[0]
        return PreparedAction(
            status="ready",
            params={
                "contact": contact.name,
                "name": contact.name,
                "number": contact.number,
                "text": text,
            },
        )

    def run(self, **params) -> Result:
        name = params.get("name")
        number = params.get("number")
        text = params.get("text")
        if not isinstance(name, str) or not isinstance(number, str) or not isinstance(text, str):
            return Result(ok=False, reply="The WhatsApp message could not be prepared.")

        url = f"whatsapp://send?phone={number[1:]}&text={quote(text, safe='')}"
        try:
            opened = self.launcher(url)
        except (OSError, ValueError) as error:
            return Result(ok=False, reply=f"I couldn't open WhatsApp: {error}.")
        if opened is False:
            return Result(ok=False, reply="I couldn't open WhatsApp.")

        if not self.auto_send:
            return Result(
                ok=True,
                reply="WhatsApp was opened with the message ready; press Send.",
                auto_send_attempted=False,
                auto_send_window_check_passed=None,
            )

        if self.send_delay_seconds < 0:
            return Result(
                ok=False,
                reply="The WhatsApp message is typed but needs you to press Send.",
                auto_send_attempted=True,
                auto_send_window_check_passed=None,
            )

        self.sleeper(self.send_delay_seconds)
        try:
            process_name, title = self.window_details()
        except (OSError, ValueError):
            process_name, title = "", ""

        process_matches = process_name.strip().casefold() == "whatsapp.root"
        if not process_matches:
            return Result(
                ok=True,
                reply="The message is typed but needs you to press Send.",
                auto_send_attempted=True,
                auto_send_window_check_passed=False,
                foreground_process=process_name,
                foreground_title=title,
            )

        try:
            self.enter_presser()
        except (ImportError, OSError, RuntimeError):
            return Result(
                ok=True,
                reply="The message is typed but needs you to press Send.",
                auto_send_attempted=True,
                auto_send_window_check_passed=True,
                foreground_process=process_name,
                foreground_title=title,
            )

        return Result(
            ok=True,
            reply="Enter pressed in WhatsApp.",
            auto_send_attempted=True,
            auto_send_window_check_passed=True,
            foreground_process=process_name,
            foreground_title=title,
        )
