"""Deterministic evidence comparisons and bank-letter date checks."""

from datetime import date
from backend.rules.names import name_score
from .common import finding, result


def compact(value):
    return "".join(str(value or "").upper().split()).replace("-", "")


def run(context):
    form, settings = context["form"], context["settings"]
    findings, comparisons = [], []
    for evidence in context.get("extracted", []):
        source = {"document_id": evidence["document_id"], "filename": evidence["filename"]}
        if evidence["confidence"] < settings["extraction_confidence_min"]:
            continue
        for key in ("legal_name", "bank_holder_name"):
            if not evidence.get(key):
                continue
            acceptable = [form.get("legal_name"), form.get("trade_name")]
            score = max([name_score(evidence[key], candidate) for candidate in acceptable if candidate] or [0])
            comparisons.append({"field": key, "score": round(score, 4), "source": source})
            if score < settings["name_match_threshold"]:
                findings.append(finding(key, "Bank holder differs from declared legal/trade name." if key == "bank_holder_name" else "Document legal name differs from submitted entity.",
                                        {**source, "observed": evidence[key], "submitted": acceptable, "similarity": score},
                                        "Provide bank-holder alias proof or corrected evidence." if key == "bank_holder_name" else "Provide evidence identifying the submitted entity.",
                                        "review" if key == "bank_holder_name" or score >= settings["name_match_review_band"]["min"] else "reject"))
        for key in ("tax_id", "bank_account", "iban", "aba", "ifsc", "incorporated_on"):
            if key == "tax_id" and evidence["doc_type"] == "w9" and form.get("country") != "US":
                continue
            if evidence.get(key) and form.get(key) and compact(evidence[key]) != compact(form[key]):
                findings.append(finding(key, f"Document {key} contradicts submitted value.", {**source, "observed": evidence[key], "submitted": form[key]},
                                        f"Resolve the {key} contradiction with authoritative evidence.", "reject"))
        if evidence["doc_type"] == "bank_letter":
            limit = settings["document_validity_rules"]["bank_letter"]["max_age_days"]
            try:
                age = (context["reference_date"] - date.fromisoformat(evidence.get("issued_on") or "")).days
                if age < 0 or age > limit:
                    raise ValueError
            except (TypeError, ValueError):
                findings.append(finding("issued_on", "Bank letter date is missing, future-dated or stale.", source, f"Provide a bank letter issued within {limit} days."))
    return result("Cross-document identity, bank and tax consistency checked.", findings, {"name_comparisons": comparisons})
