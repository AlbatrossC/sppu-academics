<div align="center">

# 📄 SPPU PYQ Sync Toolkit

**Automated pipeline for syncing, normalizing, and publishing**
**SPPU (Savitribai Phule Pune University) previous year question papers.**

[🌐 Browse Papers → sppupyqs.vercel.app](https://sppupyqs.vercel.app)

</div>

---

## 📑 Table of Contents

- [Where Papers Come From](#-where-papers-come-from)
- [Pipeline Overview](#-pipeline-overview)
- [Where Papers Are Served From](#-where-papers-are-served-from)
- [Paper Organization](#-paper-organization)
- [File Naming Scheme](#-file-naming-scheme)
- [Manifests](#-manifests)
- [Getting Started](#-getting-started)
- [Agent Mode](#-agent-mode)
- [Typical Workflow](#-typical-workflow)
- [GPU & OCR](#-gpu--ocr)
- [Project Layout](#-project-layout)
- [Documentation](#-documentation)

---

## 📥 Where Papers Come From

Papers are sourced from a public Google Drive maintained by **Zeal Education**:

> 📧 [unipunepaper@zealeducation.com](mailto:unipunepaper@zealeducation.com)  
> 📂 [drive.google.com/drive/folders/0Bz9C0ysJZ7PnMGZKeWcybUpXWGM](https://drive.google.com/drive/folders/0Bz9C0ysJZ7PnMGZKeWcybUpXWGM)

This toolkit downloads from there, normalizes everything, and republishes with structured metadata and reliable CDN delivery. GitHub acts as a tertiary fallback since all tracked PDFs are committed here.

---

## 🔁 Pipeline Overview

```
 ┌─────────────────────────────────────┐
 │   Google Drive  (Zeal Education)    │
 └───────────────┬─────────────────────┘
                 │
                 ▼
         [ mapping/ ]          ← Discover folder structure
                 │
                 ▼
         [ incoming/ ]         ← Download raw PDFs
                 │
         PyMuPDF + PaddleOCR
                 │ + Groq (last resort)
                 ▼
          [ papers/ ]          ← Rename with extracted metadata
                 │
        ┌────────┴────────┐
        ▼                 ▼
  Cloudflare R2      Cloudinary     ← Upload to both CDNs simultaneously
        └────────┬────────┘
                 │
                 ▼
         [ manifest/ ]         ← Generate JSON for the web app
                 │
                 ▼
      sppupyqs.vercel.app
```

> [!IMPORTANT]
> Every step that modifies files is **review-first** — it writes a changelog, you inspect it, then you apply. Nothing destructive happens silently.

---

## 🌐 Where Papers Are Served From

The web app reads from `manifest/` JSON files to resolve download links. Every paper is uploaded to **both** CDNs simultaneously and the canonical file path is **identical across both** — only the base URL differs.

```
Primary  │ Cloudflare R2  │ https://sppu-pyqs.albatrossc.workers.dev
Mirror   │ Cloudinary     │ https://res.cloudinary.com/diiiuwl1p/raw/upload
```

A full paper URL is formed as:

```
{baseUrl}/{relative_path_to_pdf}

── R2 ──────────────────────────────────────────────────────────────────────
https://sppu-pyqs.albatrossc.workers.dev
  /papers/artificial-intelligence-and-data-science/se/2019_pattern
  /discrete_mathematics_aids/endsem_nov_dec_2025_aids_dma_2019p.pdf

── Cloudinary ───────────────────────────────────────────────────────────────
https://res.cloudinary.com/diiiuwl1p/raw/upload
  /papers/artificial-intelligence-and-data-science/se/2019_pattern
  /discrete_mathematics_aids/endsem_nov_dec_2025_aids_dma_2019p.pdf
```

The canonical path — everything after the base URL — is identical on both. Only the base changes.

Switching the active CDN is a one-line config change in the web app — no re-uploading, no path changes.

### Hosting history

Papers were originally hosted on **Supabase Storage**. On 1 March 2026, the Indian government issued a network-wide blocking order against Supabase ([TechCrunch, Feb 27 2026](https://techcrunch.com/2026/02/27/india-disrupts-access-to-popular-developer-platform-supabase-with-blocking-order/)), which broke delivery overnight for the entire target audience — Indian students. This triggered a full migration to Cloudflare R2 + Cloudinary. No Supabase scripts remain in the codebase. The identical-path dual-CDN design is a direct consequence of that incident.

---

## 🗂️ Paper Organization

Papers span four folder families, each with its own hierarchy depth:

### 🔧 Standard Engineering Branches
`Branch / Year / Pattern / Subject`

```
papers/computer-engineering/te/2019_pattern/web_technology_comp/
```

Covers: `AI & Data Science` · `AI & Machine Learning` · `Civil` · `Computer` · `E&TC` · `Electrical` · `Electronics & Computer` · `IT` · `Mechanical` · `Robotics`

### 🎓 First Year
`First Year / Pattern / Subject` *(no year tier)*

```
papers/first-year/2019_pattern/engineering_mathematics_I_fy/
```

### 💼 MBA
`M.B.A / Semester / Pattern / Subject` *(semesters, not years)*

```
papers/m-b-a/sem_II/2019_pattern/financial_management/
```

### 🏅 Honors Course
`Honors Course / Year / Subject` *(no pattern tier)*

```
papers/honors-course/te/artificial_intelligence_hc/
```

> **Naming conventions:** Branches use hyphens (`computer-engineering`); everything else uses underscores (`2019_pattern`). `&` becomes `and`. Roman numerals stay uppercase (`engineering_mathematics_II`).

---

## 🏷️ File Naming Scheme

Every PDF follows this pattern:

```
{exam_type}_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf
```

| Field | Values | Source |
|---|---|---|
| `exam_type` | `insem` · `endsem` · `other` | Detected from total marks on the paper — **30 → `insem`**, **70 → `endsem`**, anything else → `other` |
| `month` | `may_jun`, `oct`, `nov_dec`, … | **Filename only** — Drive filenames carry only month and year; Groq is used to normalize unusual or ambiguous month formats |
| `year` | e.g. `2024` | Filename → PyMuPDF (header text) → PaddleOCR (page crop) → Groq |
| `branch_code` | `comp`, `aids`, `fy`, `hc`, … | **Always from folder path — never a model** |
| `subject_code` | `wt`, `ml`, `em1`, `ai`, … | **Always from folder path — never a model** |
| `pattern_code` | `2019p`, `te`, … | **Always from folder path — never a model** |

### Raw Drive filename → Normalized filename

Files on Drive carry only the exam month and year. Everything else — branch, subject, pattern, exam type — is derived from context.

| Raw filename (from Drive) | Normalized filename |
|---|---|
| `May - 2024.pdf` | `endsem_may_jun_2024_comp_wt_2019p.pdf` |
| `Oct 2023.pdf` | `insem_oct_2023_aids_ml_2019p.pdf` |
| `Nov Dec 2022.pdf` | `endsem_nov_dec_2022_fy_em1_2019p.pdf` |
| `May 2024.pdf` | `endsem_may_2024_hc_ai_te.pdf` |

*The folder the file lives in tells the pipeline its branch, subject, and pattern. The mark count on the paper tells it whether it's an insem or endsem.*

---

## 📦 Manifests

`manifest/` is the final deliverable — per-subject JSON files that the web app reads to know which PDFs exist, where they live on the CDN, and which semester they belong to.

After uploading papers to both CDNs:

```bash
python tools/upload_pipeline.py manifest
```

Then copy `manifest/` into the web app repository.

---

## 🚀 Getting Started

### 1 — Clone this branch

```bash
git clone -b sppu-pyqs https://github.com/AlbatrossC/sppu-academics.git
cd sppu-academics
```

### 2 — Set up Python

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
```

### 3 — Create config files

```bash
cp .env.example .env
cp config.example.json config.json
```

### 4 — Fill in `.env`

```env
# ── Google Drive (required) ────────────────────────────────────────────────
GOOGLE_API_KEY=...              # Google Cloud Console → enable Drive API

# ── Groq (optional — month/year normalization fallback) ───────────────────
GROQ_API_KEY=...                # console.groq.com

# ── Cloudflare R2 (required for uploads) ──────────────────────────────────
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=sppu-pyqs
R2_ENDPOINT_URL=https://....r2.cloudflarestorage.com

# ── Cloudinary (required for mirror uploads) ──────────────────────────────
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

### 5 — Fill in `config.json`

```json
{ "root_folder_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM" }
```

### 6 — Launch the interactive console

```bash
python main.py
```

Or run individual tools directly — see [Typical Workflow](#-typical-workflow).

---

## 🤖 Agent Mode

The entire toolkit is designed to work with AI coding agents. To use it, pass two things to your agent:

1. **The contents of [`docs/agents.md`](docs/agents.md)** — covers every operation, folder family, and edge case the agent needs to pick the right commands
2. **Your task in plain English** — describe what you want done

The agent reads the doc, determines the right commands, reviews changelogs, and applies — the same review-first pipeline a human would follow through `main.py`, just hands-free.

**Compatible with:** Antigravity · Claude Code · Codex · any agent that can read files and run shell commands

### Example tasks to pass alongside `docs/agents.md`

```
"Fetch the latest Computer Engineering papers"
"Check if E&TC has a new pattern available"
"Scan AI and Data Science files and check if they're up to date"
"Rename the files in incoming"
"Fix the needs_review files"
"Run verify and move for First Year"
"Upload everything to R2"
"Map semesters for AIDS TE 2019 Pattern"
```

---

## 🔄 Typical Workflow

```bash
# ── Step 1: Validate mappings (offline, no API calls) ─────────────────────
python tools/validate_mappings.py

# ── Step 2: Discover and sync Drive folders ───────────────────────────────
python tools/sync.py --folders
python tools/sync.py --folders --apply
python tools/rename_folders.py --create

# ── Step 3: Scan Drive for new PDFs and download ──────────────────────────
python tools/sync.py --files "Computer Engineering"
python tools/sync.py --files --apply --rclone --workers 8

# ── Step 4: Normalize folders and rename PDFs ─────────────────────────────
python tools/rename_folders.py
python tools/rename_files.py --ocr-workers 1
python tools/rename_files.py --apply

# ── Step 5: Verify and move to papers/ ───────────────────────────────────
python tools/verify.py
python tools/move.py

# ── Step 6: Upload to both CDNs and generate manifests ───────────────────
python tools/upload_pipeline.py scan
python tools/upload_pipeline.py sync --workers 4
python tools/upload_pipeline.py manifest

# ── Step 7: Check current status ─────────────────────────────────────────
python tools/status.py --print
```

Each review step writes a changelog under `changelog/` — read it before running the matching `--apply`.

| Changelog file | Covers |
|---|---|
| `changelog/folder.md` | Folder renames and creations |
| `changelog/files.md` | File downloads and deletions |
| `changelog/rename.md` | PDF metadata renames |

---

## ⚡ GPU & OCR

PaddleOCR reads mark totals from PDF page images when embedded text is missing or garbled. It defaults to GPU and processes hundreds of PDFs in minutes.

```bash
# GPU (default — recommended for large batches)
python tools/rename_files.py --ocr-workers 1 --ocr-device gpu:0

# CPU fallback
python tools/rename_files.py --ocr-workers 1 --ocr-device cpu
```

| Component | Version |
|---|---|
| PaddleOCR | 3.6.0 |
| PaddlePaddle GPU | 3.3.0 |
| PaddleX | 3.6.1 |

> Without a GPU the pipeline still works — considerably slower on large batches.

---

## 🗃️ Project Layout

```
sppu-academics/
│
├── papers/           # Normalized PDFs                        [committed]
├── manifest/         # Delivery JSON for the web app          [committed]
├── mapping/          # Drive structure maps & name registry   [committed]
│
├── tools/            # Pipeline scripts
├── docs/             # Per-tool documentation
├── main.py           # Interactive console
│
├── incoming/         # Raw downloads                          [gitignored]
├── needs_review/     # Files that failed renaming             [gitignored]
├── changelog/        # Review changelogs                      [gitignored]
└── tracking/         # SQLite state                           [gitignored]
```

---

## 📚 Documentation

| Doc | What it covers |
|---|---|
| [Overview](docs/overview.md) | Architecture, lifecycle stages, tool effects |
| [Agents](docs/agents.md) | Instructions for AI coding agents |
| [Sync](docs/sync.md) | Folder & file sync from Drive |
| [Mapping](docs/mapping.md) | JSON mapping schemas |
| [Rename Folders](docs/rename_folders.md) | Folder normalization rules |
| [Rename Files](docs/rename_files.md) | PDF metadata extraction & naming |
| [Verify & Move](docs/verify_move.md) | Final checks before `papers/` |
| [Upload Pipeline](docs/upload_pipeline.md) | R2 uploads & manifest generation |
| [Semester Mapping](docs/semester.md) | Assigning semester numbers to subjects |
| [Pipeline](docs/pipeline.md) | One-command orchestrated runs |
| [Disaster Recovery](docs/disaster_recovery.md) | Rebuilding from a fresh clone |

---

<div align="center">

Question papers are sourced from [Zeal Education's](mailto:unipunepaper@zealeducation.com) public Drive archive.  
This project provides tooling and delivery infrastructure only.  
Content rights belong to **SPPU** and the respective authors.

</div>