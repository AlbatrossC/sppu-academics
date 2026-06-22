# extract.py

import fitz

PDF_FILE = "document.pdf"
OUTPUT_FILE = "text.txt"

doc = fitz.open(PDF_FILE)

full_text = ""

for page in doc:
    full_text += page.get_text("text") + "\n"

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(full_text)

print(f"Text extracted to {OUTPUT_FILE}")