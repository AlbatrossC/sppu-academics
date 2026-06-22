# Calls db.save_*() directly — no threading.
# db.py makes a synchronous HTTP call to the Cloudflare Worker (~100ms),
# so threading was removed because Vercel's serverless runtime kills
# background threads when the response is sent.
from .db import save_api_request, save_paper_download


def log_api_request_async(subject_link, question_no, status):
    try:
        save_api_request(subject_link, question_no, status)
    except Exception:
        pass
    return True


def log_paper_download_async(fingerprint_id, subject):
    try:
        save_paper_download(fingerprint_id, subject)
    except Exception:
        pass
    return True


class AsyncAPILogger:
    def start(self):
        return None

    def log_api_request(self, subject_link, question_no, status):
        return log_api_request_async(subject_link, question_no, status)


api_logger = AsyncAPILogger()
