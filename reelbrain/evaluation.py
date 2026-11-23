"""Non-empty independently labeled golden set required before any quality pass claim."""
from .contracts import canonical_resource

def evaluate(ground_truth:list[str],predicted:list[str],unsupported:int=0)->dict:
    def normalize(xs):
        out=set()
        for s in xs:
            try:out.add(canonical_resource(s))
            except ValueError:out.add(s)
        return out
    gt,pr=normalize(ground_truth),normalize(predicted)
    tp=len(gt&pr);precision=(tp/len(pr) if pr else 0.0);recall=(tp/len(gt) if gt else 0.0)
    return {'precision':precision,'recall':recall,'true_positives':tp,'false_positives':sorted(pr-gt),'false_negatives':sorted(gt-pr),'unsupported':unsupported,'gate_pass':bool(gt and precision>=.98 and recall>=.95 and unsupported==0)}
