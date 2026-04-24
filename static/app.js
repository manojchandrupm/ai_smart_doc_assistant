// =============================================
// GLOBAL STATE & AUTHENTICATION
// =============================================
let currentSessionId = null;
let isRegisterMode = false;
let chatSocket = null;
let currentBotBubble = null;

function getToken() {
    return localStorage.getItem("token");
}

function setToken(token) {
    localStorage.setItem("token", token);
}

function logout() {
    localStorage.removeItem("token");
    currentSessionId = null;
    if (chatSocket) {
        chatSocket.close();
        chatSocket = null;
    }

    // Clear out the Chat Box so the next user doesn't see old messages
    const chatBox = document.getElementById("chatBox");
    if (chatBox) {
        chatBox.innerHTML = `
            <div class="message bot-message">
                <div class="message-content">Hi! Upload a PDF on the Documents tab and ask me questions about it.</div>
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
            loadThreads();
        } else if (response.status === 401) {
            // Token is expired or invalid — clear it and go to login
            localStorage.removeItem("token");
            currentSessionId = null;
            showPage("auth");
        } else {
            // Server error (5xx) or other — don't wipe the token, just show login
            showPage("auth");
        }
    } catch (error) {
        // Network error (e.g. server cold-starting on Render) — don't wipe the token
        // Show auth page so user can retry, but keep the stored token
        showPage("auth");
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
            loadThreads();
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
        document.getElementById("navDocs").classList.remove("active");
    } else if (page === "documents") {
        document.getElementById("documentsPage").style.display = "flex";
        document.getElementById("navDocs").classList.add("active");
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

        // Check auth status BEFORE parsing body
        if (response.status === 401) {
            showPage("auth"); // Don't wipe token here; user will re-login
            return;
        }

        if (!response.ok) {
            listContainer.innerHTML = "<p class='no-docs-msg'>Server error loading documents. Please try again.</p>";
            return;
        }

        const data = await response.json();

        if (!Array.isArray(data) || data.length === 0) {
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

        if (response.status === 401) { showPage("auth"); return; }

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

    const textDiv = document.createElement("div");
    textDiv.className = "msg-text";
    textDiv.textContent = content;
    messageContent.appendChild(textDiv);

    // Append sources if they exist
    if (sources && sources.length > 0) {
        const sourcesList = buildSourcesList(sources);
        messageContent.appendChild(sourcesList);
    }

    messageDiv.appendChild(messageContent);
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    return messageContent;
}

function buildSourcesList(sources) {
    const ul = document.createElement("ul");
    ul.style.cssText = "margin-top: 10px; font-size: 0.85em; opacity: 0.8;";
    const uniqueFilenames = [...new Set(sources.map(s => s.filename))];
    uniqueFilenames.forEach(filename => {
        const li = document.createElement("li");
        li.textContent = `Source File: ${filename}`;
        ul.appendChild(li);
    });
    return ul;
}

// =============================================
// WEBSOCKET LOGIC
// =============================================
let streamingText = ""; // accumulates raw streaming text

function connectWebSocket() {
    const token = getToken();
    if (!token) return;

    if (chatSocket && (chatSocket.readyState === WebSocket.OPEN || chatSocket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/chat/ws?token=${token}`;
    
    chatSocket = new WebSocket(wsUrl);

    chatSocket.onopen = () => {
        console.log("WebSocket connected!");
    };

    chatSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.error) {
            console.error("WS Error:", data.error);
            if (currentBotBubble) {
                currentBotBubble.querySelector('.msg-text').textContent = "Error: " + data.error;
            }
            sendBtn.disabled = false;
            questionInput.disabled = false;
            currentBotBubble = null;
            return;
        }

        if (data.type === "session_meta") {
            const wasNewSession = !currentSessionId;
            currentSessionId = data.session_id;
            if (wasNewSession) loadThreads();

        } else if (data.type === "token") {
            if (currentBotBubble) {
                let chunk = data.content;
                chunk = chunk.replace(/\[GENERAL\]/g, "");
                streamingText += chunk;

                const textDiv = currentBotBubble.querySelector('.msg-text');
                textDiv.classList.add('streaming');
                // Schedule DOM paint on next animation frame for smooth rendering
                requestAnimationFrame(() => {
                    textDiv.textContent = streamingText;
                    chatBox.scrollTop = chatBox.scrollHeight;
                });
            }

        } else if (data.type === "end") {
            if (currentBotBubble) {
                const textDiv = currentBotBubble.querySelector('.msg-text');
                textDiv.classList.remove('streaming');
                let finalText = data.full_answer || streamingText;
                finalText = finalText.replace(/\[GENERAL\]/g, "").trim();
                textDiv.textContent = finalText;

                if (data.sources && data.sources.length > 0) {
                    currentBotBubble.appendChild(buildSourcesList(data.sources));
                }
                chatBox.scrollTop = chatBox.scrollHeight;
            }
            // Reset state
            streamingText = "";
            currentBotBubble = null;
            sendBtn.disabled = false;
            questionInput.disabled = false;
            questionInput.focus();
        }
    };

    chatSocket.onerror = (err) => {
        console.error("WebSocket error:", err);
    };

    chatSocket.onclose = () => {
        console.log("WebSocket disconnected.");
        chatSocket = null;
    };
}

// =============================================
// Send a question (Updated for WebSockets)
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

    sendBtn.disabled = true;
    questionInput.disabled = true;

    // Reset streaming accumulator and create fresh bot bubble
    streamingText = "";
    currentBotBubble = addMessage("thinking...", "bot");

    const payload = {
        message: question,
        top_k: 3,
        session_id: currentSessionId
    };

    if (!chatSocket || chatSocket.readyState !== WebSocket.OPEN) {
        connectWebSocket();
        chatSocket.addEventListener('open', () => {
            chatSocket.send(JSON.stringify(payload));
        }, { once: true });
    } else {
        chatSocket.send(JSON.stringify(payload));
    }
}

// =============================================
// Chat History / Threads Logic
// =============================================
async function loadThreads() {
    const listContainer = document.getElementById("threadList");
    if (!listContainer) return;

    try {
        const response = await fetch("/chat/sessions", { headers: getAuthHeaders() });
        if (!response.ok) return;

        const sessions = await response.json();
        listContainer.innerHTML = "";

        if (sessions.length === 0) {
            listContainer.innerHTML = "<p style='font-size: 12px; color: #6b7280; padding: 10px;'>No previous chats.</p>";
            return;
        }

        sessions.forEach(session => {
            const wrapper = document.createElement("div");
            wrapper.className = "thread-wrapper";

            const btn = document.createElement("button");
            btn.className = "thread-btn" + (session.session_id === currentSessionId ? " active-thread" : "");
            btn.textContent = session.title || "New Chat";
            btn.onclick = () => loadThreadMessages(session.session_id);

            const deleteBtn = document.createElement("button");
            deleteBtn.className = "delete-thread-btn";
            deleteBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>`;
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                deleteThread(session.session_id, session.title || "New Chat");
            };

            wrapper.appendChild(btn);
            wrapper.appendChild(deleteBtn);
            listContainer.appendChild(wrapper);
        });
    } catch (e) {
        console.error("Error loading threads:", e);
    }
}

async function loadThreadMessages(sessionId) {
    currentSessionId = sessionId;
    showPage("chat");
    loadThreads(); // Update active state styling

    const chatBox = document.getElementById("chatBox");
    chatBox.innerHTML = "<div style='text-align:center; color:#6b7280; padding: 20px;'>Loading...</div>";

    try {
        const response = await fetch(`/chat/sessions/${sessionId}/messages`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error("Failed to load messages");

        const messages = await response.json();
        chatBox.innerHTML = "";

        if (messages.length === 0) {
            startNewChat();
            return;
        }

        messages.forEach(msg => {
            addMessage(msg.message, msg.role === "assistant" ? "bot" : "user", msg.sources);
        });
    } catch (e) {
        console.error("Error loading messages:", e);
        chatBox.innerHTML = "<div style='color:red; padding: 20px;'>Error loading messages.</div>";
    }
}

function startNewChat() {
    currentSessionId = null;
    loadThreads(); // Update active state styling
    showPage("chat");

    const chatBox = document.getElementById("chatBox");
    if (chatBox) {
        chatBox.innerHTML = `
            <div class="message bot-message">
                <div class="message-content">Hi! Upload a PDF on the Documents tab and ask me questions about it.</div>
            </div>`;
    }
}

async function deleteThread(sessionId, title) {
    const confirmed = confirm(`Are you sure you want to delete the chat "${title}"?`);
    if (!confirmed) return;

    try {
        const response = await fetch(`/chat/sessions/${sessionId}`, {
            method: "DELETE",
            headers: getAuthHeaders()
        });

        if (response.status === 401) { showPage("auth"); return; }
        if (!response.ok) {
            alert("Failed to delete the chat session.");
            return;
        }

        if (currentSessionId === sessionId) {
            startNewChat();
        } else {
            loadThreads();
        }
    } catch (e) {
        console.error("Error deleting thread:", e);
        alert("Something went wrong while deleting.");
    }
}