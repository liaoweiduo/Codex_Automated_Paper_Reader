import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from conference_papers import (  # noqa: E402
    assign_direction,
    build_payload,
    candidate_invitations,
    render_conference_markdown,
    run,
    normalize_virtual_paper,
)
from fetch_openreview import fetch_openreview_venue  # noqa: E402


def test_icml_invitation_fallback_uses_year_specific_openreview_venue():
    invitations = candidate_invitations("ICML", 2026)

    assert "ICML.cc/2026/Conference/-/Submission" in invitations
    assert "ICML.cc/2026/Conference/-/Paper" in invitations


def test_explicit_invitation_is_tried_first():
    invitations = candidate_invitations("ICML", 2026, "ICML.cc/2026/Conference/-/AcceptedPaper")

    assert invitations[0] == "ICML.cc/2026/Conference/-/AcceptedPaper"


def test_direction_assignment_uses_profile_keywords_and_categories():
    paper = {
        "title": "Test-Time Adaptation for Vision-Language Models",
        "abstract": "We study multimodal alignment under distribution shift.",
        "categories": ["cs.CV"],
    }
    profile = {
        "positive_keywords": ["test-time adaptation", "multimodal alignment"],
        "arxiv_categories": ["cs.CV"],
    }

    assert assign_direction(paper, profile) == "test-time adaptation"


def test_direction_assignment_supports_configured_high_level_directions():
    paper = {
        "title": "Test-Time Adaptation for Vision-Language Models",
        "abstract": "We study multimodal alignment under distribution shift.",
        "categories": ["cs.CV"],
    }
    profile = {"positive_keywords": []}
    directions = {
        "Multimodal and VLM": ["vision-language model", "multimodal"],
        "Adaptation and Continual Learning": ["test-time adaptation", "continual learning"],
    }

    assert assign_direction(paper, profile, directions) == "Multimodal and VLM"


def test_official_virtual_paper_normalizes_with_external_abstract_map():
    item = {
        "id": 123,
        "name": "A Vision-Language Paper",
        "authors": [{"fullname": "Alice"}, {"fullname": "Bob"}],
        "topic": "Vision and Multimodal",
        "keywords": ["Multimodal"],
        "paper_url": "https://openreview.net/forum?id=abc",
        "paper_pdf_url": "https://openreview.net/pdf?id=abc",
        "virtualsite_url": "/virtual/2026/poster/123",
        "sourceurl": "https://openreview.net/group?id=ICML.cc/2026/Conference",
    }

    paper = normalize_virtual_paper(
        item,
        {"123": "A full abstract."},
        "ICML",
        2026,
        "https://icml.cc/static/virtual/data/icml-2026-orals-posters.json",
    )

    assert paper["source"] == "icml_virtual"
    assert paper["id"] == "123"
    assert paper["authors"] == ["Alice", "Bob"]
    assert paper["abstract"] == "A full abstract."
    assert paper["url"] == "https://openreview.net/forum?id=abc"
    assert "Vision and Multimodal" in paper["categories"]


def test_markdown_groups_papers_and_preserves_required_metadata():
    payload = {
        "conference": "ICML",
        "year": 2026,
        "venue_id": "ICML.cc/2026/Conference",
        "paper_count": 1,
        "warnings": [],
        "directions": {
            "multimodal alignment": [
                {
                    "id": "abc123",
                    "title": "A Multimodal Paper",
                    "authors": ["Alice", "Bob"],
                    "abstract": "A useful abstract.",
                    "url": "https://openreview.net/forum?id=abc123",
                    "pdf_url": "https://openreview.net/pdf?id=abc123",
                    "venue": "ICML",
                    "published_at": "2026-06-01T00:00:00Z",
                    "categories": ["multimodal"],
                    "direction": "multimodal alignment",
                    "decision": "Accept (regular)",
                    "virtual_url": "https://icml.cc/virtual/2026/poster/abc123",
                }
            ]
        },
    }

    markdown = render_conference_markdown(payload)

    assert "# ICML 2026 Papers" in markdown
    assert "## Multimodal Alignment" in markdown
    assert "A Multimodal Paper" in markdown
    assert "Alice; Bob" in markdown
    assert "https://openreview.net/pdf?id=abc123" in markdown
    assert "A useful abstract." in markdown
    assert "Decision: Accept (regular)" in markdown
    assert "https://icml.cc/virtual/2026/poster/abc123" in markdown
    assert "-&gt;" not in markdown
    assert "- [ ] [[Papers/2026/2026-icml-a-multimodal-paper|A Multimodal Paper]]" in markdown


def test_virtual_paper_derives_openreview_pdf_url_when_export_omits_pdf():
    item = {
        "id": 123,
        "name": "A Vision-Language Paper",
        "authors": [],
        "paper_url": "https://openreview.net/forum?id=abc",
        "paper_pdf_url": None,
    }

    paper = normalize_virtual_paper(item, {}, "ICML", 2026, "source")

    assert paper["pdf_url"] == "https://openreview.net/pdf?id=abc"


def test_virtual_paper_derives_openreview_links_from_eventmedia():
    item = {
        "id": 68805,
        "name": "A Paper Without Direct PDF Fields",
        "authors": [],
        "paper_url": "",
        "paper_pdf_url": None,
        "eventmedia": [{"type": "URL", "uri": "https://openreview.net/forum?id=abc"}],
    }

    paper = normalize_virtual_paper(item, {}, "ICML", 2026, "source")

    assert paper["url"] == "https://openreview.net/forum?id=abc"
    assert paper["pdf_url"] == "https://openreview.net/pdf?id=abc"


def test_openreview_venue_fetch_paginates_without_daily_date_filter(monkeypatch):
    def note(note_id, title):
        return {
            "id": note_id,
            "forum": note_id,
            "cdate": 1,
            "content": {
                "title": {"value": title},
                "authors": {"value": ["Author"]},
                "abstract": {"value": "Abstract"},
            },
        }

    pages = {
        0: [note("one", "First paper")],
        1: [note("two", "Second paper")],
        2: [],
    }

    monkeypatch.setattr(
        "fetch_openreview._get_notes_http_page",
        lambda invitation, limit, offset=0: pages[offset],
    )
    monkeypatch.setattr("fetch_openreview._make_client", lambda module, warnings: None)

    papers, warnings, invitation = fetch_openreview_venue(
        {"enabled": True}, "ICML", 2026, explicit_invitation="ICML.cc/2026/Conference/-/Submission", max_results=3
    )

    assert warnings == []
    assert invitation == "ICML.cc/2026/Conference/-/Submission"
    assert [paper["id"] for paper in papers] == ["one", "two"]


def test_conference_run_writes_isolated_outputs_and_obsidian_note(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "research_profile: {positive_keywords: [alignment], arxiv_categories: []}\n"
        "sources: {openreview: {enabled: true}}\n",
        encoding="utf-8",
    )
    paper = {
        "id": "paper-1",
        "source": "openreview",
        "title": "Alignment paper",
        "authors": ["Author"],
        "abstract": "Abstract",
        "url": "https://openreview.net/forum?id=paper-1",
        "pdf_url": "https://openreview.net/pdf?id=paper-1",
        "published_at": "2026-01-01T00:00:00Z",
        "updated_at": "",
        "venue": "ICML",
        "categories": [],
    }
    monkeypatch.setattr(
        "conference_papers.fetch_openreview_venue",
        lambda *args, **kwargs: ([paper], [], "ICML.cc/2026/Conference/-/Paper"),
    )
    monkeypatch.setattr("conference_papers.official_virtual_urls", lambda *args: None)
    output_dir = tmp_path / "data" / "conferences" / "icml-2026"
    obsidian_root = tmp_path / "knowledge"

    result = run(
        type("Args", (), {
            "config": str(config_path),
            "conference": "ICML",
            "year": 2026,
            "invitation": None,
            "max_results": 10,
            "output_dir": str(output_dir),
            "obsidian_root": str(obsidian_root),
            "force": True,
        })()
    )

    assert Path(result["json_path"]).exists()
    assert Path(result["obsidian_path"]).parent.name == "Research Notes"
    assert (obsidian_root / "Research Notes" / "2026-icml-papers.md").exists()
    assert not (tmp_path / "data" / "processed").exists()


def test_explicit_openreview_invitation_bypasses_icml_virtual_default(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("research_profile: {}\nsources: {openreview: {enabled: true}}\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        "conference_papers.fetch_openreview_venue",
        lambda *args, **kwargs: (calls.append((args, kwargs)) or ([], [], "explicit-invitation")),
    )
    args = type(
        "Args",
        (),
        {
            "config": str(config_path),
            "conference": "ICML",
            "year": 2026,
            "invitation": "ICML.cc/2026/Conference/-/Paper",
            "source_url": None,
            "abstracts_url": None,
            "max_results": 1,
            "output_dir": str(tmp_path / "out"),
            "obsidian_root": str(tmp_path / "vault"),
            "force": True,
        },
    )()

    try:
        run(args)
    except RuntimeError:
        pass
    assert calls
    assert calls[0][1]["explicit_invitation"] == "ICML.cc/2026/Conference/-/Paper"


def test_build_payload_keeps_only_keyword_matches_and_applies_candidate_limit():
    def paper(paper_id, title, abstract):
        return {
            "id": paper_id,
            "source": "icml_virtual",
            "title": title,
            "authors": ["Author"],
            "abstract": abstract,
            "url": f"https://example.test/{paper_id}",
            "pdf_url": "",
            "published_at": "",
            "updated_at": "",
            "venue": "ICML 2026",
            "categories": [],
        }

    payload = build_payload(
        [
            paper("match-1", "Test-Time Adaptation", "A method for adaptation."),
            paper("match-2", "Multimodal Alignment", "A method for multimodal alignment."),
            paper("noise", "Unrelated Chemistry", "A chemistry paper."),
        ],
        "ICML",
        2026,
        "source",
        {"positive_keywords": ["test-time adaptation", "multimodal alignment"], "negative_keywords": []},
        candidate_limit=1,
    )

    assert payload["paper_count"] == 1
    assert payload["retrieved_count"] == 3
    assert payload["keyword_matched_count"] == 2
    assert payload["candidate_limit"] == 1
    assert payload["papers"][0]["id"] in {"match-1", "match-2"}
    assert all(paper["id"] != "noise" for paper in payload["papers"])
