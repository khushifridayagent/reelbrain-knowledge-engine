"""One-time pre-warm of the separate Studio index; no scheduler or production writes."""
from .api import Services
if __name__=='__main__':
    s=Services();s.open()
    while True:
        state=s.db.refresh(s.index,max_sources=25);print(state,flush=True)
        if not state['more_pending']:break
