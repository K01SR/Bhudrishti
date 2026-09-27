from enum import Enum


class SpatialTypeCode(str, Enum):
    SURFACE = "S"          # Surface land parcel
    BUILDING = "B"         # Building structure envelope
    LEVEL = "L"            # Floor level / strata slab
    UNIT = "U"             # Individual vertical unit (apartment / office)
    UNDERGROUND = "X"      # Subterranean infrastructure (tunnel, utility, pipe)
    ELEVATED = "E"         # Elevated structure (skywalk, overpass)
    AIR_RIGHT = "A"        # Aerial column / air-right volume
    PARKING = "P"          # Parking bay / slot (surface or subterranean)


SPATIAL_TYPE_DESCRIPTIONS = {
    SpatialTypeCode.SURFACE: "Surface Land Parcel",
    SpatialTypeCode.BUILDING: "Above-Ground Building Structure",
    SpatialTypeCode.LEVEL: "Floor / Level Strata Slab",
    SpatialTypeCode.UNIT: "Vertical Volumetric Property Unit (Apartment / Flat)",
    SpatialTypeCode.UNDERGROUND: "Subterranean Infrastructure (Tunnel / Utility / Basement)",
    SpatialTypeCode.ELEVATED: "Elevated Cross-Parcel Structure (Skywalk / Bridge)",
    SpatialTypeCode.AIR_RIGHT: "3D Air-Right Column / Volumetric Envelope",
    SpatialTypeCode.PARKING: "Designated Vehicular Parking Bay",
}

SPECIFICATION_LABEL = "Proposed Bhu-Drishti 3D Spatial Extension — Demo Specification"
SPECIFICATION_DISCLAIMER = (
    "This identifier represents a proposed vertical spatial extension developed for technical demonstration "
    "under the Bhu-Drishti 3D platform. It does NOT supersede or alter official 14-character parent ULPIN cadastral standards."
)
