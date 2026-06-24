import hashlib
import html as html_lib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import CODES_SITE_URL, DEFAULT_EXAM_TYPE, SITE_URL
from src.utils import (
    DEFAULT_PATTERN_YEAR,
    HONORS_KEY,
    get_legacy_redirect,
    get_subject,
    load_pattern_navigation,
    load_question_papers,
    load_sitemap_entries,
)


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
TEMPLATE_DIR = ROOT / "templates"
DIST_DIR = ROOT / "dist"
PYQS_METADATA_DIR = ROOT / "pyqs-metadata"

ASSETS = [
    "css/viewer.css",
    "css/select.css",
    "css/header.css",
    "css/footer.css",
    "js/analytics.js",
    "js/select.js",
    "js/mobile-menu.js",
    "js/download-paper.js",
    "js/viewer-page.js",
]


def minify_css(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"\s+", " ", source)
    source = re.sub(r"\s*([{}:;,>~])\s*", r"\1", source)
    return source.replace(";}", "}").strip()


def minify_js(source):
    try:
        import rjsmin

        return rjsmin.jsmin(source).strip()
    except ImportError:
        pass

    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("//"):
            lines.append(stripped)
    return "\n".join(lines).strip()


def build_assets():
    manifest = {}
    for relative_name in ASSETS:
        source_path = STATIC_DIR / relative_name
        source = source_path.read_text(encoding="utf-8")
        suffix = source_path.suffix
        if suffix == ".css":
            output = minify_css(source)
        elif suffix == ".js":
            output = minify_js(source)
        else:
            output = source

        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()[:10]
        output_name = f"{source_path.stem}.{digest}{suffix}"
        output_relative = Path("dist") / source_path.parent.relative_to(STATIC_DIR) / output_name
        output_path = DIST_DIR / "static" / output_relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
        manifest[relative_name] = f"/static/{output_relative.as_posix()}"

    (DIST_DIR / "static" / "asset-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def copy_tree(source, destination, ignore=None):
    if not source.exists():
        return
    shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore)


def copy_static_files():
    def ignore_static(directory, names):
        ignored = {"dist", "asset-manifest.json"}.intersection(names)
        if Path(directory).is_relative_to(STATIC_DIR / "pdfjs"):
            ignored.update(ignore_pdfjs_files(directory, names))
        return ignored

    copy_tree(STATIC_DIR, DIST_DIR / "static", ignore=ignore_static)
    write_pdfjs_clean_url_entry()
    copy_apple_touch_icon()
    copy_tree(STATIC_DIR / "images", DIST_DIR / "images")
    copy_tree(ROOT / "manifest", DIST_DIR / "manifest")
    copy_tree(PYQS_METADATA_DIR, DIST_DIR / "pyqs-metadata")
    write_robots_txt()
    write_llms_txt()


def copy_apple_touch_icon():
    icon = STATIC_DIR / "images" / "apple-touch-icon.png"
    if icon.exists():
        shutil.copy2(icon, DIST_DIR / "apple-touch-icon.png")


def ignore_pdfjs_files(directory, names):
    path = Path(directory)
    ignored = {name for name in names if name.endswith(".map")}
    ignored.update({"compressed.tracemonkey-pldi-09.pdf", "debugger.css", "debugger.mjs"}.intersection(names))
    if path.name == "locale":
        ignored.update(
            name
            for name in names
            if name not in {"en-US", "locale.json"}
        )
    return ignored


def write_pdfjs_clean_url_entry():
    viewer_html = DIST_DIR / "static" / "pdfjs" / "web" / "viewer.html"
    viewer_clean = DIST_DIR / "static" / "pdfjs" / "web" / "viewer"
    if viewer_html.exists():
        shutil.copy2(viewer_html, viewer_clean)


def write_robots_txt():
    source = ROOT / "robots.txt"
    if not source.exists():
        return
    content = source.read_text(encoding="utf-8").replace("{SITE_URL}", SITE_URL)
    write_file("robots.txt", content.rstrip() + "\n")


def write_llms_txt():
    source = ROOT / "llms.txt"
    if source.exists():
        write_file("llms.txt", source.read_text(encoding="utf-8").rstrip() + "\n")


def output_path_for_route(route):
    cleaned = route.strip("/")
    if not cleaned:
        return DIST_DIR / "index.html"
    return DIST_DIR / cleaned / "index.html"


def write_route(route, content):
    output_path = output_path_for_route(route)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def write_file(relative_path, content):
    output_path = DIST_DIR / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def create_environment(asset_manifest):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    def asset_url(filename):
        return asset_manifest.get(filename, f"/static/{filename}")

    env.globals.update(
        asset_url=asset_url,
        get_flashed_messages=lambda with_categories=False: [],
        site_url=SITE_URL,
        codes_site_url=CODES_SITE_URL,
    )
    return env


def render_template(env, template_name, **context):
    base_context = {
        "site_url": SITE_URL,
        "codes_site_url": CODES_SITE_URL,
        "site_name": "SPPU PYQs",
    }
    base_context.update(context)
    return env.get_template(template_name).render(**base_context)


def render_pattern_pages(env):
    data = load_question_papers()
    pattern_years = data["available_patterns"]
    for pattern_year in pattern_years:
        navigation = load_pattern_navigation(pattern_year)
        if navigation:
            html = render_template(env, "select.html", navigation=navigation)
            write_route("/" if pattern_year == DEFAULT_PATTERN_YEAR else f"/{pattern_year}", html)


def render_info_pages(env):
    for route, template in {
        "/contact": "contact.html",
        "/privacy": "privacy.html",
        "/terms": "terms.html",
    }.items():
        write_route(route, render_template(env, template))
    write_route("/sitemap", render_template(env, "sitemap.html", branches=load_sitemap_data()))


def render_viewer_pages(env):
    data = load_question_papers()
    for (pattern_key, subject_key), subject in data["subjects_by_route"].items():
        html = render_viewer(env, pattern_key, subject_key, subject)
        if html:
            write_route(subject["route_path"], html)


def render_viewer(env, pattern_key, subject_key, subject):
    subject_name = subject.get("subject_name", subject_key)
    branch_name = subject.get("branch_name", "").strip() or "Engineering"
    raw_seo = subject.get("seo_data") or {}
    fallback_title = f"SPPU {subject_name} | {branch_name} Engineering Question Papers"
    canonical_path = raw_seo.get("canonical_path") or subject.get("route_path") or f"/{pattern_key}/{subject_key}"
    seo_data = {
        "title": html_lib.unescape(raw_seo.get("title") or fallback_title),
        "description": html_lib.unescape(
            raw_seo.get("description")
            or f"{subject_name} question papers for {branch_name} students of Savitribai Phule Pune University."
        ),
        "keywords": html_lib.unescape(
            raw_seo.get("keywords") or f"{subject_name}, {branch_name}, SPPU question papers"
        ),
        "subject_name": subject_name,
    }

    subject_papers = hydrate_subject_papers(subject)
    exam_order = {"insem": 0, "endsem": 1}
    subject_papers.sort(
        key=lambda paper: (
            exam_order.get(str(paper.get("exam_type") or "").lower(), 2),
            -extract_year(paper.get("paper_label") or ""),
        )
    )
    available_exam_types = {
        str(paper.get("exam_type") or "unknown").lower()
        for paper in subject_papers
        if isinstance(paper, dict)
    }
    if DEFAULT_EXAM_TYPE in available_exam_types:
        default_exam_type = DEFAULT_EXAM_TYPE
    elif "endsem" in available_exam_types:
        default_exam_type = "endsem"
    elif "insem" in available_exam_types:
        default_exam_type = "insem"
    elif "other" in available_exam_types:
        default_exam_type = "other"
    else:
        default_exam_type = DEFAULT_EXAM_TYPE

    pdf_data = [
        {
            "filename": viewer_filename(paper),
            "originalFilename": viewer_filename(paper),
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
        (paper for paper in subject_papers if paper.get("exam_type") == default_exam_type),
        subject_papers[0] if subject_papers else None,
    )
    has_questions = any(
        paper.get("question_count", 0) > 0
        for paper in subject_papers
        if isinstance(paper, dict)
    )

    return render_template(
        env,
        "viewer.html",
        subject_name=subject_name,
        branch_name=branch_name,
        subject_link=canonical_path.lstrip("/"),
        pdf_data_for_js=pdf_data,
        subject_papers=subject_papers,
        subject_semester_key=subject.get("semester_key", ""),
        initial_questions_paper_id=(initial_paper or {}).get("pdf_id", ""),
        seo_data=seo_data,
        default_exam_type=default_exam_type,
        has_questions=has_questions,
    )


def extract_year(label):
    match = re.search(r"\d{4}", label or "")
    return int(match.group()) if match else 0


def viewer_filename(paper):
    filename = paper.get("filename") or os.path.basename(urlparse(paper.get("pdf_url", "")).path)
    exam_type = str(paper.get("exam_type") or "").lower()
    if exam_type == "other" and "other" not in filename.lower():
        return f"other-{filename}"
    return filename


def hydrate_subject_papers(subject):
    papers = [dict(paper) for paper in subject.get("papers", []) if isinstance(paper, dict)]
    metadata_document = load_subject_metadata_document(subject)
    metadata_papers = metadata_document.get("papers", []) if isinstance(metadata_document, dict) else []
    metadata_by_id = {}
    metadata_by_url = {}

    for paper in metadata_papers:
        if not isinstance(paper, dict):
            continue
        if paper.get("pdf_id"):
            metadata_by_id[str(paper.get("pdf_id"))] = paper
        if paper.get("pdf_url"):
            metadata_by_url[str(paper.get("pdf_url"))] = paper

    for paper in papers:
        metadata_paper = metadata_by_id.get(str(paper.get("pdf_id") or "")) or metadata_by_url.get(
            str(paper.get("pdf_url") or "")
        )
        questions = []
        metadata = paper.get("metadata") or {}
        extraction_info = paper.get("extraction_info") or {}
        if metadata_paper:
            metadata = metadata_paper.get("metadata") or metadata
            extraction_info = metadata_paper.get("extraction_info") or extraction_info
            questions = [
                question
                for question in metadata_paper.get("questions", [])
                if isinstance(question, dict) and question.get("question_text")
            ]

        paper["metadata"] = metadata
        paper["extraction_info"] = extraction_info
        paper["questions"] = questions
        paper["question_count"] = len(questions)
        paper["question_groups"] = group_questions(questions)
    return papers


def load_subject_metadata_document(subject):
    subject_key = subject.get("subject_link") or ""
    branch = subject.get("branch_code") or subject.get("branch_key") or ""
    semester = subject.get("semester_key") or subject.get("year_key") or "subjects"
    if not subject_key or not branch:
        return {}

    path = PYQS_METADATA_DIR / branch / semester / f"{subject_key}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def group_questions(questions):
    groups = []
    current_group = None
    for index, question in enumerate(questions, start=1):
        question_number = str(question.get("question_number") or f"Q{index}").strip()
        if not current_group or current_group["question_number"] != question_number:
            current_group = {"question_number": question_number, "questions": [], "total_marks": 0}
            groups.append(current_group)
        marks = question.get("marks")
        if isinstance(marks, (int, float)):
            current_group["total_marks"] += marks
        current_group["questions"].append(question)
    return groups


def load_sitemap_data():
    branches = {}
    for entry in load_question_papers()["question_papers_list"]:
        pattern = entry.get("pattern_year") or "honors"
        branch_name = entry.get("branch_name") or "SPPU"
        group_name = f"{pattern} - {branch_name}" if pattern != "honors" else branch_name
        branches.setdefault(group_name, [])
        branches[group_name].append({
            "url": entry["public_url"],
            "name": entry["subject_name"],
            "sem": entry.get("sem_no"),
            "year_label": entry.get("year_label") or "",
        })

    for subject_list in branches.values():
        subject_list.sort(key=lambda item: (semester_sort_value(item["sem"]), item["year_label"], item["name"]))
    return branches


def semester_sort_value(value):
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999


def write_search_index():
    entries = load_question_papers()["question_papers_list"]
    write_file("static/search.1.json", json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_sitemap_xml():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    urls = [
        {"loc": f"{SITE_URL}/", "priority": "1.0", "changefreq": "weekly"},
        {"loc": f"{SITE_URL}/2019", "priority": "0.95", "changefreq": "weekly"},
        {"loc": f"{SITE_URL}/2015", "priority": "0.8", "changefreq": "weekly"},
        {"loc": f"{SITE_URL}/2012", "priority": "0.8", "changefreq": "weekly"},
        {"loc": f"{SITE_URL}/sitemap", "priority": "0.6", "changefreq": "weekly"},
        {"loc": f"{SITE_URL}/contact", "priority": "0.7", "changefreq": "monthly"},
        {"loc": f"{SITE_URL}/privacy", "priority": "0.5", "changefreq": "monthly"},
        {"loc": f"{SITE_URL}/terms", "priority": "0.5", "changefreq": "monthly"},
    ]
    for entry in load_sitemap_entries():
        urls.append({"loc": f"{SITE_URL}{entry['public_url']}", "priority": "0.85", "changefreq": "weekly"})

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        lines.extend([
            "  <url>",
            f"    <loc>{url['loc']}</loc>",
            f"    <lastmod>{today}</lastmod>",
            f"    <priority>{url['priority']}</priority>",
            f"    <changefreq>{url['changefreq']}</changefreq>",
            "  </url>",
        ])
    lines.append("</urlset>")
    write_file("sitemap.xml", "\n".join(lines) + "\n")


def write_headers():
    content = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: SAMEORIGIN

/static/dist/*
  Cache-Control: public, max-age=31536000, immutable

/static/fonts/*
  Cache-Control: public, max-age=31536000, immutable

/static/images/*
  Cache-Control: public, max-age=31536000, immutable

/images/*
  Cache-Control: public, max-age=31536000, immutable

/static/pdfjs/web/viewer
  Content-Type: text/html; charset=utf-8
  Cache-Control: public, max-age=3600

/static/pdfjs/*
  Cache-Control: public, max-age=3600

/static/search.1.json
  Cache-Control: public, max-age=3600

/manifest/*
  Cache-Control: public, max-age=3600

/sitemap.xml
  Content-Type: application/xml; charset=utf-8
  Cache-Control: public, max-age=3600
"""
    write_file("_headers", content)


def write_redirects():
    lines = [
        "/api/question-papers/list /static/search.1.json 301",
        "/static/asset-manifest.json /static/asset-manifest.json 200",
    ]
    data = load_question_papers()
    seen = set()
    for entry in data["question_papers_list"]:
        subject_key = entry.get("subject_link", "").split("/")[-1]
        if not subject_key or subject_key in seen:
            continue
        redirect_path = get_legacy_redirect(subject_key)
        if redirect_path:
            lines.append(f"/{subject_key} {redirect_path} 301")
            seen.add(subject_key)
    lines.append("/papers/* https://sppu-pyqs.albatrossc.workers.dev/papers/:splat 302")
    write_file("_redirects", "\n".join(lines) + "\n")


def main():
    if DIST_DIR.exists():
        empty_directory(DIST_DIR)
    else:
        DIST_DIR.mkdir(parents=True, exist_ok=True)

    copy_static_files()
    asset_manifest = build_assets()
    write_search_index()

    env = create_environment(asset_manifest)
    render_pattern_pages(env)
    render_viewer_pages(env)
    render_info_pages(env)
    write_sitemap_xml()
    write_headers()
    write_redirects()

    page_count = len(list(DIST_DIR.rglob("index.html")))
    print(f"Built {page_count} HTML pages into {DIST_DIR}")


def empty_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


if __name__ == "__main__":
    main()
