import os
from src import create_app
from src.db import init_db

app = create_app()

if __name__ == "__main__":
    init_db()
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=3000, debug=debug_mode)
