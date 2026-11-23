"""Deep resource knowledge grounded to exact evidence quotes.

Fields are creator/document claims. Independent README verification is a separate step.
"""
from dataclasses import dataclass
import re
from .contracts import Observation,canonical_resource

FACT_KINDS={'purpose','feature','use_case','setup','dependency','command','limitation','example','workflow','cost','risk','integration'}

@dataclass(frozen=True)
class EvidenceClaim:
    resource_url:str
    field_type:str
    value:str
    evidence_id:str
    verbatim_quote:str


def validate_claims(claims:list[EvidenceClaim],evidence:list[Observation],supported_urls:set[str])->tuple[list[EvidenceClaim],list[dict]]:
    ids={e.uid:e for e in evidence}
    urls=set(supported_urls)
    valid=[];rejected=[]
    for c in claims:
        reason=None
        try:url=canonical_resource(c.resource_url)
        except ValueError:url=None
        if url not in urls:reason='resource_not_supported'
        elif c.field_type not in FACT_KINDS:reason='invalid_fact_type'
        elif c.evidence_id not in ids:reason='missing_evidence'
        elif ids[c.evidence_id].kind not in {'ocr','asr','caption','document','manual','verified_doc'}:
            reason='not_primary_source_evidence'
        elif len(c.value.strip())>1200 or not c.value.strip():reason='invalid_value'
        elif not c.verbatim_quote.strip() or c.verbatim_quote not in ids[c.evidence_id].text:reason='quote_not_in_evidence'
        else:
            val_tokens=set(re.findall(r'[a-z0-9]+',c.value.lower()))
            quote_tokens=set(re.findall(r'[a-z0-9]+',c.verbatim_quote.lower()))
            if val_tokens and len(val_tokens&quote_tokens)/len(val_tokens)<.70:reason='value_not_supported_by_quote'
        if reason:rejected.append({'url':c.resource_url,'field_type':c.field_type,'reason':reason})
        else:valid.append(c)
    return valid,rejected
