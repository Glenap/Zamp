"""Bundle the actual generated PDF bytes and their extracted text, never decisions."""
import base64
import json
from pathlib import Path
import fitz

root = Path(__file__).resolve().parents[3]
source = root / "backend/seed"
manifest = json.loads((source / "scenarios.json").read_text(encoding="utf-8"))
assets = {}
for path in sorted((source / "docs").glob("*.pdf")):
    with fitz.open(path) as document:
        extracted = "\n".join(page.get_text() for page in document)
    assets[path.name] = {"base64": base64.b64encode(path.read_bytes()).decode(), "extracted_text": extracted}
generated = Path(__file__).resolve().parents[1] / "worker/generated"
generated.mkdir(parents=True, exist_ok=True)
(generated / "fixtures.json").write_text(json.dumps({"manifest": manifest, "assets": assets,
    "vendors": json.loads((source / "vendors.json").read_text(encoding="utf-8")),
    "settings": json.loads((root / "backend/config/settings.json").read_text(encoding="utf-8")),
    "assumptions": (root / "ASSUMPTIONS.md").read_text(encoding="utf-8")}), encoding="utf-8")
