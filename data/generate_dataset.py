"""Builds batches.json and x500_complaints_v2.json/.csv. All data is fictional. Seed fixed for reproducibility."""
import json, random, csv, datetime as D
rng = random.Random(42)
TAX = json.load(open('taxonomy_v2.json'))
SYM = TAX['symptoms']; PRI = TAX['derivation_rules']['issue_type_priority']
RANK = {'low':0,'medium':1,'high':2}
N,P,C,F,H,M,O='noise_and_vibration','shaving_performance','power_and_charging','shaving_head_and_fitment','heat_and_safety','cleaning_and_maintenance','other_or_unclear'

# ---------- batches
BATCHES = [  # id, produced, ship_start, india, uk
 ("B-2026-03-A","2026-03",D.date(2026,4,1),11000,2000),("B-2026-04-A","2026-04",D.date(2026,5,1),12000,2500),
 ("B-2026-05-B","2026-05",D.date(2026,6,1),5500,1000),("B-2026-06-C","2026-06",D.date(2026,7,1),7000,1500),
 ("B-2026-06-D","2026-06",D.date(2026,7,15),6000,1500),("B-2026-07-A","2026-07",D.date(2026,8,10),4500,800),
 ("B-2026-08-A","2026-08",D.date(2026,9,5),4000,700)]
json.dump({"dataset_name":"ProductLoop X500 synthetic batches","disclaimer":"Fictional.","batches":[
 {"batch_id":b,"production_month":m,"ship_start":s.isoformat(),"units_shipped_india":i,"units_shipped_uk":u,"units_shipped_total":i+u} for b,m,s,i,u in BATCHES]},
 open('batches.json','w'),indent=1)
SHIP = {b:(s,i,u) for b,m,s,i,u in BATCHES}

# ---------- derivation (mirrors taxonomy_v2.json derivation_rules)
def derive(symptoms, ctx, intent):
    sev = max((SYM[s]['default_severity'] for s in symptoms), key=RANK.get)
    top = max(RANK[SYM[s]['default_severity']] for s in symptoms)
    cands = [SYM[s]['issue_type'] for s in symptoms if RANK[SYM[s]['default_severity']]==top]
    issue = min(cands, key=PRI.index)
    safety_sym = any(SYM[s]['safety'] for s in symptoms)
    if sev=='low' and ctx['persists_after_cleaning']=='yes' and issue not in (M,O): sev='medium'
    if issue==F and ctx['persists_after_cleaning']=='yes' and set(symptoms)&{'head_loose','head_wobble','head_not_fitting','blade_unit_not_seated'}: sev='high'
    if intent=='ask_question' and not safety_sym: sev='low'
    return issue, sev, sev=='high'

# ---------- text
PH = {
 'increased_noise':["it has become much louder","the noise is more than before","it is making a loud sound now"],
 'buzzing_sound':["there is a loud buzzing sound now","a strange buzzing while shaving"],
 'rattling_sound':["it rattles when I switch it on","a rattling sound comes from the head","something rattles while it runs"],
 'grinding_sound':["it makes a grinding sound","harsh grinding noise while shaving"],
 'grinding_with_resistance':["it grinds and struggles like the motor is stuck"],
 'squealing_sound':["a high pitched squeal at start","it squeals when I turn it on"],
 'increased_vibration':["it vibrates much more than before","the vibration in my hand is strong now","it shakes a lot while running"],
 'irregular_vibration':["the vibration is uneven and jerky"],
 'reduced_cutting_quality':["the shave is not as close as before","it is not cutting well anymore"],
 'missed_hairs':["it leaves many hairs behind","it misses patches on my cheeks"],
 'requires_multiple_passes':["I need to go over the same area three times","it takes many passes now"],
 'uneven_shave':["the shave is uneven around my jaw"],
 'pulling_hair':["it pulls my beard","it tugs hair instead of cutting"],
 'blade_drag':["the blades drag on my skin"],
 'not_powering_on':["it does not turn on at all","it will not start even after charging"],
 'not_charging':["it does not charge anymore","it stopped charging though the cable looks fine"],
 'slow_charging':["it takes very long to charge"],
 'battery_drains_fast':["the battery is empty very quickly","it dies after ten minutes"],
 'led_not_working':["the charging light does not come on"],
 'head_loose':["the shaving head has become loose","the top part keeps coming loose"],
 'head_not_fitting':["the head does not click into place","the head will not lock back"],
 'head_wobble':["the head wobbles while it runs"],
 'blade_unit_not_seated':["one blade unit does not sit flat"],
 'head_detached':["the head came off while it was running"],
 'lock_ring_damaged':["the lock ring looks cracked"],
 'head_joint_damage':["the rubber joint under the head is cracked"],
 'excessive_heat':["it gets very hot after two minutes","it is too hot to hold"],
 'burning_smell':["there is a burnt smell"],
 'sparking':["I saw a spark near the charging port"],
 'electrical_crackling':["it makes a crackling, popping sound"],
 'visible_damage':["the casing has a crack"],
 'water_ingress':["water got into the charging port"],
 'exposed_component':["I can see an internal part through a gap"],
 'hair_buildup':["hair keeps getting trapped under the head"],
 'difficult_to_clean':["it is hard to clean properly"],
 'cleaning_question':["how do I clean the blades properly?"],
 'blade_replacement_due':["how often should I replace the blades?"],
 'storage_question':["how should I store it when I travel?"],
 'water_exposure_question':["can I use it in the shower?"],
 'unclear_description':["something feels wrong with it","it is not working right"],
 'multiple_unresolved_symptoms':["several things feel off but I cannot say what"]}
HG = {'increased_noise':"bahut awaaz kar raha hai",'increased_vibration':"bahut vibrate kar raha hai",'not_charging':"charge nahi ho raha",
      'battery_drains_fast':"battery jaldi khatam ho jaati hai",'head_loose':"head dheela ho gaya hai",'burning_smell':"jalne ki smell aa rahi hai",'pulling_hair':"daadhi kheench raha hai",
      'head_not_fitting':"head lock nahi ho raha",'rattling_sound':"khad khad awaaz aa rahi hai",'excessive_heat':"bahut zyada garam ho jaata hai",'missed_hairs':"baal reh jaate hain",'sparking':"chingari dikhi"}
ONSET = {'today':"It started today.",'this_week':"It started this week.",'longer':"It has been like this for a few weeks.",'unknown':""}
PERS = {'yes':"I cleaned and refitted the head but it is still the same.",'no':"It got better after I cleaned it.",'not_tried':"",'not_applicable':""}
def make_text(symptoms, ctx, hinglish):
    if hinglish and all(s in HG for s in symptoms):
        t = " aur ".join(HG[s] for s in symptoms if s in HG)
        t = "Mera X500: "+t
        if ctx['persists_after_cleaning']=='yes': t += ", clean kiya phir bhi same hai"
        return t+"."
    ph = [rng.choice(PH[s]) for s in symptoms]
    t = " and ".join(ph); t = t[0].upper()+t[1:]
    t = t + ("." if not t.endswith("?") else "")
    if ctx['during_charging'] and set(symptoms) & {"burning_smell","sparking","excessive_heat","electrical_crackling"}: t += " This happens while charging."
    for extra in (ONSET[ctx['onset']], PERS[ctx['persists_after_cleaning']]):
        if extra: t += " "+extra
    return t.strip()

# ---------- random helpers
def pick_w(pairs): 
    r = rng.random()*sum(w for _,w in pairs); a=0
    for v,w in pairs:
        a+=w
        if r<=a: return v
    return pairs[-1][0]
def spread(n, start, end):
    days=(end-start).days+1
    return sorted(start+D.timedelta(days=int(i*days/n + rng.random()*days/n)) for i in range(n))
def week(k):  # current window weeks
    s=D.date(2026,9,7)+D.timedelta(days=7*k); return s, min(s+D.timedelta(days=6), D.date(2026,10,6))
PRIOR=(D.date(2026,8,8),D.date(2026,9,6)); CUR=(D.date(2026,9,7),D.date(2026,10,6))
def bg_batch(d, exclude=()):
    ok=[(b,SHIP[b][1]) for b in SHIP if d>=SHIP[b][0]+D.timedelta(days=10) and b not in exclude and b not in ("B-2026-07-A","B-2026-08-A") or
        (b in ("B-2026-07-A","B-2026-08-A") and b not in exclude and d>=SHIP[b][0]+D.timedelta(days=25))]
    return pick_w(ok)

# ---------- symptom + context pickers per category
def pick_symptoms(cat):
    if cat==N:
        out=set()
        for s,w in [('increased_noise',35),('increased_vibration',45),('rattling_sound',25),('grinding_sound',12),('buzzing_sound',10),('squealing_sound',5),('irregular_vibration',8)]:
            if rng.random()<w/100: out.add(s)
        if not out: out={'increased_vibration'}
        if out & {'rattling_sound','grinding_sound','buzzing_sound','squealing_sound'}: out.discard('increased_noise')
        return sorted(out)[:3]
    if cat==F: return [pick_w([('head_loose',35),('head_not_fitting',30),('head_wobble',25),('blade_unit_not_seated',5),('lock_ring_damaged',5)])] + ([] if rng.random()<.6 else [pick_w([('head_not_fitting',1),('head_wobble',1)])])
    if cat==P: return sorted(set(rng.sample(['reduced_cutting_quality','missed_hairs','requires_multiple_passes','uneven_shave','pulling_hair','blade_drag'],rng.choice([1,2]))))
    if cat==C: return [pick_w([('battery_drains_fast',35),('not_charging',25),('not_powering_on',15),('slow_charging',15),('led_not_working',10)])]
    if cat==M: return sorted(set(rng.sample(['hair_buildup','difficult_to_clean'],rng.choice([1,2]))))
    if cat==O: return [pick_w([('unclear_description',70),('multiple_unresolved_symptoms',30)])]
CTXW = {N:[('yes',75),('no',10),('not_tried',15)], F:[('yes',35),('no',40),('not_tried',25)],
        P:[('yes',30),('no',25),('not_tried',45)], C:[('not_applicable',100)], M:[('no',40),('not_tried',60)], O:[('not_tried',100)], H:[('not_applicable',100)]}
def pick_ctx(cat, d, heat_charge=False):
    p = pick_w(CTXW[cat])
    onset = pick_w([('today',15),('this_week',45),('longer',30),('unknown',10)])
    return {"onset":onset,"persists_after_cleaning":p,"during_charging":True if heat_charge else (False if cat in (C,H) and not heat_charge and cat==H else (None if cat in (C,O) else False))}

# ---------- existing 15 complaints, remapped to taxonomy v2
def E(i,date,hm,reg,inp,txt,syms,onset,pers,chg,conf,batch):
    return dict(complaint_id=i, ts=f"{date}T{hm}:00Z", region=reg, input_type=inp, raw=txt, symptoms=syms,
                ctx={"onset":onset,"persists_after_cleaning":pers,"during_charging":chg}, confidence=conf, batch=batch, intent='report_problem', lang='en', original=True)
EXIST=[
 E("C001","2026-09-02","09:15","India",["text"],"My X500 is slightly louder than before but it still shaves normally.",["increased_noise"],"unknown","not_tried",False,0.89,"B-2026-07-A"),
 E("C002","2026-09-04","13:20","India",["text","video"],"The shaver has started vibrating much more and makes a rattling sound when I use it.",["increased_vibration","rattling_sound"],"unknown","not_tried",False,0.94,"B-2026-07-A"),
 E("C003","2026-09-08","11:45","India",["voice"],"There is a loud buzzing sound now and the head feels shaky.",["buzzing_sound","increased_vibration"],"unknown","not_tried",False,0.91,"B-2026-07-A"),
 E("C004","2026-09-14","16:05","India",["text","audio"],"The sound is harsh and I can feel strong vibration in my hand even after cleaning it.",["grinding_sound","increased_vibration"],"unknown","yes",False,0.93,"B-2026-07-A"),
 E("C005","2026-09-21","08:30","India",["video"],"The device rattles for a few seconds after I switch it on. I cleaned the head but it is still happening.",["rattling_sound"],"unknown","yes",False,0.96,"B-2026-07-A"),
 E("C006","2026-09-27","10:10","India",["text","video"],"My X500 is noisy, vibrating heavily and gets hot after a minute. I stopped using it.",["increased_noise","increased_vibration","excessive_heat"],"unknown","not_tried",False,0.97,"B-2026-07-A"),
 E("C007","2026-09-03","14:00","India",["text"],"It leaves many hairs behind even after two passes.",["missed_hairs","requires_multiple_passes"],"unknown","not_tried",None,0.88,"B-2026-06-C"),
 E("C008","2026-09-09","18:25","India",["voice"],"It is pulling my beard and shaving quality is poor.",["pulling_hair","reduced_cutting_quality"],"unknown","not_tried",None,0.90,"B-2026-06-C"),
 E("C009","2026-09-16","07:50","United Kingdom",["text"],"The shaver is not cutting evenly around my jaw.",["uneven_shave","missed_hairs"],"unknown","not_tried",None,0.84,"B-2026-06-D"),
 E("C010","2026-09-05","12:40","India",["text"],"The charging light turns on but the battery is empty very quickly.",["battery_drains_fast"],"unknown","not_applicable",False,0.90,"B-2026-05-B"),
 E("C011","2026-09-19","19:10","India",["text","photo"],"It does not charge anymore even though the cable looks fine.",["not_charging"],"unknown","not_applicable",False,0.87,"B-2026-05-B"),
 E("C012","2026-09-10","09:55","India",["text","photo"],"The shaving head has become loose and does not click into place properly.",["head_loose","head_not_fitting"],"unknown","not_tried",False,0.95,"B-2026-06-C"),
 E("C013","2026-09-24","15:35","India",["video"],"The head came off while it was running. There is no visible crack but it will not lock back now.",["head_detached","head_not_fitting"],"unknown","yes",False,0.98,"B-2026-06-C"),
 E("C014","2026-09-12","21:05","India",["voice"],"I noticed a burnt smell while charging, so I unplugged it.",["burning_smell"],"unknown","not_applicable",True,0.96,"B-2026-05-B"),
 E("C015","2026-09-29","17:20","India",["text"],"The shaver is hard to clean and hair keeps getting trapped under the head.",["hair_buildup","difficult_to_clean"],"unknown","no",False,0.86,"B-2026-06-C"),
]

# ---------- plan of new rows: (category, date, batch or None=background, intent)
PLAN=[]
def add(cat, dates, batches=None, intent='report_problem', region=None):
    for k,d in enumerate(dates):
        PLAN.append(dict(cat=cat, date=d, batch=(batches[k] if batches else None), intent=intent, region=region))
A="B-2026-07-A"; Bc="B-2026-06-C"; Bb="B-2026-05-B"
# signal 1: noise and vibration. prior 7 new, current 24 new (weekly 3,4,6,9,2)
d=D.date
add(N,[d(2026,8,10),d(2026,8,16),d(2026,8,19),d(2026,8,25),d(2026,8,24),d(2026,8,27),d(2026,9,5)],[None,None,None,A,None,None,None])
for k,(n,others) in enumerate([(3,1),(4,1),(6,1),(9,2),(2,1)]):
    s,e=week(k); ds=spread(n,s,e); bs=[A]*(n-others)+[None]*others; rng.shuffle(bs); add(N,ds,bs)
# signal 2: head fitment. prior 4 new, current 9 new (weekly 1,2,1,3,2)
add(F,[d(2026,8,14),d(2026,8,22),d(2026,8,31),d(2026,9,4)],[None,None,Bc,None])
for k,(n,others) in enumerate([(1,0),(2,1),(1,0),(3,1),(2,0)]):
    s,e=week(k); ds=spread(n,s,e); bs=[Bc]*(n-others)+[None]*others; rng.shuffle(bs); add(F,ds,bs)
# signal 3: heat and safety. prior 2 new, current 5 new
add(H,[d(2026,8,19),d(2026,9,1)],[Bb,None])
add(H,[d(2026,9,18),d(2026,9,23),d(2026,9,30),d(2026,10,2),d(2026,10,5)],[Bb,Bb,Bb,Bb,"B-2026-06-D"])
# stable categories
add(P,spread(7,*PRIOR)); add(P,spread(5,*CUR))
add(C,spread(5,*PRIOR)); add(C,spread(6,*CUR))
add(M,spread(4,*PRIOR)); add(M,spread(4,*CUR))
add(O,spread(2,*PRIOR)); add(O,spread(3,*CUR))
# questions (do not count as complaints)
add(M,spread(3,*PRIOR),intent='ask_question'); add(M,spread(6,*CUR),intent='ask_question')

HEAT_FIXED=[ # symptoms for the 7 new heat rows in plan order
 ['burning_smell'],['excessive_heat'],['burning_smell'],['excessive_heat','increased_noise'],['sparking'],['burning_smell'],['water_ingress']]
rows=[]; hi=0
PLAN.sort(key=lambda r:(r['date']))
ids=iter(range(16,1000))
for r in PLAN:
    cat=r['cat']; dte=r['date']; intent=r['intent']
    reg = r['region'] or ('United Kingdom' if (r['batch'] is None and cat not in (N,F,H) and rng.random()<0.12) else 'India')
    batch = r['batch'] or bg_batch(dte, exclude=((A,) if cat==N else (Bc,) if cat==F else (Bb,) if cat==H else ()))
    if intent=='ask_question':
        syms=[rng.choice(['cleaning_question','blade_replacement_due','storage_question','water_exposure_question'])]
        ctx={"onset":"unknown","persists_after_cleaning":"not_applicable","during_charging":None}
    elif cat==H:
        syms=HEAT_FIXED[hi]; hi+=1
        chg = 'burning_smell' in syms or 'sparking' in syms
        ctx={"onset":pick_w([('today',30),('this_week',50),('unknown',20)]),"persists_after_cleaning":"not_applicable","during_charging":chg}
    else:
        syms=pick_symptoms(cat)
        ctx=pick_ctx(cat,dte)
        if cat==O: ctx["during_charging"]=None
        if cat==C: ctx["during_charging"]=bool(set(syms)&{'not_charging','slow_charging','led_not_working'})
    media_w = {N:[(['text'],45),(['audio'],15),(['text','audio'],15),(['video'],15),(['text','video'],10)],
               F:[(['text'],40),(['text','photo'],25),(['video'],20),(['photo'],15)],
               H:[(['text'],30),(['voice'],30),(['text','photo'],20),(['video'],20)]}.get(cat,
               [(['text'],62),(['voice'],14),(['text','photo'],14),(['video'],10)])
    inp = pick_w(media_w)
    cid=f"C{next(ids):03d}"
    rows.append(dict(complaint_id=cid, ts=f"{dte.isoformat()}T{rng.randint(6,21):02d}:{rng.randint(0,59):02d}:00Z", region=reg, input_type=inp,
        raw=None, symptoms=syms, ctx=ctx, confidence=(round(rng.uniform(0.30,0.55),2) if cat==O else round(rng.uniform(0.80,0.97),2)),
        batch=batch, intent=intent, lang='hinglish' if (cat!=O and rng.random()<0.25 and all(s in HG for s in syms)) else 'en', original=False))
allrows = EXIST + rows
EXT={'audio':'m4a','voice':'m4a','video':'mp4','photo':'jpg'}
out=[]
for r in allrows:
    issue,sev,safety = derive(r['symptoms'], r['ctx'], r['intent'])
    text = r['raw'] if r['raw'] else make_text(r['symptoms'], r['ctx'], r['lang']=='hinglish')
    media=[f"gs://productloop-evidence/x500/{r['complaint_id']}.{EXT[t]}" for t in r['input_type'] if t in EXT]
    pers=r['ctx']['persists_after_cleaning']
    outcome = 'service_advised' if safety else ('helped' if pers=='no' else ('not_helped' if pers=='yes' else 'none'))
    out.append({"complaint_id":r['complaint_id'],"timestamp":r['ts'],"region":r['region'],"product_model":"X500","batch_reference":r['batch'],
        "user_intent":r['intent'],"input_type":r['input_type'],"media_uri":media,"language":r['lang'],"raw_complaint":text,
        "symptoms":r['symptoms'],"context":r['ctx'],"issue_type":issue,"severity":sev,"safety_flag":safety,"confidence":r['confidence'],
        "counts_as_complaint":r['intent']=='report_problem',"guidance_outcome":outcome,"from_original_dataset":r['original']})
out.sort(key=lambda x:x['timestamp'])
json.dump({"dataset_name":"ProductLoop X500 Synthetic Complaints v2","taxonomy_version":TAX['version'],
 "disclaimer":"Fictional. issue_type, severity and safety_flag are derived from symptoms and context using taxonomy_v2.json. Labels are the ground truth for testing Gemini extraction.",
 "windows":{"prior":["2026-08-08","2026-09-06"],"current":["2026-09-07","2026-10-06"]},"complaints":out},
 open('x500_complaints_v2.json','w'),indent=1,ensure_ascii=False)
with open('x500_complaints_v2.csv','w',newline='') as f:
    w=csv.writer(f); cols=["complaint_id","timestamp","region","product_model","batch_reference","user_intent","input_type","media_uri","language","raw_complaint","symptoms","onset","persists_after_cleaning","during_charging","issue_type","severity","safety_flag","confidence","counts_as_complaint","guidance_outcome"]
    w.writerow(cols)
    for x in out: w.writerow([x['complaint_id'],x['timestamp'],x['region'],x['product_model'],x['batch_reference'],x['user_intent'],"|".join(x['input_type']),"|".join(x['media_uri']),x['language'],x['raw_complaint'],"|".join(x['symptoms']),x['context']['onset'],x['context']['persists_after_cleaning'],x['context']['during_charging'],x['issue_type'],x['severity'],x['safety_flag'],x['confidence'],x['counts_as_complaint'],x['guidance_outcome']])
print(len(out),"rows")
