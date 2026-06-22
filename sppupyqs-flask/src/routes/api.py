from urllib.parse import urlparse

import requests
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from ..async_logger import log_paper_download_async
from ..config import PDF_PROXY_ALLOWED_HOSTS
from ..utils import load_question_papers

api_bp = Blueprint("api", __name__, url_prefix="/api")
API_CACHE_CONTROL = "public, s-maxage=3600, stale-while-revalidate=86400"
_pdf_http = requests.Session()


@api_bp.after_request
def add_api_cache_headers(response):
    response.headers["Cache-Control"] = API_CACHE_CONTROL
    return response


@api_bp.route("/question-papers/list")
def question_papers_list():
    return jsonify(load_question_papers()["question_papers_list"])


@api_bp.route("/notify-download", methods=["POST"])
def notify_download():
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"error": "invalid json"}), 400

        fingerprint_id = (payload.get("fingerprint_id") or "").strip()[:255]
        subject_link = (payload.get("subject_link") or payload.get("subject") or "").strip()[:100]
        if not fingerprint_id or not subject_link:
            return jsonify({"error": "missing fingerprint_id or subject"}), 400

        log_paper_download_async(fingerprint_id, subject_link)
        return jsonify({"ok": True}), 200
    except Exception:
        current_app.logger.exception("notify_download error")
        return jsonify({"error": "server error"}), 500


@api_bp.route("/pdf-proxy")
def pdf_proxy():
    pdf_url = request.args.get("url", "").strip()
    if not pdf_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400

    try:
        parsed = urlparse(pdf_url)
    except Exception:
        return jsonify({"error": "Invalid URL"}), 400

    if parsed.netloc.lower() not in PDF_PROXY_ALLOWED_HOSTS:
        return jsonify({"error": "Domain not allowed"}), 403
    if not parsed.path.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    headers = {"User-Agent": "SPPU-Question-Papers-Hub/1.0"}
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header

    try:
        upstream = _pdf_http.get(pdf_url, timeout=30, stream=True, headers=headers)
        upstream.raise_for_status()
    except requests.exceptions.HTTPError as error:
        if upstream.status_code != 206:
            current_app.logger.warning(f"pdf_proxy fetch error for {pdf_url}: {error}")
            return jsonify({"error": "Failed to fetch PDF"}), 502
    except requests.exceptions.RequestException as error:
        current_app.logger.warning(f"pdf_proxy fetch error for {pdf_url}: {error}")
        return jsonify({"error": "Failed to fetch PDF"}), 502

    def generate():
        for chunk in upstream.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    response = Response(
        stream_with_context(generate()),
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "application/pdf"),
    )
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"

    for header_name in ["Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"]:
        header_val = upstream.headers.get(header_name)
        if header_val:
            response.headers[header_name] = header_val
    return response
