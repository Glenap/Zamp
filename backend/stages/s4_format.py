"""Structural and checksum validators run in plain code."""

from datetime import date
from backend.rules.aba import is_valid_aba
from backend.rules.ein import is_valid_ein
from backend.rules.gstin import is_valid_gstin
from backend.rules.iban import is_valid_iban
from backend.rules.ifsc import is_valid_ifsc
from backend.rules.vat import is_valid_de_vat
from .common import finding, result


def run(context):
    form, findings, checks = context["form"], [], []
    validator = {"US": is_valid_ein, "IN": is_valid_gstin, "DE": is_valid_de_vat}.get(form.get("country"))
    if not validator:
        findings.append(finding("tax_id", "This jurisdiction requires manual tax validation.", form.get("country"), "Verify tax registration with an authorized source."))
    elif form.get("tax_id"):
        checks.append(("tax_id", form["tax_id"], validator(form["tax_id"]), "form"))
    for key, validator in (("iban", is_valid_iban), ("aba", is_valid_aba), ("ifsc", is_valid_ifsc)):
        if form.get(key):
            checks.append((key, form[key], validator(form[key]), "form"))
    for evidence in context.get("extracted", []):
        validator = {"w9": is_valid_ein, "gst_certificate": is_valid_gstin,
                     "vat_certificate": is_valid_de_vat if form.get("country") == "DE" else None}.get(evidence["doc_type"])
        if validator and evidence.get("tax_id"):
            checks.append(("tax_id", evidence["tax_id"], validator(evidence["tax_id"]), evidence["filename"]))
        for key, validator in (("iban", is_valid_iban), ("aba", is_valid_aba), ("ifsc", is_valid_ifsc)):
            if evidence.get(key):
                checks.append((key, evidence[key], validator(evidence[key]), evidence["filename"]))
    for key, value, valid, source in checks:
        if not valid:
            findings.append(finding(key, f"{key} failed structural validation.", {"value": value, "source": source}, f"Correct {key} and matching evidence."))
    if form.get("incorporated_on"):
        try:
            if date.fromisoformat(form["incorporated_on"]) > context["reference_date"]:
                raise ValueError
        except (ValueError, TypeError):
            findings.append(finding("incorporated_on", "Incorporation date is invalid or future-dated.", form["incorporated_on"], "Correct the incorporation date and certificate."))
    return result("Identifier formats and checksums checked; ownership is not asserted.", findings,
                  {"checks": [{"field": k, "value": v, "valid": ok, "source": src} for k, v, ok, src in checks]})
