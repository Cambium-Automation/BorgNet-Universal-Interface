(() => {
  const panel = document.createElement('section');
  panel.id = 'voicevideoPanel'; panel.className = 'panel';
  panel.innerHTML = `<div class="panel-heading"><div><p class="eyebrow">VOICE & VIDEO</p><h1>Talk it through</h1><p>Record a voice turn or camera clip, or choose a recording to analyze.</p></div></div>
    <label>Input model<select id="vvModel" aria-label="Voice and video model"></select></label>
    <p class="caption">Enable a Gemini API connection to process recordings. Only Send recording uploads media to that provider. Provider quotas and data policies apply. Clips are not saved by BorgNet.</p>
    <div class="voice-controls"><label>Mode<select id="vvMode"><option value="conversation">Voice conversation</option><option value="transcribe">Dictation</option><option value="analyze">Video analysis</option></select></label>
    <button id="vvRecord" type="button">Record microphone</button><button id="vvCamera" type="button">Record camera + microphone</button><button id="vvStop" type="button" disabled>Stop recording</button>
    <label>Choose audio/video<input id="vvFile" type="file" accept="audio/webm,audio/mp4,audio/wav,audio/mpeg,audio/ogg,video/webm,video/mp4,video/quicktime"></label></div>
    <p class="caption">Up to 60 seconds per capture, 8 MB per file. Camera uses a live preview; the model receives the finished clip when you send it.</p>
    <video id="vvPreview" class="recording-preview" controls playsinline hidden></video>
    <label>Question or instruction<textarea id="vvPrompt" rows="2" maxlength="8000" placeholder="What would you like to know?"></textarea></label>
    <div class="voice-controls"><button id="vvSend" type="button" class="primary" disabled>Send recording</button><button id="vvClear" type="button">Clear recording</button>
    <button id="vvSpeak" type="button" role="switch" aria-checked="false">Speak replies</button><button id="vvSilence" type="button">Stop speaking</button></div>
    <p id="vvStatus" class="caption" role="status">Ready. Nothing is recording.</p>
    <div id="vvReplies" aria-live="polite"></div><button id="vvDraft" type="button" disabled>Use latest response in Workspace</button><button id="vvReset" type="button">New voice conversation</button>`;
  document.querySelector('#historyPanel').parentElement.append(panel);
  const nav = document.createElement('button'); nav.dataset.tab = 'voicevideo'; nav.textContent = 'Voice & video';
  nav.addEventListener('click', () => tab('voicevideo')); document.querySelector('.tabs').append(nav);
  const q = id => document.getElementById(id);
  let recorder, stream, timer, recording, previewURL, pending = false, acquiring = false, generation = 0;
  let history = [], latest = '', speak = false;
  const status = text => { q('vvStatus').textContent = text; };
  function controls() {
    const active = acquiring || recorder?.state === 'recording';
    q('vvRecord').disabled = q('vvCamera').disabled = q('vvFile').disabled = pending || active;
    q('vvStop').disabled = !active;
    q('vvSend').disabled = pending || active || !recording || !q('vvModel').value;
    q('vvClear').disabled = pending || active;
    q('vvModel').disabled = q('vvMode').disabled = pending || active;
    q('vvReset').disabled = pending || active;
  }
  function release() { clearTimeout(timer); stream?.getTracks().forEach(track => track.stop()); stream = null; }
  function stop() { generation++; acquiring = false; if (recorder?.state === 'recording') recorder.stop(); release(); controls(); }
  function clear() {
    recording = null;
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null; q('vvPreview').pause(); q('vvPreview').srcObject = null;
    q('vvPreview').removeAttribute('src'); q('vvPreview').load(); q('vvPreview').hidden = true; q('vvFile').value = ''; controls();
  }
  function use(blob) {
    clear();
    if (!blob.size || blob.size > 8000000) { status('Recording exceeds 8 MB or is empty. Choose a shorter clip.'); return; }
    recording = blob; previewURL = URL.createObjectURL(blob); q('vvPreview').src = previewURL;
    q('vvPreview').muted = false; q('vvPreview').hidden = false;
    status(`Ready to send · ${(blob.size / 1000000).toFixed(2)} MB. Review the recording first.`); controls();
  }
  async function record(camera) {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { status('Recording is unavailable here. Use a current browser or choose an audio/video file.'); return; }
    clear(); acquiring = true; const attempt = ++generation; controls(); status('Waiting for microphone/camera permission…');
    try {
      const captured = await navigator.mediaDevices.getUserMedia({audio: true, video: camera ? {width: {ideal:640}, height:{ideal:480}} : false});
      if (attempt !== generation) { captured.getTracks().forEach(track => track.stop()); return; }
      stream = captured; acquiring = false;
      const formats = camera ? ['video/webm;codecs=vp8,opus','video/mp4'] : ['audio/webm;codecs=opus','audio/mp4'];
      const mimeType = formats.find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw Error('No supported recording format. Choose an existing file instead.');
      recorder = new MediaRecorder(stream, {mimeType, videoBitsPerSecond:600000, audioBitsPerSecond:64000});
      const chunks = []; let size = 0;
      recorder.ondataavailable = event => { chunks.push(event.data); size += event.data.size; if (size > 7500000) stop(); };
      recorder.onstop = () => { release(); use(new Blob(chunks, {type:mimeType.split(';')[0]})); };
      recorder.onerror = () => { stop(); status('Recording failed. Try again or choose a file.'); };
      if (camera) { q('vvPreview').srcObject = stream; q('vvPreview').muted = true; q('vvPreview').hidden = false; await q('vvPreview').play(); }
      recorder.start(1000); timer = setTimeout(stop,60000); status('Recording · stop when you finish. Nothing has been uploaded.'); controls();
    } catch (error) { acquiring = false; release(); status(error.message || 'Microphone/camera access was not granted.'); controls(); }
  }
  async function models() {
    try { const previous = q('vvModel').value; const data = await api('/voice-video/models');
      q('vvModel').replaceChildren(new Option('Select an enabled Gemini connection',''));
      data.models.forEach(model => q('vvModel').add(new Option(model.label,model.id)));
      if (data.models.some(model => model.id === previous)) q('vvModel').value = previous;
      else if (data.models.length === 1) q('vvModel').value = data.models[0].id;
      controls();
    } catch (error) { status(error.message); }
  }
  q('vvRecord').onclick = () => record(false); q('vvCamera').onclick = () => {q('vvMode').value='analyze';record(true);};
  q('vvStop').onclick = stop; q('vvClear').onclick = () => {clear();status('Recording cleared.');};
  q('vvFile').onchange = () => {const file=q('vvFile').files[0];if(file)use(file);};
  q('vvModel').onchange = () => {history=[];controls();};
  q('vvSpeak').onclick = () => { speak=!speak; q('vvSpeak').setAttribute('aria-checked',String(speak)); if(!speak)window.speechSynthesis?.cancel(); };
  q('vvSilence').onclick = () => window.speechSynthesis?.cancel();
  q('vvReset').onclick = () => {history=[];latest='';q('vvReplies').replaceChildren();q('vvDraft').disabled=true;clear();window.speechSynthesis?.cancel();status('New voice conversation.');};
  q('vvDraft').onclick = () => {q('prompt').value=latest;tab('conversation');q('prompt').focus();};
  q('vvSend').onclick = async () => {
    if(pending || !recording)return;
    pending=true;controls();status('Sending recording to the selected provider…');
    try {
      const data = await new Promise((resolve,reject) => {const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(recording);});
      const reply = await api('/voice-video/respond',{connection:q('vvModel').value,mime:recording.type.split(';')[0],data,prompt:q('vvPrompt').value,mode:q('vvMode').value,history});
      latest=reply.text;history.push('Previous response: '+latest.slice(0,8000));history=history.slice(-6);
      const article=document.createElement('article');article.className='context-card';const heading=document.createElement('h2');heading.textContent=reply.model;const text=document.createElement('p');text.textContent=latest;article.append(heading,text);q('vvReplies').append(article);q('vvDraft').disabled=false;
      status('Response ready. Record your next turn or use the response in Workspace.');
      if(speak && window.speechSynthesis){window.speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(latest);const local=window.speechSynthesis.getVoices().find(voice=>voice.localService && voice.lang.startsWith(navigator.language.split('-')[0]));if(local){utterance.voice=local;window.speechSynthesis.speak(utterance);}else status('Response ready. No local speech voice is available on this device.');}
    }catch(error){status(error.message);}finally{pending=false;controls();}
  };
  window.addEventListener('borgnet-connections-changed',models);
  window.addEventListener('borgnet-tab-change',event=>{if(event.detail!=='voicevideo'){stop();window.speechSynthesis?.cancel();}});
  window.addEventListener('pagehide',()=>{stop();clear();window.speechSynthesis?.cancel();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  models();
})();
