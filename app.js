let socket = null;
let currentRoom = "";
let localStream = null;
let screenStream = null;

const peers = {};
const remoteStreams = {};

function initMeeting(roomCode) {
    currentRoom = roomCode;

    socket = io();

    socket.on("connect", function () {
        socket.emit("join_meeting", { room: currentRoom });
    });

    socket.on("room_users", async function (data) {
        updateParticipants(data.users);

        for (const user of data.users) {
            if (user.username !== CURRENT_USERNAME) {
                if (!peers[user.user_id]) {
                    // The server does not expose Socket.IO IDs in the public
                    // participant list. The connection request is initiated
                    // by the room client using the current event flow below.
                }
            }
        }
    });

    socket.on("system_message", function (data) {
        addSystemMessage(data.message);
    });

    socket.on("chat_message", function (data) {
        addChatMessage(data.username, data.message, data.created_at);
    });

    socket.on("connection_request", async function (data) {
        await createPeerConnection(data.from, true);
    });

    socket.on("webrtc_offer", async function (data) {
        await handleOffer(data);
    });

    socket.on("webrtc_answer", async function (data) {
        await handleAnswer(data);
    });

    socket.on("ice_candidate", async function (data) {
        await handleIceCandidate(data);
    });

    socket.on("whiteboard_draw", function (data) {
        drawRemote(data);
    });

    socket.on("whiteboard_clear", function () {
        clearCanvas(false);
    });

    setupWhiteboard();
    loadLocalMedia();
}


async function loadLocalMedia() {
    try {
        localStream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: true
        });

        const localVideo = document.getElementById("localVideo");
        localVideo.srcObject = localStream;

        document.getElementById("mediaStatus").textContent =
            "Camera and microphone enabled.";
    } catch (error) {
        console.error(error);

        document.getElementById("mediaStatus").textContent =
            "Camera/microphone permission was not granted.";

        try {
            localStream = await navigator.mediaDevices.getUserMedia({
                video: false,
                audio: true
            });
        } catch (audioError) {
            console.error(audioError);
        }
    }
}


function updateParticipants(users) {
    const box = document.getElementById("participants");
    box.innerHTML = "";

    users.forEach(function (user) {
        const span = document.createElement("span");
        span.className = "participant";
        span.textContent = user.username;
        box.appendChild(span);
    });
}


async function createPeerConnection(targetSocketId, createOffer) {
    if (peers[targetSocketId]) {
        return peers[targetSocketId];
    }

    const pc = new RTCPeerConnection({
        iceServers: [
            { urls: "stun:stun.l.google.com:19302" }
        ]
    });

    peers[targetSocketId] = pc;

    if (localStream) {
        localStream.getTracks().forEach(function (track) {
            pc.addTrack(track, localStream);
        });
    }

    pc.onicecandidate = function (event) {
        if (event.candidate) {
            socket.emit("ice_candidate", {
                target: targetSocketId,
                candidate: event.candidate
            });
        }
    };

    pc.ontrack = function (event) {
        showRemoteVideo(targetSocketId, event.streams[0]);
    };

    pc.onconnectionstatechange = function () {
        if (
            pc.connectionState === "failed" ||
            pc.connectionState === "closed" ||
            pc.connectionState === "disconnected"
        ) {
            removeRemoteVideo(targetSocketId);
        }
    };

    if (createOffer) {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        socket.emit("webrtc_offer", {
            target: targetSocketId,
            offer: offer
        });
    }

    return pc;
}


async function handleOffer(data) {
    const pc = await createPeerConnection(data.from, false);

    await pc.setRemoteDescription(new RTCSessionDescription(data.offer));

    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);

    socket.emit("webrtc_answer", {
        target: data.from,
        answer: answer
    });
}


async function handleAnswer(data) {
    const pc = peers[data.from];

    if (pc) {
        await pc.setRemoteDescription(
            new RTCSessionDescription(data.answer)
        );
    }
}


async function handleIceCandidate(data) {
    const pc = peers[data.from];

    if (pc && data.candidate) {
        try {
            await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
        } catch (error) {
            console.error(error);
        }
    }
}


function showRemoteVideo(id, stream) {
    let box = document.getElementById("remote-" + id);

    if (!box) {
        box = document.createElement("div");
        box.className = "video-box";
        box.id = "remote-" + id;

        const video = document.createElement("video");
        video.autoplay = true;
        video.playsInline = true;

        const label = document.createElement("div");
        label.className = "video-label";
        label.textContent = "Participant";

        box.appendChild(video);
        box.appendChild(label);

        document.getElementById("videoGrid").appendChild(box);
    }

    const video = box.querySelector("video");

    if (video.srcObject !== stream) {
        video.srcObject = stream;
    }
}


function removeRemoteVideo(id) {
    const box = document.getElementById("remote-" + id);

    if (box) {
        box.remove();
    }

    if (peers[id]) {
        peers[id].close();
        delete peers[id];
    }
}


function requestConnections() {
    const ids = Object.keys(peers);

    // A lightweight local-network/demo mechanism:
    // the server's connection request requires a target Socket.IO ID.
    // Socket IDs are not displayed publicly, so this function is retained
    // for compatibility with a future participant-ID UI.
}


function toggleCamera() {
    if (!localStream) return;

    const track = localStream.getVideoTracks()[0];

    if (track) {
        track.enabled = !track.enabled;
        document.getElementById("cameraBtn").textContent =
            track.enabled ? "Camera Off" : "Camera On";
    }
}


function toggleMicrophone() {
    if (!localStream) return;

    const track = localStream.getAudioTracks()[0];

    if (track) {
        track.enabled = !track.enabled;
        document.getElementById("micBtn").textContent =
            track.enabled ? "Mute" : "Unmute";
    }
}


async function shareScreen() {
    try {
        screenStream = await navigator.mediaDevices.getDisplayMedia({
            video: true
        });

        const screenTrack = screenStream.getVideoTracks()[0];

        for (const id in peers) {
            const sender = peers[id].getSenders().find(function (s) {
                return s.track && s.track.kind === "video";
            });

            if (sender) {
                await sender.replaceTrack(screenTrack);
            }
        }

        document.getElementById("screenBtn").textContent = "Stop Sharing";

        screenTrack.onended = function () {
            stopScreenShare();
        };
    } catch (error) {
        console.error(error);
    }
}


async function stopScreenShare() {
    if (!screenStream) return;

    screenStream.getTracks().forEach(function (track) {
        track.stop();
    });

    if (localStream) {
        const cameraTrack = localStream.getVideoTracks()[0];

        if (cameraTrack) {
            for (const id in peers) {
                const sender = peers[id].getSenders().find(function (s) {
                    return s.track && s.track.kind === "video";
                });

                if (sender) {
                    await sender.replaceTrack(cameraTrack);
                }
            }
        }
    }

    screenStream = null;
    document.getElementById("screenBtn").textContent = "Share Screen";
}


function sendChat(event) {
    event.preventDefault();

    const input = document.getElementById("chatInput");
    const message = input.value.trim();

    if (!message || !socket) return;

    socket.emit("chat_message", {
        room: currentRoom,
        message: message
    });

    input.value = "";
}


function addChatMessage(username, message, time) {
    const container = document.getElementById("messages");

    const div = document.createElement("div");
    div.className = "message";

    const strong = document.createElement("strong");
    strong.textContent = username + ": ";

    const span = document.createElement("span");
    span.textContent = message;

    const small = document.createElement("small");
    small.textContent = " " + (time || "");

    div.appendChild(strong);
    div.appendChild(span);
    div.appendChild(small);

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}


function addSystemMessage(message) {
    const container = document.getElementById("messages");

    const div = document.createElement("div");
    div.className = "message system-message";
    div.textContent = message;

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}


// ---------------- Whiteboard ----------------

let canvas;
let ctx;
let drawing = false;
let lastX = 0;
let lastY = 0;

function setupWhiteboard() {
    canvas = document.getElementById("whiteboard");
    ctx = canvas.getContext("2d");

    resizeCanvas();

    window.addEventListener("resize", resizeCanvas);

    canvas.addEventListener("mousedown", startDraw);
    canvas.addEventListener("mousemove", draw);
    canvas.addEventListener("mouseup", stopDraw);
    canvas.addEventListener("mouseleave", stopDraw);

    canvas.addEventListener("touchstart", function (event) {
        event.preventDefault();
        const point = getTouchPoint(event);
        startDraw(point);
    }, { passive: false });

    canvas.addEventListener("touchmove", function (event) {
        event.preventDefault();
        const point = getTouchPoint(event);
        draw(point);
    }, { passive: false });

    canvas.addEventListener("touchend", function () {
        stopDraw();
    });
}


function resizeCanvas() {
    if (!canvas) return;

    const old = canvas.toDataURL();

    canvas.width = canvas.clientWidth;
    canvas.height = 400;

    const image = new Image();

    image.onload = function () {
        ctx.drawImage(image, 0, 0);
    };

    image.src = old;
}


function getPoint(event) {
    const rect = canvas.getBoundingClientRect();

    return {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top
    };
}


function getTouchPoint(event) {
    const touch = event.touches[0];
    const rect = canvas.getBoundingClientRect();

    return {
        x: touch.clientX - rect.left,
        y: touch.clientY - rect.top
    };
}


function startDraw(eventOrPoint) {
    drawing = true;

    const point = eventOrPoint.x !== undefined
        ? eventOrPoint
        : getPoint(eventOrPoint);

    lastX = point.x;
    lastY = point.y;
}


function draw(eventOrPoint) {
    if (!drawing) return;

    const point = eventOrPoint.x !== undefined
        ? eventOrPoint
        : getPoint(eventOrPoint);

    const color = document.getElementById("penColor").value;
    const size = Number(document.getElementById("penSize").value);

    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(point.x, point.y);
    ctx.strokeStyle = color;
    ctx.lineWidth = size;
    ctx.lineCap = "round";
    ctx.stroke();

    if (socket) {
        socket.emit("whiteboard_draw", {
            room: currentRoom,
            x: point.x,
            y: point.y,
            lastX: lastX,
            lastY: lastY,
            drawing: true,
            color: color,
            size: size
        });
    }

    lastX = point.x;
    lastY = point.y;
}


function stopDraw() {
    drawing = false;
}


function drawRemote(data) {
    if (!ctx) return;

    ctx.beginPath();
    ctx.moveTo(data.lastX, data.lastY);
    ctx.lineTo(data.x, data.y);
    ctx.strokeStyle = data.color || "#000000";
    ctx.lineWidth = data.size || 3;
    ctx.lineCap = "round";
    ctx.stroke();
}


function clearCanvas(sendToOthers) {
    if (!ctx || !canvas) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (sendToOthers && socket) {
        socket.emit("whiteboard_clear", {
            room: currentRoom
        });
    }
}


function sendFile(event) {
    event.preventDefault();

    const input = document.getElementById("fileInput");
    const file = input.files[0];

    if (!file) {
        document.getElementById("fileStatus").textContent =
            "Please select a file.";
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    document.getElementById("fileStatus").textContent =
        "Uploading...";

    fetch("/upload/" + currentRoom, {
        method: "POST",
        body: formData
    })
    .then(function (response) {
        return response.json();
    })
    .then(function (data) {
        if (data.success) {
            document.getElementById("fileStatus").innerHTML =
                'Uploaded: <a href="' + data.url +
                '" target="_blank">' + escapeHtml(data.filename) +
                '</a>';

            if (socket) {
                socket.emit("chat_message", {
                    room: currentRoom,
                    message: "Shared file: " + data.filename +
                             " - " + window.location.origin + data.url
                });
            }
        } else {
            document.getElementById("fileStatus").textContent =
                data.message || "Upload failed.";
        }
    })
    .catch(function (error) {
        console.error(error);
        document.getElementById("fileStatus").textContent =
            "Upload failed.";
    });
}


function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}


function leaveMeeting() {
    if (socket) {
        socket.emit("leave_meeting", {
            room: currentRoom
        });
    }

    if (localStream) {
        localStream.getTracks().forEach(function (track) {
            track.stop();
        });
    }

    window.location.href = "/dashboard";
}
