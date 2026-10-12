# ProductLoop X500 Prototype Taxonomy v2

Controlled vocabulary for the X500 prototype. All data is fictional. The machine-readable source is `taxonomy_v2.json`; this file is generated from it.

## What Gemini returns

Gemini returns only the fields below. Code then **derives** `issue_type`, `severity` and `safety_flag` from the symptoms, so they can never disagree.

```json
{
  "product_model": "X500",
  "user_intent": "report_problem",
  "symptoms": ["rattling_sound", "increased_vibration"],
  "context": {
    "onset": "this_week",
    "persists_after_cleaning": "yes",
    "during_charging": false
  },
  "confidence": 0.88
}
```

Derived by code:

```json
{ "issue_type": "noise_and_vibration", "severity": "medium", "safety_flag": false }
```

## User intent

| Value | Meaning |
|---|---|
| `report_problem` | Describes something wrong with their own X500. Counts in trends. |
| `ask_question` | Asks how to do something. Does not count in complaint trends. |

## Issue types and symptoms

Symptoms are a **global** list. Any symptom can appear with any issue type (for example `increased_noise` together with `excessive_heat`). Each symptom has a home category, a default severity, and a flag for whether it counts as a complaint.

### `noise_and_vibration`
Unusual sound or shaking during operation.

| Symptom | Default severity | Stop-use | Counts as complaint | Meaning |
|---|---|---|---|---|
| `increased_noise` | low | no | yes | Louder than before; no specific sound named |
| `buzzing_sound` | low | no | yes | Mechanical buzzing. Electrical buzzing, crackling or popping is electrical_crackling |
| `rattling_sound` | medium | no | yes | Rattle, often from a loose head |
| `grinding_sound` | medium | no | yes | Grinding without resistance or struggling |
| `grinding_with_resistance` | high | yes | yes | Grinding while the motor struggles or seems jammed (stop-use) |
| `squealing_sound` | medium | no | yes | High-pitched squeal |
| `increased_vibration` | medium | no | yes | Stronger vibration than before |
| `irregular_vibration` | medium | no | yes | Sharp or uneven shaking |

### `shaving_performance`
Not cutting comfortably or effectively.

| Symptom | Default severity | Stop-use | Counts as complaint | Meaning |
|---|---|---|---|---|
| `reduced_cutting_quality` | low | no | yes | Poor or less close shave |
| `missed_hairs` | low | no | yes | Hairs left behind |
| `requires_multiple_passes` | low | no | yes | Needs repeated passes |
| `uneven_shave` | low | no | yes | Uneven result in some areas |
| `pulling_hair` | medium | no | yes | Pulls or tugs hair |
| `blade_drag` | low | no | yes | Blades drag or feel rough on skin |

### `power_and_charging`
Will not start, charge or hold charge.

| Symptom | Default severity | Stop-use | Counts as complaint | Meaning |
|---|---|---|---|---|
| `not_powering_on` | medium | no | yes | Will not start |
| `not_charging` | medium | no | yes | Does not charge |
| `slow_charging` | low | no | yes | Takes longer than normal to charge |
| `battery_drains_fast` | medium | no | yes | Battery runs out quickly |
| `led_not_working` | low | no | yes | Indicator LED does not light or behaves oddly |

### `shaving_head_and_fitment`
Head, lock ring, blade unit or joint does not fit or stay secure.

| Symptom | Default severity | Stop-use | Counts as complaint | Meaning |
|---|---|---|---|---|
| `head_loose` | medium | no | yes | Head feels loose |
| `head_not_fitting` | medium | no | yes | Head will not click or lock into place |
| `head_wobble` | medium | no | yes | Head wobbles in use |
| `blade_unit_not_seated` | medium | no | yes | Blade unit does not sit flush |
| `head_detached` | high | yes | yes | Head came off during use |
| `lock_ring_damaged` | high | yes | yes | Lock ring cracked or stripped |
| `head_joint_damage` | high | yes | yes | Head joint cracked, bent or broken |

### `heat_and_safety`
Heat, damage, electrical or liquid concerns that mean stop use.

| Symptom | Default severity | Stop-use | Counts as complaint | Meaning |
|---|---|---|---|---|
| `excessive_heat` | high | yes | yes | Hot to the touch, beyond warm |
| `burning_smell` | high | yes | yes | Burning or electrical smell |
| `sparking` | high | yes | yes | Visible spark or flash |
| `electrical_crackling` | high | yes | yes | Crackling or popping that is not mechanical |
| `visible_damage` | high | yes | yes | Cracked casing or other visible damage |
| `water_ingress` | high | yes | yes | Water or liquid inside the body or charging port |
| `exposed_component` | high | yes | yes | Internal parts visible |

### `cleaning_and_maintenance`
Cleaning, debris or maintenance topics.

| Symptom | Default severity | Stop-use | Counts as complaint | Meaning |
|---|---|---|---|---|
| `hair_buildup` | low | no | yes | Hair or residue trapped under the head |
| `difficult_to_clean` | low | no | yes | Hard to clean properly |
| `cleaning_question` | low | no | no (question) | How to clean (question, not a complaint) |
| `blade_replacement_due` | low | no | no (question) | Asks when to replace blades (question) |
| `storage_question` | low | no | no (question) | How to store (question) |
| `water_exposure_question` | low | no | no (question) | Asks about water or shower use (question) |

### `other_or_unclear`
Cannot be safely assigned to another category.

| Symptom | Default severity | Stop-use | Counts as complaint | Meaning |
|---|---|---|---|---|
| `unclear_description` | low | no | yes | Cannot tell what is wrong |
| `multiple_unresolved_symptoms` | low | no | yes | Several vague symptoms that cannot be assigned |

## Context fields

| Field | Allowed values |
|---|---|
| `onset` | `today`, `this_week`, `longer`, `unknown` |
| `persists_after_cleaning` | `yes`, `no`, `not_tried`, `not_applicable` |
| `during_charging` | `true`, `false`, `none` |

`persists_after_cleaning` also means "after refitting the head". It separates user or fitting errors from real defects, which the quality dashboard uses.

## Derivation rules (done in code)

- **Who decides:** Gemini returns symptoms, context and user_intent. Code derives issue_type, severity and safety_flag so they are always consistent.
- **issue_type:** Take the symptoms present. Choose the issue_type of the highest-severity symptom; break ties with issue_type_priority. Priority order: `heat_and_safety`, `shaving_head_and_fitment`, `noise_and_vibration`, `power_and_charging`, `shaving_performance`, `cleaning_and_maintenance`, `other_or_unclear`.
- **severity:**
  - severity = highest default_severity among symptoms
  - if persists_after_cleaning is yes and severity is low and issue_type is not cleaning_and_maintenance or other_or_unclear: severity = medium
  - if issue_type is shaving_head_and_fitment, symptoms include head_loose, head_wobble, head_not_fitting or blade_unit_not_seated, and persists_after_cleaning is yes: severity = high (head cannot be secured; safety guide says do not use)
  - if user_intent is ask_question: severity = low unless a safety symptom is present
- **safety_flag:** true when severity is high (stop-use conditions from 03_safety_escalation.md)
- **Heat wording:** Set excessive_heat only when the user says hot, too hot or burning. 'Warm' alone is normal per 04_operating_specs.md; ask one follow-up instead.

## Confidence

- Below **0.6**: ask one follow-up question before building the record.
- Below **0.4** after the follow-up: use `other_or_unclear`. Do not guess.

## RAG retrieval

- **filters:** product_model plus issue_type of the derived primary issue, plus any chunk that lists one of the symptoms
- **when severity high:** always also retrieve every chunk with document_type safety_escalation
- **when other or unclear:** retrieve the general service chunks and ask one clarifying question

## Extraction rules for Gemini

1. Return only symptoms from the list. Never invent symptoms.
2. Select every symptom the user states or the evidence clearly shows.
3. Use `increased_noise` only when no specific sound is named; otherwise use the specific sound symptom.
4. Set `user_intent` to `ask_question` when the user only asks how to do something.
5. Use `other_or_unclear` symptoms when evidence is insufficient.
6. Do not diagnose internal faults. A possible cause appears only in the later grounded answer, and only if a retrieved source supports it.

## Scope

Small on purpose for the hackathon. Do not add categories until the consumer-to-quality-signal demo works end to end.
