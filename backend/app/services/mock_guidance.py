"""Temporary guidance provider used until the RAG service is available.

Keep this module's return shape stable.  The RAG implementation can replace
``get_guidance`` without requiring changes to the consumer app or API.
"""
from app.models.taxonomy import Derived, Extraction


_GUIDANCE = {
    "noise_and_vibration": [
        "Switch the shaver off and remove the shaving head.",
        "Clean hair and debris from the blade units, then let them air dry fully.",
        "Refit the head, turn the lock ring until it clicks, and charge the shaver fully before testing again.",
    ],
    "shaving_head_and_fitment": [
        "Switch the shaver off and remove the shaving head.",
        "Check the head socket for debris, then refit the head with the notch facing forward.",
        "Turn the lock ring fully and confirm that the head does not wobble or lift.",
    ],
    "power_and_charging": [
        "Charge the shaver for 60 minutes with the supplied USB-C cable and a 5V/1A charger.",
        "Check that the charging port is clean and dry before connecting the cable.",
        "If the battery still lasts under 20 minutes after a full charge, arrange service.",
    ],
    "shaving_performance": [
        "Clean the blade units and allow them to air dry before reassembling.",
        "Use a gentle circular motion while shaving.",
        "Replace the blade units if they are more than 12 months old under daily use.",
    ],
    "cleaning_and_maintenance": [
        "Remove the shaving head and rinse each blade unit under warm running water.",
        "Shake off excess water and let the blade units air dry for at least 30 minutes.",
        "Refit the head and confirm the lock click before using the shaver.",
    ],
    "other_or_unclear": [
        "Please check the product manual for the relevant maintenance instructions.",
        "If the problem continues, contact an authorised service centre.",
    ],
}


def get_guidance(extraction: Extraction, derived: Derived) -> dict:
    """Return a development-only response with the future RAG response contract."""
    if derived.safety_flag:
        return {
            "service_required": True,
            "guidance": [],
            "sources": [],
            "message": "Stop using the shaver and contact an authorised service centre.",
        }

    return {
        "service_required": False,
        "guidance": _GUIDANCE[derived.issue_type.value],
        "sources": [
            {
                "chunk_id": f"mock-{derived.issue_type.value}-01",
                "title": "X500 development knowledge base",
            }
        ],
        "message": "Development-only guidance. This will be replaced by sourced RAG guidance.",
    }
