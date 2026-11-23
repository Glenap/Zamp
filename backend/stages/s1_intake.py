"""Required form and file-count checks."""

import re
from .common import finding, result


def run(context):
    form, settings = context["form"], context["settings"]
    findings = [finding(key, f"Required field {key} is missing.", action=f"Provide {key}.")
                for key in settings["required_form_fields"] if not str(form.get(key) or "").strip()]
    count = len(context["documents"])
    if not settings["min_documents"] <= count <= settings["max_documents"]:
        findings.append(finding("documents", "Document count is outside configured limits.", count,
                                f"Supply {settings['min_documents']} to {settings['max_documents']} PDF/image documents."))
    email = form.get("contact_email", "")
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        findings.append(finding("contact_email", "Contact email is malformed.", email, "Provide a valid business email."))
    return result("Submission intake checked.", findings, {"document_count": count})
