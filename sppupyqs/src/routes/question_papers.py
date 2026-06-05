import html as _html
import os
from urllib.parse import urlparse

from flask import Blueprint, abort, redirect, render_template

from ..config import CODES_SITE_URL, DEFAULT_EXAM_TYPE, QUESTION_ANSWER_WORKER_URL, SITE_URL
from ..utils import DEFAULT_PATTERN_YEAR, get_legacy_redirect, get_subject, load_pattern_navigation

question_papers_bp = Blueprint("question_papers", __name__)


@question_papers_bp.route("/")
def select_page():
    return pattern_page(DEFAULT_PATTERN_YEAR)


@question_papers_bp.route("/<pattern_year>")
def pattern_page(pattern_year):
    navigation = load_pattern_navigation(pattern_year)
    if not navigation:
        redirect_path = get_legacy_redirect(pattern_year)
        if redirect_path:
            return redirect(redirect_path, code=301)
        abort(404)

    return render_template(
        "select.html",
        navigation=navigation,
        site_url=SITE_URL,
        codes_site_url=CODES_SITE_URL,
    )


@question_papers_bp.route("/honors/<subject_key>")
def honors_viewer_page(subject_key):
    return _render_viewer("honors", subject_key)


@question_papers_bp.route("/<pattern_year>/<subject_key>")
def pattern_viewer_page(pattern_year, subject_key):
    return _render_viewer(pattern_year, subject_key)


def _render_viewer(pattern_key, subject_key):
    subject = get_subject(pattern_key, subject_key)
    if not subject:
        abort(404)

    subject_name = subject.get("subject_name", subject_key)
    branch_name = subject.get("branch_name", "").strip() or "Engineering"
    raw_seo = subject.get("seo_data") or {}
    fallback_title = f"SPPU {subject_name} | {branch_name} Engineering Question Papers"
    canonical_path = raw_seo.get("canonical_path") or subject.get("route_path") or f"/{pattern_key}/{subject_key}"
    seo_data = {
        "title": _html.unescape(raw_seo.get("title") or fallback_title),
        "description": _html.unescape(
            raw_seo.get("description")
            or f"{subject_name} question papers for {branch_name} students of Savitribai Phule Pune University."
        ),
        "keywords": _html.unescape(
            raw_seo.get("keywords")
            or f"{subject_name}, {branch_name}, SPPU question papers"
        ),
        "subject_name": subject_name,
    }

    subject_papers = subject.get("papers", [])
    available_exam_types = {
        str(paper.get("exam_type") or "unknown").lower()
        for paper in subject_papers
        if isinstance(paper, dict)
    }
    if DEFAULT_EXAM_TYPE in available_exam_types:
        viewer_default_exam_type = DEFAULT_EXAM_TYPE
    elif "endsem" in available_exam_types:
        viewer_default_exam_type = "endsem"
    elif "insem" in available_exam_types:
        viewer_default_exam_type = "insem"
    elif "other" in available_exam_types:
        viewer_default_exam_type = "other"
    else:
        viewer_default_exam_type = DEFAULT_EXAM_TYPE

    pdf_data = [
        {
            "filename": _viewer_filename(paper),
            "originalFilename": _viewer_filename(paper),
            "url": paper.get("pdf_url"),
            "link": paper.get("pdf_url"),
            "date": paper.get("paper_label") or "Paper",
            "paperId": paper.get("pdf_id"),
            "examType": paper.get("exam_type", "unknown"),
        }
        for paper in subject_papers
        if isinstance(paper, dict) and paper.get("pdf_url")
    ]

    initial_paper = next(
        (paper for paper in subject_papers if paper.get("exam_type") == viewer_default_exam_type),
        subject_papers[0] if subject_papers else None,
    )

    return render_template(
        "viewer.html",
        subject_name=subject_name,
        branch_name=branch_name,
        subject_link=canonical_path.lstrip("/"),
        pdf_data_for_js=pdf_data,
        subject_papers=subject_papers,
        subject_semester_key=subject.get("semester_key", ""),
        initial_questions_paper_id=(initial_paper or {}).get("pdf_id", ""),
        seo_data=seo_data,
        default_exam_type=viewer_default_exam_type,
        question_answer_worker_url=QUESTION_ANSWER_WORKER_URL,
        site_url=SITE_URL,
        codes_site_url=CODES_SITE_URL,
        site_name="SPPU PYQs",
    )


def _viewer_filename(paper):
    filename = paper.get("filename") or os.path.basename(urlparse(paper.get("pdf_url", "")).path)
    exam_type = str(paper.get("exam_type") or "").lower()
    if exam_type == "other" and "other" not in filename.lower():
        return f"other-{filename}"
    return filename
