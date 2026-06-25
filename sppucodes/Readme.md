# sppucodes — Developer Guide

> 🌐 [sppucodes.vercel.app](https://sppucodes.vercel.app) &nbsp;|&nbsp; Part of [sppu-academics](../README.md)

This document is for developers working on the `sppucodes` codebase. It covers how the app is structured, how data flows through it, how to add new subjects or questions, and what each module does.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Data Format — Questions JSON](#data-format--questions-json)
- [Data Format — Answer Files](#data-format--answer-files)
- [Routes Reference](#routes-reference)
- [Key Modules](#key-modules)
- [Environment Variables](#environment-variables)
- [Adding a New Subject](#adding-a-new-subject)
- [Adding a New Question](#adding-a-new-question)
- [Deployment](#deployment)
- [Dependencies](#dependencies)

---

## Overview

`sppucodes` is a Flask web application that serves SPPU lab programs and code solutions. It has two distinct access modes:

- **Browser** — renders solutions in a styled viewer with syntax highlighting, copy/download buttons, and SSR-rendered code pages
- **Terminal API** — serves plain-text or ANSI-beautified output via `curl`, designed to be used directly in a terminal without opening a browser

All content — questions and answers — is file-based. There is no traditional database for content. Submissions and contact messages are persisted via a Cloudflare Worker that writes to a Cloudflare D1 database.

---

## Project Structure

```
sppucodes/
│
├── app.py                      ← Entry point. Creates the Flask app and starts the server.
│
├── src/
│   ├── __init__.py             ← App factory (create_app). Registers blueprints, middleware, error handlers.
│   ├── config.py               ← All env vars and path constants.
│   ├── db.py                   ← DB layer — delegates to Cloudflare Worker via HTTP.
│   ├── utils.py                ← Subject/answer loading, caching, rendering helpers.
│   ├── async_logger.py         ← API request logger (synchronous, wrapped in a class).
│   ├── terminal_beautify.py    ← ANSI terminal output renderer using Rich.
│   ├── notifications.py        ← Discord webhook notifications for submissions/contact.
│   └── routes/
│       ├── main.py             ← Home, /submit, /contact, SEO routes (sitemap, robots.txt).
│       ├── subjects.py         ← /<subject> and /<subject>/<question_id> page routes.
│       └── api.py              ← /api/<subject>/<question_no> — terminal and browser API.
│
├── questions/                  ← One JSON file per subject. Defines questions and metadata.
│   ├── cnl.json
│   ├── dsl.json
│   └── ...
│
├── answers/                    ← One folder per subject. Contains the actual code files.
│   ├── cnl/
│   │   ├── 1_bus_topology.txt
│   │   └── ...
│   └── ...
│
├── templates/                  ← Jinja2 HTML templates.
│   ├── index.html
│   ├── subject.html
│   ├── question.html
│   ├── submit.html
│   ├── contact.html
│   ├── error.html
│   └── ...
│
├── static/
│   ├── css/                    ← Per-page stylesheets.
│   ├── js/                     ← Client-side JS (code viewer, analytics, terminal demo).
│   └── fonts/                  ← JetBrains Mono (woff2), served with 1-year cache headers.
│
├── requirements.txt
└── vercel.json                 ← Vercel deployment config.
```

---

## How It Works

### Request flow for a browser visit

```
User visits /{subject}/{question_id}
    │
    ▼
subjects_bp → subject_listing() or question_page()    [src/routes/subjects.py]
    │
    ▼
load_subject_data(subject_link)                        [src/utils.py]
    │   Reads questions/{subject}.json, builds index, caches with @lru_cache
    ▼
load_answer_files_ssr(subject_link, file_names)        [src/utils.py]
    │   Reads answers/{subject}/*.{py,cpp,sql,...}
    │   Detects file type → renders as code / markdown / ipynb / image
    ▼
render_template("question.html", ...)                  [templates/question.html]
```

### Request flow for a terminal API call

```
curl.exe https://sppucodes.vercel.app/api/cnl/16
    │
    ▼
api_bp → answer_api(subject_link, question_no)         [src/routes/api.py]
    │
    ▼
_cached_answer(subject_link, question_no)              [lru_cache]
    │   load_subject_data → load_answer_files
    ▼
is_terminal_request(request)
    │   True if no ?no_question or ?split params
    ▼
beautify_terminal_output(contents, question_text)      [src/terminal_beautify.py]
    │   Uses Rich to render .md → Markdown, .ipynb → panels, others → plain
    ▼
text/plain response with ANSI escape codes
```

### Caching

All subject data and answer file reads are cached in-process using `@lru_cache`. On app startup, `preload_subject_cache()` warms the cache for all subjects so the first real request is fast.

---

## Data Format — Questions JSON

Every subject has a JSON file in `questions/`. Here is the structure:

```json
{
  "default": {
    "subject_code": "CN",
    "subject_name": "Computer Networks",
    "description": "SEO meta description for the subject page.",
    "keywords": ["TCP", "UDP", "Subnetting", "..."],
    "url": "https://sppucodes.vercel.app/cnl",
    "question_paper_url": "https://sppupyqs.pages.dev/computer-networks-aids"
  },
  "questions": [
    {
      "group": "A",
      "question_no": "1",
      "id": "bus-topology",
      "question": "Demonstrate the different types of topologies...",
      "subject_code": "cn",
      "file_name": ["1_bus_topology.txt"],
      "title": "Network Topologies and Transmission Media using Packet Tracer"
    }
  ]
}
```

| Field | Description |
|:---|:---|
| `default` | Metadata for the subject page — SEO, name, linking to sppupyqs |
| `questions[].group` | Group label (A, B, C) — used to visually separate questions on the subject page |
| `questions[].question_no` | Number used by the terminal API (`/api/cnl/1`) |
| `questions[].id` | URL slug used for the browser page (`/cnl/bus-topology`) |
| `questions[].file_name` | Array of file names in `answers/{subject}/` — supports multiple files per question |
| `questions[].title` | Optional override for the page `<title>`. Falls back to first 50 chars of `question` |
| `question_paper_url` | Links the subject page to the corresponding question papers on sppupyqs |

> **Note on `question_no`:** The API matches case-insensitively. Both `/api/cnl/16` and `/api/cnl/16` work. The index is built with `.upper()` keys.

---

## Data Format — Answer Files

Answer files live in `answers/{subject_code}/`. The filename convention is:

```
{question_no}_{short_description}.{ext}
```

Examples: `1_bus_topology.txt`, `5_subnetting_program.py`, `7_tcp_ubuntu.txt`

**Supported file types and how they render:**

| Extension | Browser render | Terminal render |
|:---|:---|:---|
| `.py`, `.cpp`, `.c`, `.java`, `.sql`, `.js`, etc. | Syntax-highlighted code block | Plain text |
| `.md` | Rendered Markdown (via `markdown` lib) | Rich Markdown (bold, headers, lists) |
| `.ipynb` | Custom cell-by-cell renderer | Rich panels with syntax highlighting |
| `.txt` | Plain text code block | Plain text |
| `.pkt` | Raw file served via `/raw-answers/` | Plain text |
| Images (`.jpg`, `.png`) | Served via `/raw-answers/` as `<img>` | `[Binary File]` placeholder |

A question can have **multiple files** in `file_name`. All files are shown in sequence — useful when a question has both a Windows and Ubuntu solution, or multiple implementations.

---

## Routes Reference

| Method | Path | Blueprint | Description |
|:---|:---|:---|:---|
| `GET` | `/` | `main_bp` | Homepage |
| `GET` | `/submit` | `main_bp` | Code submission form |
| `POST` | `/submit` | `main_bp` | Saves submission → Cloudflare Worker, notifies Discord |
| `GET` | `/contact` | `main_bp` | Contact form |
| `POST` | `/contact` | `main_bp` | Saves contact → Cloudflare Worker, notifies Discord |
| `GET` | `/sitemap.xml` | `main_bp` | Dynamically generated XML sitemap |
| `GET` | `/<subject>` | `subjects_bp` | Subject listing page |
| `GET` | `/<subject>/<question_id>` | `subjects_bp` | SSR question page |
| `GET` | `/api/<subject>/<question_no>` | `api_bp` | Terminal / browser API |
| `GET` | `/api/subjects/search` | `api_bp` | Returns JSON list of all subjects |
| `GET` | `/raw-answers/<subject>/<filename>` | `raw_api_bp` | Serves raw answer files (images, PDFs) |

**API query parameters** on `/api/<subject>/<question_no>`:

| Param | Value | Effect |
|:---|:---|:---|
| `no_question` | `1` | Omits the question text from the response |
| `split` | `1`, `2`, ... | Returns only the Nth file when a question has multiple files |

---

## Key Modules

### `src/utils.py`

The core data layer. All reads go through here.

- `load_subject_data(subject_link)` — loads and caches a subject's JSON. Builds `processed_groups`, `sorted_groups`, and `_q_index` on first load.
- `load_answer_files(subject_link, files)` — loads answer files for the API (plain text, cached).
- `load_answer_files_ssr(subject_link, files)` — loads answer files for SSR pages, with type detection and rendering (markdown, ipynb, images).
- `get_render_info(filename)` — determines render type and Prism.js language class from file extension.
- `preload_subject_cache()` — called at startup to warm the `lru_cache` for all subjects.

### `src/terminal_beautify.py`

Handles ANSI-rich output for terminal requests. Uses the `rich` library.

- Only activates when the response contains `.md` or `.ipynb` files — plain code files skip it.
- Renders Markdown with `rich.markdown.Markdown` and Jupyter notebooks cell-by-cell with panels, execution counts, and output blocks.
- Plain code files fall through to a simple text response — no unnecessary dependencies.

### `src/db.py`

All writes go through a Cloudflare Worker which inserts into a Cloudflare D1 (SQLite) database. The Flask app makes a synchronous HTTP POST to the Worker and moves on.

- `save_submission()` — code contribution from the /submit form
- `save_contact()` — contact message from the /contact form
- `save_api_request()` — logs terminal API usage (subject, question, status)
- `save_paper_download()` — logs paper download events (used by sppupyqs too)

> Failures are silently swallowed so a Worker outage never affects the user experience.

### `src/notifications.py`

Sends formatted Discord embeds on form submissions. Two event types: `submit` and `contact`. Uses a synchronous `requests.post` with a 3-second timeout so it doesn't noticeably block the response.

### `src/async_logger.py`

A thin class wrapping `save_api_request()`. Originally threaded; now synchronous because Vercel kills background threads when the response is sent.

---

## Environment Variables

Create a `.env` file in the `sppucodes/` root for local development:

```env
# Required for DB writes and Discord notifications
CF_WORKER_DB_URL=https://your-worker.workers.dev
DB_API_KEY=your_api_key_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Optional overrides
SPPUCODES_SITE_URL=https://sppucodes.vercel.app
SPPUPYQS_SITE_URL=https://sppupyqs.pages.dev
SECRET_KEY=your_secret_key

# Set to "true" to show the maintenance page for all requests
MAINTENANCE_MODE=false

# Set to "true" to enable Flask debug mode locally
FLASK_DEBUG=true
```

> None of these are required to run locally — the app starts fine without them. DB writes and Discord notifications will silently no-op.

---

## Adding a New Subject

**Step 1 — Create the questions JSON**

Add `questions/{subject_code}.json`. Use an existing file as a template. The `subject_code` in the filename becomes the URL slug (e.g. `oop.json` → `/oop`).

**Step 2 — Create the answers folder**

```
answers/{subject_code}/
```

Add all answer files here. Follow the naming convention: `{question_no}_{description}.{ext}`.

**Step 3 — Link to sppupyqs** *(optional)*

Set `question_paper_url` in the `default` block to the corresponding subject URL on sppupyqs. This adds a "View Question Papers" link on the subject page.

That's it — no code changes needed. The subject is auto-discovered at startup via `os.listdir(QUESTIONS_DIR)`.

---

## Adding a New Question

**Step 1 — Add the answer file(s)**

Drop the file in `answers/{subject_code}/`. Name it `{question_no}_{description}.{ext}`.

**Step 2 — Add the question entry to the JSON**

Open `questions/{subject_code}.json` and add a new entry to the `questions` array:

```json
{
  "group": "B",
  "question_no": "17",
  "id": "your-url-slug",
  "question": "Full question text as given in the lab manual.",
  "subject_code": "cnl",
  "file_name": ["17_your_file.py"],
  "title": "Optional page title override"
}
```

The `id` becomes the URL: `/{subject}/{id}`. Keep it lowercase, hyphen-separated.

> The in-process `lru_cache` will serve stale data until the next cold start. On Vercel, a fresh deployment clears it automatically. Locally, restart the server.

---

## Deployment

The app is deployed on **Vercel** using the `@vercel/python` runtime.

`vercel.json` configures:
- All routes except `/static/**` are forwarded to `app.py`
- Static assets are served directly by Vercel's CDN
- Answer files, questions, templates, and static folders are all included in the build via `includeFiles`

To deploy:

```bash
vercel --prod
```

Set all environment variables in the Vercel project dashboard under **Settings → Environment Variables**.

> The runtime is pinned to Python 3.9 in `vercel.json`. Do not use syntax or stdlib features from later versions.

---

## Dependencies

| Package | Purpose |
|:---|:---|
| `Flask` | Web framework |
| `flask-compress` | Gzip/Brotli response compression |
| `gunicorn` | WSGI server (used by Vercel) |
| `requests` | HTTP client for Cloudflare Worker and Discord webhook calls |
| `python-dotenv` | Loads `.env` for local development |
| `rich` | ANSI terminal rendering for `.md` and `.ipynb` files |
| `markdown` | Renders `.md` files to HTML for SSR pages |
| `nbformat` | Parses `.ipynb` Jupyter notebooks |
