"""DocWiz — run the local Flask server.

Usage:
    python app.py
Then open http://127.0.0.1:5000 in your browser.
"""
from dotenv import load_dotenv

load_dotenv()  # read the project's .env file before anything reads the environment

from app import create_app  # noqa: E402  (import after load_dotenv is intentional)

app = create_app()

if __name__ == "__main__":
    import sys

    key_configured = bool(app.config["GROQ_API_KEY"])
    provider = app.config["EMBEDDING_PROVIDER"]
    embedding_model = app.config["EMBEDDING_MODEL"] or {
        "gemini": "gemini-embedding-001",
        "groq": "nomic-embed-text-v1_5",
    }.get(provider, "(provider default)")
    embedding_key_ok = {
        "gemini": bool(app.config["EMBEDDING_API_KEY"] or app.config.get("GEMINI_API_KEY")),
        "groq": bool(app.config["EMBEDDING_API_KEY"] or app.config["GROQ_API_KEY"]),
    }.get(provider, True)
    print("")
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │  DocWiz — ask questions about your PDFs, locally.  │")
    print("  └─────────────────────────────────────────────────────┘")
    print("")
    print(f"  Embeddings: {provider} ({embedding_model})")
    print("  Open:  http://127.0.0.1:5000")
    if not embedding_key_ok:
        print("")
        print(f"  ⚠  No API key for the '{provider}' embedding provider.")
        print("     Set EMBEDDING_API_KEY in .env (see .env.example) —")
        print("     uploads need it to index your PDFs.")
    if not key_configured:
        print("")
        print("  ⚠  GROQ_API_KEY is not set. Uploads and search work,")
        print("     but questions cannot be answered until you add your")
        print("     key to the .env file (see .env.example) and restart.")
    print("")
    print("  Press Ctrl+C to stop.")
    sys.stdout.flush()

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
