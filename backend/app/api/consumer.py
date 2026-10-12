"""Development API for the consumer report journey.

Reports currently use an in-memory store. Gemini handles extraction and
conversation, while retrieval remains a development adapter.
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from time import perf_counter
import json
import re
import hashlib
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.guardrails.safety_rules import safety_response, check_stop_use
from app.models.taxonomy import Context, Derived, Extraction, UserIntent
from app.rules.derive import derive
from app.services.mock_guidance import get_guidance
from app.services.retrieval import retrieve_for_report
from app import config
from starlette.concurrency import run_in_threadpool
from app.services import media_jobs
from app.services import gemini
from app.services.corrections import merge_correction
from app.services.lifecycle import get_store, now
from app.services.greetings import greeting_reply
from app.tools.extract import extract_from_bytes

router = APIRouter(prefix="/api", tags=["consumer"])


class IntakeRequest(BaseModel):
    user_id: str = Field(min_length=1)
    message: str = ""
    extraction: Extraction | None = None


class GuidanceRequest(BaseModel):
    extraction: Extraction
    derived: Derived | None = None


class FollowUpRequest(GuidanceRequest):
    follow_up: dict


class ConfirmRequest(GuidanceRequest):
    user_id: str = Field(min_length=1)
    consent_share: bool = False
    complaint_id: str | None = None


class OutcomeRequest(BaseModel):
    outcome: str = Field(pattern="^(helped|not_fixed)$")


class CallbackRequest(BaseModel):
    slot: str = Field(min_length=3, max_length=80)
    user_id: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    time_zone: str = 'Asia/Kolkata'


class ConversationMessage(BaseModel):
    role: Literal['user', 'assistant']
    text: str = Field(max_length=10000)


class ConversationRequest(IntakeRequest):
    complaint_id: str | None = None
    debug: bool = False
    history: list[ConversationMessage] = Field(default_factory=list, max_length=100)
    report_id: str | None = None
    event: Literal['message', 'session_start', 'media_added', 'report_confirmed', 'callback_requested',
                   'resolved', 'not_resolved', 'create_ticket', 'add_details', 'edit_report', 'onset_selected'] = 'message'


_REPORTS: dict[str, dict] = {}

_GREETING_MESSAGE = (
    "Hi! I can help with that. Please describe what is happening, or attach a photo, "
    "sound recording, or video."
)
_WELCOME_MESSAGE = ('Welcome to ProductLoop X500 support! How can I help you today? '
                    'Feel free to describe your issue or send a picture or video.')


def _is_greeting(message: str) -> bool:
    """Recognise a greeting only when it is the whole message, not a fault description."""
    return greeting_reply(message) is not None

# Conversation policy belongs to code, not a model prompt, so each issue type
# gets a relevant question instead of the generic cleaning question.
_FOLLOW_UPS = {
    "noise_and_vibration": {
        "field": "persists_after_cleaning",
        "question": "Does it still happen after cleaning and refitting the shaving head?",
        "replies": ["Yes, still", "No, it stopped", "Haven't tried"],
    },
    "shaving_performance": {
        "field": "persists_after_cleaning",
        "question": "Have you cleaned the blade units since this started?",
        "replies": ["Yes, still", "No, it improved", "Haven't tried"],
    },
    "power_and_charging": {
        "field": "during_charging",
        "question": "Does this happen while the shaver is charging?",
        "replies": ["Yes", "No", "Not sure"],
    },
    "shaving_head_and_fitment": {
        "field": "persists_after_cleaning",
        "question": "After cleaning and refitting the head, does it click securely into place?",
        "replies": ["No, still loose", "Yes, it clicks", "Haven't tried"],
    },
    "cleaning_and_maintenance": {
        "field": "persists_after_cleaning",
        "question": "Have you tried removing the trapped hair and rinsing the blade units?",
        "replies": ["Yes, still blocked", "No, it cleared", "Haven't tried"],
    },
}


def _dummy_extract(message: str) -> Extraction:
    """Temporary local stand-in for Gemini extraction; never use this in production."""
    text = message.lower().replace("_", " ").replace("-", " ")
    symptoms: list[str] = []
    mappings = {
        "rattling_sound": ("rattle", "rattling"),
        "grinding_sound": ("grind", "grinding"),
        "increased_noise": ("noisy", "noise", "loud"),
        "increased_vibration": ("vibrat", "shaking", "shake"),
        "battery_drains_fast": ("battery drain", "drains", "battery dies"),
        "not_powering_on": ("won't turn on", "will not turn on", "not power"),
        "not_charging": ("not charging", "won't charge", "will not charge"),
        "head_loose": ("head loose", "head wobb", "head shakes"),
        "head_not_fitting": ("head does not fit", "head won't fit"),
        "pulling_hair": ("pulling", "pulls my hair"),
        "reduced_cutting_quality": ("not cutting", "poor shave", "close shave"),
        "missed_hairs": ("missed hair", "hairs left", "leaves hair"),
        "requires_multiple_passes": ("multiple passes", "many passes", "several passes"),
        "uneven_shave": ("uneven shave", "patchy shave"),
        "blade_drag": ("blade drag", "blades drag", "feels rough"),
        "hair_buildup": (
            "hair stuck", "hair trapped", "hair buildup", "hair build", "hair under",
            "stuck in the blade", "stuck in blade", "stuck in the head", "stuck in head", "debris under",
        ),
        "difficult_to_clean": ("hard to clean", "difficult to clean", "cannot clean"),
        "blade_replacement_due": ("replace blades", "replace the blades", "blade replacement"),
        "storage_question": ("store", "storage"),
        "water_exposure_question": ("shower", "waterproof", "wet shave"),
        "slow_charging": ("slow charge", "charging slowly", "takes long to charge"),
        "led_not_working": ("led not", "light not", "indicator not"),
        "head_wobble": ("head wobbles", "head wobble"),
        "blade_unit_not_seated": ("blade not seated", "blade unit not seated", "does not sit flush"),
        "cleaning_question": ("clean", "wash"),
    }
    for symptom, terms in mappings.items():
        if any(term in text for term in terms):
            symptoms.append(symptom)

    intent = UserIntent.ask_question if "?" in message or text.startswith(("how ", "can i", "should i")) else UserIntent.report_problem
    if not symptoms:
        symptoms = ["unclear_description"]
    return Extraction(
        user_intent=intent,
        symptoms=symptoms,
        context=Context(),
        confidence=0.55 if symptoms == ["unclear_description"] else 0.8,
    )


def _classification(extraction: Extraction) -> Derived:
    return derive(extraction.symptoms, extraction.context, extraction.user_intent.value)


def _workflow_reply(request: ConversationRequest, report: dict | None) -> dict | None:
    """Known controls need state transitions, not intent inference or generated prose."""
    event = request.event
    if event == 'message' and report:
        # Only exact stand-alone commands; mixed messages still need interpretation.
        command = request.message.strip().lower().rstrip('.!')
        event = {'that fixed it': 'resolved', 'still not fixed': 'not_resolved',
                 'create ticket': 'create_ticket', 'create a ticket': 'create_ticket',
                 'add more details': 'add_details'}.get(command, event)
    if event not in {'resolved', 'not_resolved', 'create_ticket', 'add_details', 'edit_report', 'callback_requested'}:
        return None
    if event not in {'edit_report', 'add_details'} and not report:
        raise HTTPException(status_code=409, detail='Submit your report before using this action.')
    action = 'continue'
    if event == 'resolved':
        save_outcome(report['report_id'], OutcomeRequest(outcome='helped'))
        action, message = 'resolved', 'Glad that helped! Your report is marked resolved.'
    elif event == 'not_resolved':
        if report.get('status') == 'ticket_raised':
            message = f"Your support ticket {report['ticket_id']} is already raised. You can choose a support option below."
        else:
            report.update(status='unresolved', outcome='not_fixed')
            report.update(get_store().save_report(report, 'not_resolved'))
            action, message = 'ticket_confirm', 'Sorry that didn’t resolve it. Would you like me to create a support ticket?'
    elif event == 'create_ticket':
        if report.get('status') != 'ticket_raised':
            save_outcome(report['report_id'], OutcomeRequest(outcome='not_fixed'))
        action = 'raise_ticket'
        message = f"Your support ticket {report['ticket_id']} has been created. Choose a support option below."
    elif event == 'callback_requested':
        if not report.get('callback') or report.get('status') != 'ticket_raised':
            raise HTTPException(status_code=409, detail='Save a callback request first.')
        message = f"Your callback request is saved for {report['callback']['slot']}."
    elif event == 'edit_report':
        action, message = 'edit_report', 'What would you like to correct in your report?'
    else:
        action, message = 'add_details', 'Please describe the additional details, or attach another photo, recording or video.'
    return {'message': message, 'action': action, 'report': report,
            'extraction': request.extraction, 'derived': None,
            'mode': 'workflow', 'model': None, 'sources': [], 'retrieval_mode': None}


def _conversation(request: ConversationRequest):
    """Greetings are instant; substantive turns use Gemini and extracted media data."""
    report = _REPORTS.get(request.report_id) if request.report_id else None
    if request.report_id and (not report or report['user_id'] != request.user_id):
        raise HTTPException(status_code=404, detail='Report not found')
    if request.event == 'onset_selected':
        onset = {'Today': 'today', 'This week': 'this_week', 'Longer ago': 'longer'}.get(request.message)
        if not onset or not request.extraction or report:
            raise HTTPException(status_code=409, detail='Choose a start time for the current draft report.')
        extraction = Extraction.model_validate({**request.extraction.model_dump(mode='json'),
            'context': {**request.extraction.context.model_dump(mode='json'), 'onset': onset}})
        derived = _classification(extraction)
        return {'message': 'Please review your report below.' if not derived.safety_flag else 'Please stop using and charging the shaver and seek service.',
                'action': 'stop_use' if derived.safety_flag else 'confirm_report',
                'extraction': extraction, 'derived': derived, 'report': None,
                'follow_up': None, 'mode': 'workflow', 'model': None, 'sources': [], 'retrieval_mode': None}
    workflow = _workflow_reply(request, report)
    if workflow is not None:
        return workflow
    if request.event == 'report_confirmed' and not report:
        raise HTTPException(status_code=409, detail='Submit your report first.')
    if (request.event == 'session_start' and not request.message.strip()) or (
        request.event == 'message' and _is_greeting(request.message)
    ):
        return {'message': _WELCOME_MESSAGE if request.event == 'session_start' else greeting_reply(request.message),
                'action': 'continue', 'extraction': request.extraction,
                'derived': _classification(request.extraction) if request.extraction else None,
                'report': report, 'mode': 'instant_greeting', 'model': None,
                'sources': [], 'retrieval_mode': None}
    incident_id = request.report_id or request.complaint_id
    evidence = [item for item in get_store().all('evidence')
                if incident_id and item.get('complaint_id') == incident_id
                and item.get('extraction_status') == 'completed']
    payload = {
        'message': request.message, 'event': request.event,
        'history': [item.model_dump() for item in request.history],
        'previous_extraction': request.extraction.model_dump(mode='json') if request.extraction else None,
        'saved_report': report,
        'independent_media_findings': [{k: item.get(k) for k in
            ('evidence_id', 'extracted_symptoms', 'extracted_summary')} for item in evidence],
    }
    stop_use = check_stop_use(request.message)
    extraction = request.extraction
    derived = _classification(request.extraction) if request.extraction else None
    trace = []
    def trace_stage(name, started, output, model=None):
        if request.debug:
            trace.append({'stage': name, 'elapsed_ms': round((perf_counter() - started) * 1000, 1),
                          'model': model, 'output': output})
    try:
        started = perf_counter()
        # Confirmation already has structured findings. Only the answer needs an LLM.
        decision = (gemini.ConversationDecision(
            extraction=Extraction.model_validate(report['extraction']), action='show_guidance')
            if request.event == 'report_confirmed' else gemini.understand_conversation(payload))
        trace_stage('Interpretation' if request.event != 'report_confirmed' else 'Saved extraction (interpretation skipped)',
                    started, decision.model_dump(mode='json'), config.MODEL_CHAT if request.event != 'report_confirmed' else None)
        started = perf_counter()
        extraction, correction_question = merge_correction(request.extraction,
            decision.extraction, decision.correction, request.message, evidence)
        if stop_use:
            extraction = Extraction.model_validate({
                **(extraction.model_dump(mode='json') if extraction else {'confidence': 1}),
                'symptoms': list(dict.fromkeys([*(extraction.symptoms if extraction else []), *stop_use.symptoms])),
            })
        derived = _classification(extraction) if extraction else None
        trace_stage('Merged evidence and rule classification', started,
                    {'extraction': extraction.model_dump(mode='json') if extraction else None,
                     'derived': derived.model_dump(mode='json') if derived else None,
                     'safety_matches': list(stop_use.symptoms) if stop_use else []})
        action = decision.action
        if decision.correction:
            action = 'continue'
        if derived and derived.safety_flag:
            action = 'stop_use'
        elif action in ('resolved', 'ticket_confirm', 'raise_ticket') and not report:
            action = 'confirm_report' if extraction else 'continue'
        elif action == 'confirm_report' and (report or not extraction):
            action = 'continue'
        if correction_question:
            return {'message': correction_question, 'action': action if action == 'stop_use' else 'continue',
                    'extraction': extraction, 'derived': derived, 'report': report,
                    'mode': 'correction_clarification', 'model': config.MODEL_CHAT,
                    'sources': [], 'retrieval_mode': None}
        # Ask this once for an identified, non-safety draft issue. Unknown onset
        # must never turn a greeting, usage question or hazard into this questionnaire.
        onset_asked = any(item.role == 'assistant' and 'When did this start?' in item.text for item in request.history)
        if (extraction and derived and not derived.safety_flag and not report
                and extraction.user_intent.value == 'report_problem'
                and extraction.context.onset.value == 'unknown'
                and derived.issue_type.value != 'other_or_unclear'
                and action in ('continue', 'confirm_report') and not onset_asked
                and request.event in ('message', 'media_added')):
            return {'message': 'When did this start?', 'action': 'ask_onset',
                    'extraction': extraction, 'derived': derived, 'report': None,
                    'follow_up': {'field': 'onset', 'replies': ['Today', 'This week', 'Longer ago']},
                    'mode': 'workflow', 'model': None, 'sources': [], 'retrieval_mode': None,
                    **({'debug': {'stages': trace}} if request.debug else {})}
        if report and action in ('resolved', 'raise_ticket'):
            # Reuse the same record; do not generate a new ticket on repeat requests.
            if action == 'resolved' or report.get('status') != 'ticket_raised':
                save_outcome(report['report_id'], OutcomeRequest(outcome='helped' if action == 'resolved' else 'not_fixed'))
        payload.update(extraction=extraction.model_dump(mode='json') if extraction else None,
                       derived=derived.model_dump(mode='json') if derived else None,
                       action=action, saved_report=report, knowledge=None)
        sources = []
        mode = 'gemini_conversation'
        model = config.MODEL_CHAT
        retrieval_mode = None
        if extraction and derived and not derived.safety_flag and (
            action == 'show_guidance' or request.event == 'report_confirmed'
        ):
            try:
                started = perf_counter()
                retrieval = retrieve_for_report(request.message, extraction, derived)
                trace_stage('Knowledge retrieval', started, retrieval)
                retrieval_mode = retrieval['mode']
                if not retrieval['chunks']:
                    message = 'I couldn’t find a verified next step for this issue. You can try again or contact support.'
                    action, mode, model = 'guidance_unavailable', 'knowledge_gap', None
                else:
                    started = perf_counter()
                    answer = gemini.reason_over_retrieval(message=request.message, history=payload['history'],
                        extraction=extraction, derived=derived.model_dump(mode='json'), retrieval=retrieval, saved_report=report)
                    trace_stage('Post-retrieval answer', started, answer.model_dump(mode='json'), config.MODEL_REASON)
                    if not answer.source_ids:
                        # No verified citation: never display potentially unsupported steps.
                        message = 'I couldn’t find a verified next step for this issue. You can try again or contact support.'
                        action, mode, model = 'guidance_unavailable', 'knowledge_gap', None
                    else:
                        message = answer.message
                        sources = [{'chunk_id': chunk['chunk_id'], 'title': chunk['title'],
                                    'source_file':chunk.get('source_file','')} for chunk in retrieval['chunks']
                                   if chunk['chunk_id'] in answer.source_ids]
                        mode, model = 'gemini_reasoning', config.MODEL_REASON
            except Exception as rag_error:
                trace_stage('Guidance unavailable', started, {'error_type':type(rag_error).__name__})
                message = 'Sorry, I couldn’t load the troubleshooting steps right now. Please try again or contact support.'
                action, mode, model = 'guidance_unavailable', 'retrieval_error', None
                sources = []
        elif action == 'stop_use':
            message = None
            mode, model = 'safety_guardrail', None
        else:
            started = perf_counter()
            message = gemini.reply_to_conversation(payload)
            trace_stage('Conversation reply', started, {'message': message, 'action': action}, config.MODEL_CHAT)
        return {'message': message, 'action': action, 'extraction': extraction, 'derived': derived,
                'report': report, 'mode': mode, 'model': model, 'sources': sources, 'retrieval_mode': retrieval_mode,
                **({'debug': {'stages': trace}} if request.debug else {})}
    except Exception as exc:
        if stop_use or (derived and derived.safety_flag):
            return {'action': 'stop_use', 'message': None,
                    'extraction': extraction, 'derived': derived,
                    'mode': 'safety_guardrail', 'report': report}
        raise HTTPException(status_code=503, detail='The conversation service is unavailable. Please retry your message.') from exc


@router.post('/conversation')
def conversation(request: ConversationRequest):
    store = get_store()
    incident_id = request.report_id or request.complaint_id
    if incident_id:
        saved = store.incident(incident_id, request.user_id)
        # Prefer persisted state to a stale browser extraction, especially after corrections.
        if saved.get('extraction') and request.event != 'onset_selected':
            request.extraction = Extraction.model_validate(saved['extraction'])
    result = _conversation(request)
    extraction = result.get('extraction')
    derived = result.get('derived')
    if result.get('action') == 'stop_use' and extraction is None:
        safety = check_stop_use(request.message)
        if safety:
            extraction = Extraction(symptoms=list(safety.symptoms), confidence=1)
            derived = _classification(extraction)
    if extraction and derived and result.get('mode') != 'instant_greeting':
        extraction = extraction.model_dump(mode='json') if hasattr(extraction, 'model_dump') else extraction
        derived = derived.model_dump(mode='json') if hasattr(derived, 'model_dump') else derived
        if incident_id or extraction.get('user_intent') == 'report_problem':
            incident = store.draft(request.user_id, incident_id)
            incident_id = incident['report_id']
            updated = store.classify(incident_id, request.user_id, extraction, derived,
                request.message if request.event == 'message' else '',
                'media' if request.event == 'media_added' else 'text')
            if updated.get('submitted_at'):
                _REPORTS[incident_id] = updated
                result['report'] = updated
            previous_symptoms = {s.value for s in request.extraction.symptoms} if request.extraction else set()
            retracted = previous_symptoms - set(extraction.get('symptoms', [])) - {'unclear_description'}
            if retracted:
                with store.lock, store.db:
                    store.event(incident_id, 'complaint_corrected',
                        details={'previous_symptoms': sorted(previous_symptoms),
                                 'current_symptoms': extraction['symptoms'],
                                 'retracted_symptoms': sorted(retracted)})
    if result.get('action') == 'stop_use':
        findings = extraction or request.extraction
        symptoms = findings.get('symptoms', []) if isinstance(findings, dict) else findings.symptoms if findings else []
        matched = check_stop_use(request.message)
        result['response'] = safety_response([*symptoms, *(matched.symptoms if matched else [])])
        if result.get('mode') != 'correction_clarification':
            result['message'] = None
    result['complaint_id'] = incident_id
    return result


def _follow_up(derived: Derived) -> dict | None:
    """Return the next structured question for a non-safety report."""
    return _FOLLOW_UPS.get(derived.issue_type.value)


@router.post("/conversation/follow-up")
def conversational_follow_up(request: FollowUpRequest):
    """Phrase a code-selected follow-up with the text-only reasoning model."""
    follow_up = request.follow_up
    fallback = follow_up["question"]
    summary = {
        "product_model": request.extraction.product_model,
        "symptoms": [symptom.value for symptom in request.extraction.symptoms],
        "context": request.extraction.context.model_dump(mode="json"),
        "issue_type": request.derived.issue_type.value if request.derived else None,
        "severity": request.derived.severity.value if request.derived else None,
    }
    try:
        message = gemini.write_follow_up(summary=summary, required_field=follow_up["field"], fallback_question=fallback)
        mode = "text_reasoning_llm"
    except Exception:
        message = fallback
        mode = "development_template"
    return {"message": message, "replies": follow_up["replies"], "mode": mode}


@router.post("/media/extract")
async def extract_media(
    file: UploadFile = File(...),
    message: str = Form(""),
    prior_symptoms_json: str = Form("[]"),
    debug: bool = Form(False),
    user_id: str = Form('development-user'),
    complaint_id: str | None = Form(None),
    evidence_id: str | None = Form(None),
    audio_purpose: Literal['general', 'spoken_complaint', 'device_sound'] = Form('general'),
):
    """Analyse new media directly while archiving an independent copy in parallel.

    Earlier media is represented by its already extracted symptoms. It is never
    resubmitted to Gemini when a user adds another attachment.
    """
    if not (file.content_type or "").startswith(("image/", "audio/", "video/")):
        raise HTTPException(status_code=415, detail="Upload an image, audio, or video file.")
    try:
        prior_symptoms = json.loads(prior_symptoms_json)
        if not isinstance(prior_symptoms, list) or not all(isinstance(item, str) for item in prior_symptoms):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="prior_symptoms_json must be a JSON string array.")

    try:
        if prior_symptoms:
            Extraction(symptoms=prior_symptoms, confidence=1)
    except ValueError:
        raise HTTPException(status_code=422, detail='Invalid prior symptoms.')
    data = await file.read(15 * 1024 * 1024 + 1)
    if not data or len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='Choose a non-empty media file up to 15 MiB.')
    evidence_id = evidence_id if isinstance(evidence_id,str) else None
    complaint_id = complaint_id if isinstance(complaint_id,str) else None
    audio_purpose = audio_purpose if isinstance(audio_purpose,str) else 'general'
    if audio_purpose != 'general' and not (file.content_type or '').startswith('audio/'):
        raise HTTPException(422, 'Audio purpose requires an audio file.')
    fingerprint_parts = [message,prior_symptoms_json,file.content_type]
    if audio_purpose != 'general': fingerprint_parts.append(audio_purpose)
    fingerprint = hashlib.sha256(data + json.dumps(fingerprint_parts).encode()).hexdigest()
    if evidence_id:
        if not re.fullmatch(r'ev_[a-f0-9]{32}',evidence_id):
            raise HTTPException(422,'Invalid evidence ID')
        previous = get_store().get('evidence',evidence_id)
        if previous:
            if previous['consumer_id'] != user_id or previous['complaint_id'] != complaint_id:
                raise HTTPException(404,'Evidence not found')
            if previous.get('request_hash') != fingerprint:
                raise HTTPException(409,'This evidence ID belongs to different input.')
            if previous.get('api_result'):
                cached = previous['api_result']
                cached['storage'] = media_jobs.status(evidence_id,user_id)
                cached['media']['source'] = cached['storage']['storage_uri']
                return cached
            raise HTTPException(409,'This upload is already processing or was interrupted. Check its status; reattach the file if processing failed.')
    incident = get_store().draft(user_id, complaint_id if isinstance(complaint_id, str) else None)
    complaint_id = incident['report_id']
    evidence_id = media_jobs.start_upload(data, file.filename, file.content_type, user_id, complaint_id, evidence_id)
    with get_store().lock, get_store().db:
        record = get_store().get('evidence',evidence_id)
        get_store().put('evidence',evidence_id,{**record,'request_hash':fingerprint})
    stages = []
    if debug:
        stages.append({'stage': 'Parallel branch: archival upload (not awaited)',
                       'model': None, 'elapsed_ms': 0,
                       'output': {'evidence_id': evidence_id, 'storage_status': 'pending'}})
    prompt = message or ""
    if audio_purpose == 'spoken_complaint':
        prompt = 'This audio is the user describing their problem verbally. Extract the meaning of their speech, preserving negations and attempted remedies. Do not treat their voice as a shaver noise. Distinguish what they report from any device sound actually audible. If speech is unclear, state that limitation; do not guess.\nUser context: ' + prompt
    elif audio_purpose == 'device_sound':
        prompt = 'This audio was supplied as a device-sound recording. Analyse audible device sounds; do not confuse speech or background noise with the shaver. Do not infer heat, smell or an internal cause from sound alone.\nUser context: ' + prompt
    started = perf_counter()
    try:
        media_extraction = await run_in_threadpool(extract_from_bytes, data, file.content_type, prompt)
        if audio_purpose != 'spoken_complaint':
            media_extraction.speech = None
        analysis_mode = "multimodal_gemini"
    except Exception:
        # Enables UI development without a Google Cloud credential or model access.
        # The response identifies this path explicitly so it is never mistaken for AI analysis.
        media_extraction = _dummy_extract(f"{prompt} {file.filename or ''}")
        analysis_mode = "development_fallback"

    if debug:
        stages.append({'stage': 'Parallel branch: Gemini direct media extraction' if analysis_mode == 'multimodal_gemini' else 'Extraction failed — development fallback',
                       'model': config.MODEL_EXTRACT if analysis_mode == 'multimodal_gemini' else None,
                       'elapsed_ms': round((perf_counter() - started) * 1000, 1),
                       'status': 'complete' if analysis_mode == 'multimodal_gemini' else 'fallback',
                       'output': {'input_mode': 'inline_bytes', 'size_bytes': len(data),
                                  'analysis_mode': analysis_mode, 'findings': media_extraction.model_dump(mode='json')}})
    started = perf_counter()
    saved_symptoms = (get_store().incident(complaint_id,user_id).get('extraction') or {}).get('symptoms',[])
    combined_symptoms = list(dict.fromkeys([*saved_symptoms, *prior_symptoms, *(symptom.value for symptom in media_extraction.symptoms)]))
    # Revalidate rather than model_copy so symptoms remain Enum values.
    combined = Extraction.model_validate({**media_extraction.model_dump(mode="json"), "symptoms": combined_symptoms})
    derived = _classification(combined)
    if analysis_mode == 'multimodal_gemini':
        get_store().evidence_update(evidence_id, {
            'extraction_status':'completed', 'extracted_symptoms':[s.value for s in media_extraction.symptoms],
            'extracted_context':media_extraction.context.model_dump(mode='json'),
            'extracted_summary':', '.join(s.value for s in media_extraction.symptoms),
            'extraction_confidence':media_extraction.confidence, 'extraction_model':config.MODEL_EXTRACT,
            'extraction_prompt_version':'media-v1', 'extracted_at':now()}, 'evidence_analysed')
        updated = get_store().classify(complaint_id,user_id,combined.model_dump(mode='json'),
            derived.model_dump(mode='json'),message,file.content_type.split('/')[0])
        if updated.get('submitted_at'):
            _REPORTS[complaint_id] = updated
    else:
        get_store().evidence_update(evidence_id, {'extraction_status':'failed'}, 'analysis_failed')
    if debug:
        stages.append({'stage': 'Merge evidence and classify', 'model': None,
                       'elapsed_ms': round((perf_counter() - started) * 1000, 1),
                       'output': {'prior_symptoms': prior_symptoms, 'extraction': combined.model_dump(mode='json'),
                                  'derived': derived.model_dump(mode='json')}})
    storage = media_jobs.status(evidence_id, user_id)
    result = {
        'evidence_id': evidence_id,
        'complaint_id': complaint_id,
        'storage': storage,
        'analysis_status': 'completed' if analysis_mode == 'multimodal_gemini' else 'failed',
        "analysis_mode": analysis_mode,
        "model": config.MODEL_EXTRACT if analysis_mode == 'multimodal_gemini' else None,
        "media": {"filename": file.filename, "content_type": file.content_type, "source": storage['storage_uri']},
        "media_extraction": media_extraction,
        "extraction": combined,
        "derived": derived,
        "media_summary": f"Detected: {', '.join(symptom.replace('_', ' ') for symptom in media_extraction.symptoms)}.",
        **({'debug': {'stages': stages}} if debug else {}),
    }
    with get_store().lock, get_store().db:
        record = get_store().get('evidence',evidence_id)
        get_store().put('evidence',evidence_id,{**record,'api_result':jsonable_encoder(result)})
    return result


@router.get('/media/{evidence_id}/status')
def media_status(evidence_id: str, user_id: str):
    return media_jobs.status(evidence_id, user_id)


@router.post("/intake")
def intake(request: IntakeRequest):
    """Classify a message for the consumer UI; accepts a Gemini extraction when available."""
    stop_use = check_stop_use(request.message)
    if stop_use:
        return {
            "action": "stop_use",
            "matched_symptoms": list(stop_use.symptoms),
            "response": safety_response([*stop_use.symptoms, *(request.extraction.symptoms if request.extraction else [])]),
        }

    # A greeting is conversation, not an unclear product complaint.  Keep the
    # consumer in the initial state and invite them to describe or attach evidence.
    if not request.extraction and _is_greeting(request.message):
        return {"action": "greeting", "message": _GREETING_MESSAGE}

    extraction = request.extraction or _dummy_extract(request.message)
    derived = _classification(extraction)
    if derived.safety_flag:
        return {"action": "stop_use", "extraction": extraction, "derived": derived, "response": safety_response(extraction.symptoms)}
    if [symptom.value for symptom in extraction.symptoms] == ["unclear_description"] or extraction.confidence < 0.6:
        return {
            "action": "need_description",
            "extraction": extraction,
            "derived": derived,
            "message": "I can help with that. Please describe what is happening, or attach a photo, sound recording, or video.",
        }
    if extraction.user_intent.value == "ask_question":
        return {"action": "show_guidance", "extraction": extraction, "derived": derived, "guidance": get_guidance(extraction, derived)}
    return {"action": "confirm_report", "extraction": extraction, "derived": derived, "follow_up": _follow_up(derived)}


@router.post("/guidance")
def guidance(request: GuidanceRequest):
    """Stable seam for RAG. Replace mock_guidance.get_guidance when RAG is ready."""
    derived = request.derived or _classification(request.extraction)
    return get_guidance(request.extraction, derived)


@router.post("/reports/confirm", status_code=201)
def confirm_report(request: ConfirmRequest):
    with get_store().lock:
        return _confirm_report(request)


def _confirm_report(request: ConfirmRequest):
    """Submit the existing draft; a retry with the same ID returns the same report."""
    derived = _classification(request.extraction)
    store = get_store()
    draft = store.draft(request.user_id, request.complaint_id)
    if draft['status'] == 'abandoned':
        raise HTTPException(409,'Start a new report; this draft was discarded.')
    report_id = draft['report_id']
    if draft.get('submitted_at'):
        _REPORTS[report_id] = draft
        return {'report':draft, 'guidance':get_guidance(request.extraction,derived)}
    report = {
        **draft,
        "report_id": report_id,
        "user_id": request.user_id,
        "submitted_at": now(),
        "consent_share": request.consent_share,
        "status": "awaiting_feedback",
        "extraction": request.extraction.model_dump(mode="json"),
        "derived": derived.model_dump(mode="json"),
    }
    report = store.save_report(report, 'report_submitted')
    for evidence in store.all('evidence'):
        if evidence['complaint_id'] == report_id and evidence.get('consent_share') != request.consent_share:
            store.evidence_update(evidence['evidence_id'], {'consent_share':request.consent_share}, 'evidence_consent_updated')
    _REPORTS[report_id] = report
    return {"report": report, "guidance": get_guidance(request.extraction, derived)}


@router.get("/reports")
def my_reports(user_id: str):
    """List only the requesting user's development reports."""
    return [report for report in get_store().all('complaints') if report["user_id"] == user_id and (report.get('submitted_at') or report.get('legacy_confirmed'))]


@router.post("/reports/{report_id}/outcome")
def save_outcome(report_id: str, request: OutcomeRequest):
    report = _REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    target = 'resolved' if request.outcome == 'helped' else 'ticket_raised'
    if report.get('status') == target and report.get('outcome') == request.outcome:
        return report
    report["outcome"] = request.outcome
    if request.outcome == "helped":
        report["status"] = "resolved"
        report['resolved_at'] = now()
    else:
        # Development placeholder for the future service/ticketing integration.
        # Keep the original complaint ID so one issue remains one traceable record.
        report["status"] = "ticket_raised"
        report['resolved_at'] = None
        if not report.get('ticket_id'):
            report["ticket_id"] = f"SR-{uuid4().hex[:8].upper()}"
    report.update(get_store().save_report(report, 'resolved' if request.outcome == 'helped' else 'ticket_raised'))
    return report


@router.post("/reports/{report_id}/callback")
def request_callback(report_id: str, request: CallbackRequest):
    """Save a development callback request for an existing service ticket."""
    report = _REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if request.user_id and report['user_id'] != request.user_id:
        raise HTTPException(404, 'Report not found')
    if report.get("status") != "ticket_raised":
        raise HTTPException(status_code=409, detail="A callback can be requested after a service ticket is raised.")
    if report.get('callback'):
        return report
    try:
        zone = ZoneInfo(request.time_zone)
        start = request.scheduled_start
        if start is None:
            # Compatibility for the existing demo controls; explicit timestamps
            # are used by the updated UI.
            match = re.fullmatch(r'(Today|Tomorrow) · (\d{1,2}:\d{2})(?:[–-]\d{1,2}:\d{2})? (AM|PM)', request.slot)
            if not match:
                raise ValueError('Invalid callback slot')
            day = datetime.now(zone) + timedelta(days=match[1] == 'Tomorrow')
            time = datetime.strptime(match[2] + ' ' + match[3], '%I:%M %p').time()
            start = datetime.combine(day.date(),time,tzinfo=zone)
        end = request.scheduled_end or start + timedelta(minutes=30)
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError('Invalid callback time')
        if request.scheduled_start and start <= datetime.now(timezone.utc):
            raise ValueError('Choose a future callback slot')
    except (ValueError, KeyError) as exc:
        raise HTTPException(422,str(exc)) from exc
    report["callback"] = {"slot": request.slot, "requested_at": now(), 'status':'demo_requested',
        'scheduled_start':start.isoformat(), 'scheduled_end':end.isoformat(), 'time_zone':request.time_zone}
    report.update(get_store().save_report(report, 'callback_requested'))
    return report
