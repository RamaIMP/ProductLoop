# ProductLoop X500 data v2

All data is fictional. Source of truth for product content: `../Data_synthetic/*.md` (unchanged). Where those files disagree, `03_safety_escalation.md` wins (see `kb_conflicts_log.md`).

| File | What it is |
|---|---|
| `taxonomy_v2.json` / `.md` | Controlled vocabulary: 7 issue types, 41 global symptoms, context fields, derivation rules for issue type, severity and safety flag |
| `x500_rag_knowledge_base_v2.json` | 41 RAG chunks built from the five markdown files, tagged with issue types, symptoms, severity and source section |
| `kb_conflicts_log.md` | The 8 conflicts between the source files and how each was resolved |
| `x500_complaints_v2.json` / `.csv` | 111 rows (102 complaints, 9 questions) over 60 days, with labels derived from the taxonomy |
| `batches.json` | 7 batches with units shipped for India and UK |
| `test_media/` | 8 test files, `answer_key.json`, `recording_script.md`, `source/` (brand-free base photo and mask) |

## The demo data (not tied to one category)
Windows: prior 8 Aug to 6 Sep, current 7 Sep to 6 Oct 2026.

| Category | Prior | Current | Change | State |
|---|---|---|---|---|
| noise_and_vibration | 9 | 27 | +200% | rising (78% from B-2026-07-A, 8.8x its share of units) |
| shaving_head_and_fitment | 4 | 11 | +175% | rising (82% from B-2026-06-C, 5.8x) |
| heat_and_safety | 2 | 7 | +250% | rising, every event is safety-flagged (71% from B-2026-05-B, 6.6x) |
| shaving_performance | 8 | 7 | -12% | stable |
| power_and_charging | 6 | 7 | +17% | stable |
| cleaning_and_maintenance | 4 | 5 | +25% | stable |
| other_or_unclear | 2 | 3 | +50% | tiny |

The nine questions (`user_intent: ask_question`) are excluded from the counts.

## Notes
- The 15 original complaints keep their IDs, dates, batches and v1 severities. Symptom names were remapped to v2. **C006:** "gets warm" became "gets hot" so it follows the new heat wording rule. **C003:** "loud buzzing" is deliberately ambiguous (mechanical or electrical), a test of the follow-up rule.
- Severity and `safety_flag` are derived by code, never chosen by Gemini. `from_original_dataset` marks the 15.
- Small categories can show a batch concentration by chance (for example 3 of 7). Require a minimum count before flagging one.
- Media links in the complaints are placeholders (`gs://productloop-evidence/...`); only the six files in `test_media/` exist.
- **Test media:** audio is synthesised or text-to-speech. Images and videos are edited from one real product photo (brand name removed, 300 px wide, so they look soft). Hair, wear, wobble, cable and camera shake are synthetic. Keep them internal: the source photo is third-party. Real recordings (`test_media/recording_script.md`) are a more honest test.

## Rebuild
`python3 build_kb.py` · `python3 generate_dataset.py` · `python3 validate_dataset.py` · `python3 make_answer_key.py` · `cd test_media && python3 make_real_images.py && python3 make_real_videos.py` (needs ffmpeg)
