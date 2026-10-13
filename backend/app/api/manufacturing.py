"""Local POC evidence and on-demand interpretation endpoints."""
import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from app.api.dashboard import local_review_only
from app.models.manufacturing import EvidenceRequest, EvidencePackage
from app.services.manufacturing_evidence import generate_evidence, EvidenceTooLarge
from app.services import analysis_store
from app.models.manufacturing import StrictModel
from pydantic import Field
from typing import Literal
from app.auth import staff_access

router=APIRouter(prefix='/api/manufacturing',tags=['manufacturing'],dependencies=[Depends(local_review_only)])

@router.post('/analysis',status_code=202)
def watch_analysis(request: EvidenceRequest,response: Response):
    response.headers['Cache-Control']='private, no-store'
    try:return analysis_store.subscribe(request)
    except Exception:
        logging.getLogger(__name__).exception('Analysis subscription failed')
        raise HTTPException(503,'Could not queue this scope. Please retry.')

@router.get('/analysis')
def saved_analysis(response: Response,issue_type: str,start_date: date,end_date: date,region: str | None=None):
    response.headers['Cache-Control']='private, no-store'
    try:request=EvidenceRequest(issue_type=issue_type,start_date=start_date,end_date=end_date,region=region)
    except ValidationError:raise HTTPException(422,'Invalid analysis scope')
    try:return analysis_store.saved(request)
    except Exception:
        logging.getLogger(__name__).exception('Saved analysis read failed')
        raise HTTPException(503,'Could not read saved analysis. No Gemini call was made.')

@router.get('/analyses/{analysis_id}/evidence/{ref}')
def verify_evidence(analysis_id: str,ref: str,response: Response):
    response.headers['Cache-Control']='private, no-store'
    try:result=analysis_store.evidence_link(analysis_id,ref)
    except Exception:raise HTTPException(503,'Could not compare source evidence. The saved analysis remains unchanged.')
    if result is None:raise HTTPException(404,'Evidence not found in this analysis version')
    return result

class SMEFeedback(StrictModel):
    hypothesis_index: int=Field(ge=0)
    verdict: Literal['supported','not_supported','needs_more_evidence']
    comment: str=Field(min_length=1,max_length=3000)
    reviewer_label: str=Field(default='Local SME (unverified)',min_length=1,max_length=100)

@router.post('/analyses/{analysis_id}/reviews',status_code=201)
def submit_review(analysis_id: str,feedback: SMEFeedback,user=Depends(staff_access)):
    feedback.reviewer_label = user['uid']
    try:return analysis_store.review(analysis_id,**feedback.model_dump())
    except LookupError:raise HTTPException(404,'Analysis not found')
    except ValueError:raise HTTPException(422,'Invalid hypothesis for this analysis version')
    except Exception:
        logging.getLogger(__name__).exception('SME review save failed')
        raise HTTPException(503,'Review could not be saved. Please retry.')

@router.get('/evidence',response_model=EvidencePackage)
def evidence(response: Response,issue_type: str,start_date: date,end_date: date,region: str | None=None):
    """Build a validated evidence package. Dates are inclusive; baseline is equally long."""
    response.headers['Cache-Control']='private, no-store'
    try:request=EvidenceRequest(issue_type=issue_type,start_date=start_date,end_date=end_date,region=region)
    except ValidationError:raise HTTPException(422,'Select a supported issue and an inclusive date range of 1–366 days.')
    try:return generate_evidence(request)
    except EvidenceTooLarge as exc:raise HTTPException(413,str(exc))
    except Exception:
        logging.getLogger(__name__).exception('Manufacturing evidence generation failed')
        raise HTTPException(503,'Could not assemble a complete evidence package. Check source data and BigQuery access, then retry.')
