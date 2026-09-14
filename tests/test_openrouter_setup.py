import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location('connect_openrouter',Path(__file__).parents[1]/'scripts/connect_openrouter.py')
setup=importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_setup_updates_existing_connection_without_printing_key(tmp_path,monkeypatch,capsys):
    (tmp_path/'browser-session.json').write_text(json.dumps({'token':'private-session'}))
    monkeypatch.setattr('sys.argv',['connect_openrouter.py','--data-dir',str(tmp_path)])
    monkeypatch.setenv('OPENROUTER_API_KEY','private-api-key')
    calls=[]
    def request(url,headers,body=None):
        calls.append((url,headers.copy(),body))
        if url.endswith('/api/state'):
            return {'token':'csrf','connections':[{'id':'existing','kind':'openai','url':'https://openrouter.ai/api/v1','options':{'temperature':0.3},'purpose':'coding'}]}
        if url.endswith('/key'):return {'data':{}}
        if url.endswith('/discover'):return {'models':['openrouter/free']}
        return {'id':'existing'}
    monkeypatch.setattr(setup,'request',request)
    setup.main()
    payload=calls[2][2]
    assert payload['id']=='existing' and payload['options']=={'temperature':0.3,'free_only':True}
    assert payload['model']=='openrouter/free' and payload['api_key']=='private-api-key'
    assert calls[1][1]=={'Authorization':'Bearer private-api-key'}
    assert 'private-api-key' not in capsys.readouterr().out
