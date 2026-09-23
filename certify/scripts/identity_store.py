"""
Reads and writes the one identity row the demo issues credentials for
(farmer_identity_data.csv, keyed by INDIVIDUAL_ID from issuance_flow.py).
Certify reads this CSV live on every request, so editing it here takes
effect on the very next credential issued - no restart needed.

Split out from server.py so it's testable on its own and reusable if
something other than the Flask demo ever needs to edit this data.
"""
import csv
import os

from issuance_flow import INDIVIDUAL_ID

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "docker-compose", "config", "farmer_identity_data.csv")

# What the UI is allowed to edit. "givenName" and "familyName" are left out
# on purpose - they're derived from fullName automatically (see split_name
# below) so they can't drift out of sync with it. "face" is included but the
# UI renders it as a camera capture, not a text box - a base64 image isn't
# something anyone should be typing.
EDITABLE_FIELDS = [
    "fullName", "mobileNumber", "dateOfBirth", "gender", "state", "district",
    "villageOrTown", "postalCode", "landArea", "landOwnershipType",
    "primaryCropType", "secondaryCropType", "farmerID", "face",
]


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split()
    if len(parts) <= 1:
        return full_name, ""
    return " ".join(parts[:-1]), parts[-1]


def read_identity() -> dict:
    with open(CSV_PATH, newline="") as f:
        for row in csv.DictReader(f):
            if row["id"] == INDIVIDUAL_ID:
                return {field: row[field] for field in EDITABLE_FIELDS}
    raise ValueError(f"no identity row found for id={INDIVIDUAL_ID}")


def update_identity(fields: dict) -> dict:
    """Merges the given fields into the existing row and writes the whole
    CSV back. Unknown field names are ignored rather than rejected, so the
    UI can send a full form post without needing to filter it first."""
    with open(CSV_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys())

    updated = None
    for row in rows:
        if row["id"] == INDIVIDUAL_ID:
            for key, value in fields.items():
                if key in EDITABLE_FIELDS:
                    row[key] = value
            given, family = split_name(row["fullName"])
            row["givenName"] = given
            row["familyName"] = family
            updated = row
            break

    if updated is None:
        raise ValueError(f"no identity row found for id={INDIVIDUAL_ID}")

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {field: updated[field] for field in EDITABLE_FIELDS}
