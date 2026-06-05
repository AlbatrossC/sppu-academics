import os
from datetime import datetime

from flask import Blueprint, abort, make_response, render_template, request, redirect, flash, url_for, send_from_directory, jsonify

from ..config import BASE_DIR, CODES_SITE_URL, SITE_URL
from ..db import save_contact
from ..notifications import send_discord_notification_async
from ..utils import load_question_papers, load_sitemap_entries

main_bp = Blueprint("main", __name__)


def _is_ajax_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _notification_request_context():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else (request.remote_addr or "Unknown")
    return {
        "ip_address": ip_address,
        "source_url": request.url,
        "user_agent": request.headers.get("User-Agent", "Unknown")
    }


@main_bp.route("/contact", methods=["GET", "POST"])
def contact_us():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        if save_contact(name, email, message):
            success_message = "Your message has been sent successfully!"
            flash(success_message, "success")
            send_discord_notification_async("contact", {
                "name": name,
                "email": email,
                "message": message,
                **_notification_request_context()
            })
            if _is_ajax_request():
                return jsonify({"ok": True, "message": success_message}), 200
        else:
            error_message = "An error occurred. Please try again."
            flash(error_message, "error")
            if _is_ajax_request():
                return jsonify({"ok": False, "message": error_message}), 500

        return redirect(url_for('main.contact_us'))

    return render_template("contact.html")


@main_bp.route("/images/<filename>")
def get_image(filename):
    images_dir = os.path.join(BASE_DIR, "static", "images")
    if not os.path.exists(os.path.join(images_dir, filename)):
        abort(404)
    return send_from_directory(images_dir, filename)


@main_bp.route("/robots.txt")
def robots():
    return send_from_directory(BASE_DIR, "robots.txt")


@main_bp.route("/sitemap.xml")
def sitemap():
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
        urls.append({
            "loc": f"{SITE_URL}{entry['public_url']}",
            "priority": "0.85",
            "changefreq": "weekly"
        })

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for url in urls:
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{url['loc']}</loc>")
        xml_lines.append(f"    <lastmod>{today}</lastmod>")
        xml_lines.append(f"    <priority>{url['priority']}</priority>")
        xml_lines.append(f"    <changefreq>{url['changefreq']}</changefreq>")
        xml_lines.append("  </url>")

    xml_lines.append("</urlset>")

    response = make_response("\n".join(xml_lines))
    response.headers["Content-Type"] = "application/xml"
    return response


def _load_sitemap_data():
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
        subject_list.sort(key=lambda s: (s["sem"] or 0, s["year_label"], s["name"]))

    return branches


@main_bp.route("/sitemap")
def sitemap_html():
    return render_template(
        "sitemap.html",
        site_url=SITE_URL,
        codes_site_url=CODES_SITE_URL,
        branches=_load_sitemap_data()
    )


@main_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@main_bp.route("/terms")
def terms():
    return render_template("terms.html")


@main_bp.route("/ads.txt")
def ads_txt():
    return send_from_directory(BASE_DIR, "ads.txt")


@main_bp.route("/3fae365259364fc18250c434fb1477f0.txt")
def bing_site_verification():
    return send_from_directory(BASE_DIR, "3fae365259364fc18250c434fb1477f0.txt")
