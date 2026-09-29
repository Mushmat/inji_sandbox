"""The mock person every credential is issued for, editable from the Playground.

The pre-authorized Certify and the test issuer take the person with each request, so a save
applies to them straight away. The eSignet Certify's CSV data plugin reads farmer_identity_data.csv
once at startup, so it picks changes up only when it restarts (certify/scripts/certify_control.py),
which happens when someone asks for it.
"""

import re
from datetime import date, datetime

import certify_control  # certify/scripts
import identity_store  # certify/scripts

# MOSIP doesn't define a Farmer ID; the Farmer credential is our own mock. 9 digits matches the
# ID this data has always used. Mobile and PIN code follow Indian formats, like the rest of the data.
RULES = {
    "farmerID": (r"\d{9}", "Farmer ID must be exactly 9 digits."),
    "mobileNumber": (r"[6-9]\d{9}", "Mobile number must be 10 digits starting with 6, 7, 8 or 9."),
    "postalCode": (r"[1-9]\d{5}", "PIN code must be 6 digits and can't start with 0."),
    "fullName": (r"[A-Za-z][A-Za-z .'-]{0,79}", "Full name takes letters, spaces, dots, apostrophes and hyphens (up to 80)."),
    "gender": (r"Female|Male|Other", "Gender must be Female, Male or Other."),
}


def validate(fields: dict) -> dict:
    """{field: message} for every value that breaks a rule. Empty means all good."""
    errors = {}
    for name, value in fields.items():
        if name == "face":
            if value and not value.startswith("data:image/"):
                errors[name] = "The photo must be an image."
            continue
        value = (value or "").strip()
        if name == "dateOfBirth":
            try:
                born = datetime.strptime(value, "%d-%m-%Y").date()
                if not (date(1900, 1, 1) <= born < date.today()):
                    errors[name] = "Date of birth must be between 1900 and today."
            except ValueError:
                errors[name] = "Date of birth must be a real date (DD-MM-YYYY)."
        elif name in RULES and not re.fullmatch(RULES[name][0], value):
            errors[name] = RULES[name][1]
        elif not value:
            errors[name] = "This can't be empty."
    return errors


class InvalidIdentity(ValueError):
    def __init__(self, errors: dict):
        super().__init__(" ".join(errors.values()))
        self.errors = errors


# Set when the details change, cleared once the eSignet Certify has restarted and read them.
_esignet_pending = {"value": False}


def read() -> dict:
    return {"individual_id": identity_store.INDIVIDUAL_ID, "fields": identity_store.EDITABLE_FIELDS,
            "identity": identity_store.read_identity(), "restart": restart_status()}


def save(fields: dict, reload_esignet: bool = False) -> dict:
    """Saves the person. The pre-authorized Certify and the test issuer use it from the next run.
    The eSignet Certify reads the CSV only at startup, so it restarts only when asked, which takes
    minutes under emulation and shouldn't hold everything else up."""
    unknown = sorted(set(fields) - set(identity_store.EDITABLE_FIELDS))
    if unknown:
        raise ValueError(f"These fields can't be edited: {', '.join(unknown)}")
    errors = validate(fields)
    if errors:
        raise InvalidIdentity(errors)
    before = identity_store.read_identity()
    updated = identity_store.update_identity({k: v.strip() if k != "face" else v for k, v in fields.items()})
    if updated != before:
        _esignet_pending["value"] = True
    if reload_esignet:
        reload()
    return {"individual_id": identity_store.INDIVIDUAL_ID, "fields": identity_store.EDITABLE_FIELDS,
            "identity": updated, "restart": restart_status()}


def reload() -> dict:
    """Restart the eSignet Certify so it reads the saved details."""
    if certify_control.start_restart():
        _esignet_pending["value"] = False  # it reads the file as it starts, so these details are covered
    return restart_status()


def restart_status() -> dict:
    return {**certify_control.get_status(), "esignet_pending": _esignet_pending["value"]}


def certify_restarting() -> bool:
    return bool(certify_control.get_status().get("restarting"))


def subject() -> dict:
    """The current person as a credential subject, for the test issuer. The photo is left
    out: it's large, and the test issuer's credential shapes don't carry one."""
    return {k: v for k, v in identity_store.read_identity().items() if k != "face"}
