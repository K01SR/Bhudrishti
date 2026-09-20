"""What the Ed25519 signature on a record does and does not prove.

Returned with every response that carries a cryptographic proof, and rendered
by the public verification page.

The signing is real Ed25519, and that is exactly the problem. The private key
is published in this repository (``app.core.crypto``), so anyone who clones it
can sign any payload and this service will report that signature as valid. The
signature therefore establishes nothing about who produced a record, only that
the bytes have not changed since this service signed them. Reporting that as
official verification, or attributing it to a land-records authority,
inverts what it proves.

The wording is centralised here because it previously lived in ``qr.py`` only,
while ``properties.py`` and ``verification.py`` returned a ``signer_authority``
naming the Thane District Land Records Verifier with no such signature behind
it.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

#: No authority signs these records. Kept explicit rather than omitted so a
#: consumer can tell "no signer" apart from "this endpoint has no opinion".
NO_SIGNING_AUTHORITY: Optional[str] = None

#: The only claim these signatures support.
SIGNATURE_STATUS = "SELF_SIGNED_BY_THIS_SERVICE"

CRYPTO_DISCLOSURE: Dict[str, Any] = {
    "signature_algorithm": "Ed25519",
    "signature_validates": (
        "Only that these exact bytes have not changed since this service signed "
        "them."
    ),
    "signature_does_not_validate": (
        "It does not establish who created the record, that any authority "
        "reviewed it, or that the underlying property data is correct."
    ),
    "why": (
        "The signing key is published in this repository, so anyone with a copy "
        "of the code can produce a signature that this endpoint will report as "
        "valid. The check is self-referential."
    ),
    "public_key_published": False,
    "independent_auditor": None,
}
