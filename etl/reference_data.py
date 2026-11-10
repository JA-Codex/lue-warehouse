"""Fixed reference data shared by the SQL loaders and the data generator.

One place for the small static members (decision D19-style: no drift between documents and code).
Every value follows the frozen Phase 1 pack (docs/phase1/07_Data_Dictionary.xlsx, tools/model.py).
sql/30_dimensions/01_reference_dimensions.sql loads the same members into lue_dw;
scripts/test_reference.py fails if the two ever differ.

The codes are the business keys. The source system S1 (LUE-PMS) must use the same codes in
src_pms.payment_methods, src_pms.charge_types and src_pms.lease_events.event_code.
"""

# (method_code, method_name, channel_group, typical_settlement_days), in dimension key order 1..6.
PAYMENT_METHODS = [
    ("CASH", "Cash", "Cash", 0),
    ("CHEQUE", "Cheque", "Cheque", 3),
    ("BANK", "Bank transfer", "Bank", 1),
    ("RAAST", "Raast", "Instant payment", 0),
    ("JAZZ", "JazzCash", "Mobile wallet", 1),
    ("EASY", "Easypaisa", "Mobile wallet", 1),
]

# (charge_code, charge_type_name, charge_category), in dimension key order 1..6.
CHARGE_TYPES = [
    ("RENT", "Rent", "Rent"),
    ("SERVICE", "Service charge", "Ancillary"),
    ("LATEFEE", "Late fee", "Penalty"),
    ("UTILITY", "Utility", "Ancillary"),
    ("CREDIT", "Credit note", "Credit"),
    ("DEPADJ", "Deposit adjustment", "Credit"),
]

# (event_code, event_name, is_exit_event), in dimension key order 1..4.
LEASE_EVENT_TYPES = [
    ("SIGN", "Signed", False),
    ("RENEW", "Renewed", False),
    ("NOTICE", "Notice given", True),
    ("TERM", "Terminated", True),
]


def flags_label(is_emergency: bool, is_recurring: bool, is_tenant_caused: bool) -> str:
    """Readable label of one request-flags combination (dictionary example, middle dot)."""
    return " \u00b7 ".join(
        [
            "Emergency" if is_emergency else "Not emergency",
            "Recurring" if is_recurring else "Not recurring",
            "Tenant-caused" if is_tenant_caused else "Not tenant-caused",
        ]
    )


# Dimension key order for dim_request_flags: false before true, emergency varying slowest.
REQUEST_FLAG_COMBINATIONS = [
    (e, r, t) for e in (False, True) for r in (False, True) for t in (False, True)
]
