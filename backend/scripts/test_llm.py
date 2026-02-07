"""
Test LLM API key and model (OpenAI or Gemini).
Run from repo root: python backend/scripts/test_llm.py
Requires: pip install openai python-dotenv  (or google-generativeai for Gemini)
"""
import os
import sys
from pathlib import Path

env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")


def test_openai():
    if not OPENAI_API_KEY:
        print("ERR OPENAI_API_KEY not set in .env")
        return False
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        r = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=10,
        )
        text = (r.choices[0].message.content or "").strip()
        print(f"OK  LLM (OpenAI {LLM_MODEL}): {text!r}")
        return True
    except Exception as e:
        print(f"ERR LLM (OpenAI): {e}")
        return False


def test_gemini():
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        print("ERR GEMINI_API_KEY / GOOGLE_API_KEY not set in .env")
        return False
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel(os.getenv("LLM_MODEL", "gemini-1.5-pro"))
        r = model.generate_content("Reply with exactly: OK")
        text = (r.text or "").strip()
        print(f"OK  LLM (Gemini): {text!r}")
        return True
    except Exception as e:
        print(f"ERR LLM (Gemini): {e}")
        return False


def main():
    print("Testing LLM...")
    if PROVIDER == "openai":
        ok = test_openai()
    elif PROVIDER == "gemini":
        ok = test_gemini()
    else:
        print(f"ERR Unknown LLM_PROVIDER={PROVIDER}. Use openai or gemini.")
        ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
