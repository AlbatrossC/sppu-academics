import os
import json

BASE_DIR = os.path.dirname(__file__)

QUESTION_PAPERS = os.path.join(BASE_DIR, "questionpapers.json")
VIEWER = os.path.join(BASE_DIR, "viewerseo.json")
OUTPUT = os.path.join(BASE_DIR, "comparison_report.txt")

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

qp = load_json(QUESTION_PAPERS)
vw = load_json(VIEWER)

# Extract slugs from questionpapers.json
qp_subjects = set()
for branch, sems in qp.items():
    for sem, subjects in sems.items():
        for slug in subjects.keys():
            qp_subjects.add(slug)

# Extract slugs + names from viewerseo.json
vw_subjects = {}
for branch, bdata in vw["branches"].items():
    for sem, subjects in bdata["semesters"].items():
        for entry in subjects:
            vw_subjects[entry["link"]] = entry["subjectName"]

# Build unified comparison
all_slugs = sorted(set(vw_subjects.keys()) | qp_subjects)
table_data = []
for slug in all_slugs:
    subject_name = vw_subjects.get(slug, "")
    viewer_value = slug if slug in vw_subjects else "✗"
    qp_value = slug if slug in qp_subjects else "✗"
    table_data.append((subject_name, viewer_value, qp_value))

# Column widths
max_name_len = max((len(row[0]) for row in table_data if row[0]), default=20)
max_viewer_len = max(len(row[1]) for row in table_data)
max_qp_len = max(len(row[2]) for row in table_data)

col1_width = max(max_name_len, len("Subject Name")) + 2
col2_width = max(max_viewer_len, len("In viewerseo.json")) + 2
col3_width = max(max_qp_len, len("In questionpapers.json")) + 2

report = []
separator = f"+{'-' * col1_width}+{'-' * col2_width}+{'-' * col3_width}+"
header = f"| {'Subject Name'.ljust(col1_width - 1)}| {'In viewerseo.json'.ljust(col2_width - 1)}| {'In questionpapers.json'.ljust(col3_width - 1)}|"

report.append(separator)
report.append(header)
report.append(separator)

for subject_name, viewer_value, qp_value in table_data:
    display_name = subject_name if subject_name else "(Missing Name)"
    row = f"| {display_name.ljust(col1_width - 1)}| {viewer_value.ljust(col2_width - 1)}| {qp_value.ljust(col3_width - 1)}|"
    report.append(row)

report.append(separator)

viewer_only = [s for s in all_slugs if s in vw_subjects and s not in qp_subjects]
qp_only = [s for s in all_slugs if s not in vw_subjects and s in qp_subjects]
in_both = [s for s in all_slugs if s in vw_subjects and s in qp_subjects]

report.append("")
report.append("=" * 60)
report.append("SUMMARY")
report.append("=" * 60)
report.append(f"Total Unique Subjects: {len(all_slugs)}")
report.append(f"Present in Both: {len(in_both)}")
report.append(f"Missing in questionpapers.json: {len(viewer_only)}")
report.append(f"Missing in viewerseo.json: {len(qp_only)}")
report.append("")

if viewer_only:
    report.append("Subjects only in viewerseo.json:")
    for slug in viewer_only:
        report.append(f"  • {vw_subjects[slug]} → {slug}")
    report.append("")

if qp_only:
    report.append("Subjects only in questionpapers.json:")
    for slug in qp_only:
        report.append(f"  • {slug}")
    report.append("")

report.append("=" * 60)

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write("\n".join(report))

print("Report generated → comparison_report.txt")
print(f"Total subjects analyzed: {len(all_slugs)}")
