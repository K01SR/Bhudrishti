"""Ownership and title conflict detection for the vertical cadastre.

What this file is not: a second R010. ``app.qa_engine.rules`` R010 answers "is
this same space claimed twice?" — the duplicate *spatial claim* check, about one
space attracting two submissions. R011 is the unique-identity counterpart. There
is nothing about a title register in either, and the checks below are not those
two rules again.

They are keyed on different things, and the difference is enforced in code
rather than asserted in a comment:

* R010 groups by *spatial identity*. So does this file, once, in
  :meth:`OwnershipClashDetector.shared_spatial_identities` — and every finding
  below is skipped for any identity that appears on more than one unit record.
  Those batches are counted and handed back as ``deferred_to_duplicate_claim``
  instead of being re-reported here. Two records claiming Flat 201 is R010's
  finding, whoever their holders happen to be, and reporting it a second time as
  a "conflict" would double-count one defect.
* Title conflict is about *holders*. Once identities are known to be distinct,
  the question becomes who holds what: two parties carrying live ownership over
  one space, shares that add up to more than the space, instruments that claim
  the same succession, and volumes that two different parties both hold.

So the four checks here are:

* **R013 Concurrent Active Ownership Claims** — on one unit, recorded shares
  that add up to more than 100% (impossible on any reading), an allocation that
  cannot be verified because a share is unstated, or a testamentary/instrument
  claim sitting alongside a live ownership. Co-ownership that adds up is *not* a
  finding: undivided shares held by several parties are ordinary, and calling
  them a conflict would be a false accusation against the register.
* **R014 Volumetric Overlap Between Distinct Registered Units** — two units with
  different identities whose 3D volumes intersect while live rights name
  different parties. Overlaps where one party holds both sides are counted and
  named as a partition problem (R004's subject), not a title problem.
* **R015 Registered Unit With No Recorded Title** — a unit recorded as claimed
  or approved that carries no right at all. Reported as a WARNING and worded as
  a gap in this register: an absent row is not proof that nobody holds title.
* **R016 Approved Unit With Disputed Or Lapsed Title** — the unit is approved
  while its only live title is disputed or its validity has run out.

Scope of the claims made: every finding is a comparison of rows held in this
system, not a determination of legal title. This platform is not a registry of
deeds and nothing here adjudicates one, so each finding says which records were
compared and sends the matter to manual adjudication. With no unit rows at all
the report is ``NO_RECORDS``: an empty register cannot produce a clean result,
and saying PASS there would assert an absence of conflict that was never tested.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shapely.geometry import Polygon, shape

from app.qa_engine.rules import RuleSeverity, RuleStatus

# Right types that assert an interest in the unit itself. A mortgage or an
# easement sits over the title without claiming it, so two lenders on one flat are
# not a title conflict.
OWNERSHIP_RIGHT_TYPES = {"OWNERSHIP", "CO_OWNERSHIP", "CONDOMINIUM", "TENURE"}

# Instruments that assert a *future* or *alternative* succession. One of these
# standing next to a live ownership is a contested claim on the face of the
# record, whoever eventually prevails.
CONTESTING_RIGHT_TYPES = {
    "WILL",
    "AGREEMENT_TO_SELL",
    "CONVEYANCE_PENDING",
    "INHERITANCE_PENDING",
    "POWER_OF_ATTORNEY",
    "COURT_ORDER",
}

# A right that still encumbers. DISPUTED stays in this set on purpose: a disputed
# encumbrance has not been released and still needs to be resolved.
LIVE_ENCUMBRANCE_STATUSES = {"ACTIVE", "DISPUTED", "PENDING", ""}
CLOSED_ENCUMBRANCE_STATUSES = {"RELEASED", "CANCELLED", "SATISFIED", "DISCHARGED", "LAPSED"}

# Unit statuses that put a unit forward as claimed or occupied. Absence of a
# status is treated as "recorded" too (see _is_registered), because a unit row
# with rights on it is a registered space whether or not a workflow moved it on.
CLAIMED_UNIT_STATUSES = {"SUBMITTED", "GENERATED", "APPROVED", "OCCUPIED", "ALLOCATED"}
UNCLAIMED_UNIT_STATUSES = {"DRAFT", "REJECTED", "PROPOSED"}

_SHARE_TOLERANCE_PCT = 0.5  # rounding in a share column is not over-allocation


def _status_of(right: Dict[str, Any]) -> str:
    return str(right.get("encumbrance_status") or "").strip().upper()


def _right_type(right: Dict[str, Any]) -> str:
    return str(right.get("right_type") or "").strip().upper()


def _share_of(right: Dict[str, Any]) -> Optional[float]:
    """Recorded share as a number, or None when the row does not state one."""
    share = right.get("share_pct", right.get("share"))
    if isinstance(share, bool) or not isinstance(share, (int, float)):
        return None
    return float(share)


def _party_of(right: Dict[str, Any]) -> Optional[str]:
    """Who the row names. None when the row names nobody."""
    for key in ("party_name", "party_id", "party", "party_type"):
        value = right.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_moment(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _rights_of(unit: Dict[str, Any]) -> List[Dict[str, Any]]:
    rights = unit.get("rights") or []
    return [r for r in rights if isinstance(r, dict)]


def _is_live(right: Dict[str, Any], as_of: datetime) -> bool:
    """True while the row still asserts something over the unit."""
    if _status_of(right) in CLOSED_ENCUMBRANCE_STATUSES:
        return False
    valid_to = _parse_moment(right.get("valid_to"))
    return valid_to is None or valid_to > as_of


def _is_lapsed(right: Dict[str, Any], as_of: datetime) -> bool:
    if _status_of(right) in CLOSED_ENCUMBRANCE_STATUSES:
        return True
    valid_to = _parse_moment(right.get("valid_to"))
    return valid_to is not None and valid_to <= as_of


def _identity(unit: Dict[str, Any]) -> str:
    """The registered identity of a volumetric unit, level and number together."""
    proposed = unit.get("proposed_3d_id") or unit.get("unit_id") or unit.get("id")
    if proposed:
        return str(proposed)
    return f"{unit.get('level_code', '?')}-{unit.get('unit_number', '?')}"


def _is_registered(unit: Dict[str, Any]) -> bool:
    """Does this row put the unit forward as a claimed or approved space?

    A row with no status is read as recorded rather than as a draft: the register
    holds it, so holding it without any right on it is a gap worth reporting. An
    explicit draft or rejection is not, because nobody has asserted anything yet.
    """
    status = str(unit.get("status") or "").strip().upper()
    if status in UNCLAIMED_UNIT_STATUSES:
        return False
    return True


def _footprint(unit: Dict[str, Any]) -> Optional[Polygon]:
    """Plan view of a unit, or None when it has none we can read.

    No CRS handling here on purpose: the area of an intersection in an unknown
    frame is not a square metre, so this module reports an overlap *fraction*
    (:meth:`check_volumetric_overlap`) rather than an area, and leaves the units
    to the caller who knows the frame.
    """
    geojson = unit.get("footprint_geojson") or unit.get("geometry_geojson")
    try:
        if isinstance(geojson, dict) and geojson.get("type"):
            geom = shape(geojson)
            return geom if isinstance(geom, Polygon) else None
        ring = unit.get("coords") or unit.get("ring_geo")
        if isinstance(ring, list) and len(ring) >= 4:
            return Polygon(ring)
    except Exception:  # noqa: BLE001 - an unreadable outline is a gap, not a crash
        return None
    return None


def _label(unit: Dict[str, Any]) -> str:
    level = unit.get("level_code")
    number = unit.get("unit_number") or unit.get("unit_label") or "?"
    return f"{level}-{number}" if level else str(number)


class OwnershipClashDetector:
    """Compares recorded rights to find title conflicts needing adjudication."""

    def __init__(self, as_of: Optional[datetime] = None):
        self.as_of = as_of or datetime.now(timezone.utc)

    # --- scope -----------------------------------------------------
    def shared_spatial_identities(self, units: List[Dict[str, Any]]) -> List[str]:
        """Unit identities carried by more than one record.

        This is the R010 predicate, computed once so the checks below can step
        around it. It is not reported as a finding here: a repeated spatial
        claim is a duplicate submission whichever parties it names, and it is
        the duplicate spatial claim rule's finding to make. What this file does
        with the answer is refuse to read a title conflict out of it.
        """
        counts: Dict[str, int] = {}
        for unit in units:
            identity = _identity(unit)
            counts[identity] = counts.get(identity, 0) + 1
        return sorted(identity for identity, count in counts.items() if count > 1)

    # --- R013 ------------------------------------------------------
    def check_concurrent_claims(
        self, unit: Dict[str, Any], as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Title conflicts on a single registered unit. Empty when the record is clean.

        Clean means more than "one owner": an undivided 50/50 held by two
        co-owners is a normal register entry and is not returned here. What is
        returned is an allocation that cannot exist, an allocation that cannot be
        checked, or an instrument claiming the same succession as a live title.
        """
        moment = as_of or self.as_of
        rights = _rights_of(unit)
        live = [r for r in rights if _is_live(r, moment)]
        ownership = [r for r in live if _right_type(r) in OWNERSHIP_RIGHT_TYPES]
        holders = sorted({_party_of(r) for r in ownership if _party_of(r)})
        conflicts: List[Dict[str, Any]] = []

        if len(holders) > 1:
            shares = [_share_of(r) for r in ownership]
            stated = [s for s in shares if s is not None]
            if stated and len(stated) == len(shares):
                total = round(sum(stated), 2)
                if total > 100.0 + _SHARE_TOLERANCE_PCT:
                    conflicts.append({
                        "conflict_type": "OVER_ALLOCATED_TITLE",
                        "unit": _label(unit),
                        "unit_key": _identity(unit),
                        "claimants": [
                            {"party": _party_of(r), "right_type": _right_type(r), "share_pct": _share_of(r)}
                            for r in ownership
                        ],
                        "recorded_total_share_pct": total,
                        "severity": RuleSeverity.CRITICAL,
                        "basis": "recorded share_pct values on live OWNERSHIP rights for this unit",
                    })
            else:
                conflicts.append({
                    "conflict_type": "UNVERIFIABLE_ALLOCATION",
                    "unit": _label(unit),
                    "unit_key": _identity(unit),
                    "claimants": [
                        {"party": _party_of(r), "right_type": _right_type(r), "share_pct": _share_of(r)}
                        for r in ownership
                    ],
                    "recorded_total_share_pct": None,
                    "severity": RuleSeverity.HIGH,
                    "basis": "several parties hold live OWNERSHIP and at least one row states no share_pct, "
                             "so the allocation cannot be checked from this register",
                })

        contested = [r for r in live if _right_type(r) in CONTESTING_RIGHT_TYPES]
        if contested and ownership:
            conflicts.append({
                "conflict_type": "CONTESTED_SUCCESSIVE_INTEREST",
                "unit": _label(unit),
                "unit_key": _identity(unit),
                "claimants": [
                    {"party": _party_of(r), "right_type": _right_type(r), "share_pct": _share_of(r)}
                    for r in contested
                ],
                "live_owners": holders,
                "severity": RuleSeverity.HIGH,
                "basis": f"live {'/'.join(sorted({_right_type(r) for r in contested}))} instrument recorded "
                         "alongside a live OWNERSHIP right over the same unit",
            })

        unidentified = [r for r in ownership if not _party_of(r)]
        if unidentified:
            conflicts.append({
                "conflict_type": "UNIDENTIFIED_HOLDER",
                "unit": _label(unit),
                "unit_key": _identity(unit),
                "claimants": [{"party": None, "right_type": _right_type(r), "share_pct": _share_of(r)}
                              for r in unidentified],
                "severity": RuleSeverity.MEDIUM,
                "basis": "an OWNERSHIP row names no party, so no holder can be established from this register",
            })
        return conflicts

    # --- R014 ------------------------------------------------------
    def check_volumetric_overlap(
        self, a: Dict[str, Any], b: Dict[str, Any], as_of: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Do two unit volumes intersect in plan and in elevation?

        Reports the shared Z band and the shared fraction of the smaller plan.
        No square metres: the plan frame is whatever the caller stored it in, and
        an area computed in an unknown frame would be a number without a unit.
        """
        moment = as_of or self.as_of
        empty = {
            "overlap": False,
            "severity": "NONE",
            "overlap_ratio": 0.0,
            "overlap_min_z": None,
            "overlap_max_z": None,
            "overlap_height_m": 0.0,
            "same_unit_identity": False,
            "same_party": False,
            "holders_a": [],
            "holders_b": [],
            "reason": "",
        }

        if _identity(a) == _identity(b):
            return {**empty, "same_unit_identity": True,
                    "reason": "both records carry the same unit identity; a repeated claim on one space is a "
                              "duplicate spatial claim, not an overlap between distinct units"}

        holders_a = self._live_owners(a, moment)
        holders_b = self._live_owners(b, moment)
        shared = sorted(set(holders_a) & set(holders_b))
        # same_party is reported as a flag rather than an early exit: whether the
        # volumes actually intersect is still worth computing, because an overlap
        # under one party is counted and named as a partition question.
        base = {
            **empty,
            "same_party": bool(shared),
            "holders_a": sorted(holders_a),
            "holders_b": sorted(holders_b),
        }

        a_poly, b_poly = _footprint(a), _footprint(b)
        if a_poly is None or b_poly is None:
            return {**base, "reason": "one of the units has no readable footprint, so the volumes cannot be compared"}

        min_z = max(float(a.get("min_z", 0.0)), float(b.get("min_z", 0.0)))
        max_z = min(float(a.get("max_z", 0.0)), float(b.get("max_z", 0.0)))
        if max_z <= min_z:
            return {**base, "reason": "the Z bands do not overlap, so the volumes are stacked, not coincident"}

        try:
            intersection = a_poly.intersection(b_poly)
        except Exception:  # noqa: BLE001 - an invalid ring cannot be compared
            return {**base, "reason": "the footprints could not be intersected"}
        smallest = min(a_poly.area, b_poly.area)
        if smallest <= 0.0 or intersection.is_empty or intersection.area <= 0.0:
            return {**base, "reason": "the footprints share no plan area"}

        ratio = round(float(intersection.area) / float(smallest), 4)
        if shared:
            return {
                **base,
                "overlap": True,
                "overlap_ratio": ratio,
                "overlap_min_z": round(min_z, 2),
                "overlap_max_z": round(max_z, 2),
                "overlap_height_m": round(max_z - min_z, 2),
                "reason": f"the volumes do overlap, but both units are held by {', '.join(shared)}; overlapping "
                          "plans under one party are a partition problem between units, not a title conflict",
            }
        return {
            "overlap": True,
            "severity": RuleSeverity.CRITICAL,
            "overlap_ratio": ratio,
            "overlap_min_z": round(min_z, 2),
            "overlap_max_z": round(max_z, 2),
            "overlap_height_m": round(max_z - min_z, 2),
            "same_unit_identity": False,
            "same_party": False,
            "holders_a": sorted(holders_a),
            "holders_b": sorted(holders_b),
            "reason": f"distinct registered units share {ratio:.1%} of the smaller plan between Z={min_z:.2f} "
                      f"and Z={max_z:.2f}, and live rights name different parties",
        }

    def _live_owners(self, unit: Dict[str, Any], moment: datetime) -> List[str]:
        return sorted(
            {
                _party_of(r)
                for r in _rights_of(unit)
                if _right_type(r) in OWNERSHIP_RIGHT_TYPES and _is_live(r, moment) and _party_of(r)
            }
        )

    # --- R016 ------------------------------------------------------
    def check_title_condition(self, unit: Dict[str, Any], as_of: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Approved unit whose only live title is disputed or has run out."""
        moment = as_of or self.as_of
        status = str(unit.get("status") or "").strip().upper()
        if status != "APPROVED":
            return None
        rights = _rights_of(unit)
        live = [r for r in rights if _is_live(r, moment)]
        disputed = [r for r in live if _status_of(r) == "DISPUTED"]
        lapsed = [r for r in rights if _is_lapsed(r, moment)]
        ownership = [r for r in rights if _right_type(r) in OWNERSHIP_RIGHT_TYPES]
        if not ownership or (not disputed and not lapsed):
            return None
        return {
            "unit": _label(unit),
            "unit_key": _identity(unit),
            "unit_status": status,
            "disputed": [
                {"party": _party_of(r), "right_type": _right_type(r), "encumbrance_status": _status_of(r)}
                for r in disputed
            ],
            "lapsed": [
                {"party": _party_of(r), "right_type": _right_type(r), "valid_to": r.get("valid_to")}
                for r in lapsed
            ],
            "basis": "unit status is APPROVED while its recorded OWNERSHIP right is disputed or past valid_to",
        }

    # --- report ----------------------------------------------------
    def run_rules(
        self,
        units: List[Dict[str, Any]],
        parcel_data: Optional[Dict[str, Any]] = None,
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """R013-R016 as a QA report in the shape ``TopologyQAEngine`` returns.

        Same finding keys, same status and severity vocabularies, same summary
        counters, so :meth:`attach_to` can fold these into a full run instead of
        the two reports having to be read side by side.
        """
        moment = as_of or self.as_of
        records = [u for u in units if isinstance(u, dict)]
        deferred = self.shared_spatial_identities(records)
        by_identity: Dict[str, List[Dict[str, Any]]] = {}
        for unit in records:
            by_identity.setdefault(_identity(unit), []).append(unit)
        # Only identities carried by exactly one record are read for title. A
        # repeated identity is R010's duplicate claim, and reading its pooled
        # rights as competing owners would report one defect twice.
        single = [group[0] for group in by_identity.values() if len(group) == 1]

        parcel_ref = None
        if isinstance(parcel_data, dict):
            parcel_ref = parcel_data.get("ulpin") or parcel_data.get("parcel_id")

        concurrent: List[Dict[str, Any]] = []
        for unit in single:
            concurrent.extend(self.check_concurrent_claims(unit, moment))

        overlaps: List[Dict[str, Any]] = []
        same_party_overlaps = 0
        comparable = [u for u in single if _footprint(u) is not None]
        for i in range(len(comparable)):
            for j in range(i + 1, len(comparable)):
                res = self.check_volumetric_overlap(comparable[i], comparable[j], moment)
                if not res["overlap"]:
                    continue
                if res["same_party"]:
                    # Real overlap, one holder on both sides: a partition problem
                    # between two of a party's own units, which the partition
                    # rule reports. Counting it here would invent a party on the
                    # other side of the claim.
                    same_party_overlaps += 1
                    continue
                overlaps.append({
                    "unit_a": _label(comparable[i]),
                    "unit_b": _label(comparable[j]),
                    "unit_a_key": _identity(comparable[i]),
                    "unit_b_key": _identity(comparable[j]),
                    "holders_a": res["holders_a"],
                    "holders_b": res["holders_b"],
                    "overlap_ratio": res["overlap_ratio"],
                    "overlap_min_z": res["overlap_min_z"],
                    "overlap_max_z": res["overlap_max_z"],
                    "overlap_height_m": res["overlap_height_m"],
                    "basis": res["reason"],
                })

        untitled = [
            _label(u)
            for u in single
            if _is_registered(u) and not _rights_of(u)
        ]
        lapsed_approved = [
            cond for cond in (self.check_title_condition(u, moment) for u in single) if cond is not None
        ]

        scope = (
            f"{len(records)} unit record(s) supplied; {len(single)} carried a single spatial identity. "
            f"{len(deferred)} repeated identit(ies) were left to the duplicate spatial claim rule."
            + (f" Parcel on record: {parcel_ref}." if parcel_ref else "")
        )

        findings = [
            self._r013(concurrent, scope),
            self._r014(overlaps, same_party_overlaps, scope),
            self._r015(untitled, scope),
            self._r016(lapsed_approved, scope),
        ]
        if not records:
            # Nothing to compare. A PASS here would assert an absence of conflict
            # that was never tested, so each check says it did not run instead.
            for finding in findings:
                finding["status"] = RuleStatus.WARNING
                finding["severity"] = RuleSeverity.MEDIUM
                finding["message"] = (
                    "No unit records were supplied, so this check did not run. An empty register is not a "
                    "clean result and must not be read as one."
                )
                finding["recommended_action"] = (
                    "Supply the unit rows with their recorded rights, then re-run. Until then no statement "
                    "about title conflict is supported."
                )

        passed = sum(1 for f in findings if f["status"] == RuleStatus.PASS)
        failed = sum(1 for f in findings if f["status"] == RuleStatus.FAIL)
        warning = sum(1 for f in findings if f["status"] == RuleStatus.WARNING)

        return {
            "total_rules": len(findings),
            "passed_rules": passed,
            "failed_rules": failed,
            "warning_rules": warning,
            # An empty register has no clean result to report, so it does not get
            # the PASS label a full engine run would give it.
            "overall_status": "NO_RECORDS" if not records else (
                "FAIL" if failed > 0 else ("WARNING" if warning > 0 else "PASS")
            ),
            "register_populated": bool(records),
            "as_of": moment.isoformat(),
            "evidence_basis": "RECORD_COMPARISON",
            "authoritative": False,
            "disclaimer": (
                "Each finding compares rows held in this system against each other. It is not a "
                "determination of legal title: this platform is not a registry of deeds, holds no copy of "
                "any instrument, and cannot say who holds title. Anything reported here is referred for "
                "manual adjudication by the competent authority."
            ),
            "deferred_to_duplicate_claim": deferred,
            "findings": findings,
        }

    # --- finding builders ------------------------------------------
    def _r013(self, conflicts: List[Dict[str, Any]], scope: str) -> Dict[str, Any]:
        if not conflicts:
            return {
                "rule_id": "R013",
                "rule_name": "Concurrent Active Ownership Claim Detection",
                "severity": RuleSeverity.LOW,
                "status": RuleStatus.PASS,
                "message": f"No competing or over-allocated live title on any singly-identified unit. {scope}",
                "recommended_action": None,
                "details": [],
            }
        by_type: Dict[str, int] = {}
        for conflict in conflicts:
            by_type[conflict["conflict_type"]] = by_type.get(conflict["conflict_type"], 0) + 1
        summary = ", ".join(f"{count}x {kind}" for kind, count in sorted(by_type.items()))
        return {
            "rule_id": "R013",
            "rule_name": "Concurrent Active Ownership Claim Detection",
            "severity": RuleSeverity.CRITICAL,
            "status": RuleStatus.FAIL,
            "message": (
                f"{len(conflicts)} title conflict(s) recorded on units that carry one spatial identity: "
                f"{summary}. Undivided shares that add up to 100% are not counted as conflicts. {scope}"
            ),
            "recommended_action": (
                "Refer to the competent authority for title adjudication. Do not register, transfer or "
                "mortgage a unit listed here until the allocation or the competing instrument is resolved."
            ),
            "details": conflicts,
        }

    def _r014(
        self, overlaps: List[Dict[str, Any]], same_party_overlaps: int, scope: str
    ) -> Dict[str, Any]:
        if not overlaps:
            note = (
                f" {same_party_overlaps} further overlapping pair(s) are held by one common party and are a "
                "partition question between units rather than a title conflict."
                if same_party_overlaps
                else ""
            )
            return {
                "rule_id": "R014",
                "rule_name": "Volumetric Overlap Between Distinct Registered Units",
                "severity": RuleSeverity.LOW,
                "status": RuleStatus.PASS,
                "message": f"No volume is claimed by two distinct registered units under different parties. {scope}{note}",
                "recommended_action": None,
                "details": [],
            }
        worst = max(o["overlap_ratio"] for o in overlaps)
        return {
            "rule_id": "R014",
            "rule_name": "Volumetric Overlap Between Distinct Registered Units",
            "severity": RuleSeverity.CRITICAL,
            "status": RuleStatus.FAIL,
            "message": (
                f"{len(overlaps)} pair(s) of distinct registered units overlap in 3D while live rights name "
                f"different parties; the largest shared plan fraction is {worst:.1%}. "
                + (
                    f"{same_party_overlaps} further overlapping pair(s) share one party and are excluded here "
                    "as a partition question. "
                    if same_party_overlaps
                    else ""
                )
                + scope
            ),
            "recommended_action": (
                "Two parties hold the same volume. Establish which registration governs before any transfer, "
                "and refer the overlap for adjudication by the competent authority."
            ),
            "details": overlaps,
        }

    def _r015(self, untitled: List[str], scope: str) -> Dict[str, Any]:
        if not untitled:
            return {
                "rule_id": "R015",
                "rule_name": "Recorded Unit Without Recorded Title",
                "severity": RuleSeverity.LOW,
                "status": RuleStatus.PASS,
                "message": f"Every registered unit supplied carries at least one recorded right. {scope}",
                "recommended_action": None,
                "details": [],
            }
        return {
            "rule_id": "R015",
            "rule_name": "Recorded Unit Without Recorded Title",
            "severity": RuleSeverity.MEDIUM,
            "status": RuleStatus.WARNING,
            "message": (
                f"{len(untitled)} registered unit(s) carry no right of any kind: {', '.join(untitled)}. "
                f"That is a gap in this register, not evidence that nobody holds title. {scope}"
            ),
            "recommended_action": (
                "Request the instrument record for these units from the source register. Until it arrives the "
                "gap cannot be read either way, so do not infer ownership or its absence from this report."
            ),
            "details": untitled,
        }

    def _r016(self, conditions: List[Dict[str, Any]], scope: str) -> Dict[str, Any]:
        if not conditions:
            return {
                "rule_id": "R016",
                "rule_name": "Approved Unit With Disputed Or Lapsed Title",
                "severity": RuleSeverity.LOW,
                "status": RuleStatus.PASS,
                "message": f"No approved unit rests on a disputed or expired title. {scope}",
                "recommended_action": None,
                "details": [],
            }
        return {
            "rule_id": "R016",
            "rule_name": "Approved Unit With Disputed Or Lapsed Title",
            "severity": RuleSeverity.MEDIUM,
            "status": RuleStatus.WARNING,
            "message": (
                f"{len(conditions)} approved unit(s) rest on a disputed or expired title: "
                f"{', '.join(c['unit'] for c in conditions)}. {scope}"
            ),
            "recommended_action": (
                "Re-confirm the title instrument behind each approval. An approval recorded against a disputed "
                "or expired right needs the competent authority to confirm it before the unit is dealt with."
            ),
            "details": conditions,
        }

    # --- integration -----------------------------------------------
    def attach_to(
        self, report: Dict[str, Any], units: List[Dict[str, Any]], parcel_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fold R013-R016 into a report already produced by TopologyQAEngine.

        Counters are recomputed over the merged findings, so a caller can keep
        reading ``total_rules``/``failed_rules``/``overall_status`` as totals
        rather than per-detector subtotals.
        """
        merged = dict(report)
        extra = self.run_rules(units, parcel_data=parcel_data)
        findings = list(report.get("findings") or []) + extra["findings"]
        passed = sum(1 for f in findings if f["status"] == RuleStatus.PASS)
        failed = sum(1 for f in findings if f["status"] == RuleStatus.FAIL)
        warning = sum(1 for f in findings if f["status"] == RuleStatus.WARNING)
        merged["findings"] = findings
        merged["total_rules"] = len(findings)
        merged["passed_rules"] = passed
        merged["failed_rules"] = failed
        merged["warning_rules"] = warning
        merged["overall_status"] = "FAIL" if failed > 0 else ("WARNING" if warning > 0 else "PASS")
        merged["ownership_report"] = extra
        return merged