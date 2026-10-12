import json
tax=json.load(open('taxonomy_v2.json')); SYM=tax['symptoms']; PRI=tax['derivation_rules']['issue_type_priority']; R={'low':0,'medium':1,'high':2}
kb={c['chunk_id'] for c in json.load(open('x500_rag_knowledge_base_v2.json'))['chunks']}
def derive(syms,pers):
    top=max(R[SYM[s]['default_severity']] for s in syms); sev=[k for k,v in R.items() if v==top][0]
    issue=min([SYM[s]['issue_type'] for s in syms if R[SYM[s]['default_severity']]==top],key=PRI.index)
    if sev=='low' and pers=='yes' and issue not in ('cleaning_and_maintenance','other_or_unclear'): sev='medium'
    return issue,sev,sev=='high'
T=[
 ("audio1_rattling_grinding.m4a","audio","noise_and_vibration","This is the sound my X500 makes now.","Synthesised rattle with grinding texture, 8 s.",
  ["rattling_sound"],["grinding_sound","buzzing_sound"],["increased_noise","excessive_heat","burning_smell","head_detached"],"not_tried",False,
  ["x500_trb_noise_steps","x500_man_fit_steps"],"Only symptoms the sound supports. No vibration or heat claims. A specific sound is named, so increased_noise must be absent."),
 ("audio2_spoken_burnt_smell.m4a","audio","heat_and_safety","(no typed message; voice only)","Spoken (Indian English): burnt smell while charging last night, unplugged straight away, not used since. Transcript is in the recording script.",
  ["burning_smell"],[],["sparking","excessive_heat","electrical_crackling"],"not_applicable",True,
  ["x500_saf_stop_heat","x500_trb_heat_escalate"],"Must trigger the stop-use response: stop using, do not charge, contact service. No troubleshooting steps offered. Expected onset: this_week."),
 ("video1_loose_head_wobble.mp4","video","shaving_head_and_fitment","The shaving head feels loose when I switch it on.","Portrait phone-style clip made from a real product photo (brand removed): the head wobbles from 1.5 s with a rattling sound. Motion is synthetic.",
  ["head_wobble"],["head_loose","rattling_sound","increased_vibration"],["head_detached","lock_ring_damaged","head_joint_damage","visible_damage"],"not_tried",False,
  ["x500_trb_fit_steps","x500_man_fit_steps"],"The head stays attached, so head_detached must not appear. Should ask one follow-up: did you clean and refit the head?"),
 ("video2_charging_led_off.mp4","video","power_and_charging","I plugged it in for an hour and the light never came on. It does not charge.","Portrait phone-style clip made from a real product photo (brand removed): a cable is plugged into the base and the status lights stay off. Motion is synthetic.",
  ["led_not_working","not_charging"],[],["burning_smell","excessive_heat","water_ingress","not_powering_on"],"not_applicable",True,
  ["x500_trb_power_steps","x500_man_led"],"Nothing in the clip suggests heat, smell or liquid, so none of those may appear."),
 ("image1_hair_buildup_under_head.jpg","image","cleaning_and_maintenance","Hair keeps getting stuck in the head and it is hard to clean.","Real product photo (brand removed) with stray hair edited onto the cutting foils.",
  ["hair_buildup","difficult_to_clean"],[],["visible_damage","head_joint_damage"],"not_tried",False,
  ["x500_man_cleaning","x500_man_clean_freq"],"user_intent is report_problem. Low severity. No safety language."),
 ("image2_worn_blade_surface.jpg","image","shaving_performance","It pulls my beard and the blades look worn.","Real product photo (brand removed) with the foils edited to look dull, scratched and pitted.",
  ["pulling_hair"],["reduced_cutting_quality","blade_drag"],["visible_damage","head_joint_damage","exposed_component"],"not_tried",False,
  ["x500_trb_cutting_steps","x500_man_blades"],"Normal blade wear is not a safety issue, so visible_damage must not appear (the stop-use damage rule is for cracked casing, joint or exposed parts)."),
 ("video3_head_detaches.mp4","video","shaving_head_and_fitment","The shaving head came off while it was running.","Portrait phone-style clip made from a real product photo (brand removed): the head wobbles more and more after switch-on, then comes off and is thrown to the right, leaving the shaft sleeve exposed. A clack is heard at the moment it comes off. Motion is synthetic.",
  ["head_detached"],["head_wobble","head_loose","head_not_fitting","rattling_sound","increased_vibration","increased_noise"],["burning_smell","sparking","water_ingress","excessive_heat"],"not_tried",False,
  ["x500_saf_stop_damage","x500_trb_fit_escalate"],"A head that comes off is a stop-use condition: high severity and safety flag true, and the app must show the stop-use screen, with no troubleshooting steps."),
 ("image3_cracked_casing.jpg","image","heat_and_safety","The casing has cracked near the power button.","Real product photo (brand removed) with a branching crack drawn across the casing above the power button.",
  ["visible_damage"],["head_joint_damage"],["burning_smell","sparking","water_ingress","excessive_heat"],"not_applicable",False,
  ["x500_saf_stop_damage"],"A cracked casing is a stop-use condition (high severity, safety flag true). Nothing in the image suggests heat, smell or liquid, so none of those may appear."),
]
cases=[]
for f,kind,cat,msg,desc,must,may,mnot,pers,chg,chunks,note in T:
    assert all(s in SYM for s in must+may+mnot); assert all(c in kb for c in chunks),chunks
    issue,sev,safe=derive(must,pers); assert issue==cat,(f,issue)
    cases.append({"file":f,"kind":kind,"message_to_send":msg,"description":desc,"user_intent":"report_problem",
      "expected":{"must_have_symptoms":must,"may_have_symptoms":may,"must_not_have_symptoms":mnot,
                  "context":{"persists_after_cleaning":pers,"during_charging":chg},
                  "derived":{"issue_type":issue,"severity":sev,"safety_flag":safe}},
      "expected_chunks_retrieved":chunks,"notes":note})
json.dump({"purpose":"Answer key for the six generated test inputs, one per category family. Compare Gemini output to must_have / may_have / must_not_have.",
 "covers":sorted({c['expected']['derived']['issue_type'] for c in cases}),"cases":cases},open('test_media/answer_key.json','w'),indent=1)
print("cases:",[(c['file'].split('_')[0],c['expected']['derived']['issue_type'],c['expected']['derived']['severity']) for c in cases])
