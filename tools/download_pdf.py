import urllib.request
import os
import subprocess
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = "http://collegecirculars.unipune.ac.in/sites/documents/Syllabus2021/TE_Computer_Engineering_2019_Syllabus_05072021.pdf"
pdf_path = "/tmp/TE.pdf"
txt_path = "/tmp/TE.txt"

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx) as response:
    with open(pdf_path, 'wb') as f:
        f.write(response.read())

print("PDF downloaded.")

# Try to extract text using python's pypdf if available, else pip install it
try:
    import pypdf
except ImportError:
    subprocess.run(["pip3", "install", "pypdf", "--break-system-packages"], check=True)
    import pypdf

reader = pypdf.PdfReader(pdf_path)
text = ""
for page in reader.pages:
    text += page.extract_text() + "\n"

with open(txt_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Text extracted. Length:", len(text))
