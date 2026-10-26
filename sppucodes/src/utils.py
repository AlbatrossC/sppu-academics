import json
import os
import re
from uuid import uuid4
from html import escape
from functools import lru_cache

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from .config import QUESTIONS_DIR, ANSWERS_DIR


@lru_cache(maxsize=64)
def load_subject_data(subject_link):
    json_path = os.path.join(QUESTIONS_DIR, f"{subject_link}.json")
    if not os.path.exists(json_path):
        return None

    with open(json_path, "r", encoding="utf-8-sig") as file_obj:
        data = json.load(file_obj)

    questions = data.get("questions", [])
    groups = {}
    for question in questions:
        question_text = question.get("question")
        if isinstance(question_text, str):
            question["question"] = question_text.replace("/n", "\n")
        groups.setdefault(question.get("group", ""), []).append(question)

    data["processed_groups"] = groups
    data["sorted_groups"] = sorted(groups.keys())
    data["_q_index"] = {
        str(question.get("question_no")).upper(): question
        for question in questions
    }
    return data


def get_question_by_id(questions, question_id):
    return next((question for question in questions if question["id"] == question_id), None)


def get_question_by_number(questions, question_no):
    return next((question for question in questions if str(question.get("question_no")) == str(question_no)), None)


def organize_questions_by_group(questions):
    groups = {}
    for question in questions:
        groups.setdefault(question["group"], []).append(question)
    return groups, sorted(groups.keys())


@lru_cache(maxsize=256)
def _read_answer_file(filepath):
    ext = filepath.split(".")[-1].lower() if "." in filepath else ""
    if ext in ["pdf", "jpg", "jpeg", "png", "gif", "svg", "webp"]:
        return "[Binary File - Use Raw Route]"

    try:
        with open(filepath, "r", encoding="utf-8") as file_obj:
            return file_obj.read().strip()
    except UnicodeDecodeError:
        return "[Binary or Unsupported Text Format]"


@lru_cache(maxsize=256)
def load_answer_files(subject_link, files):
    subject_dir = os.path.join(ANSWERS_DIR, subject_link)
    if not os.path.exists(subject_dir):
        return None, "Answer directory missing"

    contents = []
    for filename in files:
        path = os.path.join(subject_dir, filename)
        if not os.path.exists(path):
            return None, f"File missing: {filename}"
        contents.append((filename, _read_answer_file(path)))

    return contents, None


LANGUAGE_MAP = {
    "cpp": "language-cpp", "c": "language-c", "h": "language-c", "hpp": "language-cpp",
    "py": "language-python", "python": "language-python",
    "js": "language-javascript", "ts": "language-typescript",
    "java": "language-java", "cs": "language-csharp",
    "rb": "language-ruby", "go": "language-go", "rs": "language-rust",
    "sql": "language-sql", "sh": "language-bash", "bash": "language-bash",
    "html": "language-html", "css": "language-css", "xml": "language-xml",
    "json": "language-json", "yaml": "language-yaml", "yml": "language-yaml",
    "md": "language-markdown", "txt": "language-plaintext",
    "r": "language-r", "swift": "language-swift", "kt": "language-kotlin",
    "php": "language-php", "lua": "language-lua", "perl": "language-perl",
    "scala": "language-scala", "dart": "language-dart",
}


def get_ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def get_render_info(filename):
    ext = get_ext(filename)
    if ext in LANGUAGE_MAP:
        return {"type": "code", "language_class": LANGUAGE_MAP[ext]}
    if ext == "md":
        return {"type": "markdown", "language_class": "language-markdown"}
    if ext == "ipynb":
        return {"type": "notebook", "language_class": None}
    if ext in ("jpg", "jpeg", "png", "gif", "svg", "webp"):
        return {"type": "image", "language_class": None}
    if ext == "pdf":
        return {"type": "pdf", "language_class": None}
    return {"type": "code", "language_class": "language-plaintext"}


def render_markdown(content):
    try:
        import markdown as md
        return md.markdown(content, extensions=["fenced_code", "codehilite", "tables"])
    except Exception:
        return content


def highlight_code(source, language):
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        return escape(source)
    return highlight(source, lexer, HtmlFormatter(nowrap=True)).rstrip('\n')


def render_ipynb(content):
    try:
        import nbformat
        import json as _json
        notebook = _json.loads(content) if isinstance(content, str) else content
        nb = nbformat.reads(_json.dumps(notebook), as_version=4)
    except Exception:
        return None

    cells_html = []
    notebook_id = uuid4().hex
    code_cell_number = 0
    for cell in nb.cells:
        source = cell.source
        if isinstance(source, list):
            source = "".join(source)
        if cell.cell_type == "markdown":
            cells_html.append(
                '<div class="ipynb-markdown">'
                f'{render_markdown(source)}'
                '</div>'
            )
        elif cell.cell_type == "code":
            code_cell_number += 1
            cell_id = f'cell-{notebook_id}-{code_cell_number}'
            highlighted = highlight_code(source, 'python')
            outputs_html = []
            for output in cell.get('outputs', []):
                data = output.get('data', {})
                if data.get('image/png'):
                    image = data['image/png']
                    image = ''.join(image) if isinstance(image, list) else image
                    outputs_html.append(f'<img src="data:image/png;base64,{escape(image, quote=True)}" class="ipynb-output-image" alt="Cell {code_cell_number} output">')
                text = output.get('text', data.get('text/plain', ''))
                if output.get('output_type') == 'error':
                    text = '\n'.join(output.get('traceback', []))
                text = ''.join(text) if isinstance(text, list) else text
                if text:
                    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
                    outputs_html.append(f'<pre class="ipynb-output-text">{escape(text)}</pre>')
            output_html = '<div class="ipynb-outputs">' + ''.join(outputs_html) + '</div>' if outputs_html else ''
            cells_html.append(
                '<div class="ipynb-code-container">'
                f'<div class="ipynb-cell-header"><span>Code Cell {code_cell_number}</span>'
                f'<button type="button" class="cell-copy-btn" onclick="copyCell(\'{cell_id}\', this)">Copy</button></div>'
                f'<div class="ipynb-code"><pre id="{cell_id}"><code class="syntax-code language-python">{highlighted}</code></pre></div>'
                f'{output_html}'
                '</div>'
            )
        elif cell.cell_type == "raw":
            cells_html.append(
                f'<pre class="ipynb-raw">{escape(source)}</pre>'
            )

    return '<div class="ipynb-notebook">' + "\n".join(cells_html) + '</div>'


def load_answer_files_ssr(subject_link, files):
    subject_dir = os.path.join(ANSWERS_DIR, subject_link)
    if not os.path.exists(subject_dir):
        return None

    results = []
    for filename in files:
        path = os.path.join(subject_dir, filename)
        if not os.path.exists(path):
            continue

        info = get_render_info(filename)
        raw_url = f"/raw-answers/{subject_link}/{filename}"
        info["filename"] = filename
        info["raw_url"] = raw_url

        if info["type"] == "image":
            info["content"] = raw_url
        elif info["type"] == "pdf":
            info["content"] = None
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
            except (UnicodeDecodeError, IOError):
                if info["type"] == "code":
                    info["type"] = "code"
                    info["content"] = "[Binary or unsupported text format]"
                else:
                    info["content"] = None
                results.append(info)
                continue

            if info["type"] == "markdown":
                info["content"] = render_markdown(content)
            elif info["type"] == "notebook":
                rendered = render_ipynb(content)
                info["content"] = rendered if rendered else content
            else:
                info["content"] = content
                info["highlighted_content"] = highlight_code(
                    content, info["language_class"].removeprefix('language-')
                )

        results.append(info)

    return results


def preload_subject_cache():
    if not os.path.exists(QUESTIONS_DIR):
        return

    for filename in os.listdir(QUESTIONS_DIR):
        if filename.endswith(".json"):
            load_subject_data(filename[:-5])
