import os
import json
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()
# Configure Cloudinary credentials
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# Root directory containing PDF files (change as needed)
ROOT_DIR = 'cse'
OUTPUT_JSON = 'questionpapers.json'

# Load existing JSON if present; otherwise, initialize a new structure
if os.path.exists(OUTPUT_JSON):
    with open(OUTPUT_JSON, 'r') as f:
        questionpapers = json.load(f)
else:
    questionpapers = {}

mainfolder = os.path.basename(ROOT_DIR)

# Ensure main folder entry exists in JSON
questionpapers.setdefault(mainfolder, {})

# Walk through the folder tree
for root, _, files in os.walk(ROOT_DIR):
    for file in files:
        # Skip non-PDF files
        if not file.lower().endswith('.pdf'):
            continue

        file_path = os.path.join(root, file)
        relative_path = os.path.relpath(file_path, ROOT_DIR).replace('\\', '/')
        parts = relative_path.split('/')

        # Expect path structure like: branch/subject/filename.pdf
        if len(parts) < 3:
            print(f"[Skipped] Improperly structured path: {relative_path}")
            continue

        branch, subject = parts[0], parts[1]

        # Ensure nested keys exist
        questionpapers[mainfolder].setdefault(branch, {})
        questionpapers[mainfolder][branch].setdefault(subject, [])

        # Check if file already uploaded
        uploaded_files = {os.path.basename(url) for url in questionpapers[mainfolder][branch][subject]}
        if file in uploaded_files:
            print(f"[Skipped] Already uploaded: {file}")
            continue

        # Cloudinary upload path
        cloudinary_folder = f"{mainfolder}/{branch}/{subject}"

        try:
            response = cloudinary.uploader.upload(
                file_path,
                resource_type="raw",
                folder=cloudinary_folder,
                use_filename=True,
                unique_filename=False,
                overwrite=False
            )
            file_url = response['secure_url']
            questionpapers[mainfolder][branch][subject].append(file_url)
            print(f"[Uploaded] {file} → {file_url}")
        except Exception as e:
            print(f"[Error] Failed to upload {file}: {e}")

# Write the updated JSON index
with open(OUTPUT_JSON, 'w') as f:
    json.dump(questionpapers, f, indent=4)

print("\n✅ Upload complete. JSON index saved to 'questionpapers.json'.")
