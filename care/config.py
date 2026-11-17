import json
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
INSTANCE = ROOT / "instance"
INSTANCE.mkdir(exist_ok=True)
key_file = INSTANCE / "keys.json"
if not key_file.exists():
    key_file.write_text(
        json.dumps(
            {
                "secret": secrets.token_hex(32),
                "encryption_key": Fernet.generate_key().decode(),
                "identity_key": secrets.token_hex(32),
            }
        ),
        encoding="utf-8",
    )
KEYS = json.loads(key_file.read_text(encoding="utf-8"))
DATABASE = os.getenv("CARE_DATABASE", "CareHomeCourse2026")
SERVER = os.getenv("CARE_SERVER", r".\SQLEXPRESS")
CONNECTION_STRING = os.getenv(
    "CARE_CONNECTION_STRING",
    f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE={DATABASE};"
    "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;",
)
