"""The mock person every credential is issued for, editable from the Playground.

Certify's CSV data plugin reads farmer_identity_data.csv once at startup, so a save
restarts Certify in the background (certify/scripts/certify_control.py). The test issuer
signs whatever it's given, so it picks up changes straight away.
"""

import certify_control  # certify/scripts
import identity_store  # certify/scripts


def read() -> dict:
    return {"individual_id": identity_store.INDIVIDUAL_ID, "fields": identity_store.EDITABLE_FIELDS,
            "identity": identity_store.read_identity(), "restart": certify_control.get_status()}


def save(fields: dict) -> dict:
    unknown = sorted(set(fields) - set(identity_store.EDITABLE_FIELDS))
    if unknown:
        raise ValueError(f"These fields can't be edited: {', '.join(unknown)}")
    updated = identity_store.update_identity(fields)
    certify_control.start_restart()
    return {"individual_id": identity_store.INDIVIDUAL_ID, "fields": identity_store.EDITABLE_FIELDS,
            "identity": updated, "restart": certify_control.get_status()}


def restart_status() -> dict:
    return certify_control.get_status()


def certify_restarting() -> bool:
    return bool(certify_control.get_status().get("restarting"))


def subject() -> dict:
    """The current person as a credential subject, for the test issuer. The photo is left
    out: it's large, and the test issuer's credential shapes don't carry one."""
    return {k: v for k, v in identity_store.read_identity().items() if k != "face"}
