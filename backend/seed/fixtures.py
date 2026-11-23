"""Explicit scenario intent lives outside the submitted form and documents."""

from datetime import date, timedelta

from backend.rules.gstin import gstin_check_digit
from backend.rules.vat import de_vat_check_digit

NORTHWIND_ACCOUNT = "9000000101"
ABA = "021000021"
IFSC = "HDFC0001234"


def german_iban(account: int) -> str:
    bban = f"37040044{account:010d}"
    # DE -> 13,14; append zero check digits before computing the remainder.
    check = 98 - int(bban + "131400") % 97
    return f"DE{check:02d}{bban}"


def german_vat(body: str) -> str:
    return "DE" + body + de_vat_check_digit(body)


def indian_gstin(pan="AACCS1234K", state="33") -> str:
    body = state + pan + "1Z"
    return body + gstin_check_digit(body)


def form(name, country, domain, tax_id, account, incorporated_on="2018-04-16", **bank):
    return {
        "legal_name": name, "trade_name": None, "country": country,
        "contact_name": "Demo Procurement Contact", "contact_email": f"onboarding@{domain}",
        "email_domain": domain, "tax_id": tax_id,
        "tax_id_type": {"US": "EIN", "IN": "GSTIN", "DE": "VAT"}[country],
        "bank_account": account, "bank_holder_name": name,
        "incorporated_on": incorporated_on,
        "registered_address": "100 Example Commerce Way, Demo Industrial Park",
        "bank_country": country, "annual_spend": 50000, **bank,
    }


def scenarios(as_of: date, sanctions_name: str):
    # S1: No intentional defects. Identifiers pass format/checksum checks.
    s1 = form("Brightline Logistics LLC", "US", "brightline-logistics.example",
              "36-7000101", "740015920101", aba=ABA)
    # S2: Only the cheque holder differs; no alias proof is supplied. GSTIN/IFSC are valid.
    s2 = form("Sundaram Fasteners Pvt Ltd", "IN", "sundaram-fasteners.example",
              indian_gstin(), "50200076543210", ifsc=IFSC)
    # S3: Valid identifiers, but account exactly reuses Northwind's; company age is 30 days.
    s3 = form("Silvercrest Rapid Sourcing LLC", "US", "silvercrest-rapid.example",
              "36-7000103", NORTHWIND_ACCOUNT,
              incorporated_on=(as_of - timedelta(days=30)).isoformat(), aba=ABA)
    s3["annual_spend"] = 250000
    # S4: Valid German form VAT/IBAN. Wrong-country W-9 and degraded scan are intentional.
    s4 = form("Rheinblick Maschinenhandel GmbH", "DE", "rheinblick-demo.example",
              german_vat("12345678"), "0532013000", iban="DE89370400440532013000", bic="COBADEFFXXX")
    # S5: Same entity/form as S4, corrected VAT and bank evidence; explicitly linked parent.
    s5 = dict(s4)
    # S6: Valid identifiers; exact entity hit in the configured fictional sanctions list.
    s6 = form(sanctions_name, "US", "obsidian-meridian.example",
              "36-7000106", "740015920106", aba=ABA)
    for submission in (s1, s2, s3, s4, s5, s6):
        submission["documents_issued_on"] = as_of.isoformat()
    rows = [
        ("S1", s1, ["s1_w9.pdf", "s1_bank_letter.pdf", "s1_incorporation.pdf"],
         "APPROVED", "Happy path: complete, consistent US evidence.", "No intentional defects."),
        ("S2", s2, ["s2_gst_certificate.pdf", "s2_cancelled_cheque.pdf", "s2_incorporation.pdf"],
         "PENDING", "Manual review: bank holder Sundaram Traders differs from legal name without alias proof.",
         "Intentional bank-holder mismatch only; GSTIN and IFSC remain valid."),
        ("S3", s3, ["s3_w9.pdf", "s3_bank_letter.pdf", "s3_incorporation.pdf"],
         "REJECTED", "Bank-detail fraud indicator: account reused from approved Northwind; new name/domain, age <90 days.",
         "Intentional shared bank account and recent incorporation; no checksum defects."),
        ("S4", s4, ["s4_wrong_w9.pdf", "s4_bank_scan.pdf", "s4_incorporation.pdf"],
         "PENDING", "Wrong-country tax document and low-quality image-only bank letter require corrected evidence.",
         "Intentional US W-9 instead of German VAT evidence, plus degraded scan. All numeric identifiers remain valid."),
        ("S5", s5, ["s5_vat_certificate.pdf", "s5_bank_letter.pdf", "s4_incorporation.pdf"],
         "APPROVED", "Resubmission of S4: corrected VAT certificate and clear bank letter resolve document defects.",
         "No remaining intentional defect; same form and incorporation document as S4."),
        ("S6", s6, ["s6_w9.pdf", "s6_bank_letter.pdf", "s6_incorporation.pdf"],
         "REJECTED", "Exact hit in mock sanctions list; all other supplied evidence is consistent.",
         "Intentional fictional sanctions-name hit only; no checksum defects."),
    ]
    return {
        "fixture_only": True, "reference_date": as_of.isoformat(),
        "notice": "Expected outcomes are test intentions, not pipeline outputs. All documents are synthetic.",
        "scenarios": [
            {"id": sid, "parent_submission_id": "S4" if sid == "S5" else None,
             "title": {"S1": "Complete US submission", "S2": "Trade-name mismatch",
                       "S3": "Reused bank account", "S4": "Wrong and unreadable documents",
                       "S5": "Corrected resubmission", "S6": "Mock sanctions-list hit"}[sid],
             "form": data, "documents": docs, "expected_decision": expected,
             "description": description, "intentional_comment": comment}
            for sid, data, docs, expected, description, comment in rows
        ],
    }


def existing_vendors():
    names = [
        ("Northwind Industrial Supplies LLC", "US", "northwind-industrial.example"),
        ("Cedarbridge Packaging LLC", "US", "cedarbridge.example"),
        ("Alderstone Precision Parts Inc", "US", "alderstone.example"),
        ("Harborlane Freight LLC", "US", "harborlane.example"),
        ("Meadowpeak Office Supply Inc", "US", "meadowpeak.example"),
        ("Pinehaven Safety Products LLC", "US", "pinehaven.example"),
        ("Clearbrook Fabrication Inc", "US", "clearbrook.example"),
        ("Summitvale Maintenance LLC", "US", "summitvale.example"),
        ("Kaveri Precision Tools Pvt Ltd", "IN", "kaveri-tools.example"),
        ("Deccan Packaging Solutions Pvt Ltd", "IN", "deccan-packaging.example"),
        ("Malabar Industrial Components Pvt Ltd", "IN", "malabar-components.example"),
        ("Sahyadri Logistics Pvt Ltd", "IN", "sahyadri-logistics.example"),
        ("Nilgiri Textile Supply Pvt Ltd", "IN", "nilgiri-textiles.example"),
        ("Konkan Electrical Systems Pvt Ltd", "IN", "konkan-electrical.example"),
        ("Elbenhain Werkzeuge GmbH", "DE", "elbenhain.example"),
        ("Mainbogen Verpackung GmbH", "DE", "mainbogen.example"),
        ("Havelstein Technik GmbH", "DE", "havelstein.example"),
        ("Isarwinkel Logistik GmbH", "DE", "isarwinkel.example"),
        ("Willowmere Engineering Ltd", "GB", "willowmere.example"),
        ("Oakfen Commercial Supply Ltd", "GB", "oakfen.example"),
    ]
    vendors = []
    for index, (name, country, domain) in enumerate(names, 1):
        tax = None
        iban = None
        account = f"74001592{index:04d}"
        if country == "US":
            tax = f"36-{7000000 + index:07d}"
        elif country == "IN":
            tax = indian_gstin(pan=f"AACCT{1200 + index:04d}K")
        elif country == "DE":
            tax = german_vat(str(12345000 + index))
            iban = german_iban(532013000 + index)
        else:
            # A standard GB checksum example; no invented UK tax ID is asserted as valid.
            iban = "GB82WEST12345698765432" if index == 19 else "GB29NWBK60161331926819"
        if index == 1:
            account = NORTHWIND_ACCOUNT
        vendors.append({
            "id": index, "legal_name": name, "trade_name": None, "country": country,
            "tax_id": tax, "bank_account": account, "iban": iban,
            "status": "PENDING" if index == 20 else "APPROVED", "email_domain": domain,
            "created_at": "2024-01-15T09:00:00Z",
        })
    return vendors
