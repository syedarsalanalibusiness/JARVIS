const $ = (id) => document.getElementById(id);
const start = $("start"), stop = $("stop"), mic = $("mic"), send = $("send"), text = $("text");
const status = $("status"), state = $("state"), orb = $("orb"), messages = $("messages");
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let socket, stream, inputContext, processor, recognition, textRecorder, textChunks = [], recordingTimer, voiceTurnTimer, textRequestTimer, textRequestPending = false, browserVoice = false, isRecording = false, outputContext, nextAudioTime = 0, activeSources = [], receivedAudioThisTurn = false, activeMode = "voice";
let httpTextFallback = false, userStopped = false, connectionErrorShown = false;
const textSessionId = crypto.randomUUID();
function canRecordTextVoice() { return !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder); }

function setStatus(value, live = false) { status.textContent = value; status.classList.toggle("on", live); state.textContent = live ? (activeMode === "text" ? "Text chat is ready." : "JARVIS is listening.") : "Ready when you are."; orb.classList.toggle("live", live); }
function addMessage(role, value) { const node = document.createElement("article"); node.className = `message ${role}`; node.innerHTML = `<b>${role === "user" ? "YOU" : "JARVIS"}</b>`; if (value) node.append(document.createTextNode(value)); messages.append(node); node.scrollIntoView({behavior:"smooth", block:"end"}); return node; }
function wsUrl() { return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/jarvis`; }
function bytesToBase64(bytes) { let binary = ""; const slice = 0x8000; for (let i=0;i<bytes.length;i+=slice) binary += String.fromCharCode(...bytes.subarray(i,i+slice)); return btoa(binary); }
function base64ToBytes(b64) { const binary = atob(b64), out = new Uint8Array(binary.length); for(let i=0;i<binary.length;i++) out[i]=binary.charCodeAt(i); return out; }

function enableHttpTextMode() {
  activeMode = "text"; httpTextFallback = true;
  setStatus("TEXT MODE", true);
  state.textContent = "Live connection nahi bani. Aap text mein sawaal bhej sakte hain.";
  start.disabled = false; stop.disabled = true; mic.disabled = !canRecordTextVoice(); send.disabled = false;
}

async function sendTextQuestion(value) {
  if (!value) return;
  if (textRequestPending) { addMessage("assistant", "Pichhla sawaal abhi process ho raha hai; jawab aane dein."); return; }
  if (value.length > 4000) { addMessage("assistant", "Sawaal 4,000 characters se chhota rakhein."); return; }

  clearTimeout(voiceTurnTimer);
  receivedAudioThisTurn = false;
  addMessage("user", value);
  text.value = "";
  textRequestPending = true;
  send.disabled = true;
  state.textContent = "JARVIS jawab tayyar kar raha hai…";

  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({type:"text", text:value, language:$("language").value}));
    textRequestTimer = setTimeout(() => {
      if (!textRequestPending) return;
      textRequestPending = false; send.disabled = false;
      state.textContent = "Jawab abhi nahi aaya. Dobara koshish kar sakte hain.";
      addMessage("assistant", "JARVIS se 80 seconds mein jawab nahi aaya. API key, quota, ya cloud logs check karein.");
    }, 80000);
    return;
  }

  httpTextFallback = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({text:value, language:$("language").value, session_id:textSessionId})
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`);
    addMessage("assistant", result.text || "JARVIS ne khaali jawab bheja.");
    if (Array.isArray(result.sources)) showSources(result.sources);
    speakFallback(result.text);
  } catch (error) {
    addMessage("assistant", `Chat request failed: ${error.message}`);
  } finally {
    clearTimeout(textRequestTimer);
    textRequestPending = false;
    send.disabled = false;
    setStatus("TEXT MODE", true);
  }
}

async function connect() {
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
  httpTextFallback = false; userStopped = false; connectionErrorShown = false; activeMode = "voice";
  setStatus("CONNECTING"); start.disabled = true; stop.disabled = true; mic.disabled = true; send.disabled = true;
  try {
    const current = new WebSocket(wsUrl()); socket = current;
    current.onopen = () => { if (socket === current) current.send(JSON.stringify({type:"start", language:$("language").value})); };
    current.onmessage = ({data}) => {
      try { handle(JSON.parse(data)); }
      catch { if (!connectionErrorShown) { connectionErrorShown = true; addMessage("assistant", "JARVIS ka server response samajh nahi aaya."); } }
    };
    current.onerror = () => {
      if (socket !== current || userStopped) return;
      if (!connectionErrorShown) {
        connectionErrorShown = true;
        addMessage("assistant", "Live connection nahi bani; text chat ke liye cloud HTTP connection try kar raha hoon.");
      }
      enableHttpTextMode();
    };
    current.onclose = () => {
      if (socket !== current) return;
      clearTimeout(voiceTurnTimer);
      if (userStopped) {
        setStatus("OFFLINE"); start.disabled = false; stop.disabled = true; mic.disabled = true; send.disabled = true;
        return;
      }
      if (!httpTextFallback && !connectionErrorShown) {
        connectionErrorShown = true;
        addMessage("assistant", "Live connection band ho gayi; text chat ab cloud HTTP se chalegi.");
      }
      enableHttpTextMode();
    };
  } catch (error) {
    addMessage("assistant", `Live connection nahi bani: ${error.message}`);
    enableHttpTextMode();
  }
}

function finishTextRequest() { clearTimeout(textRequestTimer); textRequestPending = false; send.disabled = httpTextFallback || socket?.readyState === WebSocket.OPEN ? false : true; }
function handle(event) {
  if (event.type === "ready") { activeMode=event.mode||"voice"; setStatus(activeMode === "text" ? "TEXT MODE" : "ONLINE", true); state.textContent=activeMode === "text" ? "Text chat and recorded voice input are ready." : "JARVIS is listening."; start.disabled=true; stop.disabled=false; mic.disabled=!event.voice_available&&!canRecordTextVoice(); send.disabled=false; if(activeMode === "text") addMessage("assistant", `${event.message ? `${event.message} ` : ""}Typed chat uses Groq. Hold the mic to record a question for Groq Whisper.${canRecordTextVoice() ? "" : " This browser cannot record audio; please type."}`); }
  if (event.type === "status") setStatus("LISTENING", true);
  if (event.type === "interaction_status") {
    if (event.status === "IN_PROGRESS") state.textContent = "JARVIS is thinking through your request…";
    if (event.status === "IDLE") state.textContent = "JARVIS is listening.";
  }
  if (event.type === "fallback_started") { setStatus("LOCAL BACKUP", true); state.textContent=event.message; }
  if (event.type === "error") { clearTimeout(voiceTurnTimer); finishTextRequest(); addMessage("assistant", event.message); setStatus("ERROR"); socket?.close(); }
  if (event.type === "chat_error") { clearTimeout(voiceTurnTimer); finishTextRequest(); addMessage("assistant", event.message); setStatus(activeMode === "text" ? "TEXT MODE" : "ONLINE", true); }
  if (event.type === "voice_unavailable") { clearTimeout(voiceTurnTimer); activeMode="text"; mic.disabled=!canRecordTextVoice(); setStatus("TEXT MODE", true); state.textContent="Voice is unavailable right now; typed chat is ready."; addMessage("assistant", `${event.message} Typed chat remains available.${canRecordTextVoice() ? " Hold the mic to record a question for Groq Whisper." : " This browser cannot record audio; please type."}`); }
  if (event.type === "transcript") addMessage("user", event.text);
  if (event.type === "response") { finishTextRequest(); let last = messages.querySelector(".assistant:last-child"); if (!last?.dataset.streaming) { last = addMessage("assistant", ""); last.dataset.streaming="1"; } last.append(document.createTextNode(event.text)); if (event.preview && "speechSynthesis" in window) { speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(event.text); const selected=$("language").value; utterance.lang=selected==="Urdu"||selected==="Roman Urdu"?"ur-PK":selected==="English"?"en-US":/[\u0900-\u097F]/.test(value)?"hi-IN":/[\u0600-\u06FF]/.test(value)?"ur-PK":"en-US"; speechSynthesis.speak(utterance); } }
  if (event.type === "turn_complete") { clearTimeout(voiceTurnTimer); finishTextRequest(); const last=messages.querySelector(".assistant:last-child"); if(last) delete last.dataset.streaming; if (!receivedAudioThisTurn && event.text) speakFallback(event.text); setStatus(activeMode === "text" ? "TEXT MODE" : "ONLINE", true); }
  if (event.type === "audio") { receivedAudioThisTurn = true; playPcm(event.data); }
  if (event.type === "interrupted") { stopPlayback(); setStatus("LISTENING", true); }
  if (event.type === "sources") showSources(event.items);
}

function showSources(items) { const box=$("sources"), list=$("source-list"); list.replaceChildren(); items.forEach(item => { const a=document.createElement("a"); a.className="source"; a.href=item.url||"#"; a.target="_blank"; a.rel="noopener"; a.textContent=item.title; const s=document.createElement("small"); s.textContent=item.snippet; a.append(s); list.append(a); }); box.hidden=!items.length; }

async function startRecording() {
  if (isRecording) return;
  if (activeMode === "text") {
    if (!canRecordTextVoice()) { addMessage("assistant", "This browser cannot record audio. Please type your question."); return; }
    stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true}});
    textChunks = [];
    const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? {mimeType:"audio/webm;codecs=opus"} : undefined;
    textRecorder = new MediaRecorder(stream, options);
    textRecorder.ondataavailable = (event) => { if (event.data.size) textChunks.push(event.data); };
    textRecorder.onerror = () => addMessage("assistant", "Recording failed. Check microphone permission and try again.");
    textRecorder.onstop = async () => {
      isRecording = false; mic.classList.remove("live");
      stream?.getTracks().forEach(track => track.stop()); stream = null;
      state.textContent = "Transcribing your voice question…";
      try {
        const blob = new Blob(textChunks, {type:textRecorder.mimeType || "audio/webm"});
        const response = await fetch("/api/transcribe", {method:"POST", headers:{"Content-Type":blob.type || "audio/webm"}, body:blob});
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || `Transcription failed (${response.status})`);
        if (!result.text) throw new Error("No speech was detected. Hold the mic and try again.");
        await sendTextQuestion(result.text.trim());
      } catch (error) {
        addMessage("assistant", `Voice question failed: ${error.message}. You can still type.`);
        setStatus("TEXT MODE", true);
      }
    };
    textRecorder.start(); isRecording = true; mic.classList.add("live");
    state.textContent = "Listening… release the mic to send your question.";
    recordingTimer = setTimeout(() => { if (isRecording && textRecorder?.state === "recording") { addMessage("assistant", "Recording limit is 30 seconds; sending it now."); stopRecording(); } }, 30000);
    return;
  }
  if (socket?.readyState !== WebSocket.OPEN) { addMessage("assistant", "Live voice is unavailable. Type your question or reconnect."); return; }
  stopPlayback(); socket.send(JSON.stringify({type:"interrupt"}));
  stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true}});
  inputContext = new AudioContext(); const source=inputContext.createMediaStreamSource(stream); processor=inputContext.createScriptProcessor(4096,1,1);
  processor.onaudioprocess = (event) => { if (!isRecording) return; const input=event.inputBuffer.getChannelData(0); const target=Math.floor(input.length*16000/inputContext.sampleRate); const pcm=new Int16Array(target); for(let i=0;i<target;i++){const x=Math.max(-1,Math.min(1,input[Math.floor(i*inputContext.sampleRate/16000)]));pcm[i]=x<0?x*32768:x*32767;} socket.send(JSON.stringify({type:"audio",data:bytesToBase64(new Uint8Array(pcm.buffer))})); };
  source.connect(processor); processor.connect(inputContext.destination); isRecording=true; mic.classList.add("live"); state.textContent="Listening — release to send.";
}
function stopRecording() { if(!isRecording)return; if(activeMode==="text"){isRecording=false;clearTimeout(recordingTimer);if(textRecorder?.state==="recording")textRecorder.stop();return;} if(browserVoice){recognition?.stop(); return;} isRecording=false; processor?.disconnect(); inputContext?.close(); stream?.getTracks().forEach(t=>t.stop()); mic.classList.remove("live"); socket?.send(JSON.stringify({type:"audio_end"})); state.textContent="JARVIS is thinking…"; clearTimeout(voiceTurnTimer); voiceTurnTimer=setTimeout(()=>{if(activeMode!=="voice")return;activeMode="text";mic.disabled=!canRecordTextVoice();setStatus("TEXT MODE",true);state.textContent="No live voice reply. Use the recorded mic or type.";addMessage("assistant",`Live voice did not reply in time. You can record a voice question for Groq Whisper or type it.${canRecordTextVoice()?"":" This browser cannot record audio."}`);},25000); }
function playPcm(data) { outputContext ||= new AudioContext({sampleRate:24000}); const bytes=base64ToBytes(data), pcm=new Int16Array(bytes.buffer), buffer=outputContext.createBuffer(1,pcm.length,24000), channel=buffer.getChannelData(0); for(let i=0;i<pcm.length;i++)channel[i]=pcm[i]/32768; const source=outputContext.createBufferSource(); source.buffer=buffer; source.connect(outputContext.destination); const when=Math.max(outputContext.currentTime,nextAudioTime); source.start(when); nextAudioTime=when+buffer.duration; activeSources.push(source); source.onended=()=>activeSources=activeSources.filter(x=>x!==source); }
function stopPlayback(){activeSources.forEach(s=>{try{s.stop()}catch{}});activeSources=[];nextAudioTime=0;}
function speakFallback(value) { if (!value || !("speechSynthesis" in window)) return; speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(value); const selected=$("language").value; utterance.lang=selected==="Urdu"||selected==="Roman Urdu"?"ur-PK":"en-US"; speechSynthesis.speak(utterance); }

start.onclick=connect; stop.onclick=()=>{ userStopped=true; httpTextFallback=false; stopRecording(); stopPlayback(); socket?.send(JSON.stringify({type:"stop"})); socket?.close(); };
mic.onpointerdown=()=>startRecording().catch(e=>addMessage("assistant",`Microphone unavailable: ${e.message}`)); mic.onpointerup=stopRecording; mic.onpointerleave=stopRecording;
send.onclick=()=>{const value=text.value.trim();if(value)sendTextQuestion(value);}; text.onkeydown=e=>{if(e.key==="Enter")send.click();};
