import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from unified_reader import normalize_interests, route_paper, validate_note
from fetch_reader_sources import parse_nature_feed, parse_scholar_mail


def test_plain_chinese_topics_and_duplicate_priority():
    topics = normalize_interests({'level0':['SAE 的优化'], 'level1':['THINGS 数据集'], 'level2':[]})
    assert topics[0]['label'] == 'SAE 的优化'
    route = route_paper({'id':'x'}, [{'topic':'THINGS 数据集','confidence':.9,'reason':'uses dataset'}, {'topic':'SAE 的优化','confidence':.8,'reason':'optimizes sparsity'}], topics)
    assert route['level'] == 'level0' and route['archive'] and route['notify']


def test_low_confidence_and_unknown_topic_do_not_archive():
    topics = normalize_interests({'level0':['SAE'], 'level1':['THINGS'], 'level2':['人机比较']})
    assert route_paper({}, [{'topic':'THINGS','confidence':.5,'reason':'weak'}], topics)['level'] is None
    assert route_paper({}, [{'topic':'人机比较','confidence':.9,'reason':'comparison'}], topics)['archive'] is False
    with pytest.raises(ValueError): route_paper({}, [{'topic':'unknown','confidence':1,'reason':'x'}], topics)
    with pytest.raises(ValueError): route_paper({}, [{'topic':'SAE','confidence':float('nan'),'reason':'x'}], topics)


def test_invalid_topics():
    with pytest.raises(ValueError): normalize_interests({'level0':'oops'})
    with pytest.raises(ValueError): normalize_interests({'level0':['same'],'level1':['same']})


def test_nature_feed_filters_date_and_preserves_doi():
    xml = b'''<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>A model</title><link>https://www.nature.com/articles/s1</link><dc:date>2026-10-28</dc:date><dc:identifier>doi:10.1038/s1</dc:identifier><description>Abstract</description></item></channel></rss>'''
    from datetime import date
    rows = parse_nature_feed(xml, 'Nature', date(2026,10,28), 1)
    assert rows[0]['doi'] == '10.1038/s1'
    assert not parse_nature_feed(xml, 'Nature', date(2026,10,29), 1)


def test_scholar_mail_not_arbitrary_links():
    msg = b'''From: scholaralerts-noreply@google.com\nDate: Wed, 28 Oct 2026 08:00:00 +0000\nContent-Type: text/html; charset=utf-8\n\n<h3><a href="https://arxiv.org/abs/123">A paper</a></h3><a href="https://google.com/unsubscribe">Unsubscribe</a>'''
    rows = parse_scholar_mail(msg)
    assert len(rows) == 1 and rows[0]['title'] == 'A paper'
    assert rows[0]['discovered_at'].startswith('2026-10-28')


def test_incomplete_note_cannot_pass_gate(tmp_path):
    note = tmp_path / 'note.md'
    note.write_text('---\nreading_evidence: abstract-only\n---\n待补充')
    assert validate_note(note, tmp_path)['complete'] is False


def test_fetch_does_not_hide_other_sources_on_failure(tmp_path, monkeypatch):
    import unified_reader as reader
    from datetime import date
    monkeypatch.setattr(reader,'fetch_nature',lambda *a: ([{'id':'n','title':'A paper','source':'nature','doi':'10.x/y'}],[]))
    monkeypatch.setattr(reader,'fetch_scholar_mail',lambda *a: ([],['setup_required']))
    config={'level0':['SAE'],'sources':{'nature':{},'google_scholar':{}}}
    result=reader.fetch(config,date(2026,10,28),tmp_path)
    assert result['status']=='partial' and result['count']==1
    assert result['sources']['google_scholar']['status']=='unavailable'


def test_all_source_failures_not_no_papers(tmp_path,monkeypatch):
    import unified_reader as reader
    from datetime import date
    monkeypatch.setattr(reader,'fetch_nature',lambda *a: ([],['HTTP 403']))
    with pytest.raises(RuntimeError): reader.fetch({'level0':['SAE'],'sources':{'nature':{}}},date(2026,10,28),tmp_path)


def test_routing_requires_all_candidates(tmp_path):
    import unified_reader as reader,json
    (tmp_path/'candidates.json').write_text(json.dumps([{'id':'1'},{'id':'2'}]))
    (tmp_path/'decisions.json').write_text(json.dumps([{'id':'1','matches':[]}]))
    with pytest.raises(ValueError):reader.load_routes({'level0':['SAE']},tmp_path)


def test_finalize_validates_artifacts_and_deduplicates_level0_alert(tmp_path,monkeypatch):
    import unified_reader as reader,json,yaml
    monkeypatch.setattr(reader,'BASE',tmp_path)
    vault=tmp_path/'vault';out=tmp_path/'2026-10-28';out.mkdir()
    image_dir=vault/'Attachments/Paper Figures/x';image_dir.mkdir(parents=True)
    for name in ['core','results']:(image_dir/f'{name}.png').write_bytes(b'png-fixture')
    note=vault/'Papers/2026/a.md';note.parent.mkdir(parents=True)
    meta={'type':'paper','title':'Paper','paper_id':'1','authors':['Author'],'url':'https://example.org',
          'reading_evidence':'pdf','interest_level':'level0','reading_status':'complete',
          'figure_sources':[{'role':name,'figure':'1','page':2,'url':'https://example.org','image':f'Attachments/Paper Figures/x/{name}.png'} for name in ['core','results']]}
    body='---\n'+yaml.safe_dump(meta)+'---\n'
    for section in reader.REQUIRED_SECTIONS:body+='## '+section+'\n'+'Evidence explained from the actual paper with details.\n'
    for name in ['core','results']:body+=f'![[Attachments/Paper Figures/x/{name}.png]]\n'
    note.write_text(body)
    config={'level0':['SAE'],'vault':str(vault)}
    (out/'candidates.json').write_text(json.dumps([{'id':'1','url':'https://example.org','title':'Paper','reader_key':'fixture-paper'}]))
    (out/'decisions.json').write_text(json.dumps([{'id':'1','matches':[{'topic':'SAE','confidence':.9,'reason':'specific training change'}]}]))
    (out/'completion.json').write_text(json.dumps([{'id':'1','note':'Papers/2026/a.md'}]))
    calls=[]
    monkeypatch.setattr(reader.subprocess,'run',lambda *a,**kw:calls.append(a))
    assert reader.finalize(config,out,notify=True)['complete']==1
    assert len(calls)==1
    assert reader.finalize(config,out,notify=True)['alerts']==0
    assert len(calls)==1


def test_gmail_import_preserves_snippet_pdf_and_received_date(tmp_path):
    from import_scholar_gmail import import_messages
    import json
    from datetime import date
    from fetch_reader_sources import fetch_scholar_mail
    payload={'messages':[{'id':'gmail1','payload':{'mime_type':'text/html','headers':[{'name':'From','value':'Google Scholar Alerts <scholaralerts-noreply@google.com>'},{'name':'Date','value':'Wed, 28 Oct 2026 23:30:00 -0700'}],'body':{'content':'<h3><a href="https://scholar.google.com/scholar_url?url=https%3A%2F%2Farxiv.org%2Fpdf%2F2410.23251">Paper title</a></h3><div class="gse_alrt_sni">Actual abstract fragment.</div>'}}}]}
    result=import_messages(payload,tmp_path,date(2026,10,29))
    assert result['paper_count']==1
    stored=json.loads((tmp_path/'gmail-gmail1.json').read_text())
    assert stored[0]['abstract']=='Actual abstract fragment.'
    assert stored[0]['pdf_url']=='https://arxiv.org/pdf/2410.23251'
    assert stored[0]['discovered_at'].startswith('2026-10-29')
    papers,warnings=fetch_scholar_mail({'inbox_dir':str(tmp_path)},date(2026,10,29),1,tmp_path)
    assert len(papers)==1 and not warnings


def test_gmail_empty_sync_distinguishes_no_mail_from_missing_connection(tmp_path):
    from import_scholar_gmail import import_messages
    from datetime import date
    from fetch_reader_sources import fetch_scholar_mail
    import_messages({'messages':[]},tmp_path,date(2026,10,28))
    assert fetch_scholar_mail({'inbox_dir':str(tmp_path)},date(2026,10,28),7,tmp_path)==([],[])
    assert fetch_scholar_mail({'inbox_dir':str(tmp_path),'transport':'gmail'},date(2026,10,29),7,tmp_path)[1]


def test_auto_auth_failure_does_not_block_other_sources(tmp_path,monkeypatch):
    import unified_reader as reader
    from datetime import date
    calls=[]
    monkeypatch.setattr(reader,'ensure_openreview_auth',lambda:calls.append('renew') or {'status':'failed','existing_token_usable':False},raising=False)
    monkeypatch.setattr(reader,'fetch_openreview',lambda *a:([],[]))
    monkeypatch.setattr(reader,'fetch_nature',lambda *a:([{'id':'n','source':'nature','title':'Paper'}],[]))
    result=reader.fetch({'level0':['SAE'],'sources':{'openreview':{'auto_renew':True},'nature':{}}},date(2026,10,28),tmp_path)
    assert calls==['renew']
    assert result['count']==1 and result['sources']['openreview']['status']=='unavailable'


def test_paid_high_match_level1_creates_download_reminder_and_pending_task(tmp_path,monkeypatch):
    import json,unified_reader as reader
    monkeypatch.setattr(reader,'BASE',tmp_path)
    vault=tmp_path/'vault';out=tmp_path/'2026-10-29';out.mkdir()
    note=vault/'Papers/2026/paid.md';note.parent.mkdir(parents=True)
    note.write_text('---\ntype: paper\npaper_id: p1\nreading_evidence: abstract-only\n---\n全文待用户下载。')
    (out/'candidates.json').write_text(json.dumps([{'id':'p1','title':'Paid paper','url':'https://example.org/paper','reader_key':'paid-key'}]))
    (out/'decisions.json').write_text(json.dumps([{'id':'p1','matches':[{'topic':'SAE','confidence':.95,'reason':'specific SAE optimization directly matches'}]}]))
    (out/'completion.json').write_text(json.dumps([{'id':'p1','note':'Papers/2026/paid.md','fulltext_status':'paywalled','access_evidence_url':'https://example.org/paper','access_evidence':'Publisher explicitly requires a subscription.'}]))
    config={'level1':['SAE'],'vault':str(vault)}
    notifications=[]
    monkeypatch.setattr(reader.subprocess,'run',lambda *args,**kwargs:notifications.append(args))
    result=reader.finalize(config,out,notify=True)
    alerts=json.loads((out/'alerts.json').read_text())
    assert result['alerts']==1 and alerts[0]['kind']=='download_required'
    queue=reader.pending_downloads(config)
    assert len(queue)==1 and queue[0]['status']=='awaiting_download'
    assert (vault/'Research Notes/待下载论文.md').exists()
    # A repeated run never adds another task for the same paper.
    assert '请下载全文' in notifications[0][0][-1]
    assert reader.finalize(config,out,notify=True)['alerts']==0
    assert len(notifications)==1
    assert len(reader.pending_downloads(config))==1


def test_network_failure_is_not_labeled_as_paid_article(tmp_path,monkeypatch):
    import json,unified_reader as reader
    monkeypatch.setattr(reader,'BASE',tmp_path)
    out=tmp_path/'2026-10-29';out.mkdir();vault=tmp_path/'vault'
    (out/'candidates.json').write_text(json.dumps([{'id':'p1','title':'Paper','reader_key':'key'}]))
    (out/'decisions.json').write_text(json.dumps([{'id':'p1','matches':[{'topic':'SAE','confidence':.95,'reason':'specific method match'}]}]))
    (out/'completion.json').write_text(json.dumps([{'id':'p1','note':'Papers/2026/a.md','fulltext_status':'network_error'}]))
    assert reader.finalize({'level1':['SAE'],'vault':str(vault)},out)['alerts']==0


def test_pending_download_detects_user_pdf_but_does_not_mark_reading_complete(tmp_path,monkeypatch):
    import json,unified_reader as reader
    monkeypatch.setattr(reader,'BASE',tmp_path)
    vault=tmp_path/'vault';target=vault/'Attachments/Paper PDFs/key.pdf';target.parent.mkdir(parents=True)
    target.write_bytes(b'%PDF-1.7\nfixture')
    state=tmp_path/'data/unified/pending_downloads.json';state.parent.mkdir(parents=True)
    state.write_text(json.dumps({'key':{'key':'key','status':'awaiting_download','pdf_target':str(target)}}))
    rows=reader.pending_downloads({'vault':str(vault)})
    assert rows[0]['status']=='ready_for_reading'


def test_selection_restricts_archives_to_top5_and_rejects_unknown(tmp_path):
    import unified_reader as reader,json
    (tmp_path/'candidates.json').write_text(json.dumps([{'id':'a'},{'id':'b'}]))
    (tmp_path/'decisions.json').write_text(json.dumps([{'id':'a','matches':[{'topic':'SAE','confidence':.95,'reason':'specific match'}]},{'id':'b','matches':[{'topic':'SAE','confidence':.9,'reason':'specific match'}]}]))
    (tmp_path/'selection.json').write_text(json.dumps({'top10_ids':['a','b'],'top5_ids':['a']}))
    routes=reader.load_routes({'level1':['SAE'],'selection':{'report_limit':10,'archive_limit':1}},tmp_path)
    assert [p['id'] for p in routes if p['archive']]==['a']
    (tmp_path/'selection.json').write_text(json.dumps({'top10_ids':['a'],'top5_ids':['b']}))
    with pytest.raises(ValueError):reader.load_routes({'level1':['SAE'],'selection':{'report_limit':10,'archive_limit':1}},tmp_path)


def test_top_five_are_first_ranked_even_for_level2(tmp_path):
    import json,unified_reader as reader
    (tmp_path/'candidates.json').write_text(json.dumps([{'id':'a'},{'id':'b'}]))
    (tmp_path/'decisions.json').write_text(json.dumps([{'id':'a','matches':[{'topic':'TTA','confidence':.9,'reason':'explicit test-time adaptation'}]},{'id':'b','matches':[{'topic':'TTA','confidence':.8,'reason':'explicit test-time adaptation'}]}]))
    (tmp_path/'selection.json').write_text(json.dumps({'top10_ids':['a','b'],'top5_ids':['a']}))
    routes=reader.load_routes({'level2':['TTA'],'selection':{'report_limit':10,'archive_limit':1}},tmp_path)
    assert routes[0]['archive'] is True and routes[1]['archive'] is False
    (tmp_path/'selection.json').write_text(json.dumps({'top10_ids':['a','b'],'top5_ids':['b']}))
    with pytest.raises(ValueError):reader.load_routes({'level2':['TTA'],'selection':{'report_limit':10,'archive_limit':1}},tmp_path)
