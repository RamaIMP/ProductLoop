"""Deterministic count-based signals. No shipment-rate or root-cause claims."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def calculate_signals(rows, settings, issue_types, now=None):
    now = now or datetime.now(timezone.utc)
    end = date.fromisoformat(str(settings['as_of_date'])) if settings.get('as_of_date') else now.astimezone(ZoneInfo('Asia/Kolkata')).date()
    days, baseline = settings['window_days'], settings.get('baseline_days') or settings['window_days']
    if days != baseline or days < 1:
        raise ValueError('Count-based comparison requires equal positive windows')
    if settings.get('batch_rate_alerts_enabled'):
        raise ValueError('Shipment-rate signals are not implemented')
    start = end-timedelta(days=days-1)
    prior_start = start-timedelta(days=baseline)
    def day(value):
        dt = value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if not dt.tzinfo: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo('Asia/Kolkata')).date()
    unique={}
    for row in rows:
        if not (row.get('counts_as_complaint') and row.get('consent_share') and row.get('submitted_at') and row.get('user_intent')=='report_problem'):
            continue
        if row.get('status') in ('draft','abandoned'): continue
        if row['issue_type'] not in issue_types: continue
        key=row['complaint_id']
        if key in unique and unique[key]!=row: raise ValueError('Conflicting duplicate complaint ID')
        unique[key]=row
    output=[]
    for issue in issue_types:
        selected=[r for r in unique.values() if r['issue_type']==issue]
        current=[r for r in selected if start<=day(r['created_at'])<=end]
        previous=[r for r in selected if prior_start<=day(r['created_at'])<start]
        n,p=len(current),len(previous)
        growth=round((n-p)/p*100,2) if p else None
        safety=sum(r.get('safety_flag') is True for r in current)
        status='low_volume' if n<settings['watch_min_events'] else 'stable'
        if not p and n>=settings['min_events']: status='new_issue_activity'
        elif p and n>=settings['min_events'] and growth>=settings['growth_pct']: status='alert'
        elif p and n>=settings['watch_min_events'] and growth>=settings['watch_growth_pct']: status='watch'
        elif p and n>=settings['watch_min_events'] and n<p: status='declining'
        review=safety>=settings['min_events_safety']
        counts=lambda field: dict(Counter(r.get(field) or 'Unknown' for r in current))
        output.append({'issue_type':issue,'product_model':'X500','computed_at':now.isoformat(),
            'window_start':str(start),'window_end':str(end),'baseline_start':str(prior_start),
            'baseline_end':str(start-timedelta(days=1)),'time_zone':'Asia/Kolkata',
            'current_count':n,'prior_count':p,'growth_pct':growth,'status':status,
            'safety_review':review,'safety_count':safety,
            'prior_safety_count':sum(r.get('safety_flag') is True for r in previous),
            'priority':'high' if review or status=='alert' else 'medium' if status in ('watch','new_issue_activity') else 'low',
            'reason':f'{n} submitted complaints versus {p} in the previous {baseline} days.' +
                (' No baseline activity; percentage growth is not defined.' if p==0 else f' Count change: {growth:+g}%.') +
                (f' {safety} safety-flagged complaints require review.' if review else ''),
            'symptoms':dict(Counter(s for r in current for s in set(r.get('symptoms') or []))),
            'batches':counts('batch_reference'),'regions':counts('region'),'outcomes':counts('status'),
            'severity':counts('severity'),
            'trend':[{'date':str(start+timedelta(days=i)),
                'current':sum(day(r['created_at'])==start+timedelta(days=i) for r in current),
                'safety':sum(day(r['created_at'])==start+timedelta(days=i) and r.get('safety_flag') is True for r in current),
                'baseline':sum(day(r['created_at'])==prior_start+timedelta(days=i) for r in previous)} for i in range(days)],
            'thresholds':{k:settings[k] for k in ('min_events','growth_pct','watch_min_events','watch_growth_pct','min_events_safety')},
            'rate_per_1000':None})
    return output
