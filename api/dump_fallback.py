"""Regenerate the bundled offline fallback JSON from a pristine in-memory demo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import api.server as server  # noqa: E402

server.write_pristine_fallback()
print("Wrote", server.FALLBACK_PATH, "and", server.WEB_FALLBACK_PATH)
