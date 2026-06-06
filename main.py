"""Interactive terminal console for the SPPU PYQ sync toolkit."""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

try:
    import questionary
    from questionary import Choice, Separator, Style
except ImportError:
    @dataclass(frozen=True)
    class Choice:  # type: ignore[no-redef]
        name: str
        value: str | None = None

        def __post_init__(self) -> None:
            if self.value is None:
                object.__setattr__(self, "value", self.name)

    class Separator(str):  # type: ignore[no-redef]
        pass

    class Style(list):  # type: ignore[no-redef]
        pass

    class _Prompt:
        def __init__(self, message: str, choices: list[Any] | None = None, default: bool = True) -> None:
            self.message = message
            self.choices = choices or []
            self.default = default

        def ask(self) -> str | bool | None:
            if not self.choices:
                suffix = "Y/n" if self.default else "y/N"
                answer = input(f"{self.message} [{suffix}] ").strip().lower()
                if not answer:
                    return self.default
                return answer in {"y", "yes"}
            actionable = [choice for choice in self.choices if not isinstance(choice, Separator)]
            print(self.message)
            for index, choice in enumerate(actionable, start=1):
                label = choice.name if isinstance(choice, Choice) else str(choice)
                print(f"  {index}. {label}")
            answer = input("> ").strip()
            if not answer:
                return None
            try:
                selected = actionable[int(answer) - 1]
            except (ValueError, IndexError):
                return None
            return selected.value if isinstance(selected, Choice) else str(selected)

    class _QuestionaryFallback:
        @staticmethod
        def select(message: str, choices: list[Any], **_: Any) -> _Prompt:
            return _Prompt(message, choices)

        @staticmethod
        def confirm(message: str, **kwargs: Any) -> _Prompt:
            return _Prompt(message, default=bool(kwargs.get("default", True)))

    questionary = _QuestionaryFallback()  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
MAPPING_DIR = ROOT / "mapping"
CHANGELOG_DIR = ROOT / "changelog"
TRACKING_DB = ROOT / "tracking" / "manifest.db"
UPLOAD_DB = ROOT / "tracking" / "uploads.db"
FOLDER_NAMES = MAPPING_DIR / "folder_names.yml"
SYNC_MAPPING = MAPPING_DIR / "sync_mapping.json"
FY_MAPPING = MAPPING_DIR / "first_year_mapping.json"
MBA_MAPPING = MAPPING_DIR / "mba.json"
HONORS_MAPPING = MAPPING_DIR / "honors_course_mapping.json"

INCOMING = ROOT / "incoming"
NEEDS_REVIEW = ROOT / "needs_review"
PAPERS = ROOT / "papers"

BACK = "Back"
EXIT = "Exit"
ALL_SCOPE = "All mapped folders"


THEME = Style(
    [
        ("qmark", "fg:#7DD3FC bold"),
        ("question", "fg:#F8FAFC bold"),
        ("answer", "fg:#86EFAC bold"),
        ("pointer", "fg:#FDE68A bold"),
        ("highlighted", "fg:#FDE68A bold"),
        ("selected", "fg:#86EFAC"),
        ("separator", "fg:#64748B"),
        ("instruction", "fg:#94A3B8 italic"),
        ("text", "fg:#CBD5E1"),
    ]
)

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
BLUE = "\033[34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
GRAY = "\033[90m"
WHITE = "\033[37m"


@dataclass(frozen=True)
class OutputEvent:
    kind: str
    title: str
    rows: tuple[tuple[str, str], ...] = ()
    detail: str = ""
    raw: str = ""
    one_line: bool = False


def color(text: str, style: str) -> str:
    if os.environ.get("NO_COLOR"):
        return text
    return f"{style}{text}{RESET}"


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def terminal_width() -> int:
    if sys.stdout.isatty():
        width = shutil.get_terminal_size((100, 24)).columns
    else:
        width = 100
    return max(84, min(128, width))


def hr(char: str = "-") -> str:
    return char * (terminal_width() - 4)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def pdf_count(path: Path) -> int:
    return len(list(path.rglob("*.pdf"))) if path.exists() else 0


def pending_count(path: Path, key: str) -> int:
    payload_path = path
    if path.name == "rename.md" and path.with_suffix(".json").exists():
        payload_path = path.with_suffix(".json")
    if not payload_path.exists():
        return 0
    try:
        if payload_path.suffix == ".json":
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        else:
            text = payload_path.read_text(encoding="utf-8")
            match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
            payload = json.loads(match.group(1)) if match else {}
    except (OSError, json.JSONDecodeError):
        return 0
    items = payload.get(key) or []
    if key == "entries":
        return sum(1 for item in items if item.get("status") == "pending")
    return len(items)


def rename_review_counts() -> Counter[str]:
    counts: Counter[str] = Counter({"ready": 0, "needs_review": 0, "retry_later": 0, "total": 0})
    payload_path = CHANGELOG_DIR / "rename.json"
    if not payload_path.exists():
        return counts
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return counts
    for entry in payload.get("entries") or []:
        counts["total"] += 1
        if entry.get("status") == "retry_pending":
            counts["retry_later"] += 1
        elif entry.get("status") == "pending" and entry.get("action") == "rename":
            counts["ready"] += 1
        elif entry.get("status") == "pending":
            counts["needs_review"] += 1
    return counts


def db_stage_counts() -> Counter[str]:
    stages = Counter(
        {
            "DISCOVERED": 0,
            "DOWNLOADED": 0,
            "FOLDER_RENAMED": 0,
            "FILE_RENAMED": 0,
            "NEEDS_REVIEW": 0,
            "VERIFIED": 0,
            "MOVED": 0,
            "MISSING": 0,
        }
    )
    if not TRACKING_DB.exists():
        return stages
    try:
        with sqlite3.connect(TRACKING_DB) as connection:
            for stage, count in connection.execute("SELECT current_stage, COUNT(*) FROM files GROUP BY current_stage"):
                stages[str(stage)] = int(count)
    except sqlite3.Error:
        pass
    return stages


def upload_stage_counts() -> Counter[str]:
    stages = Counter(
        {
            "PENDING": 0,
            "UPLOADED": 0,
            "MODIFIED": 0,
            "RENAMED": 0,
            "REMOVED": 0,
            "FAILED": 0,
            "NEEDS_TRACKING_ID": 0,
        }
    )
    if not UPLOAD_DB.exists():
        return stages
    try:
        with sqlite3.connect(UPLOAD_DB) as connection:
            for stage, count in connection.execute("SELECT state, COUNT(*) FROM uploaded_pdfs GROUP BY state"):
                stages[str(stage)] = int(count)
    except sqlite3.Error:
        pass
    return stages


def dashboard_values() -> dict[str, Any]:
    stages = db_stage_counts()
    upload_stages = upload_stage_counts()
    papers_total = pdf_count(PAPERS)
    return {
        "incoming": pdf_count(INCOMING),
        "needs_review_files": pdf_count(NEEDS_REVIEW),
        "needs_review": stages["NEEDS_REVIEW"],
        "papers": papers_total,
        "db_total": sum(stages.values()),
        "db_exists": TRACKING_DB.exists(),
        "stages": stages,
        "upload_stages": upload_stages,
        "upload_remaining": max(papers_total - upload_stages["UPLOADED"], 0),
        "folder_pending": pending_count(CHANGELOG_DIR / "folder.md", "changes"),
        "file_pending": pending_count(CHANGELOG_DIR / "files.md", "changes"),
        "rename_pending": pending_count(CHANGELOG_DIR / "rename.md", "entries"),
    }


def metric(label: str, value: int, style: str) -> str:
    return f"{color(label, GRAY)} {color(str(value), BOLD + style)}"


def clipped(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def two_column(left: str, right: str, gap: int = 4) -> str:
    width = terminal_width() - 4
    left_width = max(34, width // 2 - gap)
    right_width = width - left_width - gap
    return f"  {clipped(left, left_width):<{left_width}}{' ' * gap}{clipped(right, right_width)}"


def banner() -> None:
    clear()
    values = dashboard_values()
    stages = values["stages"]
    upload_stages = values["upload_stages"]
    width = terminal_width() - 4
    print()
    print(color("  " + "SPPU PYQ Operator Console".ljust(width), BOLD + CYAN))
    print(color("  " + "Review first. Apply deliberately. Keep the archive traceable.".ljust(width), GRAY))
    print(color("  " + hr("="), BLUE))
    print()
    print(two_column(metric("incoming", values["incoming"], CYAN), metric("downloaded", stages["DOWNLOADED"], BLUE)))
    print(two_column(metric("needs review", values["needs_review"], YELLOW), metric("renamed", stages["FILE_RENAMED"], MAGENTA)))
    print(two_column(metric("papers", values["papers"], GREEN), metric("verified", stages["VERIFIED"], GREEN)))
    print(two_column(metric("upload remaining", values["upload_remaining"], YELLOW), metric("uploaded", upload_stages["UPLOADED"], GREEN)))
    print()


def section(title: str, subtitle: str | None = None) -> None:
    print()
    print(color(f"  {title}", BOLD + WHITE))
    if subtitle:
        print(color(f"  {subtitle}", GRAY))
    print(color("  " + hr(), GRAY))


def note(message: str, tone: str = "info") -> None:
    styles = {"info": CYAN, "ok": GREEN, "warn": YELLOW, "error": RED}
    labels = {"info": "INFO", "ok": "DONE", "warn": "WARN", "error": "FAIL"}
    style = styles.get(tone, CYAN)
    label = labels.get(tone, "INFO")
    print(f"  {color(label, BOLD + style)}  {message}")


def pause() -> None:
    print()
    input(color("  Press Enter to continue...", GRAY))


def select(message: str, choices: list[Any], show_back: bool = True) -> str | None:
    items = list(choices)
    if show_back:
        items.extend([Separator("-" * 44), Choice(BACK, value=BACK)])
    try:
        answer = questionary.select(
            message,
            choices=items,
            style=THEME,
            instruction="arrows to move, enter to choose",
            qmark=">",
        ).ask()
    except KeyboardInterrupt:
        return None
    if answer in {None, BACK}:
        return None
    return str(answer)


def confirm(message: str, default: bool = True) -> bool:
    try:
        return bool(questionary.confirm(message, style=THEME, qmark=">", default=default).ask())
    except KeyboardInterrupt:
        return False


def py(*args: str) -> list[str]:
    return [PYTHON, *args]


def upload_py(*args: str) -> list[str]:
    venv_python = ROOT / ".venv" / "bin" / "python"
    executable = str(venv_python) if venv_python.exists() else PYTHON
    return [executable, "tools/upload_pipeline.py", *args]


def semester_py(*args: str) -> list[str]:
    venv_python = ROOT / ".venv" / "bin" / "python"
    executable = str(venv_python) if venv_python.exists() else PYTHON
    return [executable, "tools/semester_mapping.py", *args]


def shell_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def wrap_text(text: str, indent: str = "       ", width: int | None = None) -> list[str]:
    width = width or terminal_width() - len(indent) - 4
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return [indent]
    return textwrap.wrap(text, width=max(32, width), initial_indent=indent, subsequent_indent=indent)


def print_event(event: OutputEvent) -> None:
    if event.kind == "skip":
        return
    styles = {
        "ok": GREEN,
        "work": CYAN,
        "warn": YELLOW,
        "error": RED,
        "stat": BLUE,
        "rename": MAGENTA,
        "plain": GRAY,
    }
    labels = {
        "ok": "DONE",
        "work": "WORK",
        "warn": "WARN",
        "error": "FAIL",
        "stat": "STAT",
        "rename": "NAME",
        "plain": "LOG ",
    }
    style = styles.get(event.kind, GRAY)
    label = labels.get(event.kind, "LOG ")
    if event.one_line:
        suffix = ""
        if event.rows:
            suffix = " " + " ".join(f"{color(key + '=', GRAY)}{value}" for key, value in event.rows)
        if event.detail:
            suffix = f"{suffix} {event.detail}".rstrip()
        print(f"  {color(label, BOLD + style)}  {event.title}{suffix}")
        return
    print(f"  {color(label, BOLD + style)}  {event.title}")
    for key, value in event.rows:
        key_text = color(f"{key:<10}", GRAY)
        lines = wrap_text(value, indent=f"       {key_text} ", width=terminal_width() - 22)
        for index, line in enumerate(lines):
            if index == 0:
                print(line)
            else:
                print("       " + " " * 11 + line.strip())
    if event.detail:
        for line in wrap_text(event.detail):
            print(line)


LOG_PREFIX_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}\s+)?\d{2}:\d{2}(?::\d{2})?\s+(?:INFO|WARNING|ERROR|DEBUG)\s+[^:]+:\s+")


def clean_log_line(line: str) -> str:
    line = re.sub(r"\x1b\[[0-9;]*m", "", line.rstrip())
    return LOG_PREFIX_RE.sub("", line).strip()


def parse_output_event(raw_line: str) -> OutputEvent:
    line = clean_log_line(raw_line)
    lower = line.lower()
    if not line:
        return OutputEvent("skip", "")

    if line in {"```", "```bash"} or line in {"Generated by `python tools/status.py`.", "Generated by `python3 tools/status.py`."}:
        return OutputEvent("skip", "", raw=line)

    if line.startswith("|"):
        return OutputEvent("skip", "", raw=line)

    match = re.match(r"^#\s+(.+)$", line)
    if match:
        return OutputEvent("stat", match.group(1), raw=line)

    match = re.match(r"^##\s+(.+)$", line)
    if match:
        heading = match.group(1).strip()
        if heading.endswith("By Folder"):
            return OutputEvent("skip", "", raw=line)
        return OutputEvent("stat", heading, raw=line)

    match = re.match(r"^-\s+(PENDING|MODIFIED|RENAMED|FAILED|NEEDS_TRACKING_ID):\s+(.+?)\s+r2=(.+?)\s+cloudinary=(.+)$", line)
    if match:
        state, file_path, r2_status, cloudinary_status = match.groups()
        kind = "warn" if state in {"FAILED", "NEEDS_TRACKING_ID"} else "work"
        return OutputEvent(
            kind,
            f"{state.lower()} upload candidate",
            rows=(("file", file_path), ("r2", r2_status), ("cloud", cloudinary_status)),
            raw=line,
            one_line=True,
        )

    match = re.match(r"^-\s+([^:]+):\s+`?([^`]+)`?$", line)
    if match:
        name, value = match.groups()
        return OutputEvent("stat", name.strip(), rows=(("value", value.strip()),), raw=line, one_line=True)

    if line.startswith(("python tools/", "python3 tools/")):
        return OutputEvent("work", "Next suggested command", rows=(("command", line),), raw=line)

    match = re.match(r"Downloading file (\d+)/(\d+) with ([^:]+): (.*?) -> (.+)$", line)
    if match:
        current, total, method, source, target = match.groups()
        return OutputEvent(
            "work",
            f"Downloading {current} of {total} with {method.strip()}",
            rows=(("file", Path(source).name), ("target", target)),
            raw=line,
        )

    match = re.match(r"Downloaded file (\d+)/(\d+); remaining (\d+)", line)
    if match:
        current, total, remaining = match.groups()
        return OutputEvent("ok", f"Downloaded {current} of {total}", rows=(("remaining", remaining),), raw=line)

    match = re.match(r"Downloaded (\d+) files; (\d+) pending remain", line)
    if match:
        downloaded, remaining = match.groups()
        return OutputEvent("ok", "Download batch finished", rows=(("downloaded", downloaded), ("pending", remaining)), raw=line)

    match = re.match(r"Upload batch: (\d+) PDF\(s\), workers=(\d+)$", line)
    if match:
        total, workers = match.groups()
        return OutputEvent("work", "Upload batch started", rows=(("files", total), ("workers", workers)), raw=line)

    match = re.match(r"Upload limit: (\d+) PDF\(s\)$", line)
    if match:
        return OutputEvent("stat", "Upload batch limit", rows=(("files", match.group(1)),), raw=line)

    match = re.match(r"\[(\d+)/(\d+)\]\s+([A-Z_]+)\s+remaining=(\d+)\s+file=(.+?)\s+r2=(.+?)\s+cloudinary=(.+)$", line)
    if match:
        current, total, state, remaining, file_path, r2_status, cloudinary_status = match.groups()
        kind = "ok" if state == "UPLOADED" else "warn" if state in {"FAILED", "REMOVED"} else "work"
        return OutputEvent(
            kind,
            f"Uploaded {current} of {total}" if state == "UPLOADED" else f"Upload {state.lower()} {current} of {total}",
            rows=(("remain", remaining), ("file", file_path), ("r2", r2_status), ("cloud", cloudinary_status)),
            raw=line,
            one_line=True,
        )

    if line == "Upload preflight OK":
        return OutputEvent("ok", "Upload preflight OK", raw=line)

    match = re.match(r"^(R2 bucket|R2 endpoint|Cloudinary cloud):\s+(.+)$", line)
    if match:
        key, value = match.groups()
        return OutputEvent("stat", key, rows=(("value", value),), raw=line)

    match = re.match(r"^R2 objects under '([^']+)':\s+(\d+)$", line)
    if match:
        prefix, count = match.groups()
        return OutputEvent("stat", "R2 delete scope", rows=(("prefix", prefix), ("objects", count)), raw=line)

    match = re.match(r"^Cloudinary (raw|image) assets under '([^']+)':\s+(\d+)$", line)
    if match:
        resource_type, prefix, count = match.groups()
        return OutputEvent(
            "stat",
            "Cloudinary delete scope",
            rows=(("type", resource_type), ("prefix", prefix), ("assets", count)),
            raw=line,
        )

    match = re.match(r"^Local PDF files under (.+?):\s+(\d+)$", line)
    if match:
        scope, count = match.groups()
        return OutputEvent("stat", "Local delete scope", rows=(("scope", scope), ("files", count)), raw=line)

    match = re.match(r"^Generated manifest files:\s+(\d+)$", line)
    if match:
        return OutputEvent("stat", "Generated manifest cleanup", rows=(("files", match.group(1)),), raw=line)

    match = re.match(r"^- r2://([^/]+)/(.+)$", line)
    if match:
        bucket, key = match.groups()
        return OutputEvent("plain", f"r2://{bucket}/{key}", raw=line)

    match = re.match(r"^- cloudinary://([^/]+)/upload/(.+)$", line)
    if match:
        resource_type, public_id = match.groups()
        return OutputEvent("plain", f"cloudinary://{resource_type}/upload/{public_id}", raw=line)

    match = re.match(r"^(Would delete|Deleting) upload DB:\s+(.+)$", line)
    if match:
        action, path = match.groups()
        return OutputEvent("warn" if action == "Deleting" else "stat", action, rows=(("path", path),), raw=line)

    match = re.match(r"^Upload DB already absent:\s+(.+)$", line)
    if match:
        return OutputEvent("stat", "Upload DB already absent", rows=(("path", match.group(1)),), raw=line)

    if line == "Next files":
        return OutputEvent("stat", "Next upload candidates", raw=line)

    match = re.match(r"(Would rename|Renamed): (.+?) -> (.+)$", line)
    if match:
        action, source, target = match.groups()
        return OutputEvent("rename", action, rows=(("from", source), ("to", target)), raw=line)

    match = re.match(r"(Would rename|Renamed) (\d+) folders\.", line)
    if match:
        action, count = match.groups()
        return OutputEvent("ok", f"{action} {count} folders", raw=line)

    match = re.match(r"Reviewed PDF (\d+)/(\d+): (.+)$", line)
    if match:
        current, total, path = match.groups()
        return OutputEvent("work", f"Reviewed PDF {current} of {total}", rows=(("file", path),), raw=line)

    match = re.match(r"\s*(TEXT|PADDLEOCR|GROQ|SKIP|RETRY|REVIEW)\s+([^|]+)\|\s+(.+)$", line)
    if match:
        source, status, rest = match.groups()
        pieces = [piece.strip() for piece in rest.split("|")]
        rows: list[tuple[str, str]] = [("source", source), ("status", status.strip())]
        if pieces:
            if " -> " in pieces[0]:
                left, right = pieces[0].split(" -> ", 1)
                rows.extend([("from", left), ("to", right)])
            else:
                rows.append(("file", pieces[0]))
        for piece in pieces[1:]:
            if "=" in piece:
                key, value = piece.split("=", 1)
                rows.append((key.strip()[:10], value.strip()))
            elif piece:
                rows.append(("detail", piece))
        kind = "rename" if source in {"TEXT", "PADDLEOCR", "GROQ"} else "warn"
        return OutputEvent(kind, "Rename review result", rows=tuple(rows), raw=line)

    match = re.match(r"Scanning folder:\s+(.+?)(?:\s+\([A-Za-z0-9_-]+\))?$", line)
    if match:
        return OutputEvent("work", "Scanning Drive folder", rows=(("scope", match.group(1)),), raw=line)

    match = re.match(r"Found (\d+) child folders in (.+)$", line)
    if match:
        count, folder = match.groups()
        return OutputEvent("stat", "Drive folder scan", rows=(("folders", count), ("scope", folder)), raw=line)

    match = re.match(r"(Wrote|Updated) (.+?)(?: with (\d+) names)?\.?$", line)
    if match:
        action, path, count = match.groups()
        rows = [("path", path)]
        if count:
            rows.append(("names", count))
        return OutputEvent("ok", action, rows=tuple(rows), raw=line)

    match = re.match(r"(Would move|Moved) (\d+) verified file\(s\); (\d+) need review; (\d+) missing; (\d+) skipped\.", line)
    if match:
        action, moved, reviewed, missing, skipped = match.groups()
        return OutputEvent(
            "ok" if action == "Moved" else "stat",
            action,
            rows=(("moved", moved), ("review", reviewed), ("missing", missing), ("skipped", skipped)),
            raw=line,
        )

    if "error" in lower or "traceback" in lower or "failed" in lower:
        return OutputEvent("error", "Command reported a problem", detail=line, raw=line)
    if "rate limit" in lower or "anti-automation" in lower or "429" in lower:
        return OutputEvent("warn", "Provider limit detected", detail=line, raw=line)
    if "warning" in lower or "needs review" in lower or "missing" in lower:
        return OutputEvent("warn", "Attention needed", detail=line, raw=line)
    if any(word in lower for word in ("applied", "discarded", "generated", "promoted", "verified")):
        return OutputEvent("stat", line, raw=line)
    return OutputEvent("plain", line, raw=line)


def run_cmd(command: list[str], label: str, *, allow_failure: bool = False) -> int:
    section(label, shell_command(command))
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("FORCE_COLOR", "1")
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output_queue: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        assert proc.stdout is not None
        for output_line in proc.stdout:
            output_queue.put(output_line)
        output_queue.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    started = time.monotonic()
    last_activity = started
    stream_done = False
    last_plain = ""
    repeated_plain = 0

    while not stream_done or proc.poll() is None:
        try:
            raw = output_queue.get(timeout=1)
        except queue.Empty:
            now = time.monotonic()
            if now - last_activity > 10:
                note(f"Still running after {int(now - started)} seconds.", "info")
                last_activity = now
            continue
        if raw is None:
            stream_done = True
            continue
        event = parse_output_event(raw)
        if event.kind == "plain" and event.title == last_plain:
            repeated_plain += 1
            if repeated_plain > 2:
                continue
        else:
            last_plain = event.title if event.kind == "plain" else ""
            repeated_plain = 0
        print_event(event)
        last_activity = time.monotonic()

    proc.wait()
    thread.join(timeout=1)
    print(color("  " + hr(), GRAY))
    if proc.returncode == 0:
        note("Step completed.", "ok")
    else:
        tone = "warn" if allow_failure else "error"
        note(f"Step exited with code {proc.returncode}.", tone)
    return int(proc.returncode or 0)


def run_sequence(steps: Iterable[tuple[list[str], str]], *, stop_on_failure: bool = True) -> int:
    for command, label in steps:
        code = run_cmd(command, label, allow_failure=not stop_on_failure)
        if code != 0 and stop_on_failure:
            note("Stopped here so the current review state remains inspectable.", "warn")
            return code
    return 0


def scope_args(scope: str | None) -> list[str]:
    return [scope] if scope else []


def load_standard_branches() -> dict[str, Any]:
    return read_json(SYNC_MAPPING).get("branches", {})


def load_first_year() -> dict[str, Any]:
    return read_json(FY_MAPPING).get("patterns", {})


def load_mba() -> dict[str, Any]:
    return read_json(MBA_MAPPING).get("semesters", {})


def load_honors() -> dict[str, Any]:
    data = read_json(HONORS_MAPPING)
    if data.get("years"):
        return data["years"]
    years: dict[str, Any] = {}
    for folder_path in (data.get("folders") or {}):
        parts = [part for part in folder_path.split("/") if part]
        if len(parts) >= 2:
            years.setdefault(parts[1], {"subjects": {}})
    return years


def choose_scope() -> str | None:
    standard = load_standard_branches()
    first_year = load_first_year()
    mba = load_mba()
    honors = load_honors()
    choices: list[Any] = [Choice(ALL_SCOPE, value="")]
    if standard:
        choices.append(Separator("Standard branches"))
        choices.extend(Choice(name, value=name) for name in sorted(standard))
    special: list[Choice] = []
    if first_year:
        special.append(Choice("First Year", value="First Year"))
    if mba:
        special.append(Choice("M.B.A", value="M.B.A"))
    if honors:
        special.append(Choice("Honors Course", value="Honors Course"))
    if special:
        choices.append(Separator("Special families"))
        choices.extend(special)
    branch = select("  Scope", choices)
    if branch is None:
        return None
    if branch == "":
        return ""
    if branch == "First Year":
        return choose_first_year_scope(first_year)
    if branch == "M.B.A":
        return choose_mba_scope(mba)
    if branch == "Honors Course":
        return choose_honors_scope(honors)
    return choose_standard_scope(branch, standard.get(branch, {}))


def choose_standard_scope(branch: str, data: dict[str, Any]) -> str | None:
    years = data.get("years") or {}
    if not years:
        return branch
    year = select(f"  {branch} / year", [Choice("All years", value=""), *[Choice(name, value=name) for name in sorted(years)]])
    if year is None:
        return None
    if not year:
        return branch
    patterns = (years.get(year) or {}).get("patterns") or {}
    if not patterns:
        return f"{branch}/{year}"
    pattern = select(f"  {branch}/{year} / pattern", [Choice("All patterns", value=""), *[Choice(name, value=name) for name in sorted(patterns)]])
    if pattern is None:
        return None
    return f"{branch}/{year}" if not pattern else f"{branch}/{year}/{pattern}"


def choose_first_year_scope(data: dict[str, Any]) -> str | None:
    if not data:
        return "First Year"
    pattern = select("  First Year / pattern", [Choice("All patterns", value=""), *[Choice(name, value=name) for name in sorted(data)]])
    if pattern is None:
        return None
    return "First Year" if not pattern else f"First Year/{pattern}"


def choose_mba_scope(data: dict[str, Any]) -> str | None:
    if not data:
        return "M.B.A"
    semester = select("  M.B.A / semester", [Choice("All semesters", value=""), *[Choice(name, value=name) for name in sorted(data)]])
    if semester is None:
        return None
    if not semester:
        return "M.B.A"
    patterns = (data.get(semester) or {}).get("patterns") or {}
    if not patterns:
        return f"M.B.A/{semester}"
    pattern = select(f"  M.B.A/{semester} / pattern", [Choice("All patterns", value=""), *[Choice(name, value=name) for name in sorted(patterns)]])
    if pattern is None:
        return None
    return f"M.B.A/{semester}" if not pattern else f"M.B.A/{semester}/{pattern}"


def choose_honors_scope(data: dict[str, Any]) -> str | None:
    if not data:
        return "Honors Course"
    year = select("  Honors Course / year", [Choice("All years", value=""), *[Choice(name, value=name) for name in sorted(data)]])
    if year is None:
        return None
    return "Honors Course" if not year else f"Honors Course/{year}"


def scope_to_incoming(scope: str) -> str:
    if not scope:
        return "incoming"
    registry = read_yaml(FOLDER_NAMES).get("name_registry") or {}
    parts: list[str] = []
    for index, part in enumerate(scope.split("/")):
        entry = registry.get(part)
        if isinstance(entry, dict) and entry.get("normalized"):
            parts.append(str(entry["normalized"]))
            continue
        separator = "-" if index == 0 else "_"
        cleaned = part.strip().replace("&", " and ")
        cleaned = "".join(char if char.isalnum() else " " for char in cleaned)
        parts.append(separator.join(token.lower() for token in cleaned.split()))
    return "incoming/" + "/".join(parts)


def scope_to_existing_incoming_root(scope: str) -> str:
    if not scope:
        return "incoming"
    branch_scope = scope.split("/")[0]
    normalized = scope_to_incoming(branch_scope)
    original = f"incoming/{branch_scope}"
    if (ROOT / normalized).exists():
        return normalized
    if (ROOT / original).exists():
        return original
    return normalized


def choose_download_command(simple: bool = True) -> list[str] | None:
    method = select(
        "  Download method",
        [
            Choice("rclone bulk copyurl (Recommended)", value="rclone"),
            Choice("Google Drive API", value="drive"),
            Choice("gdown with curl fallback", value="gdown"),
        ],
    )
    if method is None:
        return None
    commands = {
        "drive": py("tools/sync.py", "--files", "--apply", "--workers", "3"),
        "gdown": py("tools/sync.py", "--files", "--apply", "--gdown", "--workers", "3", "--download-delay", "3"),
        "rclone": py("tools/sync.py", "--files", "--apply", "--rclone", "--workers", "8"),
    }
    return commands[method]


def start_review_workflow() -> None:
    banner()
    section("Start Review", "Choose the Drive scope, then build folder/file review changelogs.")
    scope = choose_scope()
    if scope is None:
        return
    scan_workers = select("  Scan speed", [Choice("Balanced, 4 workers", value="4"), Choice("Careful, 1 worker", value="1")])
    if scan_workers is None:
        return
    code = run_sequence(
        [
            (py("tools/sync.py", "--folders", *scope_args(scope)), "Review Drive folders"),
            (py("tools/sync.py", "--files", *scope_args(scope), "--workers", scan_workers), "Review Drive PDFs"),
            (py("tools/status.py", "--print"), "Refresh status"),
        ],
        stop_on_failure=True,
    )
    if code != 0:
        pause()
        return
    pending = pending_count(CHANGELOG_DIR / "files.md", "changes")
    note(f"Pending downloads: {pending}", "info")
    if pending <= 0:
        note("No reviewed PDFs are waiting to download.", "ok")
        pause()
    elif confirm("  Download reviewed PDFs now?", default=True):
        download_and_prepare(scope)
    else:
        pause()


def download_and_prepare(scope: str = "") -> None:
    pending = pending_count(CHANGELOG_DIR / "files.md", "changes")
    if pending <= 0:
        note("No reviewed PDFs are waiting to download.", "ok")
        pause()
        return
    command = choose_download_command(simple=True)
    if command is None:
        return
    code = run_cmd(command, "Download reviewed PDFs", allow_failure=True)
    if code != 0:
        action = select(
            "  Download did not finish cleanly",
            [Choice("Stop here", value="stop"), Choice("Continue with downloaded files", value="continue")],
            show_back=False,
        )
        if action != "continue":
            pause()
            return
    incoming_scope = scope_to_incoming(scope)
    raw_incoming_scope = scope_to_existing_incoming_root(scope)
    run_sequence(
        [
            (py("tools/rename_folders.py", "--create"), "Update folder name registry"),
            (py("tools/rename_folders.py", "--path", raw_incoming_scope), f"Normalize folders under {raw_incoming_scope}"),
        ]
    )
    if confirm("  Review PDF filenames now?", default=True):
        run_cmd(py("tools/rename_files.py", "--path", incoming_scope, "--ocr-workers", "1"), f"Review PDF names under {incoming_scope}")
    pause()


def continue_workflow() -> None:
    banner()
    section("Continue Work", "Pick the next phase only. Advanced tools are in the toolbox.")
    values = dashboard_values()
    choices = [
        Choice(f"Download reviewed PDFs ({values['file_pending']} pending)", value="download"),
        Choice("Normalize incoming folders", value="normalize"),
        Choice("Review PDF filenames", value="rename_review"),
        Choice(f"Apply reviewed PDF names ({values['rename_pending']} pending)", value="rename_apply"),
        Choice("Verify and move to papers", value="verify_move"),
    ]
    action = select("  Next phase", choices)
    if action is None:
        return
    scope = ""
    if action in {"normalize", "rename_review", "rename_apply", "verify_move"}:
        chosen = choose_scope()
        if chosen is None:
            return
        scope = chosen
    incoming_scope = scope_to_incoming(scope)
    raw_incoming_scope = scope_to_existing_incoming_root(scope)
    if action == "download":
        download_and_prepare("")
    elif action == "normalize":
        run_sequence(
            [
                (py("tools/rename_folders.py", "--create"), "Update folder name registry"),
                (py("tools/rename_folders.py", "--path", raw_incoming_scope, "--dry-run"), f"Preview folder normalization under {raw_incoming_scope}"),
            ]
        )
        if confirm("  Apply these folder renames?", default=True):
            run_cmd(py("tools/rename_folders.py", "--path", raw_incoming_scope), f"Normalize folders under {raw_incoming_scope}")
        pause()
    elif action == "rename_review":
        run_cmd(py("tools/rename_files.py", "--path", incoming_scope, "--ocr-workers", "1"), f"Review PDF names under {incoming_scope}")
        pause()
    elif action == "rename_apply":
        run_cmd(py("tools/rename_files.py", "--apply", "--path", incoming_scope), f"Apply PDF names under {incoming_scope}")
        pause()
    elif action == "verify_move":
        run_sequence(
            [
                (py("tools/verify.py"), "Verify renamed files"),
                (py("tools/move.py", "--path", incoming_scope), "Move VERIFIED files"),
                (py("tools/status.py", "--print"), "Refresh status"),
            ]
        )
        pause()


def folder_mapping_workflow() -> None:
    banner()
    section("Folder Mapping", "Review and apply Drive folder mapping changes.")
    scope = choose_scope()
    if scope is None:
        return
    run_cmd(py("tools/sync.py", "--folders", *scope_args(scope)), "Review Drive folders")
    pending = pending_count(CHANGELOG_DIR / "folder.md", "changes")
    note(f"Pending folder changes: {pending}", "info")
    if pending:
        action = select(
            "  Folder changes",
            [
                Choice("Apply reviewed changes", value="apply"),
                Choice("Discard pending changes", value="discard"),
                Choice("Leave for manual review", value="leave"),
            ],
            show_back=False,
        )
        if action == "apply":
            run_sequence(
                [
                    (py("tools/sync.py", "--folders", "--apply"), "Apply folder mapping changes"),
                    (py("tools/rename_folders.py", "--create"), "Refresh folder name registry"),
                ]
            )
        elif action == "discard":
            run_cmd(py("tools/sync.py", "--folders", "--discard"), "Discard folder changes")
    pause()


def status_workflow() -> None:
    banner()
    section("Status", "Generate docs/status.md and print the current tracking report.")
    run_cmd(py("tools/status.py", "--print"), "Refresh status")
    pause()


def is_semester_review_folder(path: Path) -> bool:
    try:
        parts = path.resolve().relative_to(PAPERS.resolve()).parts
    except ValueError:
        return False
    if len(parts) == 2 and parts[0] == "first-year":
        return True
    if len(parts) == 3 and parts[0] not in {"first-year", "m-b-a", "honors-course"}:
        return True
    return False


def semester_review_folders(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    folders: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if path.is_dir() and is_semester_review_folder(path):
            folders.append(path)
    if is_semester_review_folder(root):
        folders.insert(0, root)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in folders:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def choose_semester_review_paths() -> list[str] | None:
    current = PAPERS
    while True:
        reviewable_here = is_semester_review_folder(current)
        reviewable = semester_review_folders(current)
        choices: list[Any] = []
        if reviewable_here:
            rel = current.relative_to(ROOT).as_posix()
            choices.append(Choice(f"Review this folder: {rel}", value=f"__this__:{rel}"))
        if len(reviewable) > 1 or (reviewable and not reviewable_here):
            rel = current.relative_to(ROOT).as_posix()
            choices.append(Choice(f"Review all pattern folders under {rel} ({len(reviewable)})", value="__all__"))
        if not reviewable_here:
            child_dirs = [child for child in sorted(current.iterdir(), key=lambda item: item.name.lower()) if child.is_dir()]
            for child in child_dirs:
                count = len(semester_review_folders(child))
                if count:
                    choices.append(Choice(f"{child.name} ({count})", value=child.as_posix()))
        if not choices:
            note("No standard or First Year pattern folders found here.", "warn")
            return None
        action = select(f"  Browse {current.relative_to(ROOT).as_posix()}", choices)
        if action is None:
            return None
        if action.startswith("__this__:"):
            return [action.split(":", 1)[1]]
        if action == "__all__":
            return [path.relative_to(ROOT).as_posix() for path in reviewable]
        current = Path(action)


def semester_mapping_workflow() -> None:
    banner()
    section("Semester Mapping", "Prepare review drafts, apply approved mappings, and update generated manifests.")
    action = select(
        "  Semester mapping action",
        [
            Choice("Prepare unresolved review draft", value="review"),
            Choice("Preview AI-agent context", value="preview"),
            Choice("Apply reviewed mappings", value="apply"),
            Choice("Discard pending review", value="discard"),
            Choice("Fix already-generated manifests", value="fix"),
            Choice("Preview manifest fix", value="fix_dry"),
        ],
    )
    if action is None:
        return
    if action == "review":
        paths = choose_semester_review_paths()
        if not paths:
            return
        run_cmd(semester_py("review", *paths), "Prepare semester review draft", allow_failure=True)
    elif action == "preview":
        paths = choose_semester_review_paths()
        if not paths:
            return
        run_cmd(semester_py("preview", *paths), "Preview semester mapping context", allow_failure=True)
    elif action == "apply":
        run_cmd(semester_py("apply"), "Apply reviewed semester mapping", allow_failure=True)
    elif action == "discard":
        if confirm("  Clear changelog/semester.md pending review?", default=False):
            run_cmd(semester_py("discard"), "Discard semester review", allow_failure=True)
    elif action == "fix":
        run_cmd(semester_py("fix-manifest"), "Fix generated manifests", allow_failure=True)
    elif action == "fix_dry":
        run_cmd(semester_py("fix-manifest", "--dry-run"), "Preview generated manifest fix", allow_failure=True)
    pause()


def publishing_workflow() -> None:
    banner()
    section("Publish Papers", "Upload publishing reads only from papers/. It does not scan incoming/.")
    run_cmd(upload_py("summary", "--sample", "5"), "Current publishing status")
    action = select(
        "  Publishing action",
        [
            Choice("Preflight credentials", value="preflight"),
            Choice("Scan papers and refresh DB", value="scan"),
            Choice("Upload small test batch", value="test"),
            Choice("Resume upload remaining", value="sync"),
            Choice("Retry failed uploads", value="retry"),
            Choice("Generate frontend JSON with semester mapping", value="manifest"),
            Choice("Scan, upload, and generate JSON with semester mapping", value="all"),
            Choice("Bulk delete uploaded/local papers", value="bulk_delete"),
        ],
    )
    if action is None:
        return
    if action == "preflight":
        run_cmd(upload_py("preflight"), "Check R2 and Cloudinary credentials", allow_failure=True)
    elif action == "scan":
        run_sequence(
            [
                (upload_py("scan"), "Scan papers/ and update upload DB"),
                (upload_py("summary", "--sample", "8"), "Publishing summary"),
            ]
        )
    elif action in {"test", "sync", "retry", "all"}:
        workers = choose_upload_workers()
        if workers is None:
            return
        limit = "10" if action == "test" else choose_upload_limit()
        if limit is None:
            return
        command_action = "sync" if action in {"test", "sync", "retry"} else "all"
        command = upload_py(command_action, "--workers", workers)
        if limit != "0":
            command.extend(["--limit", limit])
        if action == "retry":
            command.extend(["--state", "FAILED"])
            note("Failed uploads are retried automatically; already uploaded providers are skipped.", "info")
        if action in {"sync", "all"} and not confirm("  Start uploading PDFs to R2 and Cloudinary?", default=False):
            pause()
            return
        run_sequence(
            [
                (upload_py("preflight"), "Check upload credentials"),
                (command, "Upload papers" if command_action == "sync" else "Scan, upload, and generate JSON"),
                (upload_py("summary", "--sample", "8"), "Publishing summary"),
            ],
            stop_on_failure=False,
        )
    elif action == "manifest":
        run_sequence(
            [
                (upload_py("manifest"), "Generate frontend JSON with semester mapping"),
                (upload_py("summary", "--sample", "5"), "Publishing summary"),
            ]
        )
    elif action == "bulk_delete":
        bulk_delete_workflow()
    pause()


def simple_scan_drive_workflow() -> None:
    banner()
    section("Scan Drive", "Choose what to scan from Google Drive.")
    action = select(
        "  Scan Drive",
        [
            Choice("Scan files", value="files"),
            Choice("Scan folders", value="folders"),
        ],
    )
    if action is None:
        return
    if action == "files":
        simple_scan_files_workflow()
    elif action == "folders":
        simple_scan_folders_workflow()


def simple_scan_files_workflow() -> None:
    section("Scan Files", "Review Drive PDFs, download approved files, then continue into renaming.")
    scope = choose_scope()
    if scope is None:
        return
    run_cmd(py("tools/sync.py", "--files", *scope_args(scope), "--workers", "4"), "Scan Drive files")
    pending = pending_count(CHANGELOG_DIR / "files.md", "changes")
    note(f"Reviewed files waiting to download: {pending}", "info")
    if pending and confirm("  Download reviewed files now?", default=True):
        command = choose_download_command(simple=True)
        if command:
            run_cmd(command, "Download reviewed PDFs", allow_failure=True)
    next_action = select(
        "  Next step",
        [
            Choice("Rename folders and files", value="rename"),
            Choice("Stop here", value="stop"),
        ],
        show_back=False,
    )
    if next_action == "rename":
        simple_rename_folders()
        simple_rename_files()
        post_rename_actions()
    pause()


def simple_scan_folders_workflow() -> None:
    section("Scan Folders", "Review Drive folder mapping, then refresh local folder names.")
    scope = choose_scope()
    if scope is None:
        return
    run_cmd(py("tools/sync.py", "--folders", *scope_args(scope)), "Scan Drive folders")
    pending = pending_count(CHANGELOG_DIR / "folder.md", "changes")
    note(f"Folder mapping changes waiting: {pending}", "info")
    if pending and confirm("  Apply mapped folder changes?", default=True):
        run_sequence(
            [
                (py("tools/sync.py", "--folders", "--apply"), "Apply folder mapping changes"),
                (py("tools/rename_folders.py", "--create"), "Refresh folder name registry"),
            ]
        )
    if confirm("  Rename local incoming folders now?", default=True):
        simple_rename_folders()
    pause()


def simple_rename_workflow() -> None:
    banner()
    section("Rename Files / Folders", "Skip Drive scanning and work directly on local incoming files.")
    action = select(
        "  Rename",
        [
            Choice("Folders", value="folders"),
            Choice("Files", value="files"),
        ],
    )
    if action is None:
        return
    if action == "folders":
        simple_rename_folders()
    elif action == "files":
        simple_rename_files()
        post_rename_actions()
    pause()


def simple_rename_folders() -> None:
    run_sequence(
        [
            (py("tools/rename_folders.py", "--create"), "Refresh folder name registry"),
            (py("tools/rename_folders.py", "--path", "incoming", "--dry-run"), "Preview incoming folder renames"),
        ]
    )
    if confirm("  Apply folder renames?", default=True):
        run_cmd(py("tools/rename_folders.py", "--path", "incoming"), "Rename incoming folders")


def simple_rename_files() -> None:
    run_cmd(py("tools/rename_files.py", "--path", "incoming", "--ocr-workers", "1"), "Review and plan PDF filename changes")
    counts = rename_review_counts()
    note(
        f"Rename review: {counts['ready']} ready; {counts['needs_review']} need review; {counts['retry_later']} retry later.",
        "info",
    )


def post_rename_actions() -> None:
    while True:
        counts = rename_review_counts()
        choices: list[Any] = []
        if counts["needs_review"] > 0:
            choices.append(Choice(f"Try Groq on needs-review files ({counts['needs_review']})", value="groq"))
        if counts["ready"] > 0 or counts["needs_review"] > 0 or counts["retry_later"] > 0:
            choices.append(Choice(f"Apply rename changes ({counts['ready']} ready, {counts['needs_review']} review)", value="apply"))
            choices.append(Choice("Discard review and restore needs_review", value="rollback"))
        choices.extend(
            [
                Choice("Verify only", value="verify"),
                Choice("Verify and move", value="verify_move"),
                Choice("Stop here", value="stop"),
            ]
        )
        action = select("  Rename next step", choices, show_back=False)
        if action in {None, "stop"}:
            return
        if action == "groq":
            run_cmd(py("tools/rename_files.py", "--retry-needs-review", "--path", "incoming", "--ocr-workers", "1"), "Try Groq on needs-review files", allow_failure=True)
        elif action == "apply":
            run_cmd(py("tools/rename_files.py", "--apply", "--path", "incoming"), "Apply rename changes")
        elif action == "rollback":
            if confirm("  Delete rename review and restore NEEDS_REVIEW rows/files to incoming?", default=True):
                run_cmd(py("tools/rename_files.py", "--rollback-needs-review", "--path", "incoming"), "Restore stale rename review")
        elif action == "verify":
            run_cmd(py("tools/verify.py"), "Verify files")
        elif action == "verify_move":
            run_sequence([(py("tools/verify.py"), "Verify files"), (py("tools/move.py"), "Move verified files")])
            return


def simple_verify_move_workflow() -> None:
    banner()
    section("Verify / Move", "Validate renamed files and optionally move VERIFIED files into papers/.")
    action = select(
        "  Verify / Move",
        [
            Choice("Verify", value="verify"),
            Choice("Verify and move", value="verify_move"),
            Choice("Exit", value="exit"),
        ],
        show_back=False,
    )
    if action in {None, "exit"}:
        return
    if action == "verify":
        run_cmd(py("tools/verify.py"), "Verify files")
    elif action == "verify_move":
        run_sequence([(py("tools/verify.py"), "Verify files"), (py("tools/move.py"), "Move verified files")])
    pause()


def simple_upload_workflow() -> None:
    banner()
    section("Upload Files", "Publish reads only from papers/. It does not scan incoming/.")
    action = select(
        "  Upload",
        [
            Choice("Scan, upload, and generate JSON with semester mapping", value="all"),
            Choice("Check current progress", value="summary"),
            Choice("Upload papers", value="upload"),
            Choice("Generate JSON with semester mapping", value="manifest"),
            Choice("Bulk delete uploaded/local papers", value="bulk_delete"),
        ],
    )
    if action is None:
        return
    if action == "summary":
        run_cmd(upload_py("summary", "--sample", "8"), "Current upload progress")
    elif action == "manifest":
        run_cmd(upload_py("manifest"), "Generate frontend JSON with semester mapping")
    elif action in {"upload", "all"}:
        run_cmd(upload_py("summary", "--sample", "5"), "Current upload progress")
        if not confirm("  Continue upload? Already uploaded PDFs will be skipped.", default=True):
            pause()
            return
        command = upload_py("all" if action == "all" else "sync", "--workers", "4")
        run_sequence(
            [
                (command, "Upload papers" if action == "upload" else "Scan, upload, and generate JSON with semester mapping"),
                (upload_py("summary", "--sample", "8"), "Upload progress after run"),
            ],
            stop_on_failure=False,
        )
    elif action == "bulk_delete":
        bulk_delete_workflow()
    pause()


def choose_bulk_delete_target() -> str | None:
    return select(
        "  Bulk delete target",
        [
            Choice("Delete from cloud only", value="cloud"),
            Choice("Delete local papers/ files only", value="local"),
            Choice("Delete both cloud and local papers/ files", value="both"),
        ],
    )


def bulk_delete_workflow() -> None:
    target = choose_bulk_delete_target()
    if target is None:
        return
    note("Dry run first: this previews the exact papers/ scope without deleting.", "info")
    preview_code = run_cmd(upload_py("bulk-delete", "--target", target, "--dry-run"), "Preview bulk delete", allow_failure=True)
    if preview_code != 0:
        note("Preview failed, so no delete command was run.", "warn")
        return
    if not confirm("  Run the actual bulk delete now? This cannot be undone.", default=False):
        return
    run_cmd(upload_py("bulk-delete", "--target", target, "--yes"), "Run bulk delete", allow_failure=True)


def choose_upload_workers() -> str | None:
    return select(
        "  Upload speed",
        [
            Choice("Balanced, 4 workers", value="4"),
            Choice("Careful, 1 worker", value="1"),
            Choice("Fast, 8 workers", value="8"),
        ],
    )


def choose_upload_limit() -> str | None:
    return select(
        "  Batch size",
        [
            Choice("All remaining", value="0"),
            Choice("50 PDFs", value="50"),
            Choice("100 PDFs", value="100"),
            Choice("250 PDFs", value="250"),
        ],
    )


def toolbox_workflow() -> None:
    banner()
    section("Toolbox", "Less common commands, kept away from the main path.")
    action = select(
        "  Tool",
        [
            Choice("Download pending with advanced methods", value="downloads"),
            Choice("Rename changelog: apply, retry, or discard", value="rename"),
            Choice("Verify / move dry runs", value="verify"),
            Choice("SQLite tracking maintenance", value="tracking"),
            Choice("Run tools/pipeline.py", value="pipeline"),
        ],
    )
    if action is None:
        return
    if action == "downloads":
        command = choose_download_command(simple=False)
        if command:
            run_cmd(command, "Apply pending downloads", allow_failure=True)
        pause()
    elif action == "rename":
        rename_toolbox()
    elif action == "verify":
        verify_toolbox()
    elif action == "tracking":
        tracking_toolbox()
    elif action == "pipeline":
        pipeline_toolbox()


def rename_toolbox() -> None:
    action = select(
        "  Rename tool",
        [
            Choice("Review PDFs", value="review"),
            Choice("Apply rename changelog", value="apply"),
            Choice("Apply, verify, and move", value="apply_all"),
            Choice("Discard rename changelog", value="discard"),
        ],
    )
    if action is None:
        return
    if action == "discard":
        if confirm("  Delete changelog/rename.md and rename.json?", default=False):
            run_cmd(py("tools/rename_files.py", "--discard"), "Discard rename changelog")
        pause()
        return
    scope = choose_scope()
    if scope is None:
        return
    incoming_scope = scope_to_incoming(scope)
    if action == "review":
        run_cmd(py("tools/rename_files.py", "--path", incoming_scope, "--ocr-workers", "1"), f"Review PDF names under {incoming_scope}")
    elif action == "apply":
        run_cmd(py("tools/rename_files.py", "--apply", "--path", incoming_scope), f"Apply PDF names under {incoming_scope}")
    elif action == "apply_all":
        run_sequence(
            [
                (py("tools/rename_files.py", "--apply", "--path", incoming_scope), f"Apply PDF names under {incoming_scope}"),
                (py("tools/verify.py"), "Verify renamed files"),
                (py("tools/move.py", "--path", incoming_scope), "Move VERIFIED files"),
            ]
        )
    pause()


def verify_toolbox() -> None:
    action = select(
        "  Verify / move",
        [
            Choice("Verify only", value="verify"),
            Choice("Verify dry run", value="verify_dry"),
            Choice("Move VERIFIED files", value="move"),
            Choice("Move dry run", value="move_dry"),
            Choice("Verify then move", value="both"),
        ],
    )
    if action is None:
        return
    if action == "verify":
        run_cmd(py("tools/verify.py"), "Verify renamed files")
    elif action == "verify_dry":
        run_cmd(py("tools/verify.py", "--dry-run"), "Verify dry run")
    elif action == "move":
        run_cmd(py("tools/move.py"), "Move VERIFIED files")
    elif action == "move_dry":
        run_cmd(py("tools/move.py", "--dry-run"), "Move dry run")
    else:
        run_sequence([(py("tools/verify.py"), "Verify renamed files"), (py("tools/move.py"), "Move VERIFIED files")])
    pause()


def tracking_toolbox() -> None:
    action = select(
        "  Tracking",
        [
            Choice("Create / migrate manifest.db", value="migrate"),
            Choice("Show DB-first status", value="status"),
            Choice("Verify DB consistency dry run", value="dry"),
        ],
    )
    if action is None:
        return
    if action == "migrate":
        run_cmd(py("tools/migrate_tracking.py", "--print"), "Migrate tracking DB")
    elif action == "dry":
        run_cmd(py("tools/verify.py", "--dry-run"), "Verify DB consistency")
    else:
        run_cmd(py("tools/status.py", "--print"), "Show tracking status")
    pause()


def pipeline_toolbox() -> None:
    scope = choose_scope()
    if scope is None:
        return
    mode = select(
        "  Pipeline mode",
        [
            Choice("Review only", value="review"),
            Choice("Apply reviewed downloads and rename review", value="apply_reviewed"),
            Choice("Apply renames, verify, move", value="apply_renames"),
            Choice("Full run with apply", value="full"),
        ],
    )
    if mode is None:
        return
    args = ["--scope", scope] if scope else []
    dry_run = confirm("  Print the pipeline commands without running them?", default=False)
    dry_args = ["--dry-run"] if dry_run else []
    if mode == "review":
        run_cmd(py("tools/pipeline.py", "--review", *args, *dry_args), "Pipeline review")
    elif mode == "apply_reviewed":
        run_cmd(py("tools/pipeline.py", "--apply-reviewed", *args, "--workers", "3", *dry_args), "Pipeline apply reviewed")
    elif mode == "apply_renames":
        run_cmd(py("tools/pipeline.py", "--apply-renames", "--incoming-path", scope_to_incoming(scope), *dry_args), "Pipeline apply renames")
    else:
        run_cmd(py("tools/pipeline.py", "--full", "--apply", *args, "--workers", "3", *dry_args), "Pipeline full apply")
    pause()


def main_menu_choice() -> str | None:
    values = dashboard_values()
    return select(
        "  What do you want to do?",
        [
            Choice("Scan Drive", value="scan_drive"),
            Choice("Rename files / folders", value="rename"),
            Choice("Verify / move", value="verify_move"),
            Choice(f"Upload files ({values['upload_remaining']} remaining)", value="upload"),
            Choice("Semester mapping", value="semester_mapping"),
            Choice("Toolbox", value="toolbox"),
            Separator("-" * 52),
            Choice(EXIT, value=EXIT),
        ],
        show_back=False,
    )


def main() -> None:
    actions = {
        "scan_drive": simple_scan_drive_workflow,
        "rename": simple_rename_workflow,
        "verify_move": simple_verify_move_workflow,
        "upload": simple_upload_workflow,
        "semester_mapping": semester_mapping_workflow,
        "toolbox": toolbox_workflow,
    }
    while True:
        banner()
        choice = main_menu_choice()
        if choice in {None, EXIT}:
            clear()
            print()
            note("Goodbye.", "ok")
            print()
            return
        actions[choice]()


if __name__ == "__main__":
    main()
