"""Integration tests for storage and actual generated fixtures, not pipeline outcomes."""

from datetime import date
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import fitz
from fastapi.testclient import TestClient
import pytest

from backend.db import connect, init_db
from backend.main import app
from backend.rules.aba import is_valid_aba
from backend.rules.ein import is_valid_ein
from backend.rules.gstin import is_valid_gstin
from backend.rules.iban import is_valid_iban
from backend.rules.ifsc import is_valid_ifsc
from backend.rules.vat import is_valid_de_vat

ROOT = Path(__file__).resolve().parents[2]
TABLES = {"vendors_existing", "submissions", "documents", "runs", "stage_results",
          "messages_outbox", "overrides", "settings"}


def test_schema_and_foreign_keys(tmp_path):
    database = tmp_path / "fresh.sqlite3"
    init_db(database)
    init_db(database)
    with connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == TABLES
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM settings").fetchone()[0] > 0
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO documents(submission_id,filename,path) VALUES ('missing','x','x')")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO submissions(id,form_json) VALUES ('bad','not json')")
        connection.execute("UPDATE settings SET value_json='0.9' WHERE key='name_match_threshold'")
    init_db(database)
    with connect(database) as connection:
        assert json.loads(connection.execute("SELECT value_json FROM settings WHERE key='name_match_threshold'").fetchone()[0]) == 0.9


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    destination = tmp_path_factory.mktemp("fixtures")
    database = destination / "test.sqlite3"
    command = [sys.executable, str(ROOT / "backend/seed/seed.py"), "--reset", "--db", str(database),
               "--output-dir", str(destination), "--as-of", "2026-11-23"]
    # Exercise the real CLI twice, in an isolated fixture directory/database.
    for _ in range(2):
        result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        assert json.loads(result.stdout)["unique_documents"] == 17
    return destination, database, json.loads((destination / "scenarios.json").read_text())


def test_seed_counts_and_resubmission(seeded):
    destination, database, manifest = seeded
    with connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM vendors_existing").fetchone()[0] == 20
        assert connection.execute("SELECT count(*) FROM submissions").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        for table in ("runs", "stage_results", "messages_outbox", "overrides"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        assert manifest["scenarios"][4]["parent_submission_id"] == "S4"
        assert list(connection.execute("PRAGMA foreign_key_check")) == []
        for row in connection.execute("SELECT path, doc_type_detected FROM documents"):
            assert Path(row["path"]).is_file()
            assert row["doc_type_detected"] is None  # Not pre-classified by a fake pipeline.
        northwind = connection.execute("SELECT * FROM vendors_existing WHERE legal_name=?",
                                      ("Northwind Industrial Supplies LLC",)).fetchone()
        fraud = manifest["scenarios"][2]["form"]
        assert northwind["status"] == "APPROVED"
        assert fraud["bank_account"] == northwind["bank_account"]
        assert fraud["legal_name"] != northwind["legal_name"]
        assert fraud["email_domain"] != northwind["email_domain"]
        age = date.fromisoformat(manifest["reference_date"]) - date.fromisoformat(fraud["incorporated_on"])
        assert 0 <= age.days < 90
        sanctions = json.loads(connection.execute("SELECT value_json FROM settings WHERE key='sanctions_list'").fetchone()[0])
        assert len(sanctions) == 15
        assert manifest["scenarios"][5]["form"]["legal_name"] in sanctions


def test_every_document_is_real_and_scan_is_image_only(seeded):
    destination, _, manifest = seeded
    for scenario in manifest["scenarios"]:
        assert 1 <= len(scenario["documents"]) <= 4
        assert scenario["intentional_comment"]
        for filename in scenario["documents"]:
            path = destination / "docs" / filename
            assert path.is_file(), filename
            with fitz.open(path) as document:
                assert document.page_count == 1
                page = document[0]
                if filename == "s4_bank_scan.pdf":
                    assert not page.get_text().strip()
                    assert len(page.get_images()) == 1
                else:
                    assert "SYNTHETIC TEST FIXTURE" in page.get_text()
                    holder = "Sundaram Traders" if filename == "s2_cancelled_cheque.pdf" else scenario["form"]["legal_name"]
                    assert holder in page.get_text()
    with fitz.open(destination / "docs/s2_cancelled_cheque.pdf") as document:
        assert "Sundaram Traders" in document[0].get_text()
        assert document[0].rect.width > document[0].rect.height


def test_fixture_identifiers(seeded):
    _, database, manifest = seeded
    # Every scenario deliberately retains valid identifiers, including S3/S4/S6.
    for scenario in manifest["scenarios"]:
        form = scenario["form"]
        validator = {"US": is_valid_ein, "IN": is_valid_gstin, "DE": is_valid_de_vat}[form["country"]]
        assert validator(form["tax_id"]), scenario["id"]
        for key, validate in (("aba", is_valid_aba), ("iban", is_valid_iban), ("ifsc", is_valid_ifsc)):
            if form.get(key):
                assert validate(form[key]), (scenario["id"], key)
    with connect(database) as connection:
        for vendor in connection.execute("SELECT * FROM vendors_existing"):
            if vendor["iban"]:
                assert is_valid_iban(vendor["iban"])
            if vendor["country"] == "IN":
                assert is_valid_gstin(vendor["tax_id"])
            if vendor["country"] == "DE":
                assert is_valid_de_vat(vendor["tax_id"])


@pytest.mark.parametrize("validate,valid,invalid", [
    (is_valid_aba, "021000021", ["021000022", "000000000", "02100002", "991000026"]),
    (is_valid_iban, "DE89370400440532013000", ["DE89370400440532013001", "DE89", "ZZ89370400440532013000"]),
    (is_valid_iban, "GB82WEST12345698765432", ["GB83WEST12345698765432"]),
    (is_valid_gstin, "27AAPFU0939F1ZV", ["27AAPFU0939F1ZA", "00AAPFU0939F1ZV", "27AAPFU0939F1Z"]),
    (is_valid_ifsc, "HDFC0001234", ["HDFC1001234", "HDFC000123"]),
    (is_valid_ein, "36-7000101", ["00-7000101", "367000101"]),
    (is_valid_de_vat, "DE136695976", ["DE136695977", "DE13669597"]),
])
def test_checksum_reference_vectors_and_corruption(validate, valid, invalid):
    # Fixed reference examples avoid only testing a generator against itself.
    assert validate(valid)
    for value in invalid:
        assert not validate(value), value


def test_health_uses_isolated_database(tmp_path, monkeypatch):
    database = tmp_path / "health.sqlite3"
    monkeypatch.setenv("VENDORGATE_DB_PATH", str(database))
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
    assert database.is_file()
