import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_conference_paper as processor  # noqa: E402
from process_conference_paper import (  # noqa: E402
    add_paper_to_knowledge_pages,
    find_arxiv_pdf_url,
    openreview_attachment_url,
    process_one,
    render_paper_note,
    select_next_pending_paper,
)


def test_find_arxiv_pdf_url_requires_strong_title_match(monkeypatch):
    feed = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><id>http://arxiv.org/abs/2510.14853v1</id>
      <title>Rewiring Experts on the Fly:Continuous Rerouting for Better Online Adaptation in Mixture-of-Expert models</title></entry>
    </feed>'''

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return feed

    monkeypatch.setattr(processor, "urlopen", lambda request, timeout: Response())
    assert find_arxiv_pdf_url(
        "Rewiring Experts on the Fly: Continuous Rerouting for Better Online Adaptation in Mixture-of-Expert Models"
    ) == "https://arxiv.org/pdf/2510.14853v1"
    assert find_arxiv_pdf_url("Unrelated Paper Title") is None


def test_select_next_pending_paper_returns_first_unchecked_item():
    payload = {
        "papers": [
            {"id": "done", "status": "completed"},
            {"id": "next", "status": "pending"},
        ]
    }

    assert select_next_pending_paper(payload)["id"] == "next"


def test_select_next_pending_paper_can_skip_recorded_failures():
    payload = {"papers": [{"id": "failed", "status": "failed"}, {"id": "next", "status": "pending"}]}

    assert select_next_pending_paper(payload, retry_failed=False)["id"] == "next"


def test_select_next_pending_paper_excludes_ids_for_one_batch():
    payload = {"papers": [{"id": "failed", "status": "failed"}, {"id": "next", "status": "pending"}]}

    assert select_next_pending_paper(payload, excluded_ids={"failed"})["id"] == "next"


def test_openreview_access_token_can_be_read_from_local_file(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text(" secret-token \n", encoding="utf-8")
    monkeypatch.delenv("OPENREVIEW_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OPENREVIEW_ACCESS_TOKEN_FILE", str(token_file))

    assert processor.openreview_access_token() == "secret-token"


def test_openreview_attachment_url_uses_note_id():
    assert openreview_attachment_url("https://openreview.net/pdf?id=abc123") == (
        "https://api2.openreview.net/attachment?id=abc123&name=pdf"
    )


def test_render_paper_note_marks_pdf_evidence_and_links_concepts():
    paper = {
        "id": "abc",
        "title": "Test-Time Adaptation Paper",
        "authors": ["Alice"],
        "venue": "ICML 2026",
        "url": "https://openreview.net/forum?id=abc",
        "pdf_url": "https://openreview.net/pdf?id=abc",
        "abstract": "An abstract.",
        "matched_keywords": ["test-time adaptation"],
        "pdf_path": "/vault/Attachments/Paper PDFs/icml-abc.pdf",
        "pdf_text_path": "/vault/_paper_text/icml-abc.txt",
        "reading_evidence": "pdf",
    }

    note = render_paper_note(paper, ["[[test-time adaptation]]"], ["[[Continual Learning Research Thread]]"])

    assert "pdf_backed: true" in note
    assert "reading_evidence: pdf" in note
    assert "published:" in note
    assert "## 针对的问题" in note
    assert "## 核心架构与训练方法" in note
    assert "## 关键实验与结论" in note
    assert "## 总结：与其他相似工作的区别" in note
    assert "## Links" in note
    assert "[[test-time adaptation]]" in note
    assert "[[Continual Learning Research Thread]]" in note
    assert "An abstract." in note


def test_add_paper_to_knowledge_pages_is_idempotent(tmp_path):
    concepts = tmp_path / "Concepts"
    ideas = tmp_path / "Ideas"
    concepts.mkdir()
    ideas.mkdir()
    (concepts / "test-time adaptation.md").write_text("# test-time adaptation\n", encoding="utf-8")
    (ideas / "Continual Learning Research Thread.md").write_text(
        "# Continual Learning Research Thread\n", encoding="utf-8"
    )
    paper = {"id": "abc", "title": "Test Paper", "note_link": "[[2026-icml-test-paper]]"}

    add_paper_to_knowledge_pages(tmp_path, paper, ["test-time adaptation"], ["Continual Learning Research Thread"])
    add_paper_to_knowledge_pages(tmp_path, paper, ["test-time adaptation"], ["Continual Learning Research Thread"])

    concept_text = (concepts / "test-time adaptation.md").read_text(encoding="utf-8")
    idea_text = (ideas / "Continual Learning Research Thread.md").read_text(encoding="utf-8")
    assert concept_text.count("2026-icml-test-paper") == 1
    assert idea_text.count("2026-icml-test-paper") == 1


def test_process_one_updates_obsidian_queue_checkpoint(tmp_path, monkeypatch):
    queue = tmp_path / "papers.json"
    queue.write_text(
        json.dumps(
            {
                "conference": "ICML",
                "year": 2026,
                "papers": [
                    {
                        "id": "abc",
                        "title": "Checkpoint Paper",
                        "status": "pending",
                        "note_filename": "2026-icml-checkpoint-paper.md",
                        "url": "https://example.com/paper",
                        "pdf_url": "https://example.com/paper.pdf",
                        "authors": [],
                        "abstract": "Abstract",
                        "matched_keywords": [],
                    }
                ],
                "directions": {"Other": [{"id": "abc", "status": "pending"}]},
            }
        ),
        encoding="utf-8",
    )

    def fake_download(url, destination, title):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"%PDF-fake")
        return url

    def fake_extract(pdf_path, text_path):
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text("extracted", encoding="utf-8")

    monkeypatch.setattr(processor, "download_pdf", fake_download)
    monkeypatch.setattr(processor, "extract_pdf_text", fake_extract)
    result = process_one(queue, tmp_path / "vault")

    assert result["status"] == "completed"
    queue_text = (tmp_path / "vault/Research Notes/2026-icml-papers.md").read_text(encoding="utf-8")
    assert "- [x] [[Papers/2026/2026-icml-checkpoint-paper|Checkpoint Paper]]" in queue_text
    saved = json.loads(queue.read_text(encoding="utf-8"))
    assert saved["papers"][0]["status"] == "completed"
    assert saved["directions"]["Other"][0]["status"] == "completed"
