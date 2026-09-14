import json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from borgnet.server import create_app


def test_library_roundtrip(tmp_path):
    app=create_app(tmp_path/'state'); identity='20260914-010000-abcdef01'
    directory=tmp_path/'state'/'api-images';directory.mkdir()
    image=directory/identity;data=b'\x89PNG\r\n\x1a\nfixture';image.write_bytes(data)
    app.state.store.write('api-image-history',[{'id':identity}])
    with patch.object(Path,'home',return_value=tmp_path),TestClient(app) as c:
        token=c.get('/api/state').json()['token'];path='/api/images/imagegen/library'
        def post(action,id=identity):return c.post(path,json={'id':id,'action':action})
        assert post('delete').status_code==403
        c.headers['X-BorgNet-Token']=token
        assert post('save','../escape').status_code==404
        assert post('delete').status_code==200
        history=c.get('/api/images/imagegen/history').json()
        assert not history['images'] and history['trash'][0]['id']==identity
        assert image.read_bytes()==data
        assert post('restore').status_code==200
        assert len(c.get('/api/images/imagegen/history').json()['images'])==1
        for _ in range(2):assert post('save').status_code==200
        downloads=list((tmp_path/'Downloads').glob('*.png'))
        assert len(downloads)==2 and all(p.read_bytes()==data for p in downloads)
        response=c.get('/api/images/imagegen/images/'+identity)
        assert response.content==data and response.headers['content-type']=='image/png'


def test_isolation_symlinks_and_opt_in(tmp_path,monkeypatch):
    monkeypatch.delenv('BORGNET_CODEX_IMAGES',raising=False);monkeypatch.delenv('BORGNET_GROK_IMAGES',raising=False)
    a,b=create_app(tmp_path/'a'),create_app(tmp_path/'b')
    assert a.state.image_native.catalog()==[] and a.state.store.config()['connections']==[]
    identity='20260914-010000-abcdef01';d=tmp_path/'a'/'api-images';d.mkdir()
    target=tmp_path/'secret';target.write_text('fixture');(d/identity).symlink_to(target)
    assert a.state.image_api.image_path(identity) is None
    a.state.store.save_secret('image-openai','fixture-key')
    assert b.state.store.read('secrets',{})=={}


def test_failure_messages(tmp_path):
    app=create_app(tmp_path)
    msg=app.state.image_native.no_image_message(json.dumps({'sessionId':'fixture','text':'The request was rejected.','thought':'private reasoning'}))
    assert 'rejected' in msg and 'private reasoning' not in msg
    api=app.state.image_api
    assert 'rejected' in api.image_failure({'promptFeedback':{'blockReason':'SAFETY'}},'gemini')
    assert 'quota' in api.image_failure({},'xai',429)
    assert 'rejected' not in api.image_failure({},'openai')
