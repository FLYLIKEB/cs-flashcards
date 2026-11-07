(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const audio = $('lessonAudio');
  let codeLinks = [], motion = [], lessons = null, media = null, loading = null, problemId = 0, sceneIndex = 0;
  let visible = true, playing = false, ticket = 0, callbacks = {}, retryTimer = null;
  const subtitleKey = 'csCodingLessonSubtitles:v1';
  let subtitlesEnabled = true;
  try { subtitlesEnabled = localStorage.getItem(subtitleKey) !== 'off'; } catch (_) { /* Optional display preference. */ }
  function updateSubtitle() {
    const scene = lessons?.find(item => item.id === problemId)?.scenes[sceneIndex];
    const sound = media?.find(item => item.id === problemId)?.scenes[sceneIndex];
    const cues = sound?.cues;
    const duration = Number.isFinite(audio.duration) ? audio.duration : sound?.duration || 0;
    const time = audio.currentTime || 0;
    const clock = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
    $('lessonSeek').max = duration || 1;
    $('lessonSeek').value = time;
    $('lessonSeek').disabled = !sound || !audio.readyState;
    $('lessonSeek').setAttribute('aria-valuetext', `${clock(time)} / ${clock(duration)}`);
    $('lessonClock').textContent = `${clock(time)} / ${clock(duration)}`;
    let cueIndex = 0;
    let text = scene?.narration || '';
    if (Array.isArray(cues) && cues.length) {
      const time = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
      const cue = cues.find(item => time >= item.start && time < item.end) ||
        (time >= cues[cues.length - 1].end ? cues[cues.length - 1] : cues[0]);
      text = cue.text; cueIndex = cues.indexOf(cue);
    }
    window.CodingCode.update(sceneIndex, cueIndex);
    if ($('lessonSubtitle').textContent !== text) $('lessonSubtitle').textContent = text;
    $('lessonSubtitleBox').hidden = !subtitlesEnabled || !scene || !sound;
    $('lessonCaption').hidden = subtitlesEnabled && !!scene && !!sound;
    $('lessonSubtitles').setAttribute('aria-pressed', String(subtitlesEnabled));
    $('lessonSubtitles').setAttribute('aria-label', subtitlesEnabled ? '자막 끄기' : '자막 켜기');
    $('lessonSubtitles').textContent = subtitlesEnabled ? '자막 켜짐' : '자막 꺼짐';
  }
  window.CodingMotion.onTick(updateSubtitle);
  $('lessonSeek').oninput = () => {
    if (Number.isFinite(audio.duration)) audio.currentTime = Math.min(audio.duration, Number($('lessonSeek').value));
    updateSubtitle();
  };
  $('lessonSubtitles').onclick = () => {
    subtitlesEnabled = !subtitlesEnabled;
    try { localStorage.setItem(subtitleKey, subtitlesEnabled ? 'on' : 'off'); } catch (_) { /* Keep this tab usable. */ }
    updateSubtitle();
  };
  ['play', 'pause', 'timeupdate', 'seeked', 'loadedmetadata', 'ratechange', 'ended'].forEach(event => audio.addEventListener(event, updateSubtitle));
  function currentReady() { return !!lessons?.find(item => item.id === problemId) && !!media?.find(item => item.id === problemId); }
  function status(message) { $('lessonStatus').textContent = message; $('lessonStatus').classList.toggle('is-error', /못|실패|오류/.test(message)); }
  function controls() {
    const lesson = lessons?.find(item => item.id === problemId);
    const ready = !!lesson && !!media?.find(item => item.id === problemId);
    $('lessonPlay').disabled = !visible || (!ready && !!loading);
    $('lessonPlay').textContent = playing ? '일시정지' : ready ? '설명 재생' : loading ? '음성 준비 중' : '강의 다시 불러오기';
    $('lessonPlay').classList.toggle('is-playing', playing);
    $('lessonPrev').disabled = !ready || sceneIndex === 0;
    $('lessonNext').disabled = !ready || sceneIndex === lesson.scenes.length - 1;
    $('lessonRepeat').disabled = !ready;
  }
  function pause() {
    ticket++; playing = false; audio.pause(); controls();
  }
  function renderScene() {
    const lesson = lessons?.find(item => item.id === problemId);
    const track = media?.find(item => item.id === problemId);
    const voice = track?.scenes[sceneIndex]?.provenance;
    $('lessonVoiceCredit').hidden = !voice;
    $('lessonVoiceCredit').textContent = voice?.provider === 'clova'
      ? 'AI 음성 · CLOVA Dubbing' : voice?.provider === 'elevenlabs' ? 'AI 음성 · ElevenLabs' : '';
    if (!lesson || !track) {
      pause(); audio.removeAttribute('src'); audio.load();
      $('lessonPosition').textContent = '강의 준비 중';
      $('lessonSceneTitle').textContent = '이 강의의 음성을 준비하고 있어요';
      $('lessonCaption').textContent = '완성되면 이 화면에서 바로 재생할 수 있어요.';
      window.CodingMotion.mount(null); window.CodingCode.mount(null, null);
      $('lessonCards').replaceChildren(); $('lessonCode').hidden = true; $('lessonNarration').textContent = '';
      $('lessonNextProblem').hidden = true;
      status('음성 생성 중이에요. 준비 상태를 자동으로 확인하고 있어요. 직접 풀기는 지금 이용할 수 있어요.');
      updateSubtitle(); controls(); return;
    }
    const scene = lesson.scenes[sceneIndex];
    $('lessonNextProblem').hidden = true;
    const duration = Math.round(track.scenes.reduce((sum, item) => sum + item.duration, 0));
    $('lessonPosition').textContent = `${sceneIndex + 1} / ${lesson.scenes.length} · 전체 ${Math.floor(duration / 60)}분 ${duration % 60}초`;
    $('lessonSegments').replaceChildren();
    lesson.scenes.forEach((_, index) => {
      const segment = document.createElement('span');
      segment.setAttribute('aria-label', `${index + 1}번째 장면`);
      if (index === sceneIndex) segment.setAttribute('aria-current', 'step');
      $('lessonSegments').append(segment);
    });
    $('lessonSceneTitle').textContent = scene.title;
    $('lessonCaption').textContent = scene.caption;
    $('lessonNarration').textContent = scene.narration;
    $('lessonCards').replaceChildren();
    $('lessonCards').dataset.layout = scene.items.every(text => text.length <= 4 && !text.includes('\n')) ? 'sequence' : 'states';
    $('lessonCards').style.setProperty('--item-count', scene.items.length);
    audio.currentTime = 0;
    const animated = window.CodingMotion.mount(motion.find(item => item.id === problemId)?.scenes[sceneIndex], track.scenes[sceneIndex]);
    if (!animated) scene.items.forEach((text, index) => {
      const item = document.createElement('div');
      item.className = 'lesson-card' + (index === scene.active ? ' active' : '');
      item.textContent = text;
      if (index === scene.active) item.setAttribute('aria-label', '현재 단계: ' + text);
      $('lessonCards').append(item);
    });
    window.CodingCode.mount(callbacks.getJavaSolution?.(problemId), codeLinks.find(item => item.id === problemId));
    audio.src = track.scenes[sceneIndex].src + (track.sourceHash ? '?v=' + encodeURIComponent(track.sourceHash) : '');
    audio.playbackRate = Number($('lessonRate').value);
    audio.load();
    updateSubtitle();
    $('lessonStage').classList.remove('scene-enter');
    window.requestAnimationFrame(() => $('lessonStage').classList.add('scene-enter'));
    status('');
    if (visible && (sceneIndex > 0 || codeLinks.some(item => item.id === problemId))) callbacks.onAssisted?.();
    controls();
  }
  async function load() {
    if (loading) return loading;
    window.clearTimeout(retryTimer);
    status('장면과 한국어 음성을 준비하고 있어요.');
    loading = Promise.all(['/static/coding-lessons.json', '/static/coding-audio/manifest.json', '/static/coding-motion-01-15.json', '/static/coding-motion-16-30.json', '/static/coding-code-links-01-15.json', '/static/coding-code-links-16-30.json'].map(async url => {
      let response;
      try { response = await fetch(url, {cache: 'no-store'}); }
      catch (error) { if ((url.includes('coding-motion-') || url.includes('coding-code-links-'))) return []; throw error; }
      if (response.status === 404) return url.includes('manifest') ? {lessons: []} : [];
      if (!response.ok) { if ((url.includes('coding-motion-') || url.includes('coding-code-links-'))) return []; throw new Error('load'); }
      try { return await response.json(); }
      catch (error) { if ((url.includes('coding-motion-') || url.includes('coding-code-links-'))) return []; throw error; }
    })).then(([script, manifest, first, second, codeFirst, codeSecond]) => {
      if (!Array.isArray(script) || !Array.isArray(manifest.lessons)) throw new Error('format');
      for (const lesson of script) {
        const sound = manifest.lessons.find(item => item.id === lesson.id);
        if (!Array.isArray(lesson.scenes) || lesson.scenes.length !== 5) throw new Error('format');
        if (!sound) continue;
        if (sound.scenes.length !== lesson.scenes.length ||
          sound.scenes.some(item => typeof item.src !== 'string' || !item.src.startsWith('/static/coding-audio/') || !(item.duration > 0))) throw new Error('audio');
      }
      for (const sound of manifest.lessons) {
        for (const scene of sound.scenes) {
          if (scene.cues !== undefined && (!Array.isArray(scene.cues) || !scene.cues.length ||
            scene.cues.some((cue, index) => !Number.isFinite(cue.start) || !Number.isFinite(cue.end) ||
              cue.start < 0 || cue.end <= cue.start || cue.end > scene.duration + 0.1 || typeof cue.text !== 'string' ||
              !cue.text.trim() || (index && cue.start < scene.cues[index - 1].end - 0.01)))) throw new Error('captions');
        }
      }
      const storyboard = [...(Array.isArray(first) ? first : []), ...(Array.isArray(second) ? second : [])];
      try { window.CodingMotion.validate(storyboard, script, manifest.lessons); motion = storyboard; }
      catch (_) { motion = []; }
      const links = [...(Array.isArray(codeFirst) ? codeFirst : []), ...(Array.isArray(codeSecond) ? codeSecond : [])];
      try { window.CodingCode.validate(links, script, callbacks.getJavaSolution); codeLinks = links; }
      catch (_) { codeLinks = []; }
      lessons = script; media = manifest.lessons;
      renderScene();
      if (!motion.find(item => item.id === problemId)) status('애니메이션을 불러오지 못했어요. 음성과 자막은 재생할 수 있어요. 화면을 새로고침하면 다시 불러옵니다.');
    }).catch(() => {
      status('강의나 음성을 불러오지 못했어요. 연결을 확인한 뒤 다시 불러오기를 눌러주세요.');
    }).finally(() => {
      loading = null; controls();
      if (lessons && !currentReady() && visible) retryTimer = window.setTimeout(() => load(), 4000);
    });
    controls();
    return loading;
  }
  async function play() {
    if (!visible) return;
    if (!currentReady()) { await load(); return; }
    const stamp = ++ticket;
    if (audio.ended) audio.currentTime = 0;
    audio.muted = false; audio.volume = 1;
    audio.playbackRate = Number($('lessonRate').value);
    callbacks.onAssisted?.();
    playing = true; controls(); status('소리를 준비하고 있어요.');
    try {
      await audio.play();
      if (stamp !== ticket || !visible) return;
      playing = true; controls(); status('설명을 듣고 있어요.');
    } catch (_) {
      if (stamp !== ticket) return;
      playing = false; controls(); status('소리를 재생하지 못했어요. 재생 버튼을 다시 눌러주세요. 기기 음량과 연결도 확인해 주세요.');
    }
  }
  function changeScene(index, keepPlaying = false) {
    const lesson = lessons?.find(item => item.id === problemId);
    if (!lesson || index < 0 || index >= lesson.scenes.length) return;
    pause(); sceneIndex = index; callbacks.onProgress?.(sceneIndex, false);
    renderScene();
    if (keepPlaying) play();
  }
  $('lessonFullCode').addEventListener('toggle', () => { if (visible && $('lessonFullCode').open) callbacks.onAssisted?.(); });
  $('lessonPlay').onclick = () => {
    if (playing) { pause(); status('멈춘 곳부터 이어 들을 수 있어요.'); }
    else play();
  };
  $('lessonNextProblem').onclick = () => { if (callbacks.onNextLesson?.()) play(); };
  $('lessonPrev').onclick = () => changeScene(sceneIndex - 1, playing);
  $('lessonNext').onclick = () => changeScene(sceneIndex + 1, playing);
  $('lessonRepeat').onclick = () => changeScene(sceneIndex, true);
  $('lessonRate').onchange = () => { audio.playbackRate = Number($('lessonRate').value); };
  audio.onended = () => {
    if (!visible || !playing) return;
    playing = false; callbacks.onCompletedScene?.(sceneIndex);
    const lesson = lessons.find(item => item.id === problemId);
    if (sceneIndex === lesson.scenes.length - 1) {
      callbacks.onProgress?.(sceneIndex, true); controls();
      $('lessonNextProblem').hidden = problemId === 30;
      status('마지막 장면을 들었어요. 다시 듣거나, 원하면 직접 풀어보세요.');
    } else if ($('lessonAuto').checked) changeScene(sceneIndex + 1, true);
    else { controls(); status('이 장면을 다 들었어요. 준비되면 다음 장면을 눌러주세요.'); }
  };
  audio.onerror = () => {
    if (!audio.getAttribute('src')) return;
    pause(); status('이 장면의 음성을 불러오지 못했어요. 연결을 확인하고 ‘이 장면 다시’를 눌러주세요.');
  };
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && playing) { pause(); status('다른 화면으로 이동해서 멈췄어요. 돌아오면 재생을 눌러주세요.'); }
  });
  document.addEventListener('keydown', event => {
    if (event.code !== 'Space' || event.repeat || event.altKey || event.ctrlKey || event.metaKey || !visible ||
      event.target.isContentEditable || event.target.closest?.('input, textarea, select, button, summary, a')) return;
    event.preventDefault();
    if (!$('lessonPlay').disabled) $('lessonPlay').click();
  });
  window.addEventListener('pagehide', pause);
  window.CodingLesson = {
    init(options) { callbacks = options; load(); },
    setProblem(id, index = 0) {
      if (id === problemId && index === sceneIndex) return;
      pause(); problemId = id; sceneIndex = index; renderScene();
    },
    setVisible(value) {
      visible = value;
      if (!visible) pause();
      else if (lessons && (sceneIndex > 0 || codeLinks.some(item => item.id === problemId))) callbacks.onAssisted?.();
      controls();
      if (visible && !currentReady() && !loading) load();
    },
    pause,
  };
})();
