"""Read actual document evidence through the single provider boundary."""

from backend.llm import ManualReviewRequired, extract_document, provider_name
from .common import finding, result


def run(context):
    extracted, findings = [], []
    for document in context["documents"]:
        try:
            fields = extract_document(document["path"], context["settings"])
        except ManualReviewRequired as error:
            findings.append(finding("documents", str(error), {"document_id": document["id"], "filename": document["filename"]},
                                    "Review the document manually or configure the selected vision provider."))
            continue
        evidence = {"document_id": document["id"], "filename": document["filename"], **fields}
        extracted.append(evidence)
        if fields["confidence"] < context["settings"]["extraction_confidence_min"] or fields["ambiguities"]:
            findings.append(finding("extraction", "Document extraction is uncertain.", evidence,
                                    "Provide a clear document or manually verify ambiguous fields."))
        required = {"bank_letter": ["bank_holder_name", "bank_account"], "cancelled_cheque": ["bank_holder_name", "bank_account"],
                    "w9": ["legal_name", "tax_id"], "gst_certificate": ["legal_name", "tax_id"], "vat_certificate": ["legal_name", "tax_id"],
                    "incorporation_certificate": ["legal_name", "incorporated_on"]}.get(fields["doc_type"], [])
        for field in required:
            if not fields[field]:
                findings.append(finding(field, f"Document lacks readable {field}.", evidence, "Supply complete, legible evidence."))
    context["extracted"] = extracted
    return result("Some evidence needs manual review." if findings else "Documents read and classified.", findings,
                  {"documents": extracted, "provider": provider_name(), "offline_demo": provider_name() == "mock"},
                  "needs_manual_review" if findings else "passed")
