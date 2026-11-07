(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const audio = $('lessonAudio');
  let lessons = null, media = null, loading = null, problemId = 0, sceneIndex = 0;
  let visible = true, playing = false, ticket = 0, callbacks = {}, retryTimer = null;
  function currentReady() { return !!lessons?.find(item => item.id === problemId) && !!media?.find(item => item.id === problemId); }
  function status(message) { $('lessonStatus').textContent = message; }
  function controls() {
    const lesson = lessons?.find(item => item.id === problemId);
    const ready = !!lesson && !!media?.find(item => item.id === problemId);
    $('lessonPlay').disabled = !visible || (!ready && !!loading);
    $('lessonPlay').textContent = playing ? '일시정지' : ready ? '소리 켜고 재생' : loading ? '음성 준비 중' : '강의 다시 불러오기';
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
    if (!lesson || !track) {
      pause(); audio.removeAttribute('src'); audio.load();
      $('lessonPosition').textContent = '강의 준비 중';
      $('lessonSceneTitle').textContent = '이 강의의 음성을 준비하고 있어요';
      $('lessonCaption').textContent = '완성되면 이 화면에서 바로 재생할 수 있어요.';
      $('lessonCards').replaceChildren(); $('lessonCode').hidden = true; $('lessonNarration').textContent = '';
      $('lessonNextProblem').hidden = true;
      status('음성 생성 중이에요. 준비 상태를 자동으로 확인하고 있어요. 직접 풀기는 지금 이용할 수 있어요.');
      controls(); return;
    }
    const scene = lesson.scenes[sceneIndex];
    $('lessonNextProblem').hidden = true;
    $('lessonPosition').textContent = `${sceneIndex + 1} / ${lesson.scenes.length} 장면 · ${Math.ceil(track.scenes.reduce((sum, item) => sum + item.duration, 0) / 60)}분 강의`;
    $('lessonSceneTitle').textContent = scene.title;
    $('lessonCaption').textContent = scene.caption;
    $('lessonNarration').textContent = scene.narration;
    $('lessonCards').replaceChildren();
    scene.items.forEach((text, index) => {
      const item = document.createElement('div');
      item.className = 'lesson-card' + (index === scene.active ? ' active' : '');
      item.textContent = text;
      if (index === scene.active) item.setAttribute('aria-label', '현재 단계: ' + text);
      $('lessonCards').append(item);
    });
    $('lessonCode').hidden = !scene.code;
    $('lessonCode').textContent = scene.code || '';
    audio.src = track.scenes[sceneIndex].src;
    audio.playbackRate = Number($('lessonRate').value);
    audio.load();
    $('lessonStage').classList.remove('scene-enter');
    window.requestAnimationFrame(() => $('lessonStage').classList.add('scene-enter'));
    status('재생을 누르면 이 장면을 소리로 설명해 드려요.');
    if (visible && sceneIndex > 0) callbacks.onAssisted?.();
    controls();
  }
  async function load() {
    if (loading) return loading;
    window.clearTimeout(retryTimer);
    status('장면과 한국어 음성을 준비하고 있어요.');
    loading = Promise.all(['/static/coding-lessons.json', '/static/coding-audio/manifest.json'].map(async url => {
      const response = await fetch(url, {cache: 'no-store'});
      if (response.status === 404) return url.includes('manifest') ? {lessons: []} : [];
      if (!response.ok) throw new Error('load');
      return response.json();
    })).then(([script, manifest]) => {
      if (!Array.isArray(script) || !Array.isArray(manifest.lessons)) throw new Error('format');
      for (const lesson of script) {
        const sound = manifest.lessons.find(item => item.id === lesson.id);
        if (!Array.isArray(lesson.scenes) || lesson.scenes.length !== 5) throw new Error('format');
        if (!sound) continue;
        if (sound.scenes.length !== lesson.scenes.length ||
          sound.scenes.some(item => typeof item.src !== 'string' || !item.src.startsWith('/static/coding-audio/') || !(item.duration > 0))) throw new Error('audio');
      }
      lessons = script; media = manifest.lessons;
      renderScene();
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
      playing = true; controls(); status('설명 중이에요. 기기 음량을 조절해서 편하게 들어주세요.');
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
  $('lessonPlay').onclick = () => {
    if (playing) { pause(); status('잠깐 멈췄어요. 재생을 누르면 이어서 설명해요.'); }
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
      else if (sceneIndex > 0 && lessons) callbacks.onAssisted?.();
      controls();
      if (visible && !currentReady() && !loading) load();
    },
    pause,
  };
})();
