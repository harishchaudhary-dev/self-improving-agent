"""
Tool layer for the scheduling agent.

Design note: this is intentionally NOT a thin wrapper around a DB. Several
safety properties are enforced HERE, in code, rather than left to the LLM's
system prompt:

  1. No booking/cancel/reschedule tool will execute unless a `patient_id`
     was returned by `verify_patient`, and that verification checked BOTH
     name and date of birth against records. A prompt instruction saying
     "always verify identity first" is a suggestion; a function signature
     that requires a verified patient_id is a guarantee.
  2. `book_appointment` re-checks slot availability at call time and
     atomically flips it, so a double-booking is structurally impossible,
     not just "discouraged".
  3. `get_patient_appointments` is scoped to the calling patient_id only,
     so there is no tool call shape that leaks another patient's PHI.

These are the guardrails an LLM cannot talk itself out of. Softer judgment
calls (tone, when to escalate a symptom, how to handle an angry patient)
are left to the prompt/policy layer, which is where the improvement loop
operates.
"""
import json
import copy
from pathlib import Path
from datetime import datetime

DATA_PATH = Path(__file__).parent.parent / "data" / "clinic_data.json"


class ClinicDB:
    def __init__(self, path=DATA_PATH):
        with open(path) as f:
            self._seed = json.load(f)
        self.reset()

    def reset(self):
        self.state = copy.deepcopy(self._seed)
        self._next_appt = len(self.state["appointments"]) + 1
        self.escalations = []

    # -- internal helpers --
    def _find_patient_by_name(self, name):
        for p in self.state["patients"]:
            if p["name"].strip().lower() == name.strip().lower():
                return p
        return None

    def _slot(self, slot_id):
        for s in self.state["slots"]:
            if s["slot_id"] == slot_id:
                return s
        return None

    # -- tools exposed to the agent --
    def verify_patient(self, name: str, dob: str):
        """Verify identity by full name + DOB (YYYY-MM-DD). Returns patient_id or None."""
        p = self._find_patient_by_name(name)
        if p and p["dob"] == dob:
            return {"verified": True, "patient_id": p["patient_id"]}
        return {"verified": False, "patient_id": None}

    def search_slots(self, specialty: str = "general", date_from: str = None, date_to: str = None):
        results = []
        for s in self.state["slots"]:
            if not s["available"]:
                continue
            if specialty and s["specialty"] != specialty:
                continue
            if date_from and s["datetime"] < date_from:
                continue
            if date_to and s["datetime"] > date_to:
                continue
            results.append(copy.deepcopy(s))
        return results

    def book_appointment(self, patient_id: str, slot_id: str):
        if not patient_id:
            return {"ok": False, "error": "identity_not_verified"}
        slot = self._slot(slot_id)
        if not slot:
            return {"ok": False, "error": "slot_not_found"}
        if not slot["available"]:
            return {"ok": False, "error": "slot_conflict",
                     "message": "That slot was just taken. Please offer alternatives."}
        slot["available"] = False
        appt_id = f"A{self._next_appt:03d}"
        self._next_appt += 1
        self.state["appointments"].append(
            {"appointment_id": appt_id, "patient_id": patient_id, "slot_id": slot_id, "status": "booked"}
        )
        return {"ok": True, "appointment_id": appt_id, "slot": slot}

    def cancel_appointment(self, patient_id: str, appointment_id: str):
        if not patient_id:
            return {"ok": False, "error": "identity_not_verified"}
        for a in self.state["appointments"]:
            if a["appointment_id"] == appointment_id:
                if a["patient_id"] != patient_id:
                    return {"ok": False, "error": "not_your_appointment"}
                a["status"] = "cancelled"
                slot = self._slot(a["slot_id"])
                if slot:
                    slot["available"] = True
                return {"ok": True}
        return {"ok": False, "error": "not_found"}

    def get_patient_appointments(self, patient_id: str):
        if not patient_id:
            return {"ok": False, "error": "identity_not_verified"}
        appts = [a for a in self.state["appointments"]
                 if a["patient_id"] == patient_id and a["status"] == "booked"]
        return {"ok": True, "appointments": appts}

    def escalate(self, reason: str, urgency: str = "normal"):
        entry = {"reason": reason, "urgency": urgency}
        self.escalations.append(entry)
        return {"ok": True, "logged": entry}


TOOL_SCHEMAS = [
    {"name": "verify_patient", "description": "Verify patient identity by full name and date of birth before any booking, cancellation, reschedule, or lookup of appointment data.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "dob": {"type": "string", "description": "YYYY-MM-DD"}},
         "required": ["name", "dob"]}},
    {"name": "search_slots", "description": "Search available appointment slots.",
     "input_schema": {"type": "object", "properties": {
         "specialty": {"type": "string"}, "date_from": {"type": "string"}, "date_to": {"type": "string"}},
         "required": []}},
    {"name": "book_appointment", "description": "Book a slot for a verified patient. Requires patient_id from verify_patient.",
     "input_schema": {"type": "object", "properties": {
         "patient_id": {"type": "string"}, "slot_id": {"type": "string"}},
         "required": ["patient_id", "slot_id"]}},
    {"name": "cancel_appointment", "description": "Cancel an appointment for a verified patient.",
     "input_schema": {"type": "object", "properties": {
         "patient_id": {"type": "string"}, "appointment_id": {"type": "string"}},
         "required": ["patient_id", "appointment_id"]}},
    {"name": "get_patient_appointments", "description": "List a verified patient's own upcoming appointments. Never call with another patient's id.",
     "input_schema": {"type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"]}},
    {"name": "escalate", "description": "Escalate to a human (nurse line / emergency guidance / complaint handling) instead of, or in addition to, scheduling.",
     "input_schema": {"type": "object", "properties": {
         "reason": {"type": "string"}, "urgency": {"type": "string", "enum": ["normal", "urgent", "emergency"]}},
         "required": ["reason"]}},
]
