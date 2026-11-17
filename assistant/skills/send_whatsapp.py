from pathlib import Path
from urllib.parse import quote
import os
import webbrowser

from assistant.core.contacts import find_contacts, load_contacts
from assistant.skills.base import PreparedAction, Result, Skill


def open_whatsapp_link(url: str) -> bool:
    if os.name == "nt":
        os.startfile(url)
        return True
    return webbrowser.open(url)


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

    def __init__(self, contacts_path: Path | None = None, launcher=open_whatsapp_link):
        self.contacts_path = contacts_path
        self.launcher = launcher

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
        return Result(
            ok=True,
            reply="WhatsApp was opened with the message ready; press Send.",
        )
