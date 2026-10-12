"""Deterministic stop-use checks supplement the model's interpreted symptoms.
The conversation API merges positive hazard matches with extraction before deriving safety.
Conditions come from data/Data_synthetic/03_safety_escalation.md (burning smell, heat, sparks, damage, liquid, electrical sounds,
grinding with resistance, a head that cannot be secured). Audio and video are covered by the safety flag derived from extracted symptoms."""
import re
from dataclasses import dataclass

# implied taxonomy symptom -> patterns (matched on lower-case text)
_RULES: dict[str, list[str]] = {
    "burning_smell": [r"\bburn(?:t|ed|ing)\b", r"\bsmok(?:e|ing|ey)\b", r"\bjal(?:ne|a|ta)\b", r"\bdhuan\b"],
    "sparking": [r"\bspark(?:s|ed|ing)?\b", r"\bchingari\b", r"\bflash(?:ed|es|ing)?\b"],
    "electrical_crackling": [r"\bcrackl\w+", r"\bpopp(?:ing|ed)\b", r"\b(?:electric(?:al)?\s+)?shock(?:ed|s)?\b", r"\bzap(?:ped|s)?\b"],
    "excessive_heat": [
        r"\b(?:too|very|extremely|really|so|super|burning)\s+hot\b", r"\bhot\s+to\s+(?:the\s+)?(?:touch|hold|handle)\b", r"\bgets?\s+(?:very\s+|really\s+|too\s+)?hot\b",
        r"\bgot\s+(?:very\s+|really\s+|too\s+)?hot\b", r"\boverheat\w*", r"\bmelt(?:ed|ing|s)?\b", r"\b(?:bahut|bohot|zyada|jyada)\b.{0,12}\bgaram\b",
    ],
    "visible_damage": [r"\bcrack(?:s|ed)?\b", r"\bbroken\b", r"\bsnapped\b", r"\bstripped\b", r"\bsplit\s+open\b"],
    "exposed_component": [r"\bexposed\b", r"\binternal\s+part\b", r"\b(?:see|saw|seeing)\b.{0,20}\b(?:wires?|circuit|battery)\b", r"\bwires?\b.{0,15}\b(?:showing|visible|sticking)\b"],
    "water_ingress": [
        r"\b(?:water|liquid|moisture|paani)\b.{0,25}\b(?:inside|got\s+in(?:to)?|entered|leak\w*|in\s+the\s+(?:charging\s+)?port|into\s+the)\b",
        r"\b(?:dropped|fell|dipped|dunked)\b.{0,20}\b(?:in|into)\b.{0,12}\b(?:water|sink|bath|bucket)\b", r"\bsubmerg\w+",
    ],
    "head_detached": [
        r"\b(?:head|blade|foil|cutter)\b.{0,30}\b(?:came\s+off|fell\s+off|came\s+out|detach\w*|flew|popped\s+off)\b",
        r"\b(?:came\s+off|fell\s+off|detach\w*)\b.{0,25}\b(?:while|during|when)\b.{0,15}\b(?:running|use|using|shaving|on)\b",
    ],
    "grinding_with_resistance": [
        r"\b(?:grind\w*|struggl\w*)\b.{0,40}\b(?:stuck|jammed|stall\w*|resist\w*|struggl\w*)\b", r"\bmotor\b.{0,25}\b(?:stuck|jammed|stall\w*)\b",
    ],
}
# phrases that look dangerous but are not, or that are explicitly negated
_IGNORE = [
    r"\brazor\s+burn\b", r"\bskin\s+burn\b", r"\bhot\s+(?:water|shower|towel|lather|steam)\b",
    r"\b(?:no|not|without|never|nothing|isn'?t|doesn'?t|don'?t|didn'?t|hasn'?t|haven'?t)\b(?:\s+\w+){0,2}?\s+(?:burn\w*|smok\w*|spark\w*|hot|crack\w*|melt\w*|smell\w*|overheat\w*)",
]
_COMPILED = {k: [re.compile(p) for p in v] for k, v in _RULES.items()}
_IGNORE_RE = [re.compile(p) for p in _IGNORE]
# Limit list negation to explicit hazard nouns. Do not erase an entire sentence:
# "no smoke, but it sparks" and a later positive hazard must still trigger.
# An affirmative clause after a noun ("smoke appeared") is not a negated list item.
_HAZARD_TERM = (
    r"(?:heat|smoke|sparks?|overheating|"
    r"(?:burning|burnt|electrical)\s+(?:smell|odou?r)|"
    r"(?:electrical\s+)?crackling|visible\s+damage)\b"
)
_NEITHER_HAZARD_LIST = re.compile(
    r"\bneither\s+" + _HAZARD_TERM
    + r"(?:\s+nor\s+" + _HAZARD_TERM + r")+"
    + r"\s+(?:is|was|are|were)\s+(?:present|observed|detected)\b"
)
_HAZARD_NOUN = (
    _HAZARD_TERM +
    r"(?!\s+(?:is|was|are|were|started|appeared|occurred|came|comes|happened)\b)"
)
_NEGATED_HAZARD_LIST = re.compile(
    r"\b(?:no|without|neither)\s+(?:signs?\s+of\s+)?" + _HAZARD_NOUN
    + r"(?:\s*(?:,\s*(?:(?:or|and|nor)\s+)?|\b(?:or|and|nor)\s+)"
    + _HAZARD_NOUN + r")*"
)
_WARM = re.compile(r"\bwarm(?:s|ed|ing|er)?\b|\bgaram\b")

STOP_USE_RESPONSE = {
    "title": "Stop using it now",
    "steps": ["Unplug the charger and the shaver.", "Do not charge or use it again.", "Do not open or repair it."],
    "note": "Burning smell, smoke, sparks, overheating, damage, liquid inside and a head that comes off are stop-use conditions in the X500 safety guide.",
    "priority": "high",
}


def safety_response(symptoms) -> dict:
    """Deterministic advice for observed hazards; combine rather than hide hazards."""
    syms = {getattr(s, 'value', s) for s in symptoms}
    steps = []
    electrical = syms & {'burning_smell', 'sparking', 'electrical_crackling',
                         'excessive_heat', 'water_ingress', 'exposed_component'}
    if electrical:
        steps += ['Stop using and charging the shaver.',
                  'Disconnect it from power only if it is safe to do so.',
                  'Do not open or repair it.']
    if syms & {'head_loose', 'head_wobble', 'head_not_fitting', 'blade_unit_not_seated', 'head_detached'}:
        steps += ['Do not use the shaver if the head cannot be securely attached.',
                  'Switch it off. Do not force the head into place or test it while running.']
    if 'grinding_with_resistance' in syms:
        steps += ['Switch off the shaver. Do not run or force a jammed cutting mechanism.']
    if 'visible_damage' in syms:
        steps += ['Do not use a damaged shaver. Do not attempt to open or repair it.']
    if not steps:
        steps = ['Stop using the shaver until it has been inspected.']
    return {'title': 'Stop using it now', 'steps': steps,
            'note': 'Contact an authorised service centre for inspection before using it again.',
            'priority': 'high'}


@dataclass(frozen=True)
class StopUse:
    symptoms: tuple[str, ...]
    matches: tuple[str, ...]


def _clean(text: str) -> str:
    t = " ".join(text.lower().replace("’", "'").split())
    t = _NEITHER_HAZARD_LIST.sub(" ", t)
    t = _NEGATED_HAZARD_LIST.sub(" ", t)
    for rx in _IGNORE_RE:
        t = rx.sub(" ", t)
    return t


def check_stop_use(text: str) -> StopUse | None:
    """Return the implied symptoms and matched words if the text describes a stop-use condition, else None."""
    t = _clean(text)
    symptoms, matches = [], []
    for symptom, patterns in _COMPILED.items():
        for rx in patterns:
            m = rx.search(t)
            if m:
                symptoms.append(symptom)
                matches.append(m.group(0))
                break
    return StopUse(tuple(symptoms), tuple(matches)) if symptoms else None


def mentions_warmth(text: str) -> bool:
    """'Warm' alone is normal (04_operating_specs.md). The caller should ask one follow-up instead of stopping."""
    t = _clean(text)
    return bool(_WARM.search(t)) and check_stop_use(text) is None
