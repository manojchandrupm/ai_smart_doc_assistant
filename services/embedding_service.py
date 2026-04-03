# import requests
#
# def generate_embedding(text):
#     """
#     Generate embedding using Ollama embeddings API.
#     """
#     response = requests.post(
#         "http://localhost:11434/api/embed",
#         json={
#             "model": "nomic-embed-text",
#             "input": text
#         },
#         timeout=60
#     )
#
#     response.raise_for_status()
#     data = response.json()
#
#     return data["embeddings"][0]

from google import genai
import os

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_embedding(text: str):
    """
    Generate embedding using Gemini API (cloud-based)
    """
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text
    )

    return response.embeddings[0].values