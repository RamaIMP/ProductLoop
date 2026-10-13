"""Lifecycle controls; the mounted consumer dependency binds user_id to the verified UID."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from app.auth import staff_access
from pydantic import BaseModel, Field
from app.services.lifecycle import get_store, now
from app.services import bigquery as sync

router = APIRouter(prefix='/api', tags=['lifecycle'])

class Registration(BaseModel):
    user_id: str = Field(min_length=1,max_length=200)
    serial_number: str = Field(min_length=1,max_length=120)
    product_model: str = Field(default='X500',min_length=1,max_length=100)
    batch_id: str | None = Field(default=None,max_length=120)
    region: str | None = Field(default=None,max_length=100)
    purchase_date: date | None = None

class Draft(BaseModel):
    user_id: str = Field(min_length=1,max_length=200)
    complaint_id: str = Field(pattern=r'^PL-[a-fA-F0-9-]{32,36}$')
    serial_number: str | None = None
    incident_country: str | None = Field(default=None,max_length=100)
    incident_region: str | None = Field(default=None,max_length=100)
    incident_city: str | None = Field(default=None,max_length=100)

@router.post('/units/register')
def register(request: Registration):
    record = request.model_dump(mode='json')
    record['consumer_id'] = record.pop('user_id')
    record['serial_number'] = record['serial_number'].strip()
    record['product_model'] = record['product_model'].strip().upper()
    if not record['product_model']:
        raise HTTPException(422,'Product model is required.')
    if not record['serial_number']:
        raise HTTPException(422,'Serial number is required.')
    return get_store().register(record)

@router.get('/units')
def units(user_id: str):
    return [r for r in get_store().all('registered_units') if r['consumer_id'] == user_id]


@router.get('/profile/registered-units')
def profile_registered_units(user_id: str):
    if not sync.enabled():
        return {'units':units(user_id),'source':'local_development'}
    try:
        return {'units':sync.read_profile_units(user_id),'source':'bigquery.registered_units'}
    except Exception as exc:
        # A query failure is not the same as an absent registration.
        raise HTTPException(503,'Could not load your registration from the database. Please retry.') from exc

@router.post('/incidents')
def incident(request: Draft):
    location = {k:getattr(request,k) for k in ('incident_country','incident_region','incident_city') if getattr(request,k)}
    if location:
        location['location_source'] = 'user_provided'
    return get_store().draft(request.user_id,request.complaint_id,request.serial_number,location)

@router.post('/incidents/{complaint_id}/abandon')
def abandon(complaint_id: str, user_id: str):
    record = get_store().incident(complaint_id,user_id)
    if record.get('submitted_at'):
        raise HTTPException(409,'Submitted incidents cannot be discarded as drafts.')
    if record['status'] != 'abandoned':
        record = get_store().save_report({**record,'status':'abandoned'},'draft_abandoned')
    return record

@router.get('/persistence/status', dependencies=[Depends(staff_access)])
def persistence_status():
    return sync.sync_status()


@router.get('/reports/{complaint_id}')
def report_details(complaint_id: str, user_id: str):
    store = get_store()
    report = store.incident(complaint_id,user_id)
    if not (report.get('submitted_at') or report.get('legacy_confirmed')):
        raise HTTPException(404,'Submitted report not found')
    evidence_fields = ('evidence_id','kind','original_filename','created_at',
        'storage_status','extraction_status','extracted_summary','extracted_symptoms')
    evidence = [{key:record.get(key) for key in evidence_fields}
        for record in store.all('evidence') if record['complaint_id'] == complaint_id]
    events = sorted([record for record in store.all('complaint_events')
        if record['complaint_id'] == complaint_id],key=lambda record:record['occurred_at'])
    return {'report':report,'evidence':evidence,'events':events}

@router.get('/callback-slots')
def callback_slots():
    zone = ZoneInfo('Asia/Kolkata')
    current = datetime.now(zone)
    slots = []
    for offset in range(3):
        day = current + timedelta(days=offset)
        for hour in (10,14,16):
            start = day.replace(hour=hour,minute=0,second=0,microsecond=0)
            if start <= current:
                continue
            end = start + timedelta(minutes=30)
            label = ('Today' if offset == 0 else 'Tomorrow' if offset == 1 else start.strftime('%d %b'))
            slots.append({'label':f"{label} · {start.strftime('%I:%M')}–{end.strftime('%I:%M %p')}",
                'scheduled_start':start.isoformat(), 'scheduled_end':end.isoformat(), 'time_zone':'Asia/Kolkata'})
    return slots[:3]


class ServiceAppointment(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    centre_id: str
    scheduled_start: datetime


@router.post('/reports/{complaint_id}/service-appointment')
def book_service(complaint_id: str, request: ServiceAppointment):
    centres = {'central':'XShaver Care — Central', 'park':'XShaver Care — Park Road',
               'tech':'XShaver Care — Tech Square'}
    if request.centre_id not in centres:
        raise HTTPException(422, 'Select a valid service centre.')
    store = get_store()
    with store.lock, store.db:
        report = store.incident(complaint_id, request.user_id)
        if not (report.get('submitted_at') or report.get('legacy_confirmed')):
            raise HTTPException(409, 'Submit a report before booking service.')
        if report.get('service_appointment'):
            return report['service_appointment']
        if report.get('status') == 'resolved':
            raise HTTPException(409, 'This report is resolved. Select an unresolved report.')
        slot = next((s for s in callback_slots()
                     if datetime.fromisoformat(s['scheduled_start']) == request.scheduled_start), None)
        if not slot:
            raise HTTPException(422, 'This slot is no longer available. Please select a new slot.')
        from uuid import uuid4
        booking = {'booking_id':'DEMO-APT-' + uuid4().hex[:10].upper(),
            'status':'demo_booked', 'centre_id':request.centre_id,
            'centre_name':centres[request.centre_id], 'complaint_id':complaint_id,
            'product_model':report.get('product_model') or 'X500',
            'serial_number':report.get('serial_number'), 'booked_at':now(),
            **{k:slot[k] for k in ('scheduled_start','scheduled_end','time_zone')}}
        store.save_report({**report,'service_appointment':booking}, 'service_appointment_booked')
        return booking
