"""Import decoded Gmail connector messages; persist only paper metadata, never a mailbox dump."""
from __future__ import annotations
import argparse
import base64
import json
import re
from datetime import datetime, timedelta, timezone, date
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
from pathlib import Path
from zoneinfo import ZoneInfo
from fetch_reader_sources import parse_scholar_mail
from utils import write_json_atomic

BASE = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Shanghai')


def html_parts(part):
    if part.get('mime_type',part.get('mimeType')) == 'text/html':
        body=part.get('body',{})
        if body.get('content') is not None: yield body['content']
        else:
            data=body.get('base64_url_content') or body.get('data')
            if data: yield base64.urlsafe_b64decode(data+'='*(-len(data)%4)).decode('utf-8',errors='replace')
    for child in part.get('parts') or []: yield from html_parts(child)


def search_plan(target,lookback=7):
    start=datetime.combine(target-timedelta(days=lookback-1),datetime.min.time(),TZ)
    end=datetime.combine(target+timedelta(days=1),datetime.min.time(),TZ)
    return {'date':target.isoformat(),'query':f'from:scholaralerts-noreply@google.com after:{int(start.timestamp())-1} before:{int(end.timestamp())}',
            'start':start.isoformat(),'end_exclusive':end.isoformat()}


def import_messages(payload,inbox:Path,target:date):
    messages=payload.get('messages')
    if not isinstance(messages,list): raise ValueError('messages must be an array')
    count=0
    for message in messages:
        identifier=str(message['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]+',identifier): raise ValueError('Invalid Gmail message ID')
        part=message['payload']; headers={h['name'].lower():h['value'] for h in part.get('headers',[])}
        if parseaddr(headers.get('from',''))[1].lower()!='scholaralerts-noreply@google.com':
            raise ValueError('Only Google Scholar alert messages may be imported')
        html=list(html_parts(part))
        if not html: raise ValueError(f'{identifier}: Gmail HTML body unavailable; do not mark sync successful')
        mail=EmailMessage(); mail['From']=headers['from']
        stamp=message.get('internal_date') or message.get('internalDate')
        mail['Date']=format_datetime(datetime.fromtimestamp(int(stamp)/1000,timezone.utc)) if stamp else headers['date']
        mail.set_content('\n'.join(html),subtype='html')
        papers=parse_scholar_mail(mail.as_bytes())
        if not papers: raise ValueError(f'{identifier}: no paper links parsed; inspect message format')
        for paper in papers: paper['gmail_message_id']=identifier
        write_json_atomic(inbox/f'gmail-{identifier}.json',papers); count+=len(papers)
    status={'date':target.isoformat(),'status':'ok','message_count':len(messages),'paper_count':count,
            'synced_at':datetime.now(TZ).isoformat()}
    write_json_atomic(inbox/'_gmail_sync.json',status)
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['plan','import'])
    parser.add_argument('--date',default='yesterday')
    parser.add_argument('--export',type=Path)
    parser.add_argument('--inbox',type=Path,default=BASE/'data/scholar-inbox')
    args=parser.parse_args()
    today=datetime.now(TZ).date()
    target=today-timedelta(days=1) if args.date=='yesterday' else today if args.date=='today' else date.fromisoformat(args.date)
    if args.stage=='plan': result=search_plan(target)
    else:
        if not args.export: parser.error('import requires --export with decoded connector messages JSON')
        result=import_messages(json.loads(args.export.read_text()),args.inbox,target)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
