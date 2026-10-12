# Knowledge base v2: conflicts resolved

Rule you chose: **when the Data_synthetic files disagree, `03_safety_escalation.md` wins.** The source files in `Data_synthetic/` are unchanged. Only the v2 chunks use the resolved values.

| # | Topic | What the files said | Value used in v2 | Chunk |
|---|---|---|---|---|
| 1 | Cool-down after overheating | 02 troubleshooting: cool for 15 minutes. 03 safety: cool for 5 minutes. | **5 minutes** (03) | `x500_trb_heat_steps`, `x500_saf_use_limits` |
| 2 | Charging temperature | 02 troubleshooting: ambient above 35 C is a cause. 03 safety: do not charge above 40 C or below 5 C. | **40 C upper, 5 C lower** (03) | `x500_trb_heat_steps`, `x500_saf_use_limits` |
| 3 | Liquid in the charging port | 02 troubleshooting: if damp, let it dry for 2 hours. 03 safety: water in the port or casing is a stop-use condition. | **Stop using, do not charge, contact service.** The drying step is removed. | `x500_trb_power_steps`, `x500_saf_stop_damage` |
| 4 | Water and shower use | 01 manual: wet shaving supported but keep away from water when stored. 03 safety: "shower use is permitted with the head attached and port sealed" and also "do not use near open water". | **Shower use allowed with head attached and port sealed. Avoid open water. Keep dry when stored.** | `x500_saf_use_limits`, `x500_man_storage` |
| 5 | Grinding noise | 02 troubleshooting: grinding after cleaning points to blade wear, contact service. 03 safety: grinding with resistance means stop use (jammed motor). | **Two symptoms:** `grinding_sound` (medium, contact service if it persists) and `grinding_with_resistance` (high, stop use). | `x500_trb_noise_escalate`, `x500_saf_stop_sounds` |
| 6 | Buzzing | 02 troubleshooting: steady hum is normal. 03 safety: electrical buzzing, crackling or popping is a stop-use condition. | **Mechanical buzzing** is `buzzing_sound` (low). **Electrical** crackling or popping is `electrical_crackling` (high). | `x500_spec_sound`, `x500_saf_stop_sounds` |
| 7 | Head that cannot be secured | 02 troubleshooting: escalate if the head will not click after several attempts. 03 safety: do not use if the head cannot be secured. | **Not usable.** A fitment complaint where the problem persists after refitting is derived as high severity. | `x500_trb_fit_escalate`, `x500_saf_stop_damage` |
| 8 | "Warm" vs "hot" | 04 specs: slightly warm (30-38 C) is normal; above about 45 C is abnormal. 03 safety: beyond mild warmth within 3 minutes is stop-use. | `excessive_heat` only for "hot". "Warm" alone triggers a follow-up question. | `x500_spec_temperature`, taxonomy `heat_wording` |

## Not conflicts, but worth knowing
- Cleaning uses water per the manual (rinse under warm water, air dry 30 minutes). The socket is cleaned with a dry brush per the troubleshooting guide.
- 02 troubleshooting says to use no more than 10 minutes in one session. 03 safety says the same, so the value is consistent.
- Sections of `04_operating_specs.md` are tagged as reference chunks (`operating_specs`) so the answer can say what is normal.
