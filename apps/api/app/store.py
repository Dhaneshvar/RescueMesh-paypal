from datetime import datetime, timezone
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


MERCHANTS = [
    {"id": "fps-riverbend", "name": "Riverbend Fair Price Shop", "type": "FPS", "items": {"rice": 25, "lentils": 16, "oil": 12}, "eta_minutes": 35},
    {"id": "med-hope", "name": "Hope Pharmacy", "type": "PHARMACY", "items": {"insulin": 8, "ors": 40, "bandage": 55}, "eta_minutes": 22},
    {"id": "logistics-rapid", "name": "Rapid Last-Mile", "type": "DELIVERY", "items": {"delivery": 25}, "eta_minutes": 30},
]

MISSIONS = {
    "mission-asha": {
        "id": "mission-asha",
        "household_alias": "Asha household",
        "location": "Riverbend Ward 4",
        "urgency": "critical",
        "needs": [{"item": "rice", "quantity": 5}, {"item": "lentils", "quantity": 2}, {"item": "insulin", "quantity": 1}, {"item": "delivery", "quantity": 1}],
        "consent": False,
        "entitlement": None,
        "allocations": [],
        "payment": None,
        "audit": [{"at": now(), "event": "mission_created", "detail": "Voice request transcribed and human-readable mission created."}],
    }
}


def append_audit(mission: dict, event: str, detail: str) -> None:
    mission["audit"].append({"id": str(uuid4()), "at": now(), "event": event, "detail": detail})

