"""ReportLab sample layouts, plus a genuinely image-only degraded PDF."""

from io import BytesIO
from pathlib import Path
import random

import fitz
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PAGE = (612, 792)
INK = colors.HexColor("#193449")
NOTICE = "SYNTHETIC TEST FIXTURE - NOT AN OFFICIAL DOCUMENT - NOT FOR PAYMENT"


def text(c, x, y, value, size=11, font="Helvetica"):
    c.setFont(font, size)
    c.setFillColor(INK)
    c.drawString(x, y, str(value))


def footer(c, width=612):
    c.setStrokeColor(colors.HexColor("#b6c4cc"))
    c.line(36, 43, width - 36, 43)
    text(c, 36, 29, NOTICE, 7)


def field(c, label, value, y, x=48):
    text(c, x, y, label.upper(), 8, "Helvetica-Bold")
    text(c, x, y - 20, value or "Not provided", 11)


def w9(c, form, wrong_country=False):
    text(c, 42, 739, "Form W-9", 27, "Helvetica-Bold")
    text(c, 224, 746, "Request for Taxpayer", 17, "Helvetica-Bold")
    text(c, 224, 724, "Identification Number", 17, "Helvetica-Bold")
    text(c, 42, 696, "Illustrative W-9-style fixture, not an IRS-issued form", 9)
    values = [
        ("1  Name shown on tax return", form["legal_name"]),
        ("2  Business / disregarded entity name", form.get("trade_name") or "None"),
        ("3  Federal tax classification", "Limited liability company"),
        ("4  Business address", "100 Example Commerce Way, Test City, NY 10001"),
        ("Part I  Employer identification number", "36-7000104" if wrong_country else form["tax_id"]),
        ("Part II  Certification", "Sample certification only; no real signature"),
    ]
    for index, (label, value) in enumerate(values):
        y = 663 - index * 75
        c.setStrokeColor(colors.grey)
        c.rect(36, y - 51, 540, 65)
        field(c, label, value, y)


def gst_certificate(c, form):
    c.setFillColor(colors.HexColor("#e4f0e9"))
    c.rect(0, 655, 612, 137, fill=1, stroke=0)
    text(c, 44, 747, "GOODS AND SERVICES TAX", 22, "Helvetica-Bold")
    text(c, 44, 715, "Registration Certificate - illustrative layout", 14)
    text(c, 44, 682, "FORM GST REG-06 | Tamil Nadu | Demo jurisdiction", 10)
    fields = [("Registration number (GSTIN)", form["tax_id"]),
              ("Legal name", form["legal_name"]),
              ("Constitution of business", "Private limited company"),
              ("Principal place of business", "12 Example Industrial Estate, Chennai, Tamil Nadu"),
              ("Date of registration", "2018-04-16"),
              ("Status", "Active - synthetic fixture, not registry verified")]
    for i, (label, value) in enumerate(fields):
        field(c, label, value, 610 - i * 73)


def vat_certificate(c, form):
    text(c, 48, 738, "Umsatzsteuer-Identifikationsnummer", 22, "Times-Bold")
    text(c, 48, 706, "Mitteilung zur steuerlichen Erfassung", 15, "Times-Roman")
    c.line(48, 685, 564, 685)
    text(c, 48, 649, "DEUTSCHLAND | MUSTERBESCHEINIGUNG", 10, "Helvetica-Bold")
    field(c, "Unternehmen / legal entity", form["legal_name"], 591)
    field(c, "Anschrift / registered address", "Beispielstrasse 14, 50667 Koeln, Deutschland", 515)
    field(c, "USt-IdNr. / VAT identifier", form["tax_id"], 439)
    field(c, "Register", "Amtsgericht Koeln - HRB 990104 (synthetic)", 363)
    text(c, 48, 258, "This sample records the declared VAT identifier for document testing.", 10)
    text(c, 48, 235, "No government verification, official seal or signature is represented.", 10)


def incorporation(c, form):
    c.setStrokeColor(INK)
    c.rect(28, 62, 556, 702)
    c.rect(35, 69, 542, 688)
    text(c, 68, 709, {"US": "UNITED STATES - DEMO REGISTRY", "IN": "INDIA - DEMO REGISTRY",
                      "DE": "DEUTSCHLAND - DEMO HANDELSREGISTER"}[form["country"]], 13, "Times-Bold")
    text(c, 68, 649, "Certificate of Incorporation", 28, "Times-Bold")
    text(c, 68, 594, "The following entity is recorded for this synthetic case study:", 11, "Times-Roman")
    field(c, "Registered legal name", form["legal_name"], 535, 68)
    field(c, "Jurisdiction", form["country"], 454, 68)
    field(c, "Incorporation date", form["incorporated_on"], 373, 68)
    field(c, "Reference", f"DEMO-{form['tax_id']}", 292, 68)
    c.circle(486, 161, 41)
    text(c, 466, 166, "DEMO", 11, "Helvetica-Bold")
    text(c, 468, 150, "ONLY", 10)
    text(c, 68, 157, "No authentic registration is asserted.", 10, "Times-Italic")


def bank_letter(c, form):
    c.setFillColor(INK)
    c.rect(0, 770, 612, 22, fill=1, stroke=0)
    text(c, 48, 723, "EXAMPLE COMMERCIAL BANK", 20, "Helvetica-Bold")
    text(c, 48, 699, "Business banking | synthetic branch", 10)
    c.line(48, 680, 564, 680)
    text(c, 48, 640, "To: Vendor onboarding team", 11)
    text(c, 395, 640, "Issued: " + form["documents_issued_on"], 10)
    text(c, 48, 592, "Subject: Confirmation of account details", 15, "Helvetica-Bold")
    text(c, 48, 548, "For this test fixture, the account details supplied are:", 11)
    items = [("Account holder", form["bank_holder_name"]), ("Account number", form["bank_account"])]
    for label, key in [("ABA routing number", "aba"), ("IBAN", "iban"), ("BIC", "bic"), ("IFSC", "ifsc")]:
        if form.get(key):
            items.append((label, form[key]))
    for i, (label, value) in enumerate(items):
        field(c, label, value, 498 - i * 62)
    text(c, 48, 158, "Example Bank Operations - unsigned synthetic sample", 10)
    text(c, 48, 135, "Account ownership has not been independently verified.", 10)


def cheque(c, form):
    # Landscape, unlike the portrait certificates and bank letters.
    c.setFillColor(colors.HexColor("#eef3f7"))
    c.rect(26, 75, 740, 465, fill=1, stroke=0)
    text(c, 48, 504, "EXAMPLE BANK - CHENNAI", 23, "Helvetica-Bold")
    text(c, 48, 467, "Cancelled cheque / account evidence", 13)
    field(c, "Account holder", "Sundaram Traders", 410)
    field(c, "Account number", form["bank_account"], 335)
    field(c, "IFSC", form["ifsc"], 260)
    text(c, 48, 145, "Cheque no. 000001 | For onboarding evidence only", 12, "Courier")
    c.saveState()
    c.translate(400, 300)
    c.rotate(19)
    c.setFillColor(colors.HexColor("#b73737"))
    c.setFont("Helvetica-Bold", 54)
    c.drawCentredString(0, 0, "CANCELLED")
    c.restoreState()


def create_pdf(path, kind, form):
    size = (792, 612) if kind == "cheque" else PAGE
    c = canvas.Canvas(str(path) if isinstance(path, Path) else path, pagesize=size, invariant=1)
    c.setTitle(f"VendorGate synthetic {kind}")
    c.setAuthor("VendorGate fixture generator")
    layouts = {"w9": w9, "wrong_w9": lambda c, f: w9(c, f, True), "gst": gst_certificate,
               "vat": vat_certificate, "incorporation": incorporation, "bank": bank_letter, "cheque": cheque}
    layouts[kind](c, form)
    footer(c, size[0])
    c.showPage()
    c.save()


def scanned_bank_letter(path, form):
    original = BytesIO()
    create_pdf(original, "bank", form)
    with fitz.open(stream=original.getvalue(), filetype="pdf") as source:
        bitmap = source[0].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), colorspace=fitz.csGRAY)
        image = Image.frombytes("L", (bitmap.width, bitmap.height), bitmap.samples)
    # Fixed RNG seed keeps repeated resets reproducible. Noise, rotation and blur
    # intentionally degrade extraction while leaving the sample visually recognizable.
    rng = random.Random(104)
    noise = Image.frombytes("L", image.size, rng.randbytes(image.width * image.height))
    image = Image.blend(image, noise, 0.18)
    image = image.rotate(1.2, resample=Image.Resampling.BICUBIC, fillcolor=245)
    image = image.filter(ImageFilter.GaussianBlur(0.85))
    c = canvas.Canvas(str(path), pagesize=PAGE, invariant=1)
    c.setTitle("Synthetic degraded bank letter - image only")
    # Absolutely no drawString/footer calls: the complete page is a single raster.
    c.drawImage(ImageReader(image), 0, 0, width=PAGE[0], height=PAGE[1])
    c.showPage()
    c.save()


def generate_documents(manifest, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    written = set()
    for scenario in manifest["scenarios"]:
        for filename in scenario["documents"]:
            if filename in written:
                continue
            path = directory / filename
            if filename == "s4_bank_scan.pdf":
                scanned_bank_letter(path, scenario["form"])
            else:
                kind = next(kind for token, kind in [
                    ("wrong_w9", "wrong_w9"), ("w9", "w9"), ("gst", "gst"),
                    ("vat", "vat"), ("incorporation", "incorporation"), ("cheque", "cheque"),
                    ("bank", "bank")
                ] if token in filename)
                create_pdf(path, kind, scenario["form"])
            written.add(filename)
    return len(written)
