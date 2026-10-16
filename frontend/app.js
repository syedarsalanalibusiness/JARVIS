const $ = (id) => document.getElementById(id);
const start = $("start"), stop = $("stop"), mic = $("mic"), send = $("send"), text = $("text");
const status = $("status"), state = $("state"), orb = $("orb"), messages = $("messages");
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let socket, stream, inputContext, processor, recognition, voiceTurnTimer, textRequestTimer, textRequestPending = false, browserVoice = false, isRecording = false, outputContext, nextAudioTime = 0, activeSources = [], receivedAudioThisTurn = false, activeMode = "voice";

function setStatus(value, live = false) { status.textContent = value; status.classList.toggle("on", live); state.textContent = live ? (activeMode === "text" ? "Text chat is ready." : "JARVIS is listening.") : "Ready when you are."; orb.classList.toggle("live", live); }
function addMessage(role, value) { const node = document.createElement("article"); node.className = `message ${role}`; node.innerHTML = `<b>${role === "user" ? "YOU" : "JARVIS"}</b>`; if (value) node.append(document.createTextNode(value)); messages.append(node); node.scrollIntoView({behavior:"smooth", block:"end"}); return node; }
function wsUrl() { return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/jarvis`; }
function bytesToBase64(bytes) { let binary = ""; const slice = 0x8000; for (let i=0;i<bytes.length;i+=slice) binary += String.fromCharCode(...bytes.subarray(i,i+slice)); return btoa(binary); }
function base64ToBytes(b64) { const binary = atob(b64), out = new Uint8Array(binary.length); for(let i=0;i<binary.length;i++) out[i]=binary.charCodeAt(i); return out; }

async function connect() {
  if (socket?.readyState === WebSocket.OPEN) return;
  socket = new WebSocket(wsUrl());
  socket.onopen = () => socket.send(JSON.stringify({type:"start", language:$("language").value}));
  socket.onmessage = async ({data}) => handle(JSON.parse(data));
  socket.onclose = () => { clearTimeout(voiceTurnTimer); setStatus("OFFLINE"); start.disabled=false; stop.disabled=true; mic.disabled=true; send.disabled=true; };
  socket.onerror = () => addMessage("assistant", "Connection error. Confirm the JARVIS server is running.");
}

function finishTextRequest() { clearTimeout(textRequestTimer); textRequestPending = false; send.disabled = socket?.readyState !== WebSocket.OPEN; }
function handle(event) {
  if (event.type === "ready") { activeMode=event.mode||"voice"; setStatus(activeMode === "text" ? "TEXT MODE" : "ONLINE", true); state.textContent=activeMode === "text" ? "Text chat is ready. Voice is unavailable right now." : "JARVIS is listening."; start.disabled=true; stop.disabled=false; mic.disabled=!event.voice_available&&!SpeechRecognition; send.disabled=false; if(activeMode === "text") addMessage("assistant", `${event.message ? `${event.message} ` : "Gemini Live voice is unavailable right now. "}Typed chat is ready on the lightweight text model.${SpeechRecognition ? " Browser speech input is also available." : " Use typing for now; this browser does not support speech recognition."}`); }
  if (event.type === "status") setStatus("LISTENING", true);
  if (event.type === "fallback_started") { setStatus("LOCAL BACKUP", true); state.textContent=event.message; }
  if (event.type === "error") { clearTimeout(voiceTurnTimer); finishTextRequest(); addMessage("assistant", event.message); setStatus("ERROR"); socket?.close(); }
  if (event.type === "chat_error") { clearTimeout(voiceTurnTimer); finishTextRequest(); addMessage("assistant", event.message); setStatus(activeMode === "text" ? "TEXT MODE" : "ONLINE", true); }
  if (event.type === "voice_unavailable") { clearTimeout(voiceTurnTimer); activeMode="text"; mic.disabled=!SpeechRecognition; setStatus("TEXT MODE", true); state.textContent="Voice is unavailable right now; typed chat is ready."; addMessage("assistant", `${event.message} Typed chat remains available.${SpeechRecognition ? " Browser speech input is enabled as a fallback." : " This browser has no speech-recognition fallback."}`); }
  if (event.type === "transcript") addMessage("user", event.text);
  if (event.type === "response") { finishTextRequest(); let last = messages.querySelector(".assistant:last-child"); if (!last?.dataset.streaming) { last = addMessage("assistant", ""); last.dataset.streaming="1"; } last.append(document.createTextNode(event.text)); if (event.preview && "speechSynthesis" in window) { speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(event.text); utterance.lang = $("language").value === "Urdu" ? "ur-PK" : "en-US"; speechSynthesis.speak(utterance); } }
  if (event.type === "turn_complete") { clearTimeout(voiceTurnTimer); finishTextRequest(); const last=messages.querySelector(".assistant:last-child"); if(last) delete last.dataset.streaming; if (!receivedAudioThisTurn && event.text) speakFallback(event.text); setStatus(activeMode === "text" ? "TEXT MODE" : "ONLINE", true); }
  if (event.type === "audio") { receivedAudioThisTurn = true; playPcm(event.data); }
  if (event.type === "interrupted") { stopPlayback(); setStatus("LISTENING", true); }
  if (event.type === "sources") showSources(event.items);
}

function showSources(items) { const box=$("sources"), list=$("source-list"); list.replaceChildren(); items.forEach(item => { const a=document.createElement("a"); a.className="source"; a.href=item.url||"#"; a.target="_blank"; a.rel="noopener"; a.textContent=item.title; const s=document.createElement("small"); s.textContent=item.snippet; a.append(s); list.append(a); }); box.hidden=!items.length; }

async function startRecording() {
  if (isRecording || socket?.readyState !== WebSocket.OPEN) return;
  if (activeMode === "text") {
    if (!SpeechRecognition) { addMessage("assistant", "Speech input is not supported by this browser. Please type your question."); return; }
    recognition = new SpeechRecognition();
    recognition.lang = $("language").value === "Urdu" ? "ur-PK" : "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    let heardSpeech = false;
    recognition.onstart = () => { isRecording=true; browserVoice=true; mic.classList.add("live"); state.textContent="Listening… release to send."; };
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map(result => result[0].transcript).join(" ").trim();
      if (!transcript) return;
      heardSpeech=true; addMessage("user", transcript); receivedAudioThisTurn=false;
      socket.send(JSON.stringify({type:"text",text:transcript,language:$("language").value}));
      state.textContent="JARVIS is thinking…";
    };
    recognition.onerror = (event) => { const detail=event.error==="network"?"The browser speech-to-text service could not connect to its network service. This is separate from microphone permission.":`Browser speech input failed (${event.error}).`; addMessage("assistant", `${detail} You can still type your question.`); };
    recognition.onend = () => { isRecording=false; browserVoice=false; mic.classList.remove("live"); if(!heardSpeech) state.textContent="No speech received. Hold the mic and try again, or type your question."; };
    try { recognition.start(); } catch(error) { isRecording=false; browserVoice=false; addMessage("assistant", `Could not start speech input: ${error.message}`); }
    return;
  }
  stopPlayback(); socket.send(JSON.stringify({type:"interrupt"}));
  stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true}});
  inputContext = new AudioContext(); const source=inputContext.createMediaStreamSource(stream); processor=inputContext.createScriptProcessor(4096,1,1);
  processor.onaudioprocess = (event) => { if (!isRecording) return; const input=event.inputBuffer.getChannelData(0); const target=Math.floor(input.length*16000/inputContext.sampleRate); const pcm=new Int16Array(target); for(let i=0;i<target;i++){const x=Math.max(-1,Math.min(1,input[Math.floor(i*inputContext.sampleRate/16000)]));pcm[i]=x<0?x*32768:x*32767;} socket.send(JSON.stringify({type:"audio",data:bytesToBase64(new Uint8Array(pcm.buffer))})); };
  source.connect(processor); processor.connect(inputContext.destination); isRecording=true; mic.classList.add("live"); state.textContent="Listening — release to send.";
}
function stopRecording() { if(!isRecording)return; if(browserVoice){recognition?.stop(); return;} isRecording=false; processor?.disconnect(); inputContext?.close(); stream?.getTracks().forEach(t=>t.stop()); mic.classList.remove("live"); socket?.send(JSON.stringify({type:"audio_end"})); state.textContent="JARVIS is thinking…"; clearTimeout(voiceTurnTimer); voiceTurnTimer=setTimeout(()=>{if(activeMode!=="voice")return;activeMode="text";mic.disabled=!SpeechRecognition;setStatus("TEXT MODE",true);state.textContent="No voice reply yet. Hold the mic to try browser speech, or type instead.";addMessage("assistant",`Gemini Live did not reply in time. You can retry with browser speech input or type your question.${SpeechRecognition?" The mic will now use browser speech-to-text.":" This browser does not support speech recognition."}`);},25000); }
function playPcm(data) { outputContext ||= new AudioContext({sampleRate:24000}); const bytes=base64ToBytes(data), pcm=new Int16Array(bytes.buffer), buffer=outputContext.createBuffer(1,pcm.length,24000), channel=buffer.getChannelData(0); for(let i=0;i<pcm.length;i++)channel[i]=pcm[i]/32768; const source=outputContext.createBufferSource(); source.buffer=buffer; source.connect(outputContext.destination); const when=Math.max(outputContext.currentTime,nextAudioTime); source.start(when); nextAudioTime=when+buffer.duration; activeSources.push(source); source.onended=()=>activeSources=activeSources.filter(x=>x!==source); }
function stopPlayback(){activeSources.forEach(s=>{try{s.stop()}catch{}});activeSources=[];nextAudioTime=0;}
function speakFallback(value) { if (!value || !("speechSynthesis" in window)) return; speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(value); utterance.lang = $("language").value === "Urdu" ? "ur-PK" : "en-US"; speechSynthesis.speak(utterance); }

start.onclick=connect; stop.onclick=()=>{ stopRecording(); stopPlayback(); socket?.send(JSON.stringify({type:"stop"})); socket?.close(); };
mic.onpointerdown=()=>startRecording().catch(e=>addMessage("assistant",`Microphone unavailable: ${e.message}`)); mic.onpointerup=stopRecording; mic.onpointerleave=stopRecording;
send.onclick=()=>{const value=text.value.trim();if(!value)return;if(textRequestPending){addMessage("assistant","Your last question is still waiting. Please wait for its reply before sending another.");return;} if(socket?.readyState!==WebSocket.OPEN){addMessage("assistant","Start JARVIS first, then ask your question.");return;} clearTimeout(voiceTurnTimer);receivedAudioThisTurn=false;textRequestPending=true;send.disabled=true;addMessage("user",value);socket.send(JSON.stringify({type:"text",text:value,language:$("language").value}));text.value="";state.textContent="JARVIS is thinking…";textRequestTimer=setTimeout(()=>{textRequestPending=false;send.disabled=socket?.readyState!==WebSocket.OPEN;state.textContent="No response yet.";addMessage("assistant","No reply arrived within 80 seconds. If the local model is running, check whether it finished loading; otherwise check the Gemini quota/network. You can safely try again now.");},80000);}; text.onkeydown=e=>{if(e.key==="Enter")send.click();};
