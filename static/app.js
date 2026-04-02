const uploadBtn = document.getElementById("uploadBtn");
const sendBtn = document.getElementById("sendBtn");
const pdfFile = document.getElementById("pdfFile");
const uploadStatus = document.getElementById("uploadStatus");
const questionInput = document.getElementById("questionInput");
const chatBox = document.getElementById("chatBox");

let chatHistory = [];

//----------------non Streaming add message ----------------------------
//function addMessage(content, sender = "bot", sources = "") {
//    const messageDiv = document.createElement("div");
//    messageDiv.className = `message ${sender}-message`;
//
//    const messageContent = document.createElement("div");
//    messageContent.className = "message-content";
//
//    if (sender === "bot" && sources) {
//        messageContent.innerHTML = `
//            <div>${escapeHtml(content)}</div>
//            <div class="sources"><strong>Sources:</strong><br>${escapeHtml(sources)}</div>
//        `;
//    } else {
//        messageContent.textContent = content;
//    }
//
//    messageDiv.appendChild(messageContent);
//    chatBox.appendChild(messageDiv);
//    chatBox.scrollTop = chatBox.scrollHeight;
//}


function addMessage(content, sender = "bot", sources = "") {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${sender}-message`;

    const messageContent = document.createElement("div");
    messageContent.className = "message-content";

    if (sender === "bot" && sources) {
        messageContent.innerHTML = `
            <div>${escapeHtml(content)}</div>
            <div class="sources"><strong>Sources:</strong><br>${escapeHtml(sources)}</div>
        `;
    } else {
        messageContent.textContent = content;
    }

    messageDiv.appendChild(messageContent);
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Return inner content box so streaming can update it live
    return messageContent;
}

//function addLoadingMessage() {
//    const messageDiv = document.createElement("div");
//    messageDiv.className = "message bot-message";
//    messageDiv.id = "loadingMessage";
//
//    const messageContent = document.createElement("div");
//    messageContent.className = "message-content loading";
//    messageContent.textContent = "Thinking...";
//
//    messageDiv.appendChild(messageContent);
//    chatBox.appendChild(messageDiv);
//    chatBox.scrollTop = chatBox.scrollHeight;
//}
//
//function removeLoadingMessage() {
//    const loading = document.getElementById("loadingMessage");
//    if (loading) loading.remove();
//}

function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

uploadBtn.addEventListener("click", async () => {
    if (!pdfFile.files.length) {
        uploadStatus.textContent = "Please select a PDF file.";
        return;
    }

    const formData = new FormData();
    formData.append("file", pdfFile.files[0]);

    try {
        uploadBtn.disabled = true;
        uploadStatus.textContent = "Uploading and processing document...";

        const response = await fetch("/upload/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            uploadStatus.textContent = data.detail || "Upload failed.";
            return;
        }

        uploadStatus.textContent =
            `Uploaded successfully: ${data.filename}\nTotal chunks stored: ${data.total_chunks}`;

        addMessage(`Document uploaded successfully: ${data.filename}`, "bot");
    } catch (error) {
        console.error(error);
        uploadStatus.textContent = "Error uploading document.";
    } finally {
        uploadBtn.disabled = false;
    }
});

sendBtn.addEventListener("click", sendQuestion);
questionInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
    }
});

//------------------------------ non streaming sendQuestion --------------------------------
//async function sendQuestion() {
//    const question = questionInput.value.trim();
//
//    if (!question) return;
//
//    addMessage(question, "user");
//    questionInput.value = "";
//
//    chatHistory.push({ role: "user", content: question }); chatHistory = chatHistory.slice(-6);
//
//    addLoadingMessage();
//
//    try {
//        const response = await fetch("/query/", {
//            method: "POST",
//            headers: {
//                "Content-Type": "application/json"
//            },
//            body: JSON.stringify({
//                question: question,
//                top_k: 3
//            })
//        });
//
//        const data = await response.json();
//        removeLoadingMessage();
//
//        if (!response.ok) {
//            addMessage(data.detail || "Failed to get response.", "bot");
//            return;
//        }
//
//        addMessage(data.answer || "No answer received.", "bot", data.sources || "");
//
//        chatHistory.push({ role: "assistant", content: answer }); chatHistory = chatHistory.slice(-6);
//
//    } catch (error) {
//        console.error(error);
//        removeLoadingMessage();
//        addMessage("Error while sending question.", "bot");
//    }
//}


async function sendQuestion() {
    const question = questionInput.value.trim();

    if (!question) return;

    addMessage(question, "user");
    questionInput.value = "";

    chatHistory.push({
        role: "user",
        content: question
    });
    chatHistory = chatHistory.slice(-6);

    // Create empty bot message and get its content element
    const botMessageContent = addMessage("thinking..........", "bot");

    try {
        const response = await fetch("/query/stream", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
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

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            fullText += chunk;

            // Show streaming text inside bot message box
            botMessageContent.textContent = fullText;
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        // Save only main answer in chat history, not sources
        const cleanAnswer = fullText.split("\n\nSources:")[0];

        chatHistory.push({
            role: "assistant",
            content: cleanAnswer
        });
        chatHistory = chatHistory.slice(-6);

    } catch (error) {
        console.error(error);
        botMessageContent.textContent = "Error while streaming response.";
    }
}