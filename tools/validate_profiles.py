#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from center.core.policy import policy_errors  # noqa: E402
from center.core.profiles import (  # noqa: E402
    available_profiles,
    load_device_profile_catalog,
    profile_errors,
    render_profile_desired_state,
)
from center.core.utils import load_json  # noqa: E402


DEFAULT_CATALOG = ROOT / "catalog" / "honeypots.json"
DEFAULT_PROFILES = ROOT / "catalog" / "device_mask_profiles.json"


def profile_policy(profile: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    desired = render_profile_desired_state(profile, catalog)
    return {
        "version": 1,
        "site": {"name": "profile-validation"},
        "sensors": [
            {
                "id": f"validation-{profile.get('id', 'profile')}",
                "host": "127.0.0.1",
                "architecture": "armv7l",
                "active_profile": profile.get("id"),
                "desired_state": desired,
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DeviceMaskProfile catalog against honeypot modules.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    args = parser.parse_args()

    catalog = load_json(args.catalog)
    profile_catalog = load_device_profile_catalog(args.profiles)
    errors: list[str] = []
    seen: set[str] = set()

    for profile in profile_catalog.get("profiles", []):
        if not isinstance(profile, dict):
            errors.append("profile must be an object")
            continue
        profile_id = str(profile.get("id") or "")
        if not profile_id:
            errors.append("profile id is required")
            continue
        if profile_id in seen:
            errors.append(f"duplicate profile: {profile_id}")
        seen.add(profile_id)
        errors.extend(profile_errors(profile, catalog))
        errors.extend(policy_errors(profile_policy(profile, catalog), catalog))

    rendered = available_profiles({"version": 1, "sensors": []}, catalog, profile_catalog)
    if len(rendered) != len(seen):
        errors.append("rendered profile count differs from catalog profile count")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"profiles ok: {len(seen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
