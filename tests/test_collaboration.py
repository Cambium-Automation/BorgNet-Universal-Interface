import asyncio
import json
import pytest
from borgnet.collaboration import collaborate, validate_ballot
from borgnet.config import Connection


class CouncilFixture:
    def __init__(self, task_type='question', failed=(), bad_reviews=False):
        self.calls=[];self.task_type=task_type;self.failed=failed;self.bad_reviews=bad_reviews
    async def chat(self,item,messages,system,response_schema=None):
        self.calls.append((item.id,system,messages))
        if 'PROPOSAL ROUND' in system:
            if item.id in self.failed:
                raise ValueError('Fixture unavailable')
            return 'Supported proposal from '+item.id
        data=json.loads(messages[0]['content'])
        if 'PEER REVIEW ROUND' in system:
            if self.bad_reviews:return 'Not a structured ballot'
            return json.dumps({'task_type':self.task_type,'ranking':[{'proposal_id':p['proposal_id'],'score':5 if p['proposal_id']=='P2' else 3,'reason':'Specific evidence and feasible steps'} for p in data['proposals'] if p['proposal_id']!=data['your_proposal_id']], 'concerns':['One assumption remains unverified']})
        assert 'FINAL DECISION' in system
        return json.dumps({'task_type':self.task_type,'selected_proposals':[data['allowed_selections'][0]],'answer':'The strongest supported answer.','implementation_plan':['Implement the selected change'] if self.task_type=='implementation' else [],'verification_plan':['Run the relevant regression check'] if self.task_type=='implementation' else [],'risks':['One assumption remains unverified']})


async def run(fixture):
    items=[Connection(id=f'c{i}',url='http://localhost:1234',model='fixture-chat') for i in range(3)]
    record={'results':[]}
    events=[event async for event in collaborate(fixture,items,'Operator request','',[],'c0',record,deadline=1)]
    return events,record


async def test_question_has_real_peer_review_and_ranked_final_answer():
    fixture=CouncilFixture()
    events,record=await run(fixture)
    assert len([c for c in fixture.calls if 'PROPOSAL ROUND' in c[1]])==3
    assert len([c for c in fixture.calls if 'PEER REVIEW ROUND' in c[1]])==3
    assert record['ranking'][0]['proposal_id']=='P2'
    final=record['results'][-1]
    assert final['phase']=='final' and final['status']=='complete'
    assert final['decision']['selected_proposals']==['P2']
    assert 'Implementation plan' not in final['text']
    assert [e['phase'] for e in events if e['type']=='phase']==['proposal','review']


async def test_implementation_selects_ranked_proposals_with_plans():
    _,record=await run(CouncilFixture(task_type='implementation'))
    final=record['results'][-1]
    assert final['decision']['selected_proposals']==['P2']
    assert 'Implementation plan' in final['text'] and 'Verification plan' in final['text']
    assert final['decision']['risks']


async def test_missing_proposer_is_explicit_partial_participation():
    _,record=await run(CouncilFixture(failed=('c2',)))
    final=record['results'][-1]
    assert final['status']=='partial'
    assert 'Participation was incomplete' in final['text']
    assert len(record['ranking'])==2


async def test_no_quorum_means_no_claimed_decision():
    fixture=CouncilFixture(bad_reviews=True)
    _,record=await run(fixture)
    assert record['results'][-1]['status']=='error'
    assert 'valid reviews' in record['results'][-1]['error']
    assert not any('FINAL DECISION' in call[1] for call in fixture.calls)
    assert len([c for c in fixture.calls if 'PEER REVIEW ROUND' in c[1]])==6


async def test_only_one_proposal_cannot_claim_collaboration():
    _,record=await run(CouncilFixture(failed=('c1','c2')))
    assert 'at least two' in record['results'][-1]['error']
    assert 'ranking' not in record


@pytest.mark.parametrize('ids',[['P1','P2'],['P2','P2'],['P3'],['P2','unknown']])
def test_self_votes_duplicates_missing_and_unknown_proposals_rejected(ids):
    text=json.dumps({'task_type':'question','ranking':[{'proposal_id':identity,'score':4,'reason':'Evidence'} for identity in ids]})
    with pytest.raises(ValueError):validate_ballot(text,'P1',['P1','P2','P3'])


async def test_invalid_coordinator_retries_with_another_participant():
    class Fallback(CouncilFixture):
        async def chat(self,item,messages,system,response_schema=None):
            if 'FINAL DECISION' in system and item.id=='c0':return '{}'
            return await super().chat(item,messages,system)
    _,record=await run(Fallback())
    finals=[r for r in record['results'] if r['phase']=='final']
    assert finals[0]['status']=='error' and finals[1]['status']=='complete'
    assert finals[1]['connection']!='c0'


def test_api_defaults_to_collaboration_and_preserves_final_in_history(tmp_path, monkeypatch):
    from tests.client import TestClient
    from borgnet.server import create_app
    app = create_app(tmp_path)
    fixture = CouncilFixture()
    monkeypatch.setattr(app.state.providers, 'chat', fixture.chat)
    with TestClient(app) as client:
        token = client.get('/api/state').json()['token']
        client.headers['X-BorgNet-Token'] = token
        ids = []
        for i in range(3):
            response = client.post('/api/connections', json={'url':'http://localhost:1234', 'model':'fixture-chat', 'id':f'c{i}'})
            assert response.status_code == 200
            ids.append(response.json()['id'])
        response = client.post('/api/dispatch', json={'prompt':'What is the answer?', 'connections':ids})
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[-1]['type'] == 'done'
        finals = [e for e in events if e['type']=='result' and e['phase']=='final']
        assert len(finals) == 1 and finals[0]['status'] == 'complete'
        history = client.get('/api/state').json()['history']
        assert history[-1]['results'][-1]['decision']['selected_proposals'] == ['P2']
        assert len(fixture.calls) == 7


def test_fifty_connections_dispatch_review_and_capacity_boundary(tmp_path, monkeypatch):
    from tests.client import TestClient
    from borgnet.server import create_app
    app = create_app(tmp_path)
    fixture = CouncilFixture()
    monkeypatch.setattr(app.state.providers, 'chat', fixture.chat)
    with TestClient(app) as client:
        client.headers['X-BorgNet-Token'] = client.get('/api/state').json()['token']
        ids = [f'c{i}' for i in range(50)]
        for identity in ids:
            assert client.post('/api/connections', json={'id':identity,'url':'http://localhost:1234','model':'fixture-chat'}).status_code == 200
        # Editing at capacity is allowed; adding a 51st preserves both config and secrets.
        assert client.post('/api/connections', json={'id':ids[0],'url':'http://localhost:1234','model':'fixture-chat','purpose':'Updated'}).status_code == 200
        rejected = client.post('/api/connections', json={'id':'overflow','url':'http://localhost:1234','model':'fixture-chat','api_key':'fixture-overflow-secret'})
        assert rejected.status_code == 400 and '50' in rejected.json()['error']
        assert len(client.get('/api/state').json()['connections']) == 50
        assert 'overflow' not in app.state.store.read('secrets', {})
        assert client.post('/api/dispatch', json={'prompt':'Question','connections':ids+['overflow']}).status_code == 422
        response = client.post('/api/dispatch', json={'prompt':'Choose the strongest answer','connections':ids})
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        reviews = [e for e in events if e['type']=='result' and e['phase']=='review']
        assert len(reviews) == 50
        assert all(e['status']=='complete' and len(e['ballot']['ranking'])==49 for e in reviews)
        final = next(e for e in events if e['type']=='result' and e['phase']=='final')
        assert final['status']=='complete' and len(final['ranking'])==50
        assert all(row['reviews']==49 for row in final['ranking'])
        assert len(fixture.calls)==101
        assert client.get('/api/state').json()['history'][-1]['results'][-1]['phase']=='final'


async def test_review_schema_excludes_self_and_requires_all_peer_slots():
    class Structured(CouncilFixture):
        async def chat(self,item,messages,system,response_schema=None):
            if 'PEER REVIEW ROUND' in system:
                data=json.loads(messages[0]['content'])
                peers=data['required_peer_ids']
                assert data['your_proposal_id'] not in peers
                assert data['your_proposal_id'] not in [p['proposal_id'] for p in data['proposals']]
                assert response_schema['$defs']['Vote']['properties']['proposal_id']['enum']==peers
                assert response_schema['properties']['ranking']['minItems']==2
                assert response_schema['properties']['ranking']['maxItems']==2
            elif 'FINAL DECISION' in system:
                assert response_schema is None
            else:
                assert response_schema is None
                assert 'You are the participant running model fixture-chat.' in system
            return await super().chat(item,messages,system,response_schema)
    _,record=await run(Structured())
    assert record['results'][-1]['status']=='complete'
