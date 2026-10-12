"""Local POC quality API. Add authenticated staff authorization before deployment."""
import logging
from fastapi import APIRouter, HTTPException, Query, Request, Response, Depends
from app.services.quality_complaints import list_complaints, complaint_detail, evidence_media
from app.rules.dashboard_scope import DASHBOARD_ISSUE_TYPES as ISSUE_TYPES
from app.services.signals import read_signals, refresh_signals
from app.services.signals import read_overview
from typing import Literal
from datetime import date

router=APIRouter(prefix='/api/dashboard',tags=['quality'])

def local_review_only(request: Request):
    # POC only: sensitive drill-down must not be exposed until staff auth exists.
    if request.client is None or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Staff authentication is required outside local development')

@router.get('/complaints',dependencies=[Depends(local_review_only)])
def complaints(issue_type: str, start_date: date, end_date: date, region: str | None=None, page: int=Query(1,ge=1), page_size: int=Query(10,ge=1,le=50)):
    if issue_type not in ISSUE_TYPES or not 1<=(end_date-start_date).days+1<=366: raise HTTPException(422,'Invalid issue or date range')
    try: return list_complaints(issue_type,start_date,end_date,region,page,page_size)
    except Exception:
        logging.getLogger(__name__).exception('Complaint list failed')
        raise HTTPException(503,'Could not load complaints. Please retry.')

@router.get('/complaints/{complaint_id}',dependencies=[Depends(local_review_only)])
def detail(complaint_id: str):
    try: result=complaint_detail(complaint_id)
    except Exception:
        logging.getLogger(__name__).exception('Complaint detail failed')
        raise HTTPException(503,'Could not load complaint details. Please retry.')
    if result is None: raise HTTPException(404,'Complaint unavailable')
    return result

@router.get('/complaints/{complaint_id}/evidence/{evidence_id}/media',dependencies=[Depends(local_review_only)])
def media(complaint_id: str,evidence_id: str):
    try: result=evidence_media(complaint_id,evidence_id)
    except ValueError as exc: raise HTTPException(413,str(exc))
    except Exception:
        logging.getLogger(__name__).exception('Evidence preview failed')
        raise HTTPException(503,'Could not load private media. Please retry.')
    if result is None: raise HTTPException(404,'Media preview unavailable')
    return Response(result[0],media_type=result[1],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.get('/overview')
def overview(days: Literal['7','30','90']='7', region: str | None=None, start_date: date | None=None, end_date: date | None=None):
    if bool(start_date)!=bool(end_date): raise HTTPException(422,'Both start and end dates are required')
    if start_date and not 1<=(end_date-start_date).days+1<=366:
        raise HTTPException(422,'Choose a range of 1 to 366 days')
    try:
        if start_date: return read_overview(int(days),region,start_date,end_date)
        return read_overview(int(days),region)
    except Exception:
        logging.getLogger(__name__).exception('Overview read failed')
        raise HTTPException(503,'Could not calculate this period. Check BigQuery connectivity and retry.')

@router.get('/signals')
def signals():
    try: return {'signals':read_signals()}
    except Exception:
        logging.getLogger(__name__).exception('Signal read failed')
        raise HTTPException(503,'Could not read signals. Check BigQuery connectivity and retry.')

@router.post('/signals/refresh')
def refresh():
    try: return {'signals':refresh_signals()}
    except Exception:
        logging.getLogger(__name__).exception('Signal refresh failed')
        raise HTTPException(503,'Could not refresh signals. The last saved snapshot is unchanged unless the write completed; reload to check.')
