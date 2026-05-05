import re

# ─────────────────────────────────────────────────────────
# General / greeting keyword list
# Used to detect small-talk so we skip document retrieval
# and suppress source citations for those responses.
# ─────────────────────────────────────────────────────────
GENERAL_KEYWORDS = [
    "hi", "hello", "hey", "how are you", "who are you",
    "what are you", "good morning", "good evening", "good night",
    "thanks", "thank you", "bye", "goodbye", "what can you do",
    "what is your name", "yo", "sup"
]

def is_general_question(question: str) -> bool:
    """
    Returns True ONLY when the ENTIRE user message matches a
    known greeting / small-talk phrase.

    FIX over the old version: previously used `keyword in question`
    which matched substrings — e.g. "hi there what is photosynthesis?"
    would match "hi" and skip document retrieval incorrectly.

    Now uses re.fullmatch() so the whole cleaned question must equal
    one of the keywords exactly.

    Examples:
        is_general_question("hi")                         → True
        is_general_question("hi there")                   → False  ✅
        is_general_question("hi what is photosynthesis?") → False  ✅
        is_general_question("Hello!")                     → True
    """
    # Normalise: lowercase, strip leading/trailing spaces and punctuation
    q = question.lower().strip().rstrip("?!.,")
    return any(re.fullmatch(re.escape(kw), q) for kw in GENERAL_KEYWORDS)
