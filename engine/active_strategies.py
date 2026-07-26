"""
Nothing fires live unless you've explicitly activated it. This exists so
you're never getting signals from 25 overlapping strategies at once --
you pick a small, deliberate set to actually run live.
"""
import json
import os

ACTIVE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "active_strategies.json")


def get_active() -> list:
    if os.path.exists(ACTIVE_PATH):
        with open(ACTIVE_PATH) as f:
            return json.load(f)
    return []


def set_active(genome_ids: list) -> list:
    os.makedirs(os.path.dirname(ACTIVE_PATH), exist_ok=True)
    with open(ACTIVE_PATH, "w") as f:
        json.dump(list(genome_ids), f, indent=2)
    return genome_ids


def activate(genome_id: str) -> list:
    active = set(get_active())
    active.add(genome_id)
    return set_active(list(active))


def deactivate(genome_id: str) -> list:
    active = set(get_active())
    active.discard(genome_id)
    return set_active(list(active))


def is_active(genome_id: str) -> bool:
    return genome_id in get_active()
