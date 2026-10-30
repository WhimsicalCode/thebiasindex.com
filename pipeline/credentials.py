"""API credentials for the pipeline, read from the environment and never printed.

- OPENAI_API_KEY: Luna (classify.py) and the GPT judge (ai_review.py).
- GOOGLE_CLOUD_PROJECT: Vertex AI project for the Gemini judge (ai_review.py); uses application default credentials.
"""

import os


def openai_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("Set OPENAI_API_KEY.")
    return key


def google_cloud_project():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT.")
    return project
