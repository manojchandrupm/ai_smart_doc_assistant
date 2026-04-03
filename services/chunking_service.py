def chunk_text(text, chunk_size, overlap):
    """
    Split text into overlapping character-based chunks.
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks


def create_document_chunks(filename, pages, chunk_size, overlap):
    """
    Create chunk objects with metadata:
    - filename
    - page
    - chunk_id
    - text
    """
    all_chunks = []

    for page_data in pages:
        page_number = page_data["page"]
        page_text = page_data["text"]

        page_chunks = chunk_text(page_text,chunk_size,overlap)

        for idx, chunk in enumerate(page_chunks, start=1):
            all_chunks.append({
                "chunk_id": f"{filename}_p{page_number}_c{idx}",
                "filename": filename,
                "page": page_number,
                "chunk_index": idx,
                "text": chunk
            })

    return all_chunks
