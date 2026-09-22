from typing import Dict, Any, List, Optional
import numpy as np


class ChangeDetectionPipeline:
    """
    Component 4: Multi-Epoch Temporal Change Detection.
    Compares baseline survey (Epoch 1) against monitoring survey (Epoch 2)
    to detect structural alterations, vertical additions, and volumetric discrepancies.
    
    Terminology Guard:
    Emits 'Suspected change (unverified)' with ``evidence_basis: "SYNTHETIC"``.
    A difference between two epochs is not a finding of unlawful construction:
    this method cannot see permissions, and its inputs are generated rather
    than surveyed in the current deployment.
    """

    def detect_changes(
        self,
        epoch1_height: float,
        epoch2_height: float,
        epoch1_floors: int,
        epoch2_floors: int,
        footprint_area_m2: float,
        threshold_height_m: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Detects height differences and extra floor constructions between epochs.
        """
        delta_height = round(epoch2_height - epoch1_height, 2)
        delta_floors = epoch2_floors - epoch1_floors
        
        has_change = delta_height >= threshold_height_m or delta_floors > 0
        
        if not has_change:
            return {
                "change_detected": False,
                "status": "No significant difference between supplied epochs",
                "delta_height_m": 0.0,
                "delta_floors": 0,
                "delta_volume_m3": 0.0,
                "summary": "No vertical or volumetric difference above threshold between the two supplied values.",
            }

        # Calculate added volume
        added_volume_m3 = round(footprint_area_m2 * delta_height, 2)

        return {
            "change_detected": True,
            # Prefixed SYNTHETIC because the numbers reaching this method are,
            # in the current deployment, generated rather than surveyed. The
            # arithmetic is real; the inputs are not evidence.
            "status": "Suspected change (unverified)",
            "evidence_basis": "SYNTHETIC",
            "delta_height_m": delta_height,
            "delta_floors": delta_floors,
            "delta_volume_m3": added_volume_m3,
            "epoch_from": "2026 Epoch 1 Baseline",
            "epoch_to": "2027 Epoch 2 Monitoring Survey",
            "detected_features": [
                f"Height difference of {delta_height}m between the two supplied epochs ({epoch1_height}m to {epoch2_height}m)",
                f"Floor count difference of {delta_floors} between the two supplied epochs ({epoch1_floors}F to {epoch2_floors}F)",
                f"Volume difference of {added_volume_m3} m³ between the two supplied epochs",
            ],
            "wording_note": (
                "These are differences between two supplied values. They do not "
                "establish that any construction was unauthorised, and the "
                "authorisation status of the structure is not known to this pipeline."
            ),
            "recommended_action": (
                "If both epochs are real surveys, route to District Verifier for "
                "field verification against sanctioned municipal plans."
            ),
        }

    def evaluate_change_metrics(
        self,
        true_positives: int,
        false_positives: int,
        false_negatives: int,
    ) -> Dict[str, float]:
        """Calculates Precision, Recall, and F1-Score for change detection benchmark."""
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
        }
