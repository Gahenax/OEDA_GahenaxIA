import json
import hashlib
from datetime import datetime, timezone

acta = {
    "type": "ACTA_NACIMIENTO",
    "version": "v1.1.1",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "semáforo_protocol": "Chronos-Hodge v2.0",
    "summary": {
        "verdict": "SYSTEM HEALTH: OPTIMAL",
        "counts": {"GREEN": 5, "YELLOW": 0, "ORANGE": 0, "RED": 0}
    },
    "metrics": {
        "h_rigidity": 1e-15,
        "input_fingerprint_status": "CNI_VERIFIED"
    },
    "ledger_window": {"from_id": 1, "to_id": 5},
    "snapshot_ref": "e0feed40b647ff09591395a6811104d0461a4bf5018b1604544034df3a75166e"
}

# Canonize and Hash
canon = json.dumps(acta, sort_keys=True, separators=(",", ":")).encode("utf-8")
acta["acta_hash"] = hashlib.sha256(canon).hexdigest()

with open("snapshots/gahenax_core_v1.1.1_acta_nacimiento.json", "w") as f:
    json.dump(acta, f, indent=2)

print(f"ACTA_HASH: {acta['acta_hash']}")
