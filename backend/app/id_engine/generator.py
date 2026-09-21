import re
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from app.id_engine.types import (
    SpatialTypeCode,
    SPATIAL_TYPE_DESCRIPTIONS,
    SPECIFICATION_LABEL,
    SPECIFICATION_DISCLAIMER,
)

# Base 36 Alphabet for Luhn Mod 36 Checksum
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALPHABET_MAP = {char: idx for idx, char in enumerate(ALPHABET)}


@dataclass
class Parsed3DID:
    parent_ulpin: str
    type_code: SpatialTypeCode
    type_description: str
    building_code: str
    level_code: str
    unit_code: str
    checksum: str
    raw_id: str
    is_valid: bool
    validation_message: str
    specification: str = SPECIFICATION_LABEL


def calculate_luhn_mod36_checksum(payload: str) -> str:
    """
    Computes a deterministic ISO/IEC 7064 / Luhn Mod 36 check character
    for an alphanumeric string.
    """
    cleaned = "".join(c.upper() for c in payload if c.isalnum())
    if not cleaned:
        return "0"

    factor = 2
    total_sum = 0
    modulus = 36

    # Process characters from right to left
    for char in reversed(cleaned):
        code_point = ALPHABET_MAP.get(char, 0)
        addend = factor * code_point
        # Alternate factor between 2 and 1
        factor = 1 if factor == 2 else 2
        # Sum "digits" of the product in radix 36
        addend = (addend // modulus) + (addend % modulus)
        total_sum += addend

    remainder = total_sum % modulus
    check_code_point = (modulus - remainder) % modulus
    return ALPHABET[check_code_point]


def verify_luhn_mod36_checksum(payload_with_checksum: str) -> bool:
    """
    Validates that the check character at the end matches Luhn Mod 36 checksum of preceding string.
    """
    if len(payload_with_checksum) < 2:
        return False
    body = payload_with_checksum[:-1]
    given_check = payload_with_checksum[-1].upper()
    expected_check = calculate_luhn_mod36_checksum(body)
    return given_check == expected_check


def generate_proposed_3d_id(
    parent_ulpin: str,
    type_code: str,
    building_code: str,
    level_code: str,
    unit_code: str,
) -> str:
    """
    Generates a deterministic Proposed Bhu-Drishti 3D Spatial Extension ID:
    {parent_14_char_ULPIN}/{TYPE}{BUILDING}-{LEVEL}-{UNIT}-{CHECK}
    
    Example:
    12345678901234/UB17-L05-501-W
    """
    clean_ulpin = parent_ulpin.strip().upper()
    if len(clean_ulpin) != 14:
        raise ValueError(f"Parent ULPIN must be exactly 14 characters, received '{clean_ulpin}' ({len(clean_ulpin)} chars)")

    t_code = type_code.strip().upper()
    b_code = building_code.strip().upper().replace("-", "")
    l_code = level_code.strip().upper()
    u_code = unit_code.strip().upper()

    # Pre-checksum payload: e.g. 12345678901234/UB17-L05-501
    pre_payload = f"{clean_ulpin}/{t_code}{b_code}-{l_code}-{u_code}"
    checksum = calculate_luhn_mod36_checksum(pre_payload)
    return f"{pre_payload}-{checksum}"


def parse_and_validate_3d_id(raw_id: str) -> Parsed3DID:
    """
    Parses, validates syntax and verifies checksum for a Proposed Bhu-Drishti 3D ID.
    Supports formats:
    - {parent_14}/{TYPE}{BUILDING}-{LEVEL}-{UNIT}-{CHECK} (e.g. 12345678901234/UB17-L05-501-W)
    - {parent_14}/{TYPE}-{BUILDING}-{LEVEL}-{UNIT}-{CHECK}
    """
    cleaned = raw_id.strip()
    if "/" not in cleaned:
        return Parsed3DID(
            parent_ulpin="",
            type_code=SpatialTypeCode.SURFACE,
            type_description="",
            building_code="",
            level_code="",
            unit_code="",
            checksum="",
            raw_id=raw_id,
            is_valid=False,
            validation_message="Invalid format: Missing slash separator between parent ULPIN and 3D extension.",
        )

    parent_ulpin, extension = cleaned.split("/", 1)
    if len(parent_ulpin) != 14 or not parent_ulpin.isalnum():
        return Parsed3DID(
            parent_ulpin=parent_ulpin,
            type_code=SpatialTypeCode.SURFACE,
            type_description="",
            building_code="",
            level_code="",
            unit_code="",
            checksum="",
            raw_id=raw_id,
            is_valid=False,
            validation_message="Parent ULPIN must be exactly 14 alphanumeric characters.",
        )

    tokens = extension.split("-")
    if len(tokens) < 4:
        return Parsed3DID(
            parent_ulpin=parent_ulpin,
            type_code=SpatialTypeCode.SURFACE,
            type_description="",
            building_code="",
            level_code="",
            unit_code="",
            checksum="",
            raw_id=raw_id,
            is_valid=False,
            validation_message="3D extension must have at least 4 segments: [TYPE+BUILDING]-[LEVEL]-[UNIT]-[CHECKSUM].",
        )

    checksum = tokens[-1].upper()
    body_payload = f"{parent_ulpin}/{'-'.join(tokens[:-1])}"
    expected_checksum = calculate_luhn_mod36_checksum(body_payload)

    if checksum != expected_checksum:
        return Parsed3DID(
            parent_ulpin=parent_ulpin,
            type_code=SpatialTypeCode.SURFACE,
            type_description="",
            building_code=tokens[0],
            level_code=tokens[1],
            unit_code="-".join(tokens[2:-1]),
            checksum=checksum,
            raw_id=raw_id,
            is_valid=False,
            validation_message=f"Checksum mismatch: received '{checksum}', expected '{expected_checksum}'.",
        )

    # Extract type code from the first character of tokens[0]
    first_token = tokens[0]
    first_char = first_token[0].upper()
    
    # Check if first character is a recognized spatial type code
    type_code = SpatialTypeCode.BUILDING
    building_code = first_token
    for valid_type in SpatialTypeCode:
        if first_char == valid_type.value:
            type_code = valid_type
            building_code = first_token[1:] if len(first_token) > 1 else first_token
            break

    level_code = tokens[1]
    unit_code = "-".join(tokens[2:-1])

    return Parsed3DID(
        parent_ulpin=parent_ulpin,
        type_code=type_code,
        type_description=SPATIAL_TYPE_DESCRIPTIONS.get(type_code, "Unknown Spatial Entity"),
        building_code=building_code,
        level_code=level_code,
        unit_code=unit_code,
        checksum=checksum,
        raw_id=raw_id,
        is_valid=True,
        validation_message="Deterministic checksum valid. Syntactically verified.",
    )


def explain_id_specification() -> Dict[str, Any]:
    """Returns human-readable explanation of the proposed 3D ID specification."""
    return {
        "specification_title": SPECIFICATION_LABEL,
        "disclaimer": SPECIFICATION_DISCLAIMER,
        "template": "{parent_14_char_ULPIN}/{TYPE}{BUILDING}-{LEVEL}-{UNIT}-{CHECKSUM}",
        "type_codes": {code.value: desc for code, desc in SPATIAL_TYPE_DESCRIPTIONS.items()},
        "checksum_algorithm": "ISO/IEC 7064 Alphanumeric Luhn Mod 36",
        "radix": 36,
        "alphabet": ALPHABET,
        "example": "12345678901234/UB17-L05-501-W",
        "example_breakdown": {
            "parent_14_char_ULPIN": "12345678901234 (Official Parent Land Parcel)",
            "type_code": "U (Vertical Unit / Apartment)",
            "building_code": "B17 (Building Structure B-17)",
            "level_code": "L05 (Level 5)",
            "unit_code": "501 (Flat No. 501)",
            "checksum": "W (Computed via Luhn Mod 36)",
        },
    }
