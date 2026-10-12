"""Apply explicit text corrections without discarding independent media evidence."""
import re
from app.models.taxonomy import Extraction


def merge_correction(previous, current, correction, message, evidence):
    prior = previous.model_dump(mode='json') if previous else None
    data = (current or previous).model_dump(mode='json') if (current or previous) else None
    if data is None:
        return None, None
    protected = {s for item in evidence for s in item.get('extracted_symptoms', [])}
    if previous and previous.media_findings:
        protected.update(s.value for s in previous.media_findings.symptoms)
    removed = set()
    clarification = None
    # A vague typo must not be interpreted as a resolution, even if the model misses it.
    vague = re.fullmatch(r"(?:sorry[, ]*)?(?:it|that|this)?\s*(?:was|is)?\s*(?:a\s*)?(?:typo|typo error|mistake)[.! ]*", message.strip(), re.I)
    if correction or vague:
        quote = correction.quote.strip() if correction else ''
        explicit = (correction and correction.status == 'explicit' and quote
                    and quote.casefold() in message.casefold() and not vague)
        if explicit:
            requested = {s.value for s in correction.retracted_symptoms}
            removed = requested - protected
            if requested & protected:
                clarification = 'Thanks for clarifying. The uploaded evidence still contains a conflicting finding. Which observation in the file is incorrect? Keep following the safety advice while we clarify this.'
        else:
            clarification = 'Thanks for clarifying. What was incorrect in your earlier message, and what is actually happening with the shaver?'
    symptoms = list(dict.fromkeys([*((prior or {}).get('symptoms', [])), *data['symptoms'], *sorted(protected)]))
    data['symptoms'] = [s for s in symptoms if s not in removed] or ['unclear_description']
    if removed:
        # Never retain a stale model summary or RAG query containing a retracted hazard.
        data['complaint_summary'] = 'Reported findings: ' + ', '.join(s.replace('_', ' ') for s in data['symptoms']) + '.'
        data['retrieval_query'] = None
    return Extraction.model_validate(data), clarification
