import fitz

def extract_text_from_pdf(file_path: str):
    """
    Extract text page by page from a PDF.

    Returns:
    [
        {
            "page": 1,
            "text": "..."
        }
    ]
    """
    extracted_pages = []
    doc = fitz.open(file_path)

    try:
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            text = page.get_text("text").strip()

            if text:
                extracted_pages.append({
                    "page": page_index + 1,
                    "text": text
                })
    except Exception as e:
        print("Document not found :",e)

    return extracted_pages
