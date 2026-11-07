(() => {
  'use strict';
  const key = 'csCoding48:java:v1';
  const legacyKey = 'csCoding48:v1';
  const $ = id => document.getElementById(id);
  const checklist = ['입출력과 제약을 내 말로 확인했다', '단순 풀이와 개선 이유를 설명했다', '테스트를 실행하고 경계값을 확인했다', '시간·공간 복잡도를 설명했다'];
  let problems = [], current = 1, filter = 'all', state = {language: 'java', records: {}, pythonRecords: {}}, storageError = false;
  function validRecords(value) {
    if (!value || typeof value !== 'object' || !value.records || typeof value.records !== 'object' || Array.isArray(value.records)) return false;
    return Object.entries(value.records).every(([id, r]) => /^[1-9]\d?$/.test(id) && Number(id) <= 30 && r && typeof r === 'object' &&
      typeof r.code === 'string' && typeof r.notes === 'string' && Array.isArray(r.checks) && r.checks.length === 4 && r.checks.every(v => typeof v === 'boolean') &&
      Number.isFinite(r.elapsed) && r.elapsed >= 0 && Number.isInteger(r.hints) && r.hints >= 0 && r.hints <= 3 && typeof r.answer === 'boolean' &&
      ['', 'solved', 'review', 'stuck'].includes(r.status) && Number.isFinite(r.due) && (r.started === null || (Number.isFinite(r.started) && r.started > 0)) &&
      (r.step === undefined || [0,1,2].includes(r.step)) &&
      (r.lessonScene === undefined || [0,1,2,3,4].includes(r.lessonScene)) &&
      (r.lessonWatched === undefined || typeof r.lessonWatched === 'boolean') &&
      (r.lessonAssisted === undefined || typeof r.lessonAssisted === 'boolean') &&
      (r.lessonHeard === undefined || (Array.isArray(r.lessonHeard) && r.lessonHeard.length <= 5 && r.lessonHeard.every(i => [0,1,2,3,4].includes(i)))) &&
      (r.nextAction === undefined || (typeof r.nextAction === 'string' && r.nextAction.length <= 500)));
  }
  function validState(value) {
    return validRecords(value) && (value.quietView === undefined || typeof value.quietView === 'boolean') && (value.learningMode === undefined || ['lesson','practice'].includes(value.learningMode)) && (value.language === undefined || value.language === 'java') &&
      (value.pythonRecords === undefined || validRecords({records: value.pythonRecords})) &&
      (value.focus === undefined || (value.focus && [5,10,15].includes(value.focus.minutes) &&
        typeof value.focus.hideTimer === 'boolean' && typeof value.focus.onBreak === 'boolean'));
  }
  function javaState(value) {
    if (value.language === 'java') return value;
    return {language: 'java', current: value.current, records: {}, pythonRecords: value.records};
  }
  try {
    const raw = localStorage.getItem(key) || localStorage.getItem(legacyKey);
    if (raw) { const parsed = JSON.parse(raw); if (!validState(parsed)) throw new Error('invalid'); state = javaState(parsed); }
  } catch (_) { storageError = true; $('notice').textContent = '저장 기록을 읽지 못했습니다. 기존 기록 보호를 위해 자동 저장을 중지했습니다. 백업을 복원하거나 새 기록을 다운로드하세요.'; }
  function save() {
    if (storageError) return;
    try { localStorage.setItem(key, JSON.stringify(state)); }
    catch (_) { storageError = true; $('notice').textContent = '브라우저 저장에 실패했습니다. 페이지를 닫기 전에 학습 기록을 백업하세요.'; }
  }
  function problem() { return problems.find(p => p.id === current); }
  function starter(p) { return p.java.starter; }
  function record() {
    if (!state.records[current]) state.records[current] = {code: starter(problem()), notes: state.pythonRecords?.[current]?.notes || '', checks: [false,false,false,false], elapsed: 0, started: null, hints: 0, answer: false, status: '', due: 0, step: 0, nextAction: ''};
    const r = state.records[current];
    r.step ??= 0; r.nextAction ??= '';
    return r;
  }
  function elapsed(r) { return r.elapsed + (r.started ? Math.max(0, Date.now() - r.started) / 1000 : 0); }
  function pause() { const r = record(); r.elapsed = elapsed(r); r.started = null; save(); }
  const prompts = [
    '입력과 출력을 한 문장으로 말해 보세요. 지금은 읽기만 하면 됩니다.',
    '가장 단순한 풀이부터 한 줄씩. 막히면 힌트를 하나만 열어보세요.',
    '테스트를 실행하고, 왜 이 방법을 골랐는지 한 문장으로 설명해 보세요.'
  ];
  function focusSettings() {
    state.focus ??= {minutes: 10, hideTimer: false, onBreak: false};
    return state.focus;
  }
  function renderFocus() {
    const r = record(), settings = focusSettings();
    $('sessionMinutes').value = String(settings.minutes);
    $('hideTimer').checked = settings.hideTimer;
    $('timer').hidden = settings.hideTimer;
    $('breakPanel').hidden = !settings.onBreak;
    $('workArea').hidden = settings.onBreak;
    $('breakButton').disabled = settings.onBreak;
    $('timerToggle').disabled = settings.onBreak;
    $('sessionMinutes').disabled = settings.onBreak;
    $('restart').disabled = settings.onBreak;
    $('returnNote').textContent = r.nextAction || prompts[r.step];
    $('nextAction').value = r.nextAction;
    document.querySelectorAll('[data-step]').forEach(button => {
      if (Number(button.dataset.step) === r.step) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
    ['readPanel','writePanel','reviewPanel'].forEach((id, step) => { $(id).hidden = step !== r.step; });
    $('stepPrompt').textContent = prompts[r.step];
    $('stageNext').hidden = r.step === 2;
    $('stageNext').textContent = r.step === 0 ? '이해했어요 → 코드 쓰기' : '작성했어요 → 확인 · 설명';
    $('nextProblem').hidden = !r.status;
  }
  function applyQuietView() {
    document.body.classList.toggle('quiet-view', !!state.quietView);
    $('focusView').setAttribute('aria-pressed', String(!!state.quietView));
    $('focusView').textContent = state.quietView ? '집중 끝내기' : '집중 화면';
    if (state.quietView) $('curriculum').open = false;
  }
  $('focusView').onclick = () => { state.quietView = !state.quietView; applyQuietView(); save(); };
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && state.quietView) {
      state.quietView = false; applyQuietView(); save(); $('focusView').focus();
    }
  });
  function applyMode() {
    const mode = state.learningMode || (focusSettings().onBreak ? 'practice' : 'lesson');
    $('lessonPanel').hidden = mode !== 'lesson';
    $('practicePanel').hidden = mode !== 'practice';
    $('modeLesson').setAttribute('aria-pressed', String(mode === 'lesson'));
    $('modePractice').setAttribute('aria-pressed', String(mode === 'practice'));
    $('restart').hidden = mode !== 'practice';
    $('meta').textContent = mode === 'lesson' ? problem().topic : `${problem().topic} · 권장 풀이 ${problem().minutes}분`;
    applyQuietView();
    window.CodingLesson.setVisible(mode === 'lesson');
  }
  function changeMode(mode) {
    pause(); state.learningMode = mode; save(); applyMode(); updateClock();
  }
  $('modeLesson').onclick = () => changeMode('lesson');
  $('modePractice').onclick = () => changeMode('practice');
  function changeStep(step) {
    record().step = step; save(); renderFocus(); $('stepPrompt').focus();
  }
  function updateClock() {
    if (!problems.length) return;
    const r = record(), left = Math.max(0, Math.ceil(focusSettings().minutes * 60 - elapsed(r)));
    $('timer').textContent = `${String(Math.floor(left / 60)).padStart(2,'0')}:${String(left % 60).padStart(2,'0')}`;
    $('timerToggle').textContent = r.started ? '일시정지' : left === 0 ? '한 번 더 시작' : '시작';
    if (left === 0 && r.started) {
      pause(); $('timerToggle').textContent = '한 번 더 시작';
      $('sessionStatus').textContent = '한 구간을 마쳤어요. 잠깐 쉬거나, 그대로 이어가도 괜찮아요.';
    }
  }
  function list() {
    const done = problems.filter(p => state.records[p.id]?.status === 'solved').length;
    const reviews = problems.filter(p => ['review','stuck'].includes(state.records[p.id]?.status));
    $('completed').textContent = `${done} / 30`; $('progress').value = done;
    $('reviewCount').textContent = `복습할 문제 ${reviews.length}개`;
    $('problems').replaceChildren();
    problems.filter(p => filter === 'all' || String(p.day) === filter || (filter === 'review' && reviews.includes(p))).forEach(p => {
      const r = state.records[p.id], b = document.createElement('button');
      b.textContent = `${String(p.id).padStart(2,'0')}  ${p.title}`;
      b.setAttribute('aria-current', String(p.id === current));
      const small = document.createElement('small');
      small.textContent = `${p.topic} · ${p.minutes}분 · ${{solved:'완료',review:'복습',stuck:'막힘'}[r?.status] || '미완료'}`;
      b.append(small); b.onclick = () => select(p.id); $('problems').append(b);
    });
    if (!$('problems').children.length) $('problems').textContent = '복습할 문제가 없습니다.';
  }
  function select(id) {
    if (problems.length && state.records[current]) pause();
    current = id; state.current = id; focusSettings().onBreak = false; $('curriculum').open = false; $('sessionStatus').textContent = '타이머 없이 시작해도 괜찮아요.'; render(); save(); ($('lessonPanel').hidden ? $('stepPrompt') : $('lessonSceneTitle')).focus();
  }
  function render() {
    const p = problem(), r = record();
    $('exercise').hidden = false;
    $('meta').textContent = `DAY ${p.day} / ${p.topic} / ${p.difficulty} / 권장 풀이 ${p.minutes}분`;
    $('title').textContent = `${String(p.id).padStart(2,'0')}. ${p.title}`;
    $('statement').textContent = p.statement;
    $('examples').replaceChildren();
    p.examples.forEach((example,i) => {
      const div = document.createElement('div'); div.className = 'example';
      const pre = document.createElement('pre'); pre.textContent = `예제 ${i+1}\n입력: ${example.input}\n출력: ${example.output}`;
      const note = document.createElement('p'); note.textContent = example.explanation; div.append(pre,note); $('examples').append(div);
    });
    $('referenceStatement').textContent = p.statement;
    $('referenceExamples').replaceChildren(...Array.from($('examples').children, el => el.cloneNode(true)));
    $('code').value = r.code; $('notes').value = r.notes;
    $('tests').textContent = p.java.testCode;
    const legacy = state.pythonRecords?.[current];
    $('legacyPanel').hidden = !legacy;
    $('legacyCode').textContent = legacy?.code || '';
    $('legacyMeta').textContent = legacy ? `이전 상태: ${{solved:'완료',review:'복습 필요',stuck:'미해결'}[legacy.status] || '미완료'} · 메모: ${legacy.notes || '없음'}` : '';
    $('hints').replaceChildren();
    p.hints.slice(0,r.hints).forEach((hint,i) => { const text = document.createElement('p'); text.textContent = `${i+1}. ${hint}`; $('hints').append(text); });
    $('hint').textContent = `막혔어요 · 힌트 하나 보기 (${r.hints}/3)`; $('hint').disabled = r.hints >= 3;
    $('answer').open = r.answer;
    $('approach').textContent = p.approach; $('complexity').textContent = p.complexity; $('solution').textContent = p.java.solution;
    $('pitfalls').textContent = `주의: ${p.pitfalls.join(' · ')}`; $('explain').textContent = p.explainPrompt;
    $('checks').replaceChildren();
    checklist.forEach((text,i) => { const label = document.createElement('label'), input = document.createElement('input'); input.type = 'checkbox'; input.checked = r.checks[i]; input.onchange = () => { record().checks[i] = input.checked; save(); }; label.append(input,document.createTextNode(text)); $('checks').append(label); });
    $('result').textContent = r.status ? `현재 기록: ${{solved:'독립 풀이 완료',review:'복습 필요',stuck:'미해결'}[r.status]}${r.due ? ' · 복습 예정 ' + new Date(r.due).toLocaleString('ko-KR') : ''}` : '';
    list(); renderFocus(); updateClock();
    window.CodingLesson.setProblem(p.id, r.lessonScene || 0); applyMode();
  }
  function download(name, text, type) {
    const url = window.URL.createObjectURL(new window.Blob([text], {type}));
    const a = document.createElement('a'); a.href = url; a.download = name; a.click(); window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
  }
  $('code').oninput = () => { record().code = $('code').value; save(); };
  $('code').onkeydown = event => { if (event.key === 'Tab') { event.preventDefault(); const el = $('code'), start = el.selectionStart, end = el.selectionEnd; el.setRangeText('    ',start,end,'end'); el.dispatchEvent(new window.Event('input')); } };
  $('notes').oninput = () => { record().notes = $('notes').value; save(); };
  $('timerToggle').onclick = () => {
    const r = record();
    if (r.started) { pause(); $('sessionStatus').textContent = '멈춰뒀어요. 준비되면 다시 시작하세요.'; }
    else {
      if (elapsed(r) >= focusSettings().minutes * 60) r.elapsed = 0;
      r.started = Date.now(); save(); $('sessionStatus').textContent = '지금 단계만 천천히 해보세요.';
    }
    updateClock();
  };
  document.querySelectorAll('[data-step]').forEach(button => { button.onclick = () => changeStep(Number(button.dataset.step)); });
  $('stageNext').onclick = () => changeStep(Math.min(2, record().step + 1));
  $('nextAction').oninput = () => { record().nextAction = $('nextAction').value; save(); };
  $('sessionMinutes').onchange = () => {
    pause(); focusSettings().minutes = Number($('sessionMinutes').value); record().elapsed = 0;
    save(); updateClock(); $('sessionStatus').textContent = '시간을 바꿨어요. 준비되면 시작하세요.';
  };
  $('hideTimer').onchange = () => { focusSettings().hideTimer = $('hideTimer').checked; save(); renderFocus(); };
  $('breakButton').onclick = () => {
    pause(); focusSettings().onBreak = true; save(); renderFocus(); updateClock(); $('breakTitle').focus();
  };
  $('resumeButton').onclick = () => {
    focusSettings().onBreak = false; save(); renderFocus();
    $('sessionStatus').textContent = '돌아왔어요. 타이머는 멈춘 상태예요.'; $('stepPrompt').focus();
  };
  $('hint').onclick = () => { const r = record(); r.hints = Math.min(3,r.hints+1); r.status = 'review'; r.due = Date.now()+1800000; save(); render(); };
  $('answer').ontoggle = () => { if ($('answer').open && !record().answer) { const r = record(); r.answer = true; r.status = 'review'; r.due = Date.now()+1800000; save(); list(); } };
  $('restart').onclick = () => {
    if (!window.confirm('현재 코드를 비우고 타이머·힌트를 초기화합니다. 오답 메모는 유지합니다. 재풀이할까요?')) return;
    const r = record(); r.code = starter(problem()); r.elapsed = 0; r.started = null; r.hints = 0; r.answer = false; r.lessonAssisted = false; r.checks = [false,false,false,false]; r.status = 'review'; r.due = Date.now(); r.step = 1; save(); render();
  };
  document.querySelectorAll('[data-filter]').forEach(b => b.onclick = () => { filter = b.dataset.filter; document.querySelectorAll('[data-filter]').forEach(el => el.setAttribute('aria-pressed',String(el === b))); list(); });
  document.querySelectorAll('[data-verdict]').forEach(b => b.onclick = () => {
    const r = record();
    if (b.dataset.verdict === 'solved' && (r.hints || r.answer || r.lessonAssisted || !r.checks.every(Boolean))) { $('result').textContent = '체크리스트를 모두 확인하세요. 강의·힌트·해설을 봤다면 “빈 코드로 재풀이” 후 도움 없이 풀어야 완료할 수 있습니다.'; return; }
    pause(); r.status = b.dataset.verdict; r.due = r.status === 'solved' ? 0 : Date.now()+1800000; save(); render();
  });
  $('recommend').onclick = () => {
    if (!problems.length) return;
    const due = problems.find(p => ['review','stuck'].includes(state.records[p.id]?.status) && state.records[p.id].due <= Date.now());
    const next = due || problems.find(p => !state.records[p.id]?.status) || problems.find(p => state.records[p.id]?.status !== 'solved');
    if (next) { select(next.id); $('exercise').scrollIntoView({block:'start'}); } else $('notice').textContent = '30문제 독립 풀이 완료! 시험 전에는 취약했던 문제의 접근법과 경계값을 말로 복기하세요.';
  };
  $('nextProblem').onclick = () => $('recommend').click();
  $('export').onclick = () => {
    const snapshot = JSON.parse(JSON.stringify(state));
    Object.values(snapshot.records).forEach(r => { r.elapsed = elapsed(r); r.started = null; });
    download('coding48-java-progress.json', JSON.stringify(snapshot,null,2), 'application/json');
  };
  $('restore').onclick = () => $('import').click();
  $('import').onchange = async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 5000000) throw new Error('size');
      const parsed = JSON.parse(await file.text()); if (!validState(parsed)) throw new Error('format');
      if (!window.confirm('이 브라우저의 현재 코테 기록을 백업 내용으로 바꿀까요?')) return;
      window.CodingLesson.pause();
      state = javaState(parsed); Object.values(state.records).forEach(r => { r.started = null; }); storageError = false; current = problems.some(p => p.id === state.current) ? state.current : 1; save(); render();
      if (!storageError) $('notice').textContent = '학습 기록을 복원했습니다.';
    } catch (_) { $('notice').textContent = '복원 실패: 올바른 학습 기록 JSON(5MB 이하)을 선택하세요. 현재 기록은 유지됩니다.'; }
    event.target.value = '';
  };
  $('download').onclick = () => {
    const runner = `
public class Main {
    private static int failures = 0;
    private static String display(Object value) {
        return Arrays.deepToString(new Object[]{value});
    }
    private static void check(Supplier<Object> run, Object expected, String name) {
        try {
            Object actual = run.get();
            if (!Objects.deepEquals(actual, expected)) {
                failures++;
                System.out.println("FAIL " + name + ": expected=" + display(expected) + ", actual=" + display(actual));
            } else {
                System.out.println("PASS " + name);
            }
        } catch (Throwable error) {
            failures++;
            System.out.println("FAIL " + name + ": " + error);
        }
    }
    public static void main(String[] args) {
${problem().java.testCode}
        if (failures > 0) System.exit(1);
    }
}
`;
    download('Main.java', 'import java.util.*;\nimport java.util.function.Supplier;\n\n' + record().code + '\n' + runner, 'text/x-java-source');
  };
  fetch('/static/coding-problems.json').then(response => { if (!response.ok) throw new Error('load'); return response.json(); }).then(data => {
    if (!Array.isArray(data) || data.length !== 30 || data.some(p => !p.java?.starter || !p.java?.solution || !p.java?.testCode)) throw new Error('data'); problems = data;
    current = problems.some(p => p.id === state.current) ? state.current : 1;
    window.CodingLesson.init({
      getJavaSolution(id) { return problems.find(item => item.id === id)?.java.solution || ""; },
      onNextLesson() { if (current >= 30) return false; select(current + 1); return true; },
      onProgress(scene) { record().lessonScene = scene; save(); },
      onCompletedScene(scene) {
        const r = record(); r.lessonHeard = [...new Set([...(r.lessonHeard || []), scene])];
        r.lessonWatched = r.lessonHeard.length === 5; save();
      },
      onAssisted() {
        const r = record(); r.lessonAssisted = true;
        if (r.status !== 'solved') { r.status = 'review'; r.due = Date.now() + 1800000; }
        save(); list();
      },
    });
    if (focusSettings().onBreak || state.learningMode !== 'practice') pause();
    render(); save(); $('restore').disabled = false; window.setInterval(updateClock,1000);
  }).catch(() => { $('notice').textContent = '문제를 불러오지 못했습니다. 연결을 확인하고 새로고침하세요.'; });
})();
