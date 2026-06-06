from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from config import load_config
from json_manager import (
    atomic_write_json,
    count_target_manifest_pdfs,
    iter_manifest_pdf_items,
    iter_subject_manifest_files,
    load_subject_document,
    pattern_key_from_manifest_file,
    read_json,
)
from logger import PipelineStats, ProgressLogger
from utils import (
    assign_question_ids,
    build_pdf_id,
    ensure_directory,
    load_json_file,
    load_text_file,
    timestamp_string,
)

ALL_VALUE = "__all__"
MBA_VALUE = "mba"


@dataclass(frozen=True)
class SelectionOption:
    label: str
    value: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract PYQ metadata into JSON files.")
    parser.add_argument("--pattern", help="Process only one manifest pattern, for example 2019 or honors.")
    parser.add_argument("--branch", help="Process only one branch code/key, for example aids or computer-engineering.")
    parser.add_argument("--year", help="Process only one year key, for example se, te, or be.")
    parser.add_argument("--semester", help="Process only one semester slug, for example sem-3.")
    parser.add_argument("--subject", help="Process only one subject slug.")
    parser.add_argument("--limit", type=int, help="Stop after processing N new PDFs.")
    parser.add_argument(
        "--provider",
        choices=["r2", "cloudinary"],
        default="r2",
        help="Provider base URL to use from the manifest. Defaults to r2.",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Skip selection prompts when no filters are provided.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    progress_logger = ProgressLogger(config.metadata_report_path)

    try:
        from extractor import PDFTextExtractor
        from gemini_client import GeminiExtractionError, GeminiMetadataClient
    except ImportError as error:
        progress_logger.append_event(f"Dependency error: {error}")
        print(f"Dependency error: {error}")
        return 1

    ensure_directory(config.output_dir)
    ensure_directory(config.scripts_dir)

    system_prompt = load_text_file(config.prompt_path)
    response_schema = load_json_file(config.schema_path)

    manifest_files = iter_subject_manifest_files(config.input_dir)
    if not manifest_files:
        progress_logger.append_event(f"No subject manifests found in {config.input_dir}")
        print(f"No subject manifests found in {config.input_dir}")
        return 1

    if should_prompt_for_selection(args):
        apply_interactive_selection(args, config.input_dir, manifest_files, provider=args.provider)
        if getattr(args, "selection_cancelled", False):
            print("Selection cancelled.")
            return 0

    stats = PipelineStats(
        total=count_target_manifest_pdfs(
            manifest_files,
            pattern_filter=args.pattern,
            branch_filter=args.branch,
            year_filter=args.year,
            semester_filter=args.semester,
            subject_filter=args.subject,
            provider=args.provider,
        )
    )
    if stats.total == 0:
        progress_logger.append_event("No PDFs matched the selected filters.")
        print("No PDFs matched the selected filters.")
        print_selection(args)
        return 0
    progress_logger.append_event("Pipeline started.")
    print(f"Pipeline started. Provider: {args.provider}. Target PDFs: {stats.total}")

    extractor = PDFTextExtractor(
        timeout_seconds=config.request_timeout_seconds,
        min_text_characters=config.pdf_text_min_characters,
        ocr_language=config.ocr_language,
        tesseract_cmd=config.tesseract_cmd,
    )
    try:
        gemini_client = GeminiMetadataClient(
            api_keys=config.gemini_api_keys,
            model_name=config.model_name,
            system_prompt=system_prompt,
            response_schema=response_schema,
            retries_per_key=config.gemini_retries_per_key,
            retry_delay_seconds=config.gemini_retry_delay_seconds,
        )
    except ValueError as error:
        progress_logger.append_event(f"Configuration error: {error}")
        progress_logger.append_snapshot(stats)
        print(f"Configuration error: {error}")
        print(f"Check: {config.scripts_dir / '.env'}")
        return 1

    processed_this_run = 0

    for manifest_file in manifest_files:
        pattern_key = pattern_key_from_manifest_file(manifest_file)
        if args.pattern and pattern_key != args.pattern:
            continue

        manifest_payload = read_json(manifest_file)

        for item in iter_manifest_pdf_items(
            manifest_payload,
            pattern_key=pattern_key,
            provider=args.provider,
        ):
            if args.branch and args.branch not in {item.branch, item.branch_key}:
                continue
            if args.year and item.year_key != args.year:
                continue
            if args.semester and item.semester != args.semester:
                continue
            if args.subject and item.subject_slug != args.subject:
                continue

            stats.current_branch = item.branch
            stats.current_semester = item.semester
            stats.current_subject = item.subject_slug

            output_path, subject_document = load_subject_document(
                config.output_dir,
                item.branch,
                item.semester,
                item.subject_slug,
                item.subject_name,
            )
            existing_pdf_urls = {
                paper.get("pdf_url")
                for paper in subject_document.get("papers", [])
                if isinstance(paper, dict)
            }

            pdf_url = item.pdf_url
            pdf_id = item.pdf_id or build_pdf_id(pdf_url)

            if pdf_url in existing_pdf_urls:
                stats.skipped += 1
                progress_logger.append_event(f"Skipped existing PDF: {pdf_url}")
                progress_logger.append_snapshot(stats)
                print(f"Skipped existing PDF: {pdf_url}")
                continue

            try:
                print(f"Processing PDF: {pdf_url}")
                extracted_document = extractor.extract_from_url(pdf_url)
                if extracted_document.used_ocr:
                    stats.ocr_used += 1
                    progress_logger.append_event(f"OCR used for {pdf_url}")
                    print(f"OCR used for: {pdf_url}")

                gemini_payload = gemini_client.extract_metadata(
                    branch=item.branch,
                    semester=item.semester,
                    subject_name=item.subject_name,
                    subject_slug=item.subject_slug,
                    pdf_url=pdf_url,
                    extracted_text=extracted_document.text,
                )
                questions = gemini_payload.get("questions", [])
                normalized_questions = assign_question_ids(pdf_id, questions)

                paper_payload = {
                    "pdf_id": pdf_id,
                    "pdf_url": pdf_url,
                    "canonical_path": item.canonical_path,
                    "pattern_key": item.pattern_key,
                    "pattern_year": item.pattern_year,
                    "year_key": item.year_key,
                    "year_name": item.year_name,
                    "source_metadata": {
                        "branch_key": item.branch_key,
                        "branch_name": item.branch_name,
                        "exam": item.paper.get("exam"),
                        "month": item.paper.get("month"),
                        "year": item.paper.get("year"),
                    },
                    "metadata": gemini_payload.get("metadata", {}),
                    "questions": normalized_questions,
                    "extraction_info": {
                        "method": extracted_document.extraction_method,
                        "used_ocr": extracted_document.used_ocr,
                        "page_count": extracted_document.page_count,
                        "character_count": extracted_document.character_count,
                        "processed_at": timestamp_string(),
                    },
                }
                subject_document.setdefault("papers", []).append(paper_payload)
                atomic_write_json(output_path, subject_document)

                existing_pdf_urls.add(pdf_url)
                stats.processed += 1
                processed_this_run += 1
                progress_logger.append_event(f"Processed PDF: {pdf_url}")
                progress_logger.append_snapshot(stats)
                print(f"Processed PDF: {pdf_url}")

                if args.limit and processed_this_run >= args.limit:
                    progress_logger.append_event("Processing limit reached.")
                    print("Processing limit reached.")
                    print_summary(stats)
                    return 0
            except GeminiExtractionError as error:
                stats.failed += 1
                stats.gemini_failures += 1
                progress_logger.append_event(f"Gemini failure for {pdf_url}: {error}")
                progress_logger.append_snapshot(stats)
                print(f"Gemini failure for {pdf_url}: {error}")
            except Exception as error:  # pragma: no cover
                stats.failed += 1
                progress_logger.append_event(f"PDF failure for {pdf_url}: {error}")
                progress_logger.append_snapshot(stats)
                print(f"PDF failure for {pdf_url}: {error}")

    progress_logger.append_event("Pipeline completed.")
    progress_logger.append_snapshot(stats)
    print("Pipeline completed.")
    print_summary(stats)
    return 0


def should_prompt_for_selection(args: argparse.Namespace) -> bool:
    if args.no_interactive:
        return False
    return not any([args.pattern, args.branch, args.year, args.semester, args.subject])


def apply_interactive_selection(
    args: argparse.Namespace,
    manifest_dir: Path,
    manifest_files: list[Path],
    *,
    provider: str,
) -> None:
    pattern_options = build_pattern_options(manifest_files, manifest_dir)
    selected_pattern = prompt_for_option("Select pattern / course:", pattern_options)
    if selected_pattern == MBA_VALUE:
        args.branch = MBA_VALUE
        args.selection_cancelled = False
        print_selection(args)
        return
    if selected_pattern is None:
        args.selection_cancelled = True
        return

    args.pattern = selected_pattern
    items = load_manifest_items(manifest_files, pattern_filter=args.pattern, provider=provider)

    branch_options = build_branch_options(items)
    selected_branch = prompt_for_option("Select branch:", branch_options)
    if selected_branch is None and selected_branch != ALL_VALUE:
        args.selection_cancelled = True
        return
    if selected_branch != ALL_VALUE:
        args.branch = selected_branch
        items = [item for item in items if selected_branch in {item.branch, item.branch_key}]

    year_options = build_year_options(items)
    selected_year = prompt_for_option("Select year:", year_options)
    if selected_year is None and selected_year != ALL_VALUE:
        args.selection_cancelled = True
        return
    if selected_year != ALL_VALUE:
        args.year = selected_year
        items = [item for item in items if item.year_key == selected_year]

    subject_options = build_subject_options(items)
    selected_subject = prompt_for_option("Select subject:", subject_options)
    if selected_subject is None and selected_subject != ALL_VALUE:
        args.selection_cancelled = True
        return
    if selected_subject != ALL_VALUE:
        args.subject = selected_subject

    args.selection_cancelled = False
    print_selection(args)


def build_pattern_options(manifest_files: list[Path], manifest_dir: Path) -> list[SelectionOption]:
    available_patterns = {pattern_key_from_manifest_file(path) for path in manifest_files}
    preferred_order = ["2019", "2015", "2012"]
    options = [
        SelectionOption(label=f"{pattern} Pattern", value=pattern)
        for pattern in preferred_order
        if pattern in available_patterns
    ]

    if any((manifest_dir / f"{pattern}.json").exists() for pattern in preferred_order):
        options.append(SelectionOption(label="M.B.A", value=MBA_VALUE))
    return options


def load_manifest_items(
    manifest_files: list[Path],
    *,
    pattern_filter: str | None,
    provider: str,
):
    items = []
    for manifest_file in manifest_files:
        pattern_key = pattern_key_from_manifest_file(manifest_file)
        if pattern_filter and pattern_key != pattern_filter:
            continue
        manifest_payload = read_json(manifest_file)
        items.extend(iter_manifest_pdf_items(manifest_payload, pattern_key=pattern_key, provider=provider))
    return items


def build_branch_options(items) -> list[SelectionOption]:
    branches: dict[str, str] = {}
    for item in items:
        value = item.branch or item.branch_key
        label = " - ".join(part for part in [item.branch.upper(), item.branch_name] if part)
        branches.setdefault(value, label or value)
    options = [SelectionOption(label="All branches", value=ALL_VALUE)]
    options.extend(SelectionOption(label=branches[key], value=key) for key in sorted(branches))
    return options


def build_year_options(items) -> list[SelectionOption]:
    years: dict[str, str] = {}
    for item in items:
        value = item.year_key
        if not value:
            continue
        label = " - ".join(part for part in [item.year_name, item.paper.get("yearFullName")] if part)
        years.setdefault(value, label or value.upper())
    options = [SelectionOption(label="All years", value=ALL_VALUE)]
    options.extend(SelectionOption(label=years[key], value=key) for key in sorted(years))
    return options


def build_subject_options(items) -> list[SelectionOption]:
    subjects: dict[str, str] = {}
    for item in items:
        subjects.setdefault(item.subject_slug, f"{item.subject_name} ({item.subject_slug})")
    options = [SelectionOption(label="All subjects", value=ALL_VALUE)]
    options.extend(SelectionOption(label=subjects[key], value=key) for key in sorted(subjects))
    return options


def prompt_for_option(message: str, options: list[SelectionOption]) -> str | None:
    if not options:
        return None

    try:
        import questionary

        labels = [option.label for option in options]
        selection = questionary.select(message, choices=labels, qmark=">").ask()
        if selection is None:
            return None
        return next(option.value for option in options if option.label == selection)
    except Exception:
        print(message)
        for index, option in enumerate(options, start=1):
            print(f"{index}. {option.label}")

        while True:
            raw_value = input("Enter selection number: ").strip()
            if not raw_value.isdigit():
                print("Please enter a valid number.")
                continue
            selected_index = int(raw_value)
            if 1 <= selected_index <= len(options):
                return options[selected_index - 1].value
            print("Selection out of range. Try again.")


def print_selection(args: argparse.Namespace) -> None:
    print(
        "Selected:"
        f" pattern={args.pattern or 'all'},"
        f" branch={args.branch or 'all'},"
        f" year={args.year or 'all'},"
        f" semester={args.semester or 'all'},"
        f" subject={args.subject or 'all'}"
    )


def print_summary(stats: PipelineStats) -> None:
    print(
        "Summary:"
        f" processed={stats.processed},"
        f" skipped={stats.skipped},"
        f" failed={stats.failed},"
        f" remaining={stats.remaining},"
        f" gemini_failures={stats.gemini_failures},"
        f" ocr_used={stats.ocr_used}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
