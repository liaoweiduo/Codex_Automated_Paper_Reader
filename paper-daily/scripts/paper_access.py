"""Durable user-download queue for confirmed publisher access restrictions."""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from utils import write_json_atomic

BLOCKED_STATUSES={'paywalled','institutional_access_required'}
START='<!-- CAPR-PENDING-START -->'
END='<!-- CAPR-PENDING-END -->'


def queue_path(base):return base/'data/unified/pending_downloads.json'


def load_queue(base):
    path=queue_path(base)
    return json.loads(path.read_text()) if path.exists() else {}


def queue_note(vault):return vault/'Research Notes/待下载论文.md'


def render_queue(base,vault,tasks):
    lines=['## 待下载与待解读清单','', '下载后放到对应保存位置，或在聊天里附上 PDF。文件到达后仍需精读核验，才会标为完成。','']
    if not tasks:lines.append('当前没有待下载论文。')
    for task in tasks.values():
        title=str(task.get('title',task['key'])).replace('\n',' ')
        status=task['status'];done=status=='completed'
        lines.extend([f"- [{'x' if done else ' '}] **{title}** — {status}",
            f"  - 论文页面：{task.get('url','')}",f"  - 匹配原因：{task.get('reason','')}",
            f"  - 正文访问证据：{task.get('access_evidence','')} ({task.get('access_evidence_url','')})",
            f"  - PDF 保存位置：`{task.get('pdf_target','')}`",
            f"  - 笔记：[[{task.get('note','').removesuffix('.md')}]]；发现日期：{task.get('discovered','')}；层级：{task.get('level','')}",''])
    block=START+'\n'+'\n'.join(lines)+'\n'+END
    path=queue_note(vault);path.parent.mkdir(parents=True,exist_ok=True)
    text=path.read_text() if path.exists() else '---\ntype: reading-queue\n---\n\n# 待下载论文\n'
    if START in text and END in text:
        before,tail=text.split(START,1);_,after=tail.split(END,1);text=before+block+after
    else:text=text.rstrip()+'\n\n'+block+'\n'
    path.write_text(text)
    write_json_atomic(queue_path(base),tasks)


def pending_downloads(base,config):
    vault=Path(config['vault']).expanduser().resolve();tasks=load_queue(base)
    for task in tasks.values():
        if task['status']=='completed':continue
        target=Path(task['pdf_target']).resolve()
        if not target.is_relative_to(vault/'Attachments/Paper PDFs'):raise ValueError('Unsafe pending PDF target')
        present=False
        if target.is_file():
            with target.open('rb') as handle:present=handle.read(5)==b'%PDF-'
        task['status']='ready_for_reading' if present else 'awaiting_download'
    render_queue(base,vault,tasks)
    return [task for task in tasks.values() if task['status']!='completed']


def register_download(base,config,paper,item,note,out):
    if not paper['archive'] or item.get('fulltext_status') not in BLOCKED_STATUSES:return None
    evidence_url=str(item.get('access_evidence_url',''))
    if urlparse(evidence_url).scheme not in {'http','https'} or not str(item.get('access_evidence','')).strip():
        raise ValueError('A paid/fulltext access restriction needs publisher-page evidence')
    key=paper['reader_key']
    if not re.fullmatch('[A-Za-z0-9_-]+',key):raise ValueError('Invalid paper key')
    vault=Path(config['vault']).expanduser().resolve();tasks=load_queue(base)
    if tasks.get(key,{}).get('status')=='completed':return None
    target=vault/'Attachments/Paper PDFs'/f'{key}.pdf';target.parent.mkdir(parents=True,exist_ok=True)
    reason='；'.join(m['reason'] for m in paper['matches'])
    task=dict(tasks.get(key,{}),key=key,id=paper['id'],title=paper['title'],url=paper.get('url','') or evidence_url,
        level=paper['level'],matches=paper['matches'],reason=reason,access_evidence=item['access_evidence'],access_evidence_url=evidence_url,
        pdf_target=str(target),note=str(note.relative_to(vault)),source_run=str(out),discovered=tasks.get(key,{}).get('discovered',out.name),status='awaiting_download')
    tasks[key]=task;render_queue(base,vault,tasks)
    return next((row for row in pending_downloads(base,config) if row['key']==key),None)


def resolve_download(base,config,key,note,validator):
    vault=Path(config['vault']).expanduser().resolve();tasks=load_queue(base)
    if key not in tasks:raise ValueError('Unknown pending download key')
    path=(vault/note).resolve()
    if not path.is_relative_to(vault/'Papers'):raise ValueError('Resolved note must be inside Papers')
    check=validator(path,vault)
    if not check['complete']:raise ValueError('Paper reading/figures are still incomplete')
    import yaml
    metadata=yaml.safe_load(path.read_text().split('---',2)[1])
    if str(metadata.get('paper_id'))!=str(tasks[key]['id']):raise ValueError('Resolved note belongs to a different paper')
    tasks[key].update(status='completed',note=str(path.relative_to(vault)),completed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    render_queue(base,vault,tasks)
    return tasks[key]
