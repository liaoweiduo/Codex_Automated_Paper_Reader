"""One daily discovery/reading handoff. Python never invents paper analysis."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import yaml
from fetch_arxiv import fetch_arxiv
from fetch_openreview import fetch_openreview
from openreview_auth import ensure_access_token as ensure_openreview_auth
from fetch_openalex import fetch_openalex
from fetch_pubmed import fetch_pubmed
from fetch_crossref import fetch_crossref
from fetch_europepmc import fetch_europepmc
from fetch_osf_psyarxiv import fetch_psyarxiv
from fetch_reader_sources import fetch_nature, fetch_scholar_mail
from process_conference_paper import extract_pdf_text, openreview_access_token
from utils import dedupe_papers, setup_logger, write_json_atomic, requests_get
import paper_access

BASE = Path(__file__).resolve().parents[1]
THRESHOLDS = {'level0': .7, 'level1': .8, 'level2': .6}


def normalize_interests(config: dict) -> list[dict]:
    topics, seen = [], set()
    for level in THRESHOLDS:
        items = config.get(level, [])
        if not isinstance(items, list): raise ValueError(f'{level} must be an array')
        for item in items:
            topic = {'label': item} if isinstance(item, str) else dict(item)
            label = topic.get('label','')
            if not isinstance(label,str) or not label.strip(): raise ValueError('Topic label is required')
            key = topic.get('id',label)
            if not isinstance(key,str) or key in seen: raise ValueError(f'Duplicate/invalid topic: {key}')
            seen.add(key)
            queries = topic.get('queries',[])
            if not isinstance(queries,list) or any(not isinstance(q,str) for q in queries): raise ValueError('queries must be a string array')
            topics.append(dict(topic, id=key, label=label.strip(), level=level, queries=queries))
    if not topics: raise ValueError('At least one topic is required')
    return topics


def route_paper(paper: dict, matches: list, topics: list, thresholds=None) -> dict:
    lookup = {t['id']:t for t in topics}; accepted = []
    for match in matches:
        if match['topic'] not in lookup: raise ValueError(f"Unknown topic: {match['topic']}")
        confidence = match['confidence']
        if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('confidence must be finite and between zero and one')
        if not str(match.get('reason','')).strip(): raise ValueError('Evidence-based matching reason required')
        topic = lookup[match['topic']]
        if confidence >= (thresholds or THRESHOLDS)[topic['level']]:
            accepted.append(dict(match, level=topic['level']))
    level = min((m['level'] for m in accepted), default=None)
    return dict(paper, matches=accepted, level=level, archive=level in {'level0','level1'}, notify=level=='level0')


def paper_key(paper):
    return hashlib.sha256(str(paper.get('doi') or paper.get('url') or paper['id']).lower().encode()).hexdigest()[:20]


def fetch(config: dict, target: date, out: Path):
    logger = setup_logger(out / 'fetch.log')
    topics = normalize_interests(config)
    queries = list(dict.fromkeys(q for t in topics for q in (t['queries'] or [t['label']])))
    profile = {'positive_keywords':queries,'background_topics':queries,'arxiv_categories':config.get('arxiv_categories',['cs.AI','cs.LG','cs.CL','cs.CV','stat.ML'])}
    adapters = {'arxiv':fetch_arxiv,'openalex':fetch_openalex,'pubmed':fetch_pubmed,'crossref':fetch_crossref,'europepmc':fetch_europepmc,'psyarxiv':fetch_psyarxiv}
    rows, health = [], {}
    for name, source in config['sources'].items():
        if not source.get('enabled',True): continue
        lookback = int(source.get('lookback_days',config.get('lookback_days',3)))
        try:
            if name in adapters:
                source = dict(source)
                if name in {'openalex','pubmed','europepmc','psyarxiv'}:
                    source.setdefault('search_queries',queries)
                    found, warnings = [], []
                    searches = source['search_queries']
                    per_query = max(1, int(source.get('max_results',100)) // max(1,len(searches)))
                    for query in searches:
                        batch, issues = adapters[name](dict(source,search_queries=[query],max_results=per_query),profile,target,lookback,logger)
                        found.extend(batch); warnings.extend(issues)
                        if len(batch)>=per_query: warnings.append(f'coverage_limit: query {query!r} reached {per_query} records')
                else:
                    found, warnings = adapters[name](source, profile, target, lookback, logger)
            elif name == 'openreview':
                auth = ensure_openreview_auth() if source.get('auto_renew',False) else None
                if auth and not auth.get('existing_token_usable'):
                    found, warnings = [], [f"OpenReview automatic authentication needs attention: {auth['status']}; check data/openreview-auth/status.json"]
                else:
                    found, warnings = fetch_openreview(source,target,lookback,logger)
                    if auth and auth['status']=='failed':
                        warnings.append('OpenReview renewal failed; existing verified credential was retained')
            elif name == 'nature': found,warnings = fetch_nature(source,target,lookback,logger)
            elif name == 'google_scholar': found,warnings = fetch_scholar_mail(source,target,lookback,BASE)
            else: raise ValueError(f'Unsupported source {name}')
            health[name] = {'status':'partial' if warnings and found else 'unavailable' if warnings else 'ok','count':len(found),'warnings':warnings}
            if len(found) >= int(source.get('max_results',1000000)):
                health[name]['coverage_limit'] = 'source cap reached; coverage may be incomplete'
            rows.extend(found)
        except Exception as exc:
            health[name] = {'status':'failed','count':0,'warnings':[f'{type(exc).__name__}: {exc}']}
    # Fold DOI aliases before title/source deduplication.
    by_doi, folded = {}, []
    from utils import merge_duplicate_papers
    for row in rows:
        doi = re.sub(r'^https?://doi.org/', '', str(row.get('doi','')).lower()).strip()
        if doi and doi in by_doi:
            index = by_doi[doi]; folded[index] = merge_duplicate_papers(folded[index], row)
        else:
            if doi: by_doi[doi] = len(folded)
            folded.append(row)
    candidates = dedupe_papers(folded)
    # Do not keyword-truncate: Codex must inspect even Chinese-only or paraphrased topics.
    for paper in candidates: paper['reader_key'] = paper_key(paper)
    write_json_atomic(out / 'candidates.json', candidates)
    # A fresh retrieval must never silently reuse yesterday's semantic decisions.
    for derived in ('decisions.json','selection.json','reading_queue.json','completion.json','validation.json','alerts.json'):
        (out/derived).unlink(missing_ok=True)
    healthy = any(h['status']=='ok' for h in health.values())
    payload = {'date':target.isoformat(),'topics':topics,'sources':health,'count':len(candidates),
        'status':'partial' if candidates and any(h['status']!='ok' for h in health.values()) else 'ok' if healthy else 'failed',
        'config_snapshot':config,'generated_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
    write_json_atomic(out / 'run.json',payload)
    if not candidates and not healthy: raise RuntimeError('All sources unavailable; see run.json; do not report no new papers')
    return payload


def load_routes(config, out):
    candidates = json.loads((out/'candidates.json').read_text())
    decisions = json.loads((out/'decisions.json').read_text())
    by_id = {str(d['id']):d for d in decisions}
    if len(by_id)!=len(decisions) or set(by_id)!= {str(p['id']) for p in candidates}:
        raise ValueError('decisions.json must contain exactly one decision per candidate, including rejected papers')
    topics = normalize_interests(config)
    routes=[route_paper(p,by_id[str(p['id'])].get('matches',[]),topics,config.get('thresholds')) for p in candidates]
    if config.get('selection'):
        selected=json.loads((out/'selection.json').read_text())
        top10=selected.get('top10_ids',[]);top5=selected.get('top5_ids',[])
        identities={str(p['id']) for p in routes}
        if not isinstance(top10,list) or not isinstance(top5,list) or len(top10)!=len(set(top10)) or len(top5)!=len(set(top5)):
            raise ValueError('Selection IDs must be unique arrays')
        if len(top10)>int(config['selection'].get('report_limit',10)) or len(top5)>int(config['selection'].get('archive_limit',5)):
            raise ValueError('Selection exceeds configured limits')
        if not set(top5)<=set(top10)<=identities:
            raise ValueError('Top 5 must belong to Top 10 and all IDs must be candidates')
        if top5!=top10[:int(config['selection'].get('archive_limit',5))]:
            raise ValueError('Top 5 must be the first ranked papers from Top 10')
        for paper in routes:
            paper['report_selected']=paper['id'] in top10
            if paper['id'] in top10 and not paper['level']:raise ValueError('Selected paper must match an interest')
            paper['archive']=paper['id'] in top5
    return routes


def prepare(config, out):
    routes = load_routes(config,out)
    for paper in routes:
        if not paper['archive']: continue
        folder = out/'papers'/paper['reader_key']; folder.mkdir(parents=True,exist_ok=True)
        pdf, text = folder/'paper.pdf', folder/'paper.txt'
        try:
            if not pdf.exists():
                url = paper.get('pdf_url','')
                if not url and paper.get('source')=='nature' and '/articles/' in paper.get('url',''): url=paper['url'].split('?')[0]+'.pdf'
                if not url: raise ValueError('No public PDF URL; use lawful publisher full text or supply a local PDF')
                # Never forward private credentials or browser cookies to arbitrary publisher URLs.
                headers = {}
                if urlparse(url).hostname in {'openreview.net','api2.openreview.net'}:
                    token = openreview_access_token()
                    if token: headers['Authorization'] = 'Bearer ' + token
                response = requests_get(url,timeout=45,headers=headers); response.raise_for_status()
                if not response.content.startswith(b'%PDF-'): raise ValueError('Endpoint returned non-PDF data')
                temp = pdf.with_suffix('.tmp'); temp.write_bytes(response.content); temp.replace(pdf)
            extract_pdf_text(pdf,text)
            from pypdf import PdfReader
            pages = [{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(PdfReader(pdf).pages)]
            write_json_atomic(folder/'pages.json',pages)
            paper.update(preparation_status='ready',pdf_path=str(pdf),text_path=str(text),pages_path=str(folder/'pages.json'))
        except Exception as exc: paper.update(preparation_status='needs_access',error=f'{type(exc).__name__}: {exc}')
    write_json_atomic(out/'reading_queue.json',routes)
    return {'archive':sum(p['archive'] for p in routes),'ready':sum(p.get('preparation_status')=='ready' for p in routes)}


def export_figure(pdf, page, destination, crop=None):
    if page<1: raise ValueError('Page numbers are one based')
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(pdf)
    selected = reader.pages[page-1]
    if crop:
        x0,y0,x1,y1 = crop
        width,height = float(selected.mediabox.width),float(selected.mediabox.height)
        if not (0<=x0<x1<=width and 0<=y0<y1<=height): raise ValueError('Invalid crop rectangle in PDF points, origin top-left')
        selected.cropbox.lower_left=(x0,height-y1); selected.cropbox.upper_right=(x1,height-y0)
    destination.parent.mkdir(parents=True,exist_ok=True)
    intermediate = destination.with_suffix('.crop.pdf')
    writer=PdfWriter(); writer.add_page(selected)
    with intermediate.open('wb') as handle: writer.write(handle)
    try:
        subprocess.run(['pdftoppm','-png','-singlefile','-cropbox','-r','160',str(intermediate),str(destination.with_suffix(''))],check=True,capture_output=True,timeout=60)
    finally: intermediate.unlink(missing_ok=True)
    if not destination.exists(): raise RuntimeError('Figure render did not produce PNG')


REQUIRED_SECTIONS = ['一句话总结','核心问题','核心方法','核心内容配图','主实验配图','实验设置与关键结果','Claim 与证据','局限','与关注方向的关系']


def validate_note(note: Path, vault: Path) -> dict:
    if not note.is_file(): return {'complete':False,'errors':['note does not exist']}
    content = note.read_text(); errors=[]
    if not content.startswith('---\n'): return {'complete':False,'errors':['missing YAML properties']}
    try: meta=yaml.safe_load(content.split('---',2)[1]) or {}
    except Exception: return {'complete':False,'errors':['invalid YAML']}
    for field in ['type','title','paper_id','authors','url','reading_evidence','interest_level','figure_sources']:
        if field not in meta: errors.append(f'missing property: {field}')
    if meta.get('reading_evidence') not in {'pdf','full-text'}: errors.append('full reading evidence unavailable')
    if meta.get('reading_status') != 'complete': errors.append('reading_status is not complete')
    for section in REQUIRED_SECTIONS:
        match=re.search(r'^## '+re.escape(section)+r'[^\n]*\n(.*?)(?=^## |\Z)',content,re.M|re.S)
        if not match or len(match[1].strip())<20: errors.append(f'missing/empty section: {section}')
    if re.search('待补充|待阅读|TODO|待基于',content): errors.append('placeholder content')
    images=re.findall(r'!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]',content)
    existing=[]
    for image in images:
        path=(vault/image).resolve()
        if not path.is_relative_to(vault.resolve()) or not path.is_file(): errors.append(f'missing/unsafe image: {image}')
        else: existing.append(image)
    if len(set(existing))<2: errors.append('need two distinct local original figures')
    figures=meta.get('figure_sources',[])
    if not isinstance(figures,list) or len(figures)<2 or any(not isinstance(f,dict) or not all(f.get(k) for k in ('role','figure','page','url','image')) for f in figures):
        errors.append('need source, page, figure number and role for each original figure')
    return {'complete':not errors,'errors':errors}


def pending_downloads(config):
    return paper_access.pending_downloads(BASE,config)


def finalize(config,out,notify=False):
    routes=load_routes(config,out); vault=Path(config['vault']).expanduser().resolve()
    # Read state from a fixed shared location so repeat runs never re-alert archived papers.
    state_path=BASE/'data/unified/state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'notified':[]}
    completions=json.loads((out/'completion.json').read_text())
    by_id={str(c['id']):c for c in completions}
    result,alerts=[],[]
    awaiting_user=0
    for paper in routes:
        if not paper['archive']:
            if paper.get('notify') and paper.get('reader_key') not in state['notified']:
                alerts.append({'id':paper['id'],'title':paper['title'],'note':'','complete':False,'key':paper['reader_key'],'paper_key':paper['reader_key'],'kind':'level0_match','matches':paper['matches']})
            continue
        item=by_id.get(str(paper['id']),{})
        path=(vault/item.get('note','Papers/__missing__')).resolve()
        if not path.is_relative_to(vault/'Papers'): raise ValueError('Notes must be inside vault/Papers')
        check=validate_note(path,vault)
        if path.is_file():
            try: meta=yaml.safe_load(path.read_text().split('---',2)[1]) if path.read_text().startswith('---\n') else {}
            except (yaml.YAMLError,IndexError): meta={}
            if not isinstance(meta,dict) or str(meta.get('paper_id'))!=str(paper['id']) or meta.get('interest_level')!=paper['level']:
                check['errors'].append('paper identity or tier does not match the queue'); check['complete']=False
        result.append({'id':paper['id'],'level':paper['level'],'note':str(path),**check})
        access_task=None
        if not check['complete']:
            access_task=paper_access.register_download(BASE,config,paper,item,path,out)
            if access_task and access_task['status']=='awaiting_download':awaiting_user+=1
        elif paper['reader_key'] in paper_access.load_queue(BASE):
            paper_access.resolve_download(BASE,config,paper['reader_key'],str(path.relative_to(vault)),validate_note)
        urgent_access=access_task and access_task['status']=='awaiting_download' and (
            paper['notify'] or max((m['confidence'] for m in paper['matches']),default=0)>=config.get('access_reminders',{}).get('level1_min_confidence',0.9))
        if urgent_access and 'download:'+paper['reader_key'] not in state['notified']:
            alerts.append({'id':paper['id'],'title':paper['title'],'note':str(path),'complete':False,
                'key':'download:'+paper['reader_key'],'paper_key':paper['reader_key'],'kind':'download_required',
                'matches':paper['matches'],'url':access_task['url'],'pdf_target':access_task['pdf_target']})
        elif paper['notify'] and paper['reader_key'] not in state['notified'] and not urgent_access:
            alerts.append({'id':paper['id'],'title':paper['title'],'note':str(path),'complete':check['complete'],
                'key':paper['reader_key'],'paper_key':paper['reader_key'],'kind':'level0_match','matches':paper['matches']})
    write_json_atomic(out/'validation.json',result)
    write_json_atomic(out/'alerts.json',alerts)
    if notify and alerts:
        message='；'.join(('请下载全文：' if p['kind']=='download_required' else '重点论文：')+p['title'][:70] for p in alerts[:3])
        if any(p['kind']=='download_required' for p in alerts):message+='。详情见 Obsidian「待下载论文」。'
        script='on run argv\ndisplay notification (item 1 of argv) with title "文献阅读提醒"\nend run'
        subprocess.run(['osascript','-e',script,message],check=True,capture_output=True,timeout=15)
        state['notified'].extend(p['key'] for p in alerts)
        state['notified'].extend(p['paper_key'] for p in alerts if p['kind']=='download_required')
        state['notified']=list(dict.fromkeys(state['notified']))
        write_json_atomic(state_path,state)
    report=vault/'Daily Papers/unified'/f'{out.name}-unified.md'
    return {'archived':len(result),'complete':sum(r['complete'] for r in result),'alerts':len(alerts),'incomplete':sum(not r['complete'] for r in result),'report_exists':report.is_file(),'awaiting_user_download':awaiting_user,'unexpected_incomplete':sum(not r['complete'] for r in result)-awaiting_user}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['check','fetch','prepare','figure','finalize','pending-downloads','resolve-download'])
    parser.add_argument('--config',default=str(BASE/'interests.json'))
    parser.add_argument('--date',default='yesterday')
    parser.add_argument('--pdf',type=Path); parser.add_argument('--page',type=int); parser.add_argument('--output',type=Path)
    parser.add_argument('--crop',type=float,nargs=4)
    parser.add_argument('--notify',action='store_true')
    parser.add_argument('--key')
    parser.add_argument('--note')
    args=parser.parse_args(); config=json.loads(Path(args.config).read_text())
    topics=normalize_interests(config)
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    target=today-timedelta(days=1) if args.date=='yesterday' else today if args.date=='today' else date.fromisoformat(args.date)
    out=BASE/'data/unified'/target.isoformat(); out.mkdir(parents=True,exist_ok=True)
    if args.stage in {'prepare','finalize'} and (out/'run.json').exists():
        snapshot=json.loads((out/'run.json').read_text())['config_snapshot']
        if config!=snapshot: raise ValueError('interests.json changed after fetch; rerun fetch and semantic decisions first')
    if args.stage=='check': result={'topics':topics,'sources':list(config['sources']),'vault_exists':Path(config['vault']).is_dir()}
    elif args.stage=='pending-downloads': result=pending_downloads(config)
    elif args.stage=='resolve-download':
        if not args.key or not args.note:parser.error('resolve-download requires --key and --note')
        result=paper_access.resolve_download(BASE,config,args.key,args.note,validate_note)
    elif args.stage=='fetch': result=fetch(config,target,out)
    elif args.stage=='prepare': result=prepare(config,out)
    elif args.stage=='figure':
        if not args.pdf or not args.page or not args.output: parser.error('figure requires --pdf, --page, --output')
        export_figure(args.pdf,args.page,args.output,args.crop); result={'image':str(args.output)}
    else: result=finalize(config,out,args.notify)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.stage=='finalize' and (result['unexpected_incomplete'] or not result['report_exists']): raise SystemExit(2)

if __name__=='__main__': main()
