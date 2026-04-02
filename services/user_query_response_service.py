from google import genai
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def generate_query_response(content, chat_history):

    context = "\n\n".join([match["text"] for match in content['matches']])

    history_text = ""
    if chat_history:
        history_text = "\n".join(
            [f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history]
        )

    prompt = f"""
            You are a highly accurate document question-answering assistant.

You will be given:
1. A user question
2. Retrieved context chunks from a document

Your job:
- Answer the question ONLY using the provided context.
- Do NOT use any external knowledge.
- Do NOT guess or assume anything.
- If the answer is not present in the context, reply exactly:
  "I don't know based on the provided document."
- if the question is related to the past question from the chathistory refer it and provide the correct answer.

Instructions:
- Present the answer in a clean and structured format.
- Use bullet points when listing multiple items.
- Keep sentences short and easy to understand.
- Combine information only if it is clearly available in the context.
- Do NOT include explanations like "based on the context".
- Do NOT add notes or extra commentary.

Formatting rules:
- Start with a short 1-line summary (if applicable).
- Then present details as bullet points.
- Use simple and readable English.

---
Previous conversation:
{history_text}


Current User Question:
{content['question']}

---

Retrieved document context:
{context}

---

Answer:
            """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        answer = response.text

    except Exception as e:
        answer = "Error generating answer: " + str(e)

    return answer


async def stream_query_response(content, chat_history):
    context = "\n\n".join([match["text"] for match in content["matches"]])

    history_text = ""
    if chat_history:
        history_text = "\n".join(
            [f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history]
        )

    prompt = f"""
You are a smart AI assistant.

You can handle two types of queries:
1. General conversation (greetings, casual talk)
2. Document-based questions

---

Rules:

🔹 If the user asks a GENERAL question (like "hi", "how are you", "who are you"):
- Respond naturally like a friendly assistant.
- Keep it short.
- Mention that you are a bot designed to answer questions from uploaded documents.

---

If the user asks a DOCUMENT-RELATED question:
- Answer ONLY using the provided context.
- Do NOT use any external knowledge.
- Do NOT guess or assume anything.
- If the answer is not present in the context, reply exactly:
  "I don't know based on the provided document."

---

Instructions for document answers:
- Present the answer in a clean and structured format.
- Use bullet points when listing multiple items.
- Keep sentences short and easy to understand.
- Combine information only if clearly available in the context.
- Do NOT include explanations like "based on the context".
- Do NOT add extra commentary.

Formatting rules:
- Start with a short 1-line summary (if applicable).
- Then present details as bullet points.

---

Previous conversation:
{history_text}

---

Current User Question:
{content['question']}

---

Retrieved document context:
{context}

---

Answer:
"""
    try:
        stream = await client.aio.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=prompt
        )

        async for chunk in stream:
            piece = getattr(chunk, "text", "")
            if piece:
                yield piece

    except Exception as e:
        yield f"\nError generating answer: {str(e)}"