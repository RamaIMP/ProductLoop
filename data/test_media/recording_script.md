# Recording script: real versions of the six test inputs

The files in this folder are stand-ins: synthesised sound, plus images and clips edited from a real product photo with the brand removed (hair, wear and motion are synthetic). They test the pipeline, but Gemini will read real recordings more honestly. Record these on a phone, name them like the generated files, and use the same typed message (see `answer_key.json`).

**Safety first.** Do not create a real burnt smell, spark or fluid leak, and never run the shaver with the head removed or loose near your skin. Where a hazard is the subject (audio 2), read the script instead. Keep faces and names out of every clip.

| # | File | What to record | Length | Typed message |
|---|---|---|---|---|
| 1 | `audio1_rattling_grinding` | Hold the phone 30 cm from a running shaver. Best: a shaver with a slightly loose head or worn blades. Otherwise tap a coin inside a plastic cup next to the running shaver to mimic a rattle. Quiet room, no music. | 8 to 10 s | "This is the sound my X500 makes now." |
| 2 | `audio2_spoken_burnt_smell` | Read this aloud in your normal voice: "Hello. I have the X five hundred shaver. Last night while I was charging it, there was a burnt smell, so I unplugged it straight away. I have not used it since." | about 11 s | none (voice only) |
| 3 | `video1_loose_head_wobble` | Film the shaver head from the front. With the shaver OFF, gently loosen the head so it wiggles when you push it, show it, then switch on a spare shaver briefly with the head sitting loosely. Do not hold it near your face. | 8 s | "The shaving head feels loose when I switch it on." |
| 4 | `video2_charging_led_off` | Film a shaver (any model) with the charging LED visible. Plug in the cable, show the LED stays dark, then show a clock or timer 30 to 60 minutes later with the LED still dark. Cover the LED with a bit of tape if it lights. | 8 to 10 s | "I plugged it in for an hour and the light never came on. It does not charge." |
| 5 | `image1_hair_buildup_under_head` | Remove the head, put it on a plain background in good light, and photograph the underside after a few days of use without cleaning. | 1 photo | "Hair keeps getting stuck in the head and it is hard to clean." |
| 6 | `image2_worn_blade_surface` | Close-up of an old, dull blade foil from the cutting side, in raking light so scratches show. | 1 photo | "It pulls my beard and the blades look worn." |

## Why these six
One test input per category family, so no category dominates:
noise and vibration (1), heat and safety (2), head and fitment (3), power and charging (4), cleaning and maintenance (5), shaving performance (6).

## Things to check after each run
- Gemini returns only symptoms from `taxonomy_v2.json`.
- Every `must_have_symptoms` item is present and no `must_not_have_symptoms` item appears.
- The code-derived `issue_type`, `severity` and `safety_flag` match the answer key.
- Audio 2 gives the stop-use response and no troubleshooting steps.
- The retrieved chunks include those under `expected_chunks_retrieved`.
