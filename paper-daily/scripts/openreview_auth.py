"""OpenReview interactive and scheduled authentication; secrets are never logged."""
from __future__ import annotations
import argparse
import base64
import math
import time
from types import SimpleNamespace
import getpass
import json
import os
import tempfile
import webbrowser
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from utils import requests_get,write_json_atomic,should_use_env_proxy

BASE=Path(__file__).resolve().parents[1]
API_BASE='https://api2.openreview.net'
DEFAULT_TOKEN_FILE=BASE/'.openreview_access_token'
STATUS_FILE=BASE/'data/openreview-auth/status.json'
PRIVATE_CONFIG=Path.home()/'.config/capr/openreview.json'


def token_file() -> Path:
    return Path(os.environ.get('OPENREVIEW_ACCESS_TOKEN_FILE') or DEFAULT_TOKEN_FILE).expanduser()


def openreview_access_token() -> str:
    token=os.environ.get('OPENREVIEW_ACCESS_TOKEN','').strip()
    if token:return token.removeprefix('Bearer ').strip()
    try:return token_file().read_text(encoding='utf-8').strip().removeprefix('Bearer ').strip()
    except OSError:return ''


def metadata_access_status(token: str) -> dict:
    try:
        response=requests_get(API_BASE+'/notes',params={'invitation':'TMLR/-/Submission','limit':1},headers={'Authorization':'Bearer '+token},timeout=20)
        try: data=response.json()
        except ValueError: data={}
        result={'http':response.status_code}
        if response.status_code==200 and isinstance(data.get('notes'),list):
            return dict(result,status='accessible')
        if response.status_code==401:
            return dict(result,status='authentication_failed')
        if response.status_code==403 and data.get('name')=='ChallengeRequiredError':
            result.update(status='challenge_required',error_name='ChallengeRequiredError')
            url=(data.get('details') or {}).get('challengeUrl','')
            parsed=urlparse(url)
            if parsed.scheme=='https' and parsed.hostname=='openreview.net' and parsed.path=='/challenge':
                result['challenge_url']=url
            return result
        return dict(result,status='unavailable')
    except Exception as exc:
        return {'status':'network_error','error_type':type(exc).__name__}


def validate_access_token(token: str) -> bool:
    return metadata_access_status(token)['status']=='accessible'


def save_verified_token(token: str,destination:Path,validator=validate_access_token) -> None:
    if not token or not validator(token):raise RuntimeError('OpenReview credential validation failed')
    destination.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temp=tempfile.mkstemp(prefix='.openreview-token-',dir=destination.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as handle:
            handle.write(token.strip()+'\n')
        os.replace(temp,destination)
        os.chmod(destination,0o600)
    finally:
        Path(temp).unlink(missing_ok=True)


def save_login_session(client,destination:Path,probe=metadata_access_status) -> dict:
    # This client was created by the official username/password login, not from an unverified token.
    token=getattr(client,'token',None)
    profile_id=(getattr(client,'user',None) or {}).get('profile',{}).get('id')
    if not token or not profile_id or getattr(getattr(client,'profile',None),'id',None)!=profile_id:
        raise RuntimeError('Incomplete authenticated login response')
    save_verified_token(token,destination,lambda value:value==token and bool(profile_id))
    # A paper endpoint's anti-bot challenge must not discard an authenticated login session.
    return {'authenticated':True,'metadata':probe(token)}


def report_metadata(result):
    metadata=result['metadata'];state=metadata['status']
    # The challenge URL is used only for the user's normal browser, never logged or solved by code.
    public_meta={k:v for k,v in metadata.items() if k!='challenge_url'}
    if state=='accessible':
        record_status('success',authenticated=True,metadata_access_verified=True)
        print('登录凭证已保存，论文元数据访问正常。现在可以返回 Codex。')
        return 0
    record_status('authenticated_metadata_unavailable',authenticated=True,metadata=public_meta)
    print('账号登录已成功，登录凭证已保存。')
    if state=='challenge_required':
        print('论文接口返回 403 ChallengeRequiredError：需要站点验证，与密码或 MFA 无关。')
        if metadata.get('challenge_url'):
            print('正在打开 OpenReview 返回的官方验证页面，请你在浏览器中手动完成。')
            webbrowser.open(metadata['challenge_url'])
    else:
        print('论文接口暂不可用，状态：'+state+'；无需因此重复输入密码。')
    return 3


def record_status(status: str,**extra):
    payload={'status':status,'updated_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),**extra}
    write_json_atomic(STATUS_FILE,payload)
    return payload


class PasswordLoginError(RuntimeError):
    def __init__(self,status,error_name='LoginError'):
        super().__init__('OpenReview login rejected')
        self.http=status
        self.error_name=error_name if isinstance(error_name,str) and error_name.isidentifier() and len(error_name)<80 else 'LoginError'


def load_private_config(path:Path=PRIVATE_CONFIG) -> dict:
    path=Path(path).expanduser()
    if path.stat().st_uid!=os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('Private configuration must belong to this user and have mode 600')
    try: settings=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError): raise ValueError('Private configuration is not valid JSON') from None
    if not isinstance(settings,dict) or any(not isinstance(settings.get(k),str) or not settings[k] for k in ('username','password')):
        raise ValueError('Private username/password fields must be nonempty strings')
    lifetime=settings.get('token_expires_in_seconds',604800)
    window=settings.get('renew_before_expiry_hours',24)
    if isinstance(lifetime,bool) or not isinstance(lifetime,int) or not 3600<=lifetime<=604800:
        raise ValueError('Requested token lifetime must be 3600 to 604800 seconds')
    if isinstance(window,bool) or not isinstance(window,(int,float)) or not math.isfinite(window) or not 0<window*3600<lifetime:
        raise ValueError('Renewal window must be positive and shorter than requested lifetime')
    return dict(settings,token_expires_in_seconds=lifetime,renew_before_expiry_hours=window)


def token_expiry(token:str):
    # Unverified JWT fields are only scheduling hints. API access is independently checked.
    try:
        encoded=token.split('.')[1]
        claims=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        expiry=float(claims['exp'])
        if not math.isfinite(expiry):return None
        datetime.fromtimestamp(expiry,ZoneInfo('Asia/Shanghai'))
        return expiry
    except (ValueError,KeyError,IndexError,TypeError,OverflowError,OSError): return None


def password_login(settings:dict):
    # Same /login payload used by the official client; one bounded, noninteractive attempt.
    import requests
    with requests.Session() as session:
        session.trust_env=should_use_env_proxy()
        response=session.post(API_BASE+'/login',json={'id':settings['username'],'password':settings['password'],'expiresIn':settings['token_expires_in_seconds']},
            headers={'User-Agent':'CAPR OpenReview authentication/1.0','Accept':'application/json'},timeout=30,allow_redirects=False)
        try:data=response.json()
        except ValueError:raise PasswordLoginError(response.status_code) from None
        if response.status_code!=200:raise PasswordLoginError(response.status_code,data.get('name'))
        if data.get('mfaPending'):raise PasswordLoginError(200,'ManualAuthenticationRequired')
        user=data.get('user') or {}
        return SimpleNamespace(token=data.get('token'),user=user,profile=SimpleNamespace(id=(user.get('profile') or {}).get('id')))


def ensure_access_token(config_path:Path=PRIVATE_CONFIG,force:bool=False) -> dict:
    metadata={};existing_usable=False
    try:
        settings=load_private_config(config_path)
        if os.environ.get('OPENREVIEW_ACCESS_TOKEN','').strip():
            raise ValueError('Static token environment variable overrides the renewed token file')
        token=openreview_access_token()
        expiry=token_expiry(token) if token else None
        if token and not force:
            metadata=metadata_access_status(token)
            metadata={k:v for k,v in metadata.items() if k!='challenge_url'}
            existing_usable=metadata['status']=='accessible'
            if metadata['status'] not in {'accessible','authentication_failed'}:
                return record_status('auto_auth_needs_attention',metadata=metadata,existing_token_usable=False)
            if existing_usable and expiry and expiry-time.time()>settings['renew_before_expiry_hours']*3600:
                return record_status('reused',metadata=metadata,expires_at=datetime.fromtimestamp(expiry,ZoneInfo('Asia/Shanghai')).isoformat(),existing_token_usable=True)
        client=password_login(settings)
        result=save_login_session(client,token_file(),probe=metadata_access_status)
        metadata={k:v for k,v in result['metadata'].items() if k!='challenge_url'}
        expiry=token_expiry(client.token)
        return record_status('renewed',authenticated=True,metadata=metadata,
            expires_at=datetime.fromtimestamp(expiry,ZoneInfo('Asia/Shanghai')).isoformat() if expiry else None,
            existing_token_usable=metadata['status']=='accessible')
    except Exception as exc:
        result={'error_type':type(exc).__name__,'existing_token_usable':existing_usable,'metadata':metadata}
        if isinstance(exc,PasswordLoginError):result.update(http=exc.http,error_name=exc.error_name)
        # Never serialize exception messages: a server error may echo request data.
        return record_status('failed',**result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['login','check','renew'])
    parser.add_argument('--force',action='store_true',help='Force one password login using the private configuration')
    parser.add_argument('--credentials',type=Path,default=PRIVATE_CONFIG)
    args=parser.parse_args()
    if args.stage=='renew':
        result=ensure_access_token(args.credentials,force=args.force)
        print(json.dumps(result,ensure_ascii=False))
        if not result.get('existing_token_usable'):raise SystemExit(3)
        return
    if args.stage=='check':
        token=openreview_access_token()
        metadata=metadata_access_status(token) if token else {'status':'credential_missing'}
        public_meta={k:v for k,v in metadata.items() if k!='challenge_url'}
        print(json.dumps({'credential_present':bool(token),'metadata':public_meta},ensure_ascii=False))
        if metadata['status']!='accessible':raise SystemExit(3)
        record_status('success',authenticated=True,metadata_access_verified=True)
        return
    record_status('awaiting_local_input')
    print('OpenReview 本地登录设置\n账号、密码仅提交给 OpenReview 官方 API；密码不保存、不写入聊天。')
    phase='credential_login'
    try:
        username=input('OpenReview 登录邮箱：').strip()
        password=getpass.getpass('OpenReview 密码（输入时不会显示）：')
        if not username or not password:raise ValueError('Account and password are required')
        import openreview
        client=openreview.api.OpenReviewClient(baseurl=API_BASE,username=username,password=password)
        password=''
        phase='saving_authenticated_session'
        result=save_login_session(client,token_file())
        exit_code=report_metadata(result)
        if os.environ.get('OPENREVIEW_ACCESS_TOKEN'):
            print('注意：已有环境变量会优先于本地文件；请移除旧 OPENREVIEW_ACCESS_TOKEN。')
        if exit_code:raise SystemExit(exit_code)
    except (KeyboardInterrupt,EOFError):
        record_status('cancelled');print('\n已取消；原凭证未更改。');raise SystemExit(1)
    except Exception as exc:
        # API error payloads can contain auth context; never dump exception messages or a traceback.
        record_status('failed',phase=phase,error_type=type(exc).__name__)
        print('\n设置未完成，阶段：'+phase+'（'+type(exc).__name__+'）。账号认证与论文接口访问是独立步骤，请返回 Codex 查看诊断。')
        raise SystemExit(2)

if __name__=='__main__':main()
