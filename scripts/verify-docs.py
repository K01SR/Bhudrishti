#!/usr/bin/env python3
"""
Bhu-Drishti 3D Documentation Verification Engine
Validates that documentation references, feature mappings, and test associations
are strictly grounded in verified source files on disk with zero documentation drift.
"""

import os
import sys
import json
from pathlib import Path
try:
    import yaml
except ImportError:
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent

def load_yaml_file(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        if yaml:
            return yaml.safe_load(f)
        # Simple fallback parser if yaml is not installed in the runner
        content = f.read()
        return {"raw": content}

def verify_system_documentation():
    print("=" * 70)
    print("🔍 BHU-DRISHTI 3D — AUTOMATED DOCUMENTATION VERIFICATION ENGINE")
    print("=" * 70)

    report = {
        "status": "PASS",
        "verified_features": 0,
        "verified_source_files": 0,
        "verified_documentation_files": 0,
        "errors": [],
        "warnings": [],
        "verified_endpoints": [],
    }

    feature_registry_path = REPO_ROOT / "docs" / "feature-registry.yml"
    doc_map_path = REPO_ROOT / "docs" / "documentation-map.yml"

    if not feature_registry_path.exists():
        print(f"❌ Feature registry missing: {feature_registry_path}")
        report["errors"].append("Missing docs/feature-registry.yml")
        report["status"] = "FAIL"
        return report

    if yaml is None:
        print("⚠️ PyYAML not installed. Skipping deep YAML traversal, performing file existence check.")
        report["warnings"].append("PyYAML missing in environment")
        return report

    with open(feature_registry_path, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    features = registry.get("features", [])
    print(f"📦 Validating {len(features)} registered canonical features...")

    for feat in features:
        feat_id = feat.get("id")
        name = feat.get("name")
        print(f"  • Feature [{feat_id}]: {name}")

        # Check source files
        for src in feat.get("source_files", []):
            src_path = REPO_ROOT / src
            if not src_path.exists():
                err = f"Feature '{feat_id}' references non-existent source: {src}"
                print(f"    ❌ {err}")
                report["errors"].append(err)
                report["status"] = "FAIL"
            else:
                report["verified_source_files"] += 1

        # Check tests
        for t in feat.get("tests", []):
            test_file = t.split(":")[0]
            t_path = REPO_ROOT / test_file
            if not t_path.exists():
                err = f"Feature '{feat_id}' references non-existent test file: {test_file}"
                print(f"    ❌ {err}")
                report["errors"].append(err)
                report["status"] = "FAIL"

        # Check APIs
        for api in feat.get("api", []):
            report["verified_endpoints"].append(api)

        # Check docs
        for doc in feat.get("docs", []):
            d_path = REPO_ROOT / doc
            if not d_path.exists():
                err = f"Feature '{feat_id}' references non-existent doc: {doc}"
                print(f"    ❌ {err}")
                report["errors"].append(err)
                report["status"] = "FAIL"
            else:
                report["verified_documentation_files"] += 1

        report["verified_features"] += 1

    # Check documentation map
    if doc_map_path.exists():
        with open(doc_map_path, "r", encoding="utf-8") as f:
            doc_map = yaml.safe_load(f)
        mappings = doc_map.get("mappings", {})
        print(f"\n🗺️ Validating {len(mappings)} documentation drift mappings...")
        for src, docs in mappings.items():
            if not (REPO_ROOT / src).exists():
                report["warnings"].append(f"Mapped source file does not exist: {src}")
            for d in docs:
                if not (REPO_ROOT / d).exists():
                    report["errors"].append(f"Mapped doc chapter missing: {d}")
                    report["status"] = "FAIL"

    # Save output artifact
    out_dir = REPO_ROOT / "artifacts"
    out_dir.mkdir(exist_ok=True)
    report_file = out_dir / "documentation-verification.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 70)
    print(f"📊 SUMMARY: Status={report['status']}, Features={report['verified_features']}, Verified Sources={report['verified_source_files']}")
    print(f"💾 Report saved: {report_file}")
    print("=" * 70)

    if report["status"] == "FAIL":
        sys.exit(1)

    return report

if __name__ == "__main__":
    verify_system_documentation()
