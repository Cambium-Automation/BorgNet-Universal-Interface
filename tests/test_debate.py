import asyncio
import pytest
from borgnet.debate import debate
from borgnet.config import Connection, Store
from borgnet.permissions import discussion_only, effective

class Peers:
    def __init__(self, tmp_path, reject=False, fail=False):
        self.store=Store(tmp_path); self.calls=[]; self.reject=reject; self.fail=fail
        config=self.store.config();config['permissions']={'defaults':{'full_access':True}}
        self.store.write('config',config)
    async def stream_chat(self,item,messages,system,on_delta=None):
        import json
        data=json.loads(messages[0]['content']);self.calls.append((item.id,system,data,discussion_only.get()))
        assert effective(self.store,item).full_access == (not discussion_only.get())
        if 'Implement the agreed' in system: text='Changed fixture; verification passed (mock).'
        elif 'Challenge the CURRENT' in system:
            if self.fail and item.id=='c1': raise ValueError('Offline')
            text='There is a concrete missing check.\nDISAGREE R'+str(data['revision']) if self.reject or data['revision']==1 else 'The revised check resolves my objection.\nAGREE R'+str(data['revision'])
        else: text='A complete plan with a concrete acceptance check.'
        await on_delta(text)
        return text

def members():
    return [Connection(id=f'c{i}',kind='cli',cli_provider='codex',url='http://localhost',model='default') for i in range(3)]

async def run(peers, **kwargs):
    record={'results':[]}
    events=[e async for e in debate(peers,members(),'Fix a test fixture','Shared acceptance criteria',[], 'c0',record,**kwargs)]
    return record,events

async def test_revision_specific_unanimity_and_context(tmp_path):
    peers=Peers(tmp_path)
    record,events=await run(peers)
    assert record['consensus'] is True
    assert len(record['debate_rounds'])==2
    assert [c[0] for c in peers.calls]==['c0','c1','c2','c0','c1','c0','c2','c1']
    assert all(c[3] for c in peers.calls)
    assert all(c[2]['reference_data']=='Shared acceptance criteria' for c in peers.calls)
    assert any(e['type']=='delta' for e in events)
    assert record['results'][-1]['status']=='complete'

@pytest.mark.parametrize('failure', [False,True])
async def test_dissent_and_failure_never_trigger_execution(tmp_path,failure):
    peers=Peers(tmp_path,reject=not failure,fail=failure)
    record,_=await run(peers,rounds=2,implement=True,executor_id='c0')
    assert record['consensus'] is False
    assert record['results'][-1]['status']=='partial'
    assert all(c[3] for c in peers.calls)

async def test_single_executor_only_after_consensus(tmp_path):
    peers=Peers(tmp_path)
    record,_=await run(peers,implement=True,executor_id='c2')
    executions=[c for c in peers.calls if not c[3]]
    assert len(executions)==1 and executions[0][0]=='c2'
    assert record['consensus'] is True
    assert 'Executor report' in record['results'][-1]['text']
    assert not discussion_only.get()

async def test_deadline_keeps_record(tmp_path):
    peers=Peers(tmp_path)
    async def slow(*args,**kwargs): await asyncio.sleep(1)
    peers.stream_chat=slow
    record,_=await run(peers,deadline=.01)
    assert record['consensus'] is False
    assert 'time limit' in record['results'][-1]['text']

async def test_cancellation_stops_provider(tmp_path):
    peers=Peers(tmp_path); cancelled=asyncio.Event()
    async def slow(*args,**kwargs):
        try: await asyncio.sleep(30)
        finally: cancelled.set()
    peers.stream_chat=slow
    gen=debate(peers,members(),'question','',[],'',{'results':[]})
    await anext(gen)
    await asyncio.sleep(.01)
    await gen.aclose()
    assert cancelled.is_set()

async def test_api_debate_is_recorded_and_implementation_requires_permissions(tmp_path):
    from tests.client import TestClient
    from borgnet.server import create_app
    import json
    app=create_app(tmp_path)
    with TestClient(app) as client:
        headers={'X-BorgNet-Token':client.get('/api/state').json()['token']}
        for c in members():
            assert client.post('/api/connections',json=c.model_dump(),headers=headers).status_code==200
        data={'prompt':'Discuss a fixture','connections':['c0','c1','c2'],'collaboration_mode':'debate','implement':True,'executor':'c0'}
        assert client.post('/api/dispatch',json=data,headers=headers).status_code==400
        peers=Peers(tmp_path/'fixture')
        app.state.providers.stream_chat=peers.stream_chat
        data['implement']=False
        response=client.post('/api/dispatch',json=data,headers=headers)
        assert response.status_code==200
        events=[json.loads(line) for line in response.text.splitlines()]
        assert events[-1]['type']=='done'
        assert any(e.get('consensus') is True for e in events)
        assert app.state.store.read('history',[])[-1]['mode']=='debate'


async def test_oversized_or_conflicting_assent_never_counts(tmp_path):
    peers = Peers(tmp_path)
    async def malicious(item, messages, system, on_delta):
        if 'Challenge the CURRENT' in system:
            return ('x' * (24000 - len('\nAGREE R1')) + '\nAGREE R1' + '\nDISAGREE R1'
                    if item.id == 'c1' else 'DISAGREE R1\nAGREE R1')
        return 'Candidate'
    peers.stream_chat = malicious
    record, _ = await run(peers, rounds=1, implement=True, executor_id='c0')
    assert record['consensus'] is False
    assert not record['debate_rounds'][0]['accepted']
