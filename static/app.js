// =============================================
// GLOBAL STATE & AUTHENTICATION
// =============================================
let currentSessionId = null;
let isRegisterMode = false;

function getToken() {
    return localStorage.getItem("token");
}

function setToken(token) {
    localStorage.setItem("token", token);
}

function logout() {
    localStorage.removeItem("token");
    currentSessionId = null;

    // Clear out the Chat Box so the next user doesn't see old messages
    const chatBox = document.getElementById("chatBox");
    if (chatBox) {
        chatBox.innerHTML = `
            <div class="message bot-message">
                <div class="message-content">
                    Hi! Upload a PDF on the Documents tab and ask me questions about it.
                </div>
            </div>`;
    }

    // Clear out the Documents list UI 
    const documentsList = document.getElementById("documentsList");
    if (documentsList) {
        documentsList.innerHTML = "<p class='no-docs-msg'>Loading...</p>";
    }

    checkAuth();
}

// Ensure every fetch request uses the token
function getAuthHeaders(isFileUpload = false) {
    const headers = {};
    if (!isFileUpload) {
        headers["Content-Type"] = "application/json";
    }
    const token = getToken();
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
}

// Check on load if the user's token is valid
async function checkAuth() {
    const token = getToken();
    if (!token) {
        showPage("auth");
        return;
    }

    try {
        const response = await fetch("/auth/me", { headers: getAuthHeaders() });
        if (response.ok) {
            showPage("chat"); // Logged in!
        } else {
            logout(); // Token expired or invalid
        }
    } catch (error) {
        logout();
    }
}

// =============================================
// AUTHENTICATION LOGIC (Login / Register)
// =============================================
function toggleAuthMode() {
    isRegisterMode = !isRegisterMode;
    document.getElementById("authTitle").textContent = isRegisterMode ? "Register" : "Login";
    document.getElementById("authSubmitBtn").textContent = isRegisterMode ? "Register" : "Login";
    document.getElementById("authConfirmPassword").style.display = isRegisterMode ? "block" : "none";
    document.getElementById("authConfirmPassword").required = isRegisterMode;
    document.getElementById("authToggleBtn").textContent = isRegisterMode ? "Already have an account? Login here." : "Need an account? Register here.";
    document.getElementById("authError").style.display = "none";
}

async function handleAuth(event) {
    event.preventDefault();
    const email = document.getElementById("authEmail").value;
    const password = document.getElementById("authPassword").value;
    const confirmPassword = document.getElementById("authConfirmPassword").value;
    const errorEl = document.getElementById("authError");

    errorEl.style.display = "none";

    try {
        if (isRegisterMode) {
            // REGISTER
            if (password !== confirmPassword) {
                errorEl.textContent = "Passwords do not match!";
                errorEl.style.display = "block";
                return;
            }
            const res = await fetch("/auth/register", {
                method: "POST",
                headers: getAuthHeaders(),
                body: JSON.stringify({ email, password, confirm_password: confirmPassword })
            });
            if (!res.ok) throw await res.json();
            alert("Registration successful! Please login.");
            toggleAuthMode();
        } else {
            // LOGIN
            const res = await fetch("/auth/login", {
                method: "POST",
                headers: getAuthHeaders(),
                body: JSON.stringify({ email, password })
            });
            if (!res.ok) throw await res.json();
            const data = await res.json();
            setToken(data.access_token);
            document.getElementById("authEmail").value = "";
            document.getElementById("authPassword").value = "";
            showPage("chat");
        }
    } catch (err) {
        errorEl.textContent = err.detail || "Authentication Failed";
        errorEl.style.display = "block";
    }
}

// =============================================
// STARTUP CHECK
// =============================================
checkAuth();

// =============================================
// GET PAGE ELEMENTS
// =============================================
const uploadBtn = document.getElementById("uploadBtn");
const sendBtn = document.getElementById("sendBtn");
const pdfFile = document.getElementById("pdfFile");
const uploadStatus = document.getElementById("uploadStatus");
const questionInput = document.getElementById("questionInput");
const chatBox = document.getElementById("chatBox");

function getUploadDb() {
    const selected = document.querySelector('input[name="activeDb"]:checked');
    return selected ? selected.value : "qdrant";
}

// =============================================
// Switch Pages 
// =============================================
function showPage(page) {
    document.getElementById("authPage").style.display = "none";
    document.getElementById("chatPage").style.display = "none";
    document.getElementById("documentsPage").style.display = "none";

    // Hide sidebar on auth page
    if (page === "auth") {
        document.getElementById("appSidebar").style.display = "none";
        document.getElementById("authPage").style.display = "flex";
        return;
    }

    document.getElementById("appSidebar").style.display = "flex";

    if (page === "chat") {
        document.getElementById("chatPage").style.display = "flex";
        document.getElementById("navChat").classList.add("active");
        document.getElementById("navDocs").classList.remove("active");
    } else if (page === "documents") {
        document.getElementById("documentsPage").style.display = "flex";
        document.getElementById("navDocs").classList.add("active");
        document.getElementById("navChat").classList.remove("active");
        loadDocuments();
    }
}

// =============================================
// Load Documents (Updated to hit /documents/)
// =============================================
async function loadDocuments() {
    const listContainer = document.getElementById("documentsList");
    listContainer.innerHTML = "<p class='no-docs-msg'>Loading...</p>";

    try {
        const response = await fetch("/documents/", { headers: getAuthHeaders() });
        const data = await response.json();

        if (response.status === 401) { logout(); return; }

        if (data.length === 0) {
            listContainer.innerHTML = "<p class='no-docs-msg'>No documents uploaded yet.</p>";
            return;
        }

        listContainer.innerHTML = "";
        data.forEach(doc => {
            const item = document.createElement("div");
            item.className = "doc-item";
            item.innerHTML = `
                <span class="doc-name">📄 ${doc.filename}</span>
                <div class="doc-actions">
                    <button class="delete-btn" onclick="deleteDocument('${doc.id}', '${doc.filename}')">🗑 Delete</button>
                </div>
            `;
            listContainer.appendChild(item);
        });
    } catch (error) {
        listContainer.innerHTML = "<p class='no-docs-msg'>Error loading documents.</p>";
    }
}

// =============================================
// Delete a document (Updated for new endpoint)
// =============================================
async function deleteDocument(docId, filename) {
    const confirmed = confirm(`Are you sure you want to delete "${filename}"?`);
    if (!confirmed) return;

    try {
        const response = await fetch(`/documents/${docId}`, {
            method: "DELETE",
            headers: getAuthHeaders()
        });
        if (response.status === 401) { logout(); return; }

        if (!response.ok) {
            alert("Failed to delete the document.");
            return;
        }

        alert(`"${filename}" deleted successfully.`);
        loadDocuments();
    } catch (error) {
        alert("Something went wrong while deleting.");
    }
}

// =============================================
// Upload MULTIPLE PDF files (Adding Auth Header)
// =============================================
uploadBtn.addEventListener("click", async () => {
    if (!pdfFile.files.length) {
        uploadStatus.textContent = "⚠️ Please select at least one PDF file.";
        return;
    }

    const formData = new FormData();
    for (const file of pdfFile.files) {
        formData.append("files", file);
    }
    formData.append("db_choice", getUploadDb());

    try {
        uploadBtn.disabled = true;
        uploadStatus.textContent = `⏳ Uploading...`;

        const response = await fetch("/upload/", {
            method: "POST",
            headers: getAuthHeaders(true), // true = don't set Content-Type
            body: formData
        });

        if (response.status === 401) { logout(); return; }
        const data = await response.json();
        if (!response.ok) { uploadStatus.textContent = "❌ Upload failed."; return; }

        uploadStatus.textContent = "✅ Upload completed successfully.";
        loadDocuments();
    } catch (error) {
        uploadStatus.textContent = "❌ Error uploading documents.";
    } finally {
        uploadBtn.disabled = false;
    }
});

// =============================================
// Chat Logic Helpers
// =============================================
function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function addMessage(content, sender = "bot", sources = []) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${sender}-message`;
    const messageContent = document.createElement("div");
    messageContent.className = "message-content";

    // Add text answer
    messageContent.innerHTML = `<div>${escapeHtml(content)}</div>`;

    // Append sources if they exist
    if (sources && sources.length > 0) {
        let sourceHtml = "<ul style='margin-top: 10px; font-size: 0.85em; opacity: 0.8;'>";
        sources.forEach(s => {
            sourceHtml += `<li>File: ${s.filename} (Page ${s.page})</li>`;
        });
        sourceHtml += "</ul>";
        messageContent.innerHTML += sourceHtml;
    }

    messageDiv.appendChild(messageContent);
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    return messageContent;
}

// =============================================
// Send a question (Updated to hit POST /chat/ JSON)
// =============================================
sendBtn.addEventListener("click", sendQuestion);
questionInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
});

async function sendQuestion() {
    const question = questionInput.value.trim();
    if (!question) return;

    addMessage(question, "user");
    questionInput.value = "";

    const loadingBubble = addMessage("thinking...", "bot");

    try {
        const payload = {
            message: question,
            top_k: 3,
            session_id: currentSessionId
        };

        const response = await fetch("/chat/", {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });

        if (response.status === 401) { logout(); return; }

        if (!response.ok) {
            loadingBubble.textContent = "Failed to get response.";
            return;
        }

        const data = await response.json();

        // Save session_id so AI remembers context
        currentSessionId = data.session_id;

        // Replace loading text with the actual answer and sources
        loadingBubble.parentNode.remove(); // Remove loading bubble
        addMessage(data.answer, "bot", data.sources);

    } catch (error) {
        loadingBubble.textContent = "Error communicating with server.";
    }
}
