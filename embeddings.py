"""Embeddings: 100% Free Local Embeddings (SentenceTransformers) & Gemini with Voyage fallback."""
import os
import warnings
from functools import cache

from dotenv import load_dotenv

load_dotenv()

DIMENSIONS = 1024
# Suppress huggingface symlink warnings on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", category=UserWarning)


def _pad_to_1024(vector):
    """Pad vector with zeros up to 1024 dimensions so MongoDB Vector index stays consistent."""
    if len(vector) < DIMENSIONS:
        return vector + [0.0] * (DIMENSIONS - len(vector))
    return vector[:DIMENSIONS]


@cache
def _get_local_model():
    """Load local SentenceTransformer (all-MiniLM-L6-v2) - completely free, offline, unlimited."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def _embed_local(text):
    model = _get_local_model()
    vec = model.encode(text, normalize_embeddings=True).tolist()
    return _pad_to_1024(vec)


def _embed_gemini(text):
    from google import genai
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=key)
    resp = client.models.embed_content(
        model="text-embedding-004",
        contents=text,
    )
    vec = resp.embeddings[0].values
    return _pad_to_1024(vec)


def _embed_voyage(text, input_type="document"):
    import voyageai
    client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    return client.embed([text], model="voyage-3.5", input_type=input_type).embeddings[0]


def embed(text, input_type="document"):
    """Turn text into a 1024-dimensional embedding vector.
    
    100% Free:
    1. First tries local SentenceTransformers (0 cost, no rate limits, offline).
    2. Falls back to Gemini embeddings if available.
    3. Falls back to Voyage AI only if configured and working.
    """
    # 1. Local SentenceTransformer (free, runs locally, 0 rate limit)
    try:
        return _embed_local(text)
    except Exception:
        pass

    # 2. Gemini text-embedding-004 (free 1,500 RPM with Gemini API key)
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        try:
            return _embed_gemini(text)
        except Exception:
            pass

    # 3. Voyage AI
    if os.getenv("VOYAGE_API_KEY"):
        try:
            return _embed_voyage(text, input_type=input_type)
        except Exception:
            pass

    return _embed_local(text)


if __name__ == "__main__":
    v = embed("Testing free local embeddings")
    assert len(v) == 1024
    print("[OK] embeddings.py self-check passed (dim: 1024)")
