import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))


def test_client_uses_configured_token(monkeypatch):
    import fetch_openreview as source
    monkeypatch.setenv('OPENREVIEW_ACCESS_TOKEN','private-test-token')
    calls=[]
    factory=lambda **kw: calls.append(kw) or SimpleNamespace()
    source._make_client(SimpleNamespace(api=SimpleNamespace(OpenReviewClient=factory)),[])
    assert calls[0].get('token')=='private-test-token'


def test_http_fallback_carries_same_auth(monkeypatch):
    import fetch_openreview as source
    monkeypatch.setenv('OPENREVIEW_ACCESS_TOKEN','private-test-token')
    observed=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"notes":[]}'
    def fake_open(request,**kwargs):
        observed.append(request.get_header('Authorization'));return Response()
    monkeypatch.setattr(source,'http_open',fake_open)
    source._get_notes_http('TMLR/-/Submission',1)
    source._get_notes_http_page('TMLR/-/Submission',1,0)
    assert observed==['Bearer private-test-token','Bearer private-test-token']


def test_credentials_saved_privately_only_after_validation(tmp_path):
    from openreview_auth import save_verified_token
    destination=tmp_path/'token';destination.write_text('old-token')
    with pytest.raises(RuntimeError):save_verified_token('new-token',destination,lambda token:False)
    assert destination.read_text()=='old-token'
    save_verified_token('new-token',destination,lambda token:True)
    assert destination.read_text()=='new-token\n'
    assert destination.stat().st_mode & 0o777 == 0o600


def test_successful_login_is_preserved_when_metadata_requires_challenge(tmp_path):
    from openreview_auth import save_login_session
    client=SimpleNamespace(token='fresh-token',user={'profile':{'id':'~Test_User1'}},profile=SimpleNamespace(id='~Test_User1'))
    destination=tmp_path/'token'
    result=save_login_session(client,destination,lambda token:{'status':'challenge_required','http':403,'error_name':'ChallengeRequiredError'})
    assert destination.read_text()=='fresh-token\n'
    assert result['authenticated'] is True
    assert result['metadata']['status']=='challenge_required'


def test_incomplete_login_response_cannot_replace_credential(tmp_path):
    from openreview_auth import save_login_session
    destination=tmp_path/'token';destination.write_text('old')
    with pytest.raises(RuntimeError):save_login_session(SimpleNamespace(token='unverified',user={},profile=None),destination)
    assert destination.read_text()=='old'


def test_challenge_error_is_distinct_from_invalid_auth(monkeypatch):
    import openreview_auth as auth
    response=SimpleNamespace(status_code=403,json=lambda:{'name':'ChallengeRequiredError','details':{'challengeUrl':'https://openreview.net/challenge?test=1'}})
    monkeypatch.setattr(auth,'requests_get',lambda *a,**kw:response)
    assert auth.metadata_access_status('test')['status']=='challenge_required'
    response.status_code=401
    assert auth.metadata_access_status('test')['status']=='authentication_failed'


def make_jwt(exp):
    import base64,json
    return 'header.'+base64.urlsafe_b64encode(json.dumps({'exp':exp}).encode()).decode().rstrip('=')+'.signature'


def test_renewal_reads_private_config_requests_week_and_saves_actual_expiry(tmp_path,monkeypatch,capsys):
    import openreview_auth as auth,json,time
    config=tmp_path/'private.json';config.write_text(json.dumps({'username':'test@example.org','password':'PRIVATE_TEST_PASSWORD','token_expires_in_seconds':604800,'renew_before_expiry_hours':24}));config.chmod(0o600)
    destination=tmp_path/'token';destination.write_text('old')
    new_token=make_jwt(int(time.time())+604800)
    def login(settings):
        assert settings['password']=='PRIVATE_TEST_PASSWORD'
        assert settings['token_expires_in_seconds']==604800
        return SimpleNamespace(token=new_token,user={'profile':{'id':'~Test_User1'}},profile=SimpleNamespace(id='~Test_User1'))
    monkeypatch.setattr(auth,'password_login',login,raising=False)
    monkeypatch.setattr(auth,'token_file',lambda:destination)
    monkeypatch.setattr(auth,'metadata_access_status',lambda token:{'status':'accessible','http':200})
    monkeypatch.setattr(auth,'STATUS_FILE',tmp_path/'status.json')
    result=auth.ensure_access_token(config,force=True)
    assert result['status']=='renewed' and result['metadata']['status']=='accessible'
    assert destination.read_text().strip()==new_token
    assert 'PRIVATE_TEST_PASSWORD' not in json.dumps(result)+capsys.readouterr().out+(tmp_path/'status.json').read_text()


def test_reuses_healthy_long_lived_token_without_password_login(tmp_path,monkeypatch):
    import openreview_auth as auth,json,time
    config=tmp_path/'private.json';config.write_text(json.dumps({'username':'x','password':'secret'}));config.chmod(0o600)
    monkeypatch.setattr(auth,'openreview_access_token',lambda:make_jwt(int(time.time())+604800))
    monkeypatch.setattr(auth,'metadata_access_status',lambda token:{'status':'accessible','http':200})
    monkeypatch.setattr(auth,'password_login',lambda settings:pytest.fail('unnecessary login'),raising=False)
    monkeypatch.setattr(auth,'STATUS_FILE',tmp_path/'status.json')
    assert auth.ensure_access_token(config)['status']=='reused'


def test_renewal_failure_preserves_token_and_never_leaks_error_payload(tmp_path,monkeypatch):
    import openreview_auth as auth,json
    config=tmp_path/'private.json';config.write_text(json.dumps({'username':'x','password':'PRIVATE_TEST_PASSWORD'}));config.chmod(0o600)
    destination=tmp_path/'token';destination.write_text('existing')
    monkeypatch.setattr(auth,'token_file',lambda:destination)
    monkeypatch.setattr(auth,'STATUS_FILE',tmp_path/'status.json')
    def login(settings):raise RuntimeError('remote payload PRIVATE_TEST_PASSWORD')
    monkeypatch.setattr(auth,'password_login',login,raising=False)
    result=auth.ensure_access_token(config,force=True)
    assert result['status']=='failed' and destination.read_text()=='existing'
    assert 'PRIVATE_TEST_PASSWORD' not in json.dumps(result)+(tmp_path/'status.json').read_text()


def test_private_config_rejects_world_readable_file(tmp_path):
    import openreview_auth as auth
    config=tmp_path/'private.json';config.write_text('{"username":"x","password":"secret"}');config.chmod(0o644)
    with pytest.raises(ValueError):auth.load_private_config(config)


def test_renews_near_expiry_without_force(tmp_path,monkeypatch):
    import openreview_auth as auth,json,time
    config=tmp_path/'private.json';config.write_text(json.dumps({'username':'x','password':'secret'}));config.chmod(0o600)
    destination=tmp_path/'token';destination.write_text(make_jwt(int(time.time())+3600))
    new_token=make_jwt(int(time.time())+604800);calls=[]
    monkeypatch.setattr(auth,'token_file',lambda:destination)
    monkeypatch.delenv('OPENREVIEW_ACCESS_TOKEN',raising=False)
    monkeypatch.setattr(auth,'STATUS_FILE',tmp_path/'status.json')
    monkeypatch.setattr(auth,'metadata_access_status',lambda token:{'status':'accessible','http':200})
    monkeypatch.setattr(auth,'password_login',lambda settings:calls.append('login') or SimpleNamespace(token=new_token,user={'profile':{'id':'~User1'}},profile=SimpleNamespace(id='~User1')))
    assert auth.ensure_access_token(config)['status']=='renewed'
    assert calls==['login'] and destination.read_text().strip()==new_token


def test_site_challenge_does_not_trigger_repeated_password_login(tmp_path,monkeypatch):
    import openreview_auth as auth,json,time
    config=tmp_path/'private.json';config.write_text(json.dumps({'username':'x','password':'secret'}));config.chmod(0o600)
    monkeypatch.setattr(auth,'openreview_access_token',lambda:make_jwt(int(time.time())+604800))
    monkeypatch.setattr(auth,'STATUS_FILE',tmp_path/'status.json')
    monkeypatch.setattr(auth,'metadata_access_status',lambda token:{'status':'challenge_required','http':403,'challenge_url':'https://openreview.net/challenge?private=1'})
    monkeypatch.setattr(auth,'password_login',lambda settings:pytest.fail('challenge is not fixed by password retries'))
    result=auth.ensure_access_token(config)
    assert result['status']=='auto_auth_needs_attention'
    assert 'challenge_url' not in result['metadata']
