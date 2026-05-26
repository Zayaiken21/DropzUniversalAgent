/* frontend/static/dropz_live_realtime_webrtc.js
   Dropz live chat + WebRTC audio call + screen sharing client.
   This file intentionally lives outside Streamlit so live updates do not require Streamlit reruns.
*/
(function () {
    "use strict";

    const state = {
        config: null,
        ws: null,
        users: new Map(),
        knownMessages: new Set(),
        audioStream: null,
        screenStream: null,
        audioPeers: new Map(),
        screenPeers: new Map(),
        isInCall: false,
        isScreenSharing: false,
        reconnectTimer: null,
        pendingCandidates: new Map(),
    };

    const rtcConfig = {
        iceServers: [
            { urls: "stun:stun.l.google.com:19302" }
            // Production: add TURN here.
            // { urls: "turn:your-domain.com:3478", username: "user", credential: "pass" }
        ],
    };

    function el(id) {
        return document.getElementById(id);
    }

    function nowText() {
        const d = new Date();
        return d.toISOString().slice(0, 19).replace("T", " ");
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function chatScroll() {
        return el("chatScroll");
    }

    function distanceFromBottom() {
        const box = chatScroll();
        if (!box) return 0;
        return box.scrollHeight - box.scrollTop - box.clientHeight;
    }

    function userIsNearBottom() {
        return distanceFromBottom() < 160;
    }

    function updateJumpButton() {
        const btn = el("jumpBtn");
        const box = chatScroll();
        if (!btn || !box) return;
        btn.style.display = distanceFromBottom() > 180 ? "flex" : "none";
    }

    function scrollToLatest(smooth = true) {
        const box = chatScroll();
        if (!box) return;
        box.scrollTo({
            top: box.scrollHeight,
            behavior: smooth ? "smooth" : "auto",
        });
        sessionStorage.setItem("dropz_chat_user_scrolled", "false");
        setTimeout(updateJumpButton, 160);
    }

    function pinToLatestOnLoad() {
        const box = chatScroll();
        if (!box) return;
        requestAnimationFrame(() => {
            box.scrollTop = box.scrollHeight;
            updateJumpButton();
        });
    }

    function send(payload) {
        if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return false;
        state.ws.send(JSON.stringify({
            room_id: state.config.roomId,
            user_id: state.config.userId,
            user_name: state.config.userName,
            role: state.config.role,
            ...payload,
        }));
        return true;
    }

    function connectWebSocket() {
        if (!state.config || !state.config.wsUrl) return;
        if (state.ws && [WebSocket.OPEN, WebSocket.CONNECTING].includes(state.ws.readyState)) return;

        state.ws = new WebSocket(state.config.wsUrl);

        state.ws.onopen = () => {
            send({ type: "join" });
            if (state.isInCall) send({ type: "call-start" });
            if (state.isScreenSharing) send({ type: "screen_share_start" });
        };

        state.ws.onmessage = async (event) => {
            let msg = null;
            try { msg = JSON.parse(event.data); } catch { return; }
            await handleSignal(msg);
        };

        state.ws.onclose = () => {
            clearTimeout(state.reconnectTimer);
            state.reconnectTimer = setTimeout(connectWebSocket, 1200);
        };

        state.ws.onerror = () => {
            try { state.ws.close(); } catch {}
        };
    }

    async function handleSignal(msg) {
        const type = msg.type;

        if (type === "presence_snapshot") {
            state.users.clear();
            (msg.users || []).forEach((u) => {
                if (u.user_id && u.user_id !== state.config.userId) {
                    state.users.set(String(u.user_id), u);
                }
            });
            return;
        }

        if (type === "chat_message") {
            appendChatMessage(msg);
            return;
        }

        if (type === "call-start") {
            if (msg.user_id && msg.user_id !== state.config.userId) {
                state.users.set(String(msg.user_id), msg);
                appendCallNotice(msg);
                if (state.isInCall) {
                    await createAudioOffer(String(msg.user_id));
                }
            }
            return;
        }

        if (type === "call-end" || type === "hangup") {
            closeAudioPeer(String(msg.user_id || msg.target_id || ""));
            return;
        }

        if (type === "audio-offer") {
            await handleAudioOffer(msg);
            return;
        }

        if (type === "audio-answer") {
            await handleAudioAnswer(msg);
            return;
        }

        if (type === "audio-ice-candidate") {
            await handleIceCandidate(state.audioPeers, msg);
            return;
        }

        if (type === "screen_share_start") {
            if (msg.user_id && msg.user_id !== state.config.userId) {
                state.users.set(String(msg.user_id), msg);
                appendScreenShareNotice(msg);
            }
            return;
        }

        if (type === "screen_share_stop") {
            closeScreenPeer(String(msg.user_id || msg.target_id || ""));
            return;
        }

        if (type === "request-screen-view") {
            if (state.isScreenSharing && state.screenStream && msg.user_id !== state.config.userId) {
                await createScreenOffer(String(msg.user_id));
            }
            return;
        }

        if (type === "screen-offer") {
            await handleScreenOffer(msg);
            return;
        }

        if (type === "screen-answer") {
            await handleScreenAnswer(msg);
            return;
        }

        if (type === "screen-ice-candidate") {
            await handleIceCandidate(state.screenPeers, msg);
        }
    }

    function appendChatMessage(msg) {
        const box = chatScroll();
        if (!box) return;

        const id = String(msg.id || msg.message_id || `${msg.user_id || ""}-${msg.created_at || ""}-${msg.message || ""}`);
        if (state.knownMessages.has(id)) return;
        state.knownMessages.add(id);

        const wasNearBottom = userIsNearBottom();
        const row = document.createElement("div");
        row.className = `msg-row ${msg.user_name === state.config.userName ? "is-me" : "is-other"}`;
        row.dataset.messageId = id;

        const message = String(msg.message || "");
        let bodyHtml = "";
        if (message.toLowerCase().includes("started screen sharing")) {
            bodyHtml = `
                <div class="msg-text screen-share-msg" onclick="DropzLive.viewScreenShareDock('${escapeHtml(msg.user_name)}','${escapeHtml(msg.user_id)}')">
                    🖥️ ${escapeHtml(msg.user_name)} started screen sharing.
                    <button class="view-share-btn">View</button>
                </div>`;
        } else if (message.toLowerCase().includes("joined the call")) {
            bodyHtml = `
                <div class="msg-text call-msg" onclick="DropzLive.startAudioCall()">
                    📞 ${escapeHtml(msg.user_name)} joined the call.
                    <button class="view-share-btn">Join</button>
                </div>`;
        } else {
            bodyHtml = `<div class="msg-text">${escapeHtml(message).replaceAll("\n", "<br>")}</div>`;
        }

        row.innerHTML = `
            <div class="msg-bubble">
                <div class="msg-meta">
                    <span class="msg-user">${escapeHtml(msg.user_name || "User")}</span>
                    <span class="msg-role">${escapeHtml(msg.role || "client")}</span>
                    <span class="msg-time">${escapeHtml(msg.created_at || nowText())}</span>
                </div>
                ${bodyHtml}
            </div>`;

        box.appendChild(row);
        if (wasNearBottom) scrollToLatest(false);
        updateJumpButton();
    }

    function appendScreenShareNotice(msg) {
        appendChatMessage({
            ...msg,
            message: `🖥️ ${msg.user_name || "User"} started screen sharing.`,
            created_at: msg.created_at || nowText(),
        });
    }

    function appendCallNotice(msg) {
        appendChatMessage({
            ...msg,
            message: `📞 ${msg.user_name || "User"} joined the call.`,
            created_at: msg.created_at || nowText(),
        });
    }

    function sendTextMessage() {
        const input = el("liveMessageInput");
        if (!input) return;
        const text = input.value.trim();
        if (!text) return;

        const createdAt = nowText();
        const payload = {
            type: "chat_message",
            message: text,
            media_path: null,
            media_type: null,
            created_at: createdAt,
        };

        // Optimistic append for sender; server broadcast will be deduped by content/time.
        appendChatMessage({
            ...payload,
            user_id: state.config.userId,
            user_name: state.config.userName,
            role: state.config.role,
        });

        send(payload);
        input.value = "";
        scrollToLatest(false);
    }

    function createPeer(peerMap, targetId, kind) {
        const pc = new RTCPeerConnection(rtcConfig);
        peerMap.set(targetId, pc);

        pc.onicecandidate = (event) => {
            if (!event.candidate) return;
            send({
                type: kind === "audio" ? "audio-ice-candidate" : "screen-ice-candidate",
                target_id: targetId,
                candidate: event.candidate,
            });
        };

        pc.onconnectionstatechange = () => {
            if (["closed", "failed", "disconnected"].includes(pc.connectionState)) {
                peerMap.delete(targetId);
            }
        };

        return pc;
    }

    async function ensureAudioStream() {
        if (state.audioStream) return state.audioStream;
        state.audioStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
            video: false,
        });
        return state.audioStream;
    }

    function openCallDock() {
        const dock = el("callDock");
        if (dock) dock.classList.add("active");
    }

    async function startAudioCall() {
        openCallDock();
        const status = el("callStatus");
        const msg = el("callMessage");
        try {
            const stream = await ensureAudioStream();
            state.isInCall = true;

            if (status) status.innerText = "Connected";
            if (msg) msg.innerText = "Microphone connected. Waiting for other users...";

            send({ type: "call-start", created_at: nowText() });
            appendCallNotice({
                user_id: state.config.userId,
                user_name: state.config.userName,
                role: state.config.role,
                created_at: nowText(),
            });

            for (const [uid] of state.users) {
                await createAudioOffer(uid);
            }

            startMicMeter(stream);
        } catch (err) {
            if (status) status.innerText = "Permission denied";
            if (msg) msg.innerText = "Microphone access was denied or unavailable.";
        }
    }

    function stopAudioCall() {
        state.isInCall = false;
        send({ type: "call-end" });

        for (const [uid, pc] of state.audioPeers) {
            try { pc.close(); } catch {}
        }
        state.audioPeers.clear();

        if (state.audioStream) {
            state.audioStream.getTracks().forEach((t) => t.stop());
            state.audioStream = null;
        }

        const dock = el("callDock");
        if (dock) dock.classList.remove("active");

        const bank = el("remoteAudioBank");
        if (bank) bank.innerHTML = "";
    }

    function closeAudioPeer(uid) {
        const pc = state.audioPeers.get(uid);
        if (pc) {
            try { pc.close(); } catch {}
        }
        state.audioPeers.delete(uid);
        const audio = el(`remoteAudio_${uid}`);
        if (audio) audio.remove();
    }

    async function createAudioOffer(targetId) {
        if (!targetId || targetId === state.config.userId) return;
        const stream = await ensureAudioStream();
        const pc = createPeer(state.audioPeers, targetId, "audio");
        stream.getTracks().forEach((track) => pc.addTrack(track, stream));

        pc.ontrack = (event) => attachRemoteAudio(targetId, event.streams[0]);

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        send({
            type: "audio-offer",
            target_id: targetId,
            sdp: offer.sdp,
        });
    }

    async function handleAudioOffer(msg) {
        const fromId = String(msg.user_id);
        const stream = state.isInCall ? await ensureAudioStream() : null;
        const pc = createPeer(state.audioPeers, fromId, "audio");

        if (stream) {
            stream.getTracks().forEach((track) => pc.addTrack(track, stream));
        }

        pc.ontrack = (event) => attachRemoteAudio(fromId, event.streams[0]);

        await pc.setRemoteDescription({ type: "offer", sdp: msg.sdp });
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        send({
            type: "audio-answer",
            target_id: fromId,
            sdp: answer.sdp,
        });
    }

    async function handleAudioAnswer(msg) {
        const pc = state.audioPeers.get(String(msg.user_id));
        if (!pc) return;
        await pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
    }

    function attachRemoteAudio(uid, stream) {
        if (!stream) return;
        const bank = el("remoteAudioBank");
        if (!bank) return;
        let audio = el(`remoteAudio_${uid}`);
        if (!audio) {
            audio = document.createElement("audio");
            audio.id = `remoteAudio_${uid}`;
            audio.autoplay = true;
            audio.controls = false;
            audio.playsInline = true;
            bank.appendChild(audio);
        }
        audio.srcObject = stream;
        audio.volume = 1.0;
        audio.play().catch(() => {});
        const msg = el("callMessage");
        if (msg) msg.innerText = "Live call active. Remote audio connected.";
    }

    function startMicMeter(stream) {
        try {
            const meter = el("callMeter");
            if (!meter || !window.AudioContext) return;
            const ctx = new AudioContext();
            const src = ctx.createMediaStreamSource(stream);
            const analyser = ctx.createAnalyser();
            src.connect(analyser);
            const data = new Uint8Array(analyser.frequencyBinCount);
            const tick = () => {
                if (!state.audioStream) {
                    try { ctx.close(); } catch {}
                    return;
                }
                analyser.getByteFrequencyData(data);
                const avg = data.reduce((a, b) => a + b, 0) / data.length;
                meter.style.width = `${Math.min(100, Math.max(8, avg))}%`;
                requestAnimationFrame(tick);
            };
            tick();
        } catch {}
    }

    function openScreenShareDock() {
        const dock = el("screenShareDock");
        if (dock) dock.classList.add("active");
        const placeholder = el("screenSharePlaceholder");
        if (placeholder) {
            placeholder.style.display = "flex";
            placeholder.innerHTML = "<div class='screen-icon'>🖥️</div><div>Click ▶ to start real screen sharing.</div><small>Your browser will open the system picker.</small>";
        }
    }

    function viewScreenShareDock(userName, targetUserId) {
        const dock = el("screenShareDock");
        const owner = document.querySelector(".screen-owner");
        const placeholder = el("screenSharePlaceholder");
        if (dock) dock.classList.add("active");
        if (owner) owner.innerText = userName || "User";
        if (placeholder) {
            placeholder.style.display = "flex";
            placeholder.innerHTML = "<div class='screen-icon'>🖥️</div><div>Waiting for live screen stream...</div><small>Connecting to sharer.</small>";
        }

        if (targetUserId && targetUserId !== state.config.userId) {
            send({
                type: "request-screen-view",
                target_id: String(targetUserId),
            });
        }
    }

    async function startScreenShare() {
        openScreenShareDock();

        const video = el("screenShareVideo");
        const placeholder = el("screenSharePlaceholder");

        if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
            if (placeholder) {
                placeholder.innerHTML = "<div class='screen-icon'>⚠️</div><div>Screen sharing is not supported in this browser.</div><small>Use Chrome, Edge, Firefox, or Safari on HTTPS/localhost.</small>";
            }
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getDisplayMedia({
                video: { cursor: "always" },
                audio: false,
            });

            state.screenStream = stream;
            state.isScreenSharing = true;

            if (video) {
                video.srcObject = stream;
                video.muted = true;
                video.playsInline = true;
                video.style.display = "block";
                await video.play().catch(() => {});
            }

            if (placeholder) {
                placeholder.style.display = "none";
                placeholder.innerHTML = "";
            }

            send({ type: "screen_share_start", created_at: nowText() });
            appendScreenShareNotice({
                user_id: state.config.userId,
                user_name: state.config.userName,
                role: state.config.role,
                created_at: nowText(),
            });

            for (const [uid] of state.users) {
                await createScreenOffer(uid);
            }

            stream.getVideoTracks()[0].addEventListener("ended", () => {
                stopScreenShare();
            });
        } catch (err) {
            if (placeholder) {
                placeholder.style.display = "flex";
                placeholder.innerHTML = "<div class='screen-icon'>🖥️</div><div>Screen share cancelled.</div><small>Click ▶ and select a screen/window/tab to share.</small>";
            }
        }
    }

    async function createScreenOffer(targetId) {
        if (!targetId || targetId === state.config.userId || !state.screenStream) return;
        const pc = createPeer(state.screenPeers, targetId, "screen");
        state.screenStream.getTracks().forEach((track) => pc.addTrack(track, state.screenStream));

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        send({
            type: "screen-offer",
            target_id: targetId,
            sdp: offer.sdp,
        });
    }

    async function handleScreenOffer(msg) {
        const fromId = String(msg.user_id);
        const pc = createPeer(state.screenPeers, fromId, "screen");

        pc.ontrack = (event) => {
            const video = el("screenShareVideo");
            const placeholder = el("screenSharePlaceholder");
            openScreenShareDock();
            if (video) {
                video.srcObject = event.streams[0];
                video.muted = true;
                video.playsInline = true;
                video.style.display = "block";
                video.play().catch(() => {});
            }
            if (placeholder) {
                placeholder.style.display = "none";
            }
        };

        await pc.setRemoteDescription({ type: "offer", sdp: msg.sdp });
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        send({
            type: "screen-answer",
            target_id: fromId,
            sdp: answer.sdp,
        });
    }

    async function handleScreenAnswer(msg) {
        const pc = state.screenPeers.get(String(msg.user_id));
        if (!pc) return;
        await pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
    }

    async function handleIceCandidate(peerMap, msg) {
        const uid = String(msg.user_id);
        const pc = peerMap.get(uid);
        if (!pc || !msg.candidate) return;
        try {
            await pc.addIceCandidate(msg.candidate);
        } catch {}
    }

    function stopScreenShare() {
        state.isScreenSharing = false;
        send({ type: "screen_share_stop" });

        for (const [, pc] of state.screenPeers) {
            try { pc.close(); } catch {}
        }
        state.screenPeers.clear();

        if (state.screenStream) {
            state.screenStream.getTracks().forEach((t) => t.stop());
            state.screenStream = null;
        }

        const video = el("screenShareVideo");
        const placeholder = el("screenSharePlaceholder");
        const dock = el("screenShareDock");

        if (video) {
            video.pause();
            video.srcObject = null;
            video.style.display = "none";
        }
        if (placeholder) {
            placeholder.style.display = "flex";
            placeholder.innerHTML = "<div class='screen-icon'>🖥️</div><div>Screen share stopped.</div><small>Use 🖥️ then ▶ to start again.</small>";
        }
        if (dock) {
            dock.classList.remove("fullscreen");
        }
    }

    function closeFloatingPanels(closeCall = true) {
        const screenDock = el("screenShareDock");
        const callDock = el("callDock");
        if (screenDock) screenDock.classList.remove("fullscreen");
        if (closeCall && callDock && !state.isInCall) callDock.classList.remove("active");
    }

    function toggleScreenFullscreen() {
        const dock = el("screenShareDock");
        if (dock) dock.classList.toggle("fullscreen");
    }

    function init(config) {
        state.config = config;
        (config.knownMessageIds || []).forEach((id) => state.knownMessages.add(String(id)));

        const box = chatScroll();
        if (box) {
            box.addEventListener("scroll", updateJumpButton);
        }

        const input = el("liveMessageInput");
        if (input) {
            input.addEventListener("keydown", (event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendTextMessage();
                }
            });
        }

        connectWebSocket();
        pinToLatestOnLoad();
    }

    window.DropzLive = {
        init,
        sendTextMessage,
        scrollToLatest,
        updateJumpButton,
        openCallDock,
        startAudioCall,
        stopAudioCall,
        openScreenShareDock,
        viewScreenShareDock,
        startScreenShare,
        stopScreenShare,
        toggleScreenFullscreen,
        closeFloatingPanels,
    };
})();
