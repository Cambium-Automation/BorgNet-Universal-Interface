from fastapi.testclient import TestClient as BaseClient

class TestClient(BaseClient):
    __test__ = False
    def __init__(self, app, **kwargs):
        headers = kwargs.pop('headers', {})
        super().__init__(app, base_url='http://127.0.0.1', headers={'X-BorgNet-Session': app.state.session_token, **headers}, **kwargs)
