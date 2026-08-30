#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports")

import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime, timezone

import urllib.error
import urllib.request

API_URL = "https://api.openai.com/v1/chat/completions"
API_KEY_FILE = os.path.expanduser("~/.config/openai-key")
MODEL = os.environ.get("TEXT_TO_VCF_MODEL", "").strip() or "gpt-4.1"

PHONE_EMAIL_TYPE = {"type": ["string", "null"], "enum": ["home", "work", "mobile", "main", "fax", None]}

CONTACTS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "contacts",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["contacts"],
            "properties": {
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "prefix", "given_name", "family_name", "org", "department",
                            "title", "phones", "emails", "address", "url", "note",
                        ],
                        "properties": {
                            "prefix": {"type": ["string", "null"], "description": "Academic/honorific title, e.g. Mag., Dr., DI"},
                            "given_name": {"type": ["string", "null"]},
                            "family_name": {"type": ["string", "null"]},
                            "org": {"type": ["string", "null"]},
                            "department": {"type": ["string", "null"]},
                            "title": {"type": ["string", "null"]},
                            "phones": {
                                "type": ["array", "null"],
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["value", "type"],
                                    "properties": {
                                        "value": {"type": "string"},
                                        "type": PHONE_EMAIL_TYPE,
                                    },
                                },
                            },
                            "emails": {
                                "type": ["array", "null"],
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["value", "type"],
                                    "properties": {
                                        "value": {"type": "string"},
                                        "type": PHONE_EMAIL_TYPE,
                                    },
                                },
                            },
                            "address": {
                                "type": ["object", "null"],
                                "additionalProperties": False,
                                "required": ["street", "zip", "city", "country"],
                                "properties": {
                                    "street": {"type": ["string", "null"]},
                                    "zip": {"type": ["string", "null"]},
                                    "city": {"type": ["string", "null"]},
                                    "country": {"type": ["string", "null"]},
                                },
                            },
                            "url": {"type": ["string", "null"]},
                            "note": {"type": ["string", "null"]},
                        },
                    },
                },
            },
        },
    },
}

SYSTEM_PROMPT = """\
You extract contact details from text snippets (email signatures, imprints,
websites, messages). Parse as many details as possible.
Return valid JSON only.
Schema:
{
  "contacts": [
    {
      "prefix": "Academic/honorific title (Mag., Dr., DI, Prof.)" or null,
      "given_name": "First name" or null,
      "family_name": "Last name" or null,
      "org": "Company/organization" or null,
      "department": "Department/unit within the organization" or null,
      "title": "Job title/role of the person" or null,
      "phones": [{"value": "+43 ...", "type": "home"|"work"|"mobile"|"main"|"fax"|null}] or null,
      "emails": [{"value": "a@b.c", "type": "home"|"work"|null}] or null,
      "address": {"street": ..., "zip": ..., "city": ..., "country": ...} or null,
      "url": "Website URL" or null,
      "note": "All additional details" or null
    }
  ]
}
Rules:
- Extract ALL contacts found in the text
- Keep the original language for names, titles and addresses
- Normalize phone numbers to international format when the country is clear,
  otherwise keep them as written
- Parse leftover details into the note: department, assistant, office hours,
  availability ("call after 2pm"), registration numbers, pronouns
- Put organizational units (Abteilung, Ambulanz, Institut, Referat) into
  department, not title; title is only for a person's role
- Do not invent data; use null for anything not present in the text"""


def fail(message, detail=""):
    """Report and stop.

    The message goes to stdout because the Alfred notification only shows
    stdout; anything on stderr is invisible outside the debug console. The
    server's response body is detail, and stays on stderr so the notification
    keeps to one readable line.
    """
    print(message)
    if detail:
        print(detail, file=sys.stderr)
    raise SystemExit(1)


def load_api_key():
    """Environment first, then the key file. Neither is a fatal surprise."""
    key = os.environ.get("OPENAI_API_KEY")
    if key and key.strip():
        return key.strip()
    try:
        with open(API_KEY_FILE, "r") as f:
            key = f.read().strip()
    except FileNotFoundError:
        fail(
            "No API key. Set OPENAI_API_KEY in the workflow configuration, "
            f"or put the key in {API_KEY_FILE}."
        )
    if not key:
        fail(f"{API_KEY_FILE} is empty.")
    return key


def get_input_text():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    fail("No input text")


def extract_contacts(text, api_key):
    payload = {
        "model": MODEL,
        "response_format": CONTACTS_RESPONSE_FORMAT,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 401:
            fail("OpenAI rejected the key (401). Check it in the workflow configuration.", detail)
        if exc.code == 429:
            fail("Rate limited or out of quota (429).", detail)
        fail(f"OpenAI returned HTTP {exc.code}.", detail)
    except urllib.error.URLError as exc:
        # No response object exists here, so nothing may reference one.
        fail(f"Could not reach OpenAI: {exc.reason}")

    content = body["choices"][0]["message"]["content"].strip()
    contacts = json.loads(content).get("contacts", [])

    kept = []
    for c in contacts:
        has_name = c.get("given_name") or c.get("family_name")
        has_reachable = c.get("phones") or c.get("emails")
        if not has_name and not has_reachable:
            print(f"Skipping contact without name or phone/email: {c.get('org', '?')}", file=sys.stderr)
            continue
        kept.append(c)
    return kept


def vcf_escape(text):
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


# vCard 3.0 TEL/EMAIL type parameters; "main" gets an Apple item label instead.
TYPE_PARAM = {"home": "HOME", "work": "WORK", "mobile": "CELL", "fax": "FAX"}


def build_vcard(contact, source_text):
    lines = ["BEGIN:VCARD", "VERSION:3.0"]

    prefix = contact.get("prefix") or ""
    given = contact.get("given_name") or ""
    family = contact.get("family_name") or ""
    org = contact.get("org")
    full_name = " ".join(p for p in (prefix, given, family) if p)

    lines.append(f"N:{vcf_escape(family)};{vcf_escape(given)};;{vcf_escape(prefix)};")
    fn = full_name or org or (contact.get("emails") or [{}])[0].get("value") \
        or (contact.get("phones") or [{}])[0].get("value") or "Contact"
    lines.append(f"FN:{vcf_escape(fn)}")

    department = contact.get("department")
    if org or department:
        lines.append(f"ORG:{vcf_escape(org)};{vcf_escape(department)}" if department else f"ORG:{vcf_escape(org)}")
    if contact.get("title"):
        lines.append(f"TITLE:{vcf_escape(contact['title'])}")

    item = 0
    for field, entries in (("TEL", contact.get("phones")), ("EMAIL", contact.get("emails"))):
        for entry in entries or []:
            value = vcf_escape(entry.get("value", "").strip())
            if not value:
                continue
            type_param = TYPE_PARAM.get(entry.get("type") or "")
            if type_param:
                lines.append(f"{field};TYPE={type_param}:{value}")
            elif entry.get("type") == "main":
                item += 1
                lines.append(f"item{item}.{field}:{value}")
                lines.append(f"item{item}.X-ABLabel:_$!<Main>!$_")
            else:
                lines.append(f"{field}:{value}")

    addr = contact.get("address")
    if addr and any(addr.get(k) for k in ("street", "zip", "city", "country")):
        lines.append(
            "ADR;TYPE=WORK:;;"
            f"{vcf_escape(addr.get('street'))};{vcf_escape(addr.get('city'))};;"
            f"{vcf_escape(addr.get('zip'))};{vcf_escape(addr.get('country'))}"
        )

    if contact.get("url"):
        lines.append(f"URL:{vcf_escape(contact['url'])}")

    note = "\n\n".join(p for p in (contact.get("note"), source_text) if p)
    if note:
        lines.append(f"NOTE:{vcf_escape(note)}")

    lines.append(f"REV:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    lines.append("END:VCARD")
    return lines


def build_vcf(contacts, source_text):
    lines = []
    for contact in contacts:
        lines.extend(build_vcard(contact, source_text))
    return "\r\n".join(fold_line(l) for l in lines)


def fold_line(line):
    # RFC 2426: lines longer than 75 octets should be folded with CRLF + space.
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks, i = [], 0
    while i < len(encoded):
        # First chunk gets 75 bytes; continuation chunks get 74 (the leading space counts).
        size = 75 if not chunks else 74
        end = min(i + size, len(encoded))
        # Don't split inside a multi-byte UTF-8 sequence.
        while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(encoded[i:end].decode("utf-8"))
        i = end
    return "\r\n ".join(chunks)


def main():
    try:
        text = get_input_text()
        api_key = load_api_key()
        contacts = extract_contacts(text, api_key)
        if not contacts:
            print("No contacts found in text")
            return

        vcf_content = build_vcf(contacts, text)

        fd, filepath = tempfile.mkstemp(suffix=".vcf", prefix="text-to-vcf-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(vcf_content)

        subprocess.run(["open", filepath], check=False)

        n = len(contacts)
        print(f"Opened {n} contact{'s' if n != 1 else ''} in Contacts")

    except json.JSONDecodeError:
        print("Failed to parse contact data from API")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
