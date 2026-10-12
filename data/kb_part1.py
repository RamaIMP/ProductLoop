def ch(i,src,sec,doc,issues,syms,sev,content,safety=False):
    return {"chunk_id":i,"product_model":"X500","source_file":src,"section":sec,"document_type":doc,
            "issue_types":issues,"symptoms":syms,"severity_applicability":sev,"safety_critical":safety,
            "title":sec,"content":content}
N,P,C,F,H,M,O,G='noise_and_vibration','shaving_performance','power_and_charging','shaving_head_and_fitment','heat_and_safety','cleaning_and_maintenance','other_or_unclear','general'
LM,LMH,MH=["low","medium"],["low","medium","high"],["medium","high"]
MAN,TRB="01_product_manual.md","02_troubleshooting_guide.md"
P1=[
 ch("x500_man_overview",MAN,"Overview and parts","product_manual",[G,O],[],LMH,
  "The X500 is a rotary electric shaver for daily dry and wet shaving. It has a triple-blade rotary head, a lithium-ion battery and a quick-release head for cleaning. Parts: shaving head (three rotary blades on a flexible joint), head lock ring (twist-lock that secures the head to the body), USB-C charging port on the base, power button (press once to start, hold 3 seconds to power off)."),
 ch("x500_man_led",MAN,"LED indicator","product_manual",[C],["led_not_working"],LM,
  "LED indicator: green means charged, amber means charging, red means low battery. The red LED comes on at about 10 minutes of shaving time remaining."),
 ch("x500_man_fit_steps",MAN,"Fitting the shaving head","product_manual",[F,N],["head_loose","head_not_fitting","head_wobble","blade_unit_not_seated","rattling_sound"],LM,
  "To fit the head: (1) align the head with the motor shaft, with the notch on the head facing the front; (2) press the head down firmly until you hear a click; (3) twist the lock ring clockwise until it stops; (4) gently pull the head upward to confirm it is secured. It should not lift or wobble."),
 ch("x500_man_fit_warning",MAN,"Loose head effects","product_manual",[F,N],["rattling_sound","increased_vibration","increased_noise","head_wobble"],LMH,
  "A head that is not fully locked will rattle, vibrate abnormally and produce increased noise during use. Always confirm the click before operating the shaver."),
 ch("x500_man_cleaning",MAN,"Cleaning the shaving head","product_manual",[M,N,P],["hair_buildup","difficult_to_clean","increased_noise","reduced_cutting_quality","cleaning_question"],LM,
  "To clean: (1) press the head-release button on the side of the body; (2) lift the head off and separate the three blade units; (3) rinse each blade unit under warm running water for 10 seconds; (4) shake off excess water and do not wipe the blades with a towel, as this blunts the cutting edges; (5) air dry completely before reassembling, at least 30 minutes; (6) refit the head and confirm the lock click before the next use."),
 ch("x500_man_clean_freq",MAN,"Cleaning frequency","product_manual",[M],["cleaning_question","hair_buildup"],["low"],
  "Clean the shaving head after every 3 to 4 uses, or sooner if you notice reduced cutting efficiency."),
 ch("x500_man_charging",MAN,"Charging","product_manual",[C],["not_charging","slow_charging","battery_drains_fast"],LM,
  "Use only the supplied USB-C cable and a 5V/1A charger. A full charge takes about 60 minutes and gives up to 45 minutes of shaving time. Do not use the shaver while charging. If storing for more than 2 weeks, keep at least 40% charge."),
 ch("x500_man_storage",MAN,"Storage","product_manual",[M],["storage_question","water_exposure_question"],["low"],
  "Store in the supplied travel case or an open, dry place. Do not expose to temperatures above 45 C or below 0 C. Keep the shaver away from water when not in use, because prolonged water exposure degrades the seals."),
 ch("x500_man_blades",MAN,"Blade replacement","product_manual",[M,P],["blade_replacement_due","pulling_hair","reduced_cutting_quality","blade_drag"],LM,
  "Replace blades every 12 to 18 months under daily use. Worn blades cause reduced cutting performance, more pulling and higher operating noise."),
]
def trb(sym,sec,causes,steps,esc,issues,syms,heat_note=False):
    return [
     ch(f"x500_trb_{sym}_steps",TRB,f"{sec}: causes and steps","troubleshooting_guide",issues,syms,LM,
        f"Most likely causes, in order: {causes} Steps to try: {steps}"),
     ch(f"x500_trb_{sym}_escalate",TRB,f"{sec}: when to contact service","troubleshooting_guide",issues,syms,MH,
        f"Contact an authorised service centre if: {esc}")]
P1+=trb("noise","Increased operating noise",
 "(1) shaving head not fully locked, so a loose head vibrates against the motor shaft; (2) hair and debris under the blade units, causing friction; (3) worn or damaged blade unit, as blades past service life produce grinding sounds; (4) low battery, where the motor runs at lower voltage and unevenly; (5) internal motor bearing wear, which needs service.",
 "(1) Press the release button, lift off the head and check for hair buildup around the blade housings. (2) Clean all three blade units under warm running water and shake dry. (3) Refit the head with the notch aligned and the lock ring clicking firmly. (4) Charge fully for 60 minutes and retest. (5) If noise persists, listen carefully: a steady hum is normal, but grinding, rattling or a high-pitched squeal after cleaning and recharging points to blade wear or internal damage.",
 "noise continues after cleaning and a full recharge, noise comes with heat, or the sound is grinding or squealing rather than a change in hum pitch.",
 [N],["increased_noise","rattling_sound","grinding_sound","squealing_sound","buzzing_sound"])
P1+=trb("vibration","Increased vibration",
 "(1) shaving head not fully locked, the most common cause; (2) debris under the blade units creating imbalance; (3) worn blade unit with uneven wear; (4) damaged head joint, where the flexible joint may be cracked; (5) motor imbalance, which needs service.",
 "(1) Power off. (2) Remove the head completely and inspect the head joint, the rubber-edged pivot on the body, for cracks or deformation. (3) Clean the blade units and the inside of the head casing. (4) Refit firmly and confirm the lock click. (5) If the joint looks cracked or flattened, do not continue using the shaver. (6) If the joint is intact and vibration continues after refitting, contact service.",
 "vibration is severe, the head joint is visibly damaged, or vibration comes with noise changes or heat.",
 [N],["increased_vibration","irregular_vibration","head_joint_damage"])
P1+=trb("battery","Battery draining too quickly",
 "(1) aged battery, as lithium-ion batteries lose capacity after 300 to 500 charge cycles; (2) incomplete charging from a cable or charger that does not supply the correct voltage; (3) device left on accidentally; (4) storage at extreme temperature, where heat degrades capacity.",
 "(1) Charge fully with the original USB-C cable and a 5V/1A source; avoid laptop USB ports, which may supply only 0.5A. (2) Confirm the LED turns green during and after charging. (3) Do one full discharge and recharge: use until the red LED comes on, then charge for 60 minutes. (4) If the device has been in daily use for more than 2 years, battery degradation is expected.",
 "the charge lasts fewer than 20 minutes after a confirmed full charge, or the device is less than 12 months old.",
 [C],["battery_drains_fast","slow_charging","not_charging"])
P1+=trb("fit","Shaving head does not fit or feels loose",
 "(1) incorrect alignment, with the notch not facing the front; (2) hair debris in the head socket preventing full seating; (3) damaged lock ring, stripped or cracked so it cannot engage; (4) bent or worn motor shaft, so the head cannot seat flush.",
 "(1) Remove the head fully. (2) Inspect the head socket for hair, debris or foreign material and clean with a dry brush. (3) Refit with the notch facing the front, press down firmly and twist the lock ring fully clockwise. (4) Test by pulling gently upward: if the head lifts without pressing the release button, the fit is incomplete, so repeat step 3. (5) Inspect the lock ring for cracks or stripped threads.",
 "the lock ring appears damaged, or the head cannot be made to click into place after thorough cleaning and several attempts. Do not use the shaver with an unsecured head.",
 [F],["head_loose","head_not_fitting","head_wobble","blade_unit_not_seated","lock_ring_damaged"])
# heat: safety document wins on cool-down time and charging temperature
P1+=trb("heat","Device overheating during use",
 "(1) extended continuous use, as the device should not run for more than 10 minutes at a time; (2) motor working harder because of dirty or worn blades; (3) charging when the ambient temperature is above 40 C; (4) internal fault in the motor or circuit board.",
 "(1) Power off immediately and let the device cool for at least 5 minutes. (2) Do not use for more than 10 minutes in a single session. (3) Clean the blades, because dirty blades raise motor load and heat. (4) Do not charge in direct sunlight or a hot environment; do not charge above 40 C or below 5 C.",
 "the device becomes hot to the touch, not just warm, within 2 to 3 minutes of use, or the heat comes with a burning smell. Stop using it and do not charge it.",
 [H],["excessive_heat","burning_smell"])
# power on: safety document wins on moisture (stop use, no drying step)
P1+=trb("power","Device does not power on",
 "(1) battery completely discharged; (2) charging cable or port fault; (3) liquid in the charging port; (4) internal fault.",
 "(1) Connect to a charger, wait 5 minutes and try again. (2) Try a different USB-C cable and charger. (3) Inspect the charging port for debris. If you see moisture or liquid, stop using the shaver, do not charge it and contact an authorised service centre. (4) If the LED does not light at all during charging, the charging circuit may be faulty.",
 "the device shows no LED response after 30 minutes on a known-good charger, or there is liquid in the charging port or body.",
 [C,H],["not_powering_on","not_charging","led_not_working","water_ingress"])
P1+=trb("cutting","Reduced cutting quality or pulling",
 "(1) blades past service life, to be replaced after 12 to 18 months; (2) blade units not cleaned, as hair buildup dulls cutting; (3) shaving technique, as circular motion works best with rotary shavers.",
 "(1) Clean all blade units thoroughly. (2) Check the blade replacement date and inspect the blade surface for dulling or uneven wear. (3) Replace blade units if they are more than 12 months old under daily use.",
 "pulling and discomfort continue with new blades.",
 [P],["reduced_cutting_quality","missed_hairs","requires_multiple_passes","pulling_hair","uneven_shave","blade_drag"])
