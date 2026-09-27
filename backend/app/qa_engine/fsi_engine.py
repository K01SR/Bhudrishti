from typing import Any, Dict, Optional


class FSIEngine:
    """
    Municipal Floor Space Index (FSI) check.

    FSI compares built-up area against plot area and, crucially, against a
    *permitted* ceiling that exists only in an authentic planning authority
    record. This engine therefore never invents a ceiling or a jurisdiction:
    when the rule or the measured inputs are missing it returns no verdict
    (``RULE_UNAVAILABLE`` / ``INPUTS_UNVERIFIED``) instead of a number that
    would read like a statutory determination.
    """

    STATUS_PASS = "PASS"
    STATUS_EXCEEDED = "REVIEW REQUIRED"
    STATUS_NO_RULE = "RULE_UNAVAILABLE"
    STATUS_UNVERIFIED = "INPUTS_UNVERIFIED"

    def calculate_fsi(
        self,
        plot_area_m2: float,
        total_built_up_area_m2: float,
        max_allowed_fsi: Optional[float] = None,
        jurisdiction_name: Optional[str] = None,
        inputs_authoritative: bool = False,
    ) -> Dict[str, Any]:
        """Compute FSI and, only when a real rule and real inputs exist, judge it."""
        if plot_area_m2 <= 0:
            raise ValueError("Plot area must be positive to compute FSI.")

        built_up = float(total_built_up_area_m2 or 0.0)
        fsi = round(built_up / plot_area_m2, 3)

        rule_known = max_allowed_fsi is not None and float(max_allowed_fsi) > 0
        ceiling = float(max_allowed_fsi) if rule_known else None

        if not rule_known:
            status = self.STATUS_NO_RULE
        elif not inputs_authoritative:
            status = self.STATUS_UNVERIFIED
        else:
            status = self.STATUS_PASS if fsi <= ceiling else self.STATUS_EXCEEDED

        result: Dict[str, Any] = {
            "jurisdiction": jurisdiction_name,
            "plot_area_m2": round(plot_area_m2, 2),
            "total_built_up_area_m2": round(built_up, 2),
            "calculated_fsi": fsi,
            "allowed_max_fsi": ceiling,
            "status": status,
            # Utilization only means something against a real ceiling with real
            # inputs; otherwise it is a bare ratio dressed as a compliance metric.
            "utilization_pct": round((fsi / ceiling) * 100, 1) if (rule_known and inputs_authoritative) else None,
            "inputs_authoritative": bool(inputs_authoritative),
            "assessable": bool(rule_known and inputs_authoritative),
        }

        if status == self.STATUS_NO_RULE:
            result["disclaimer"] = (
                "No permitted-FSI rule is on record for this jurisdiction, so the ratio above is "
                "descriptive only and is not a compliance determination."
            )
        elif status == self.STATUS_UNVERIFIED:
            result["disclaimer"] = (
                "Built-up area comes from a non-authoritative source, so FSI is indicative only "
                "and no over-permit finding can be issued."
            )
        else:
            result["disclaimer"] = (
                "Computed from the recorded plot area and approved built-up area against the "
                "permitted FSI for the jurisdiction. Supporting records are required for any "
                "legal determination."
            )
        return result
