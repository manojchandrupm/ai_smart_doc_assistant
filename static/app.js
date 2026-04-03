// =============================================
// GET PAGE ELEMENTS
// =============================================
const uploadBtn = document.getElementById("uploadBtn");
const sendBtn = document.getElementById("sendBtn");
const pdfFile = document.getElementById("pdfFile");
const uploadStatus = document.getElementById("uploadStatus");
const questionInput = document.getElementById("questionInput");
const chatBox = document.getElementById("chatBox");
let chatHistory = [];

// =============================================
// CHANGE 1 — Switch between Chat and Documents pages
// =============================================
function showPage(page) {
    const chatPage = document.getElementById("chatPage");
    const documentsPage = document.getElementById("documentsPage");
    const navChat = document.getElementById("navChat");
    const navDocs = document.getElementById("navDocs");

    if (page === "chat") {
        // Show chat, hide documents
        chatPage.style.display = "flex";
        documentsPage.style.display = "none";
        navChat.classList.add("active");
        navDocs.classList.remove("active");
    } else {
        // Show documents, hide chat
        chatPage.style.display = "none";
        documentsPage.style.display = "flex";
        navChat.classList.remove("active");
        navDocs.classList.add("active");
        // Every time user opens Documents tab, refresh the list
        loadDocuments();
    }
}

// =============================================
// CHANGE 2 — Load and display the list of uploaded documents
// =============================================
async function loadDocuments() {

    const listContainer = document.getElementById("documentsList");
    listContainer.innerHTML = "<p class='no-docs-msg'>Loading...</p>";

    try {
        // Call the new GET /upload/documents API
        const response = await fetch("/upload/documents");
        const data = await response.json();

        if (!data.documents || data.documents.length === 0) {
            listContainer.innerHTML = "<p class='no-docs-msg'>No documents uploaded yet.</p>";
            return;
        }

        // Build one row per document, with a delete button
        listContainer.innerHTML = "";
        data.documents.forEach(filename => {
            const item = document.createElement("div");
            item.className = "doc-item";

            // CHANGE 3 — Delete button calls deleteDocument() with the filename
            item.innerHTML = `
                <span class="doc-name">📄 ${filename}</span>
                <button class="delete-btn" onclick="deleteDocument('${filename}')">🗑 Delete</button>
            `;
            listContainer.appendChild(item);
        });

    } catch (error) {
        listContainer.innerHTML = "<p class='no-docs-msg'>Error loading documents.</p>";
        console.error("Error loading documents:", error);
    }
}

// =============================================
// CHANGE 3 — Delete a document (removes PDF file + Qdrant vectors)
// =============================================
async function deleteDocument(filename) {
    // Ask user to confirm before deleting
    const confirmed = confirm(
        `Are you sure you want to delete "${filename}"?\n` +
        `This will also remove all its data from the AI's knowledge.`
    );

    if (!confirmed) return;

    try {
        // Call the new DELETE /upload/documents/{filename} API
        const response = await fetch(`/upload/documents/${encodeURIComponent(filename)}`, {
            method: "DELETE"
        });

        const data = await response.json();

        if (!response.ok) {
            alert(data.detail || "Failed to delete the document.");
            return;
        }

        alert(`"${filename}" has been deleted successfully.`);
        loadDocuments(); // Refresh the list to reflect deletion
    } catch (error) {
        alert("Something went wrong while deleting.");
        console.error("Delete error:", error);
    }
}
// =============================================
// CHANGE 5 — Upload MULTIPLE PDF files at once
// =============================================
uploadBtn.addEventListener("click", async () => {
    if (!pdfFile.files.length) {
        uploadStatus.textContent = "⚠️ Please select at least one PDF file.";
        return;
    }
    // Append ALL selected files into FormData under the key "files"
    // The backend List[UploadFile] reads all files with that key name
    const formData = new FormData();
    for (const file of pdfFile.files) {
        formData.append("files", file);
    }
    try {
        uploadBtn.disabled = true;
        uploadStatus.textContent = `⏳ Uploading ${pdfFile.files.length} file(s)... Please wait.`;
        const response = await fetch("/upload/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            uploadStatus.textContent = "❌ " + (data.detail || "Upload failed.");
            return;
        }

        // Show a summary of which files succeeded and which failed
        let statusText = data.message + "\n\n";

        data.uploaded.forEach(f => {
            statusText += `✅ ${f.filename} (${f.total_chunks} chunks stored)\n`;
        });
        data.errors.forEach(e => {
            statusText += `❌ ${e.filename}: ${e.error}\n`;
        });
        uploadStatus.textContent = statusText;
        // Refresh doc list to show the newly uploaded files
        loadDocuments();
    } catch (error) {
        console.error(error);

        uploadStatus.textContent = "❌ Error uploading documents.";
    } finally {
        uploadBtn.disabled = false;
    }
});

// =============================================
// CHAT — Helper: Add a message bubble to the chat
// =============================================
function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
function addMessage(content, sender = "bot") {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${sender}-message`;
    const messageContent = document.createElement("div");
    messageContent.className = "message-content";
    messageContent.textContent = content;
    messageDiv.appendChild(messageContent);
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    // Return the inner element so streaming can update it live
    return messageContent;
}
// =============================================
// CHAT — Send a question (streaming response)
// =============================================
sendBtn.addEventListener("click", sendQuestion);

questionInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
    }
});

async function sendQuestion() {

    const question = questionInput.value.trim();

    if (!question) return;

    addMessage(question, "user");
    questionInput.value = "";

    // Keep last 6 messages in history for context
    chatHistory.push({ role: "user", content: question });
    chatHistory = chatHistory.slice(-6);

    // Create a placeholder bot message that will be updated as tokens stream in
    const botMessageContent = addMessage("thinking..........", "bot");
    try {
        const response = await fetch("/query/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: question,
                top_k: 3,
                chat_history: chatHistory
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            botMessageContent.textContent = errorText || "Failed to get response.";
            return;
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";

        // Read streamed chunks one by one
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            fullText += decoder.decode(value, { stream: true });

            // CHANGE 4 — Split answer from sources (sources only included for document questions)
            // The backend sends "\n\nSources:\n" only for document-related questions.
            // For greetings like "hi", there is NO Sources section at all.
            if (fullText.includes("\n\nSources:\n")) {
                const [answerPart, sourcesPart] = fullText.split("\n\nSources:\n");
                botMessageContent.innerHTML = `
                    <div>${escapeHtml(answerPart.trim())}</div>
                    <div class="sources">
                        <strong>Sources:</strong><br>${escapeHtml((sourcesPart || "").trim())}
                    </div>
                `;
            } else {
                // No sources section yet — just show the answer text
                botMessageContent.textContent = fullText;
            }
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        // Save only the clean answer (without sources) into chat history
        const cleanAnswer = fullText.split("\n\nSources:\n")[0];
        chatHistory.push({ role: "assistant", content: cleanAnswer });
        chatHistory = chatHistory.slice(-6);
    } catch (error) {
        console.error(error);
        botMessageContent.textContent = "Error while streaming response.";
    }
}