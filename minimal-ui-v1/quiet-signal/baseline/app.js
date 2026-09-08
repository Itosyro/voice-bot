(() => {
  'use strict';

  const STORAGE_KEY = 'dvizh-state-v1';
  const AREAS = ['ПДД', 'Кафе', 'Волейбол', 'Соцсети', 'Восстановление', 'Разное'];
  const AREA_EMOJI = {
    'ПДД': '◆',
    'Кафе': '▰',
    'Волейбол': '◉',
    'Соцсети': '↗',
    'Восстановление': '≈',
    'Разное': '·'
  };
  const ENERGY_TEXT = ['лежачий режим', 'режим 5 минут', 'нормальный заряд', 'много энергии'];
  const FEAR_LADDER_DEFAULT = [
    { id: 'draft', title: 'Снять 15-секундный черновик', hint: 'Без публикации и оценки.' },
    { id: 'friend', title: 'Отправить ролик одному своему', hint: 'Получить безопасную обратную связь.' },
    { id: 'story-object', title: 'Выложить сторис без лица', hint: 'Мяч, зал, кроссовки, кусок тренировки.' },
    { id: 'story-self', title: 'Выложить сторис с собой', hint: 'Без объяснений и оправданий.' },
    { id: 'reel', title: 'Опубликовать короткий ролик', hint: 'Цель — публикация, не идеальный результат.' },
    { id: 'comment', title: 'Спокойно ответить на один комментарий', hint: 'Или не отвечать: блокировка тоже граница.' }
  ];

  const VIEW_COPY = {
    direct: {
      home: 'Не спасай всю жизнь. Сделай один ход.',
      tasks: 'Не держи всё в голове. Выгрузи и режь на куски.',
      focus: 'Один раунд. Без торга с собой.',
      proof: 'Факты сильнее ощущения «я ничего не делаю».',
      week: 'Неделя без каши: жизнь, дела и восстановление в одном месте.',
      training: 'Тренируйся по готовности, а не по чувству вины.',
      social: 'Создавай контент маленькими этапами, не живи в ленте.',
      settings: 'Настрой систему под себя, а не себя под систему.',
      start: 'Начать раунд',
      suggestion: 'Начать сейчас'
    },
    calm: {
      home: 'Не нужно решать всё сразу. Выбери один следующий шаг.',
      tasks: 'Выгрузи задачи из головы и сделай их посильными.',
      focus: 'Один спокойный ограниченный раунд.',
      proof: 'Посмотри на реальные шаги, которые уже были.',
      week: 'Посмотри на ближайшие семь дней без попытки забить каждый час.',
      training: 'Проверь сон, боль и энергию перед нагрузкой.',
      social: 'Сохрани идею и сделай один безопасный шаг к публикации.',
      settings: 'Настрой приложение под свой темп.',
      start: 'Начать спокойно',
      suggestion: 'Начать шаг'
    }
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const nowIso = () => new Date().toISOString();
  const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const escapeHtml = (value = '') => String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

  function localDateKey(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function parseLocalDate(key) {
    const [year, month, day] = key.split('-').map(Number);
    return new Date(year, month - 1, day);
  }

  function formatDate(date = new Date()) {
    return new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
      .format(date)
      .replace(/^./, char => char.toUpperCase());
  }

  function createDefaultTasks() {
    const createdAt = nowIso();
    return [
      {
        id: uid(),
        title: 'Решить 10 вопросов ПДД по одной теме',
        micro: 'Открыть билеты и ответить хотя бы на 3 вопроса',
        area: 'ПДД', energy: 1, fear: 0, priority: 3, duration: 8,
        done: false, createdAt
      },
      {
        id: uid(),
        title: 'Доделать один блок меню для кафе',
        micro: 'Выбрать одно комбо и проверить название, состав и цену',
        area: 'Кафе', energy: 2, fear: 1, priority: 3, duration: 15,
        done: false, createdAt
      },
      {
        id: uid(),
        title: 'Сделать короткую тренировку техники',
        micro: 'Пять минут мягкой разминки плеч и голеностопа',
        area: 'Волейбол', energy: 3, fear: 0, priority: 3, duration: 25,
        done: false, createdAt
      },
      {
        id: uid(),
        title: 'Снять первый ролик без публикации',
        micro: 'Записать 15 секунд тренировки и оставить в черновиках',
        area: 'Соцсети', energy: 1, fear: 3, priority: 3, duration: 8,
        done: false, createdAt
      },
      {
        id: uid(),
        title: 'Выложить одну сторис про волейбол',
        micro: 'Выбрать один кадр и написать одну честную строку',
        area: 'Соцсети', energy: 2, fear: 3, priority: 2, duration: 5,
        done: false, createdAt
      },
      {
        id: uid(),
        title: 'Разгрузить тело без экрана',
        micro: 'Убрать телефон и спокойно полежать или пройтись 5 минут',
        area: 'Восстановление', energy: 1, fear: 0, priority: 2, duration: 5,
        done: false, createdAt
      }
    ];
  }

  function createDefaultState() {
    return {
      version: 1,
      hasSeenIntro: false,
      tone: 'direct',
      tasks: createDefaultTasks(),
      checkins: {},
      plans: {},
      sessions: [],
      proofs: [],
      ladder: Object.fromEntries(FEAR_LADDER_DEFAULT.map(step => [step.id, false])),
      selectedFocusTaskId: null,
      focusDuration: 8,
      createdAt: nowIso()
    };
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return createDefaultState();
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.tasks)) return createDefaultState();
      return {
        ...createDefaultState(),
        ...parsed,
        ladder: { ...Object.fromEntries(FEAR_LADDER_DEFAULT.map(step => [step.id, false])), ...(parsed.ladder || {}) }
      };
    } catch (error) {
      console.warn('Не удалось прочитать сохранение:', error);
      return createDefaultState();
    }
  }

  let state = loadState();
  let activeView = 'home';
  let taskAreaFilter = 'Все';
  let suggestionOffset = 0;
  let deferredInstallPrompt = null;
  let rescueInterval = null;
  let rescueRemaining = 90;
  let toastTimer = null;
  let pendingSession = null;

  const focus = {
    taskId: state.selectedFocusTaskId,
    totalSeconds: (state.focusDuration || 8) * 60,
    remainingSeconds: (state.focusDuration || 8) * 60,
    running: false,
    interval: null,
    startedAt: null
  };

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function getTodayCheckin() {
    const key = localDateKey();
    return state.checkins[key] || { energy: null, pain: null, fear: null };
  }

  function setTodayCheckin(field, value) {
    const key = localDateKey();
    state.checkins[key] = {
      ...getTodayCheckin(),
      [field]: Number(value),
      updatedAt: nowIso()
    };
    state.plans[key] = generatePlan(true);
    suggestionOffset = 0;
    saveState();
    renderAll();
  }

  function effectiveEnergy() {
    const checkin = getTodayCheckin();
    let energy = checkin.energy ?? 1;
    if ((checkin.pain ?? 0) >= 2) energy -= 1;
    if ((checkin.pain ?? 0) === 3) energy = 0;
    return clamp(energy, 0, 3);
  }

  function activeTasks() {
    return state.tasks.filter(task => !task.done);
  }

  function taskScore(task, mode = 'main') {
    const checkin = getTodayCheckin();
    const energy = effectiveEnergy();
    const pain = checkin.pain ?? 0;
    const fear = checkin.fear ?? 0;
    let score = task.priority * 6;

    if (task.energy <= Math.max(1, energy)) score += 10 - Math.abs(task.energy - Math.max(1, energy)) * 2;
    else score -= (task.energy - Math.max(1, energy)) * 9;

    if (pain >= 2 && task.area === 'Волейбол') score -= 30;
    if (pain === 3 && task.area !== 'Восстановление') score -= 22;
    if (pain >= 2 && task.area === 'Восстановление') score += 18;
    if (energy === 0 && task.energy === 1) score += 8;

    if (mode === 'brave') {
      score += task.fear * 12;
      if (task.area === 'Соцсети') score += 9;
    } else if (fear >= 2) {
      score -= task.fear * 3;
    }

    const recentSession = state.sessions
      .filter(session => session.taskId === task.id)
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))[0];
    if (recentSession && Date.now() - new Date(recentSession.createdAt).getTime() < 8 * 60 * 60 * 1000) score -= 5;

    return score;
  }

  function sortedCandidates(mode = 'main', excluded = []) {
    let candidates = activeTasks().filter(task => !excluded.includes(task.id));
    if (mode === 'brave') candidates = candidates.filter(task => task.fear > 0);
    if (mode === 'easy') {
      candidates.sort((a, b) => a.energy - b.energy || b.priority - a.priority || taskScore(b) - taskScore(a));
      return candidates;
    }
    return candidates.sort((a, b) => taskScore(b, mode) - taskScore(a, mode));
  }

  function generatePlan(forceDifferent = false) {
    const current = state.plans[localDateKey()] || {};
    const used = [];
    const mainCandidates = sortedCandidates('main');
    let main = mainCandidates[0]?.id || null;
    if (forceDifferent && current.main && mainCandidates.length > 1 && main === current.main) main = mainCandidates[1].id;
    if (main) used.push(main);

    const easyCandidates = sortedCandidates('easy', used);
    let easy = easyCandidates[0]?.id || main || null;
    if (forceDifferent && current.easy && easyCandidates.length > 1 && easy === current.easy) easy = easyCandidates[1].id;
    if (easy) used.push(easy);

    const braveCandidates = sortedCandidates('brave', used);
    let brave = braveCandidates[0]?.id || sortedCandidates('main', used)[0]?.id || easy || main || null;
    if (forceDifferent && current.brave && braveCandidates.length > 1 && brave === current.brave) brave = braveCandidates[1].id;

    return { main, easy, brave, generatedAt: nowIso() };
  }

  function getTodayPlan() {
    const key = localDateKey();
    const plan = state.plans[key];
    const validIds = new Set(activeTasks().map(task => task.id));
    const stillValid = plan && ['main', 'easy', 'brave'].some(slot => plan[slot] && validIds.has(plan[slot]));
    if (!stillValid) {
      state.plans[key] = generatePlan(false);
      saveState();
    }
    return state.plans[key];
  }

  function getSuggestedTasks() {
    const candidates = sortedCandidates('main');
    if (!candidates.length) return [];
    return candidates;
  }

  function getSuggestedTask() {
    const candidates = getSuggestedTasks();
    return candidates[suggestionOffset % candidates.length] || null;
  }

  function getTask(id) {
    return state.tasks.find(task => task.id === id) || null;
  }

  function energyLabel(level) {
    return ['низкая', 'средняя', 'высокая'][clamp(Number(level) - 1, 0, 2)];
  }

  function fearLabel(level) {
    return ['не страшно', 'слегка страшно', 'страшно', 'очень страшно'][clamp(Number(level), 0, 3)];
  }

  function showToast(message) {
    const toast = $('#toast');
    toast.textContent = message;
    toast.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('is-visible'), 2600);
  }

  function openModal(id) {
    const modal = $(`#${id}`);
    if (!modal) return;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeModal(id) {
    const modal = $(`#${id}`);
    if (!modal) return;
    modal.hidden = true;
    if (!$$('.modal-backdrop:not([hidden])').length) document.body.style.overflow = '';
  }

  function navigate(view) {
    if (!['home', 'tasks', 'focus', 'proof', 'week', 'training', 'social', 'settings'].includes(view)) return;
    activeView = view;
    $$('.view').forEach(section => section.classList.toggle('is-active', section.dataset.view === view));
    $$('[data-nav]').forEach(button => button.classList.toggle('is-active', button.dataset.nav === view));
    $('#viewTitle').textContent = VIEW_COPY[state.tone][view];
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (view === 'focus') renderFocus();
    if (view === 'proof') renderProof();
    if (view === 'week') renderWeek();
    if (view === 'training') { renderTraining(); renderJumpLab(); }
    if (view === 'social') renderSocial();
  }

  function renderHeader() {
    $('#todayLabel').textContent = formatDate();
    $('#viewTitle').textContent = VIEW_COPY[state.tone][activeView];
    const checkin = getTodayCheckin();
    const badge = $('#energyBadge');
    if (checkin.energy === null || checkin.energy === undefined) {
      badge.classList.remove('has-energy');
      $('#energyBadgeText').textContent = 'режим не выбран';
    } else {
      badge.classList.add('has-energy');
      $('#energyBadgeText').textContent = ENERGY_TEXT[checkin.energy];
    }
  }

  function renderCheckin() {
    const checkin = getTodayCheckin();
    $$('[data-checkin]').forEach(group => {
      const field = group.dataset.checkin;
      $$('button', group).forEach(button => {
        button.classList.toggle('is-active', Number(button.dataset.value) === checkin[field]);
      });
    });

    const bodyNote = $('#bodyNote');
    const pain = checkin.pain;
    const energy = checkin.energy;
    let note = '';
    if (pain === 3) {
      note = 'Сегодня режим восстановления: приложение убрало тяжёлые задачи. Если боль сильная, новая или не проходит, не продавливай её и обсуди с врачом.';
    } else if (pain === 2) {
      note = 'Тело забирает часть бюджета. ДВИЖ будет предлагать короткие умственные шаги; тренировку не нужно проводить через заметную боль.';
    } else if (energy === 0) {
      note = 'Нулевой заряд — не нулевой день. Сегодня достаточно одного микрошагa на 2–5 минут.';
    }
    bodyNote.hidden = !note;
    bodyNote.textContent = note;
  }

  function taskMetaHtml(task, includeFear = true) {
    return `
      <span class="meta-chip"><i class="area-dot" data-area="${escapeHtml(task.area)}"></i>${escapeHtml(task.area)}</span>
      <span class="meta-chip">${task.duration} мин</span>
      <span class="meta-chip">энергия: ${energyLabel(task.energy)}</span>
      ${includeFear && task.fear > 0 ? `<span class="meta-chip">${fearLabel(task.fear)}</span>` : ''}
    `;
  }

  function renderSuggestion() {
    const task = getSuggestedTask();
    const container = $('#nextStepContent');
    if (!task) {
      container.innerHTML = `
        <div class="next-step-body">
          <div><h2>Все текущие задачи закрыты.</h2><p>Зафиксируй победу или добавь новый следующий шаг. Не надо срочно заполнять пустоту.</p></div>
          <div class="next-step-actions"><button class="button button-primary big" data-action="new-task">Добавить задачу</button></div>
        </div>`;
      return;
    }

    const checkin = getTodayCheckin();
    const useMicro = (checkin.energy ?? 1) <= 1 || (checkin.pain ?? 0) >= 2 || task.energy > Math.max(1, effectiveEnergy());
    const headline = useMicro ? task.micro : task.title;
    const support = useMicro
      ? `Это уменьшенная версия задачи «${task.title}». После неё можно остановиться без чувства долга.`
      : `Микрошаг на случай сопротивления: ${task.micro}.`;
    const duration = useMicro ? Math.min(task.duration, 5) : task.duration;

    container.innerHTML = `
      <div class="next-step-body">
        <div>
          <h2>${escapeHtml(headline)}</h2>
          <p>${escapeHtml(support)}</p>
          <div class="task-meta">${taskMetaHtml({ ...task, duration })}</div>
        </div>
        <div class="next-step-actions">
          <button class="button button-primary big" data-action="start-suggested" data-task-id="${task.id}" data-duration="${duration}">${VIEW_COPY[state.tone].suggestion}</button>
          <button class="button button-ghost" data-action="edit-task" data-task-id="${task.id}">Разобрать задачу</button>
        </div>
      </div>`;
  }

  function renderDailyPlan() {
    const plan = getTodayPlan();
    const slots = [
      { key: 'main', index: '1', label: 'Главное', sub: 'самый полезный ход' },
      { key: 'easy', index: '2', label: 'Лёгкое', sub: 'для низкого заряда' },
      { key: 'brave', index: '3', label: 'Смелое', sub: 'маленький шаг навстречу страху' }
    ];
    const list = $('#dailyPlan');
    list.innerHTML = slots.map(slot => {
      const task = getTask(plan?.[slot.key]);
      if (!task) {
        return `<div class="plan-item"><span class="plan-index">${slot.index}</span><div class="plan-copy"><b>${slot.label}: свободно</b><small>${slot.sub}</small></div><div class="plan-actions"><button data-action="new-task" title="Добавить">+</button></div></div>`;
      }
      return `
        <div class="plan-item ${task.done ? 'is-done' : ''}">
          <span class="plan-index">${slot.index}</span>
          <div class="plan-copy"><b>${escapeHtml(task.title)}</b><small>${slot.label} · ${task.duration} мин · ${escapeHtml(task.micro)}</small></div>
          <div class="plan-actions">
            <button data-action="start-plan-task" data-task-id="${task.id}" title="Начать">▶</button>
            <button data-action="replace-plan-slot" data-slot="${slot.key}" title="Заменить">↻</button>
          </div>
        </div>`;
    }).join('');
  }

  function renderAreaFilters() {
    const counts = Object.fromEntries(AREAS.map(area => [area, state.tasks.filter(task => task.area === area && !task.done).length]));
    const filters = ['Все', ...AREAS, 'Готово'];
    $('#areaFilters').innerHTML = filters.map(filter => {
      const count = filter === 'Все' ? activeTasks().length : filter === 'Готово' ? state.tasks.filter(task => task.done).length : counts[filter];
      return `<button class="filter-chip ${taskAreaFilter === filter ? 'is-active' : ''}" data-area-filter="${escapeHtml(filter)}">${escapeHtml(filter)} · ${count}</button>`;
    }).join('');
  }

  function sortedTaskList(tasks) {
    const sort = $('#taskSort')?.value || 'fit';
    const copy = [...tasks];
    if (sort === 'fit') copy.sort((a, b) => taskScore(b) - taskScore(a));
    if (sort === 'priority') copy.sort((a, b) => b.priority - a.priority || a.energy - b.energy);
    if (sort === 'energy') copy.sort((a, b) => a.energy - b.energy || b.priority - a.priority);
    if (sort === 'recent') copy.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
    return copy;
  }

  function renderTasks() {
    renderAreaFilters();
    let tasks = state.tasks;
    if (taskAreaFilter === 'Готово') tasks = tasks.filter(task => task.done);
    else if (taskAreaFilter === 'Все') tasks = tasks.filter(task => !task.done);
    else tasks = tasks.filter(task => task.area === taskAreaFilter && !task.done);
    tasks = sortedTaskList(tasks);

    const list = $('#taskList');
    if (!tasks.length) {
      list.innerHTML = `<div class="empty-state"><h3>Здесь пусто</h3><p>Это не проблема. Добавь один конкретный следующий шаг, когда он появится.</p></div>`;
      return;
    }

    list.innerHTML = tasks.map(task => `
      <article class="task-card ${task.done ? 'is-done' : ''}">
        <button class="task-check" data-action="toggle-task" data-task-id="${task.id}" aria-label="${task.done ? 'Вернуть задачу' : 'Отметить выполненной'}">✓</button>
        <div class="task-copy">
          <h3>${escapeHtml(task.title)}</h3>
          <p>${escapeHtml(task.micro)}</p>
          <div class="task-meta">${taskMetaHtml(task)}</div>
        </div>
        <div class="task-card-actions">
          ${!task.done ? `<button data-action="start-task" data-task-id="${task.id}" title="Начать фокус">▶</button>` : ''}
          <button data-action="edit-task" data-task-id="${task.id}" title="Изменить">•••</button>
        </div>
      </article>`).join('');
  }

  function ensureFocusTask() {
    let task = getTask(focus.taskId);
    if (!task || task.done) {
      task = getSuggestedTask() || activeTasks()[0] || null;
      focus.taskId = task?.id || null;
      state.selectedFocusTaskId = focus.taskId;
      saveState();
    }
    return task;
  }

  function setFocusTask(taskId, minutes = null) {
    const task = getTask(taskId);
    if (!task || task.done) return;
    stopTimer(false);
    focus.taskId = task.id;
    state.selectedFocusTaskId = task.id;
    if (minutes !== null) state.focusDuration = clamp(Number(minutes), 2, 180);
    else state.focusDuration = [5, 8, 15, 25].includes(task.duration) ? task.duration : task.duration <= 8 ? 8 : task.duration <= 15 ? 15 : 25;
    focus.totalSeconds = state.focusDuration * 60;
    focus.remainingSeconds = focus.totalSeconds;
    saveState();
    renderFocus();
  }

  function renderFocus() {
    const task = ensureFocusTask();
    const duration = state.focusDuration || 8;
    if (!focus.running && focus.totalSeconds !== duration * 60) {
      focus.totalSeconds = duration * 60;
      focus.remainingSeconds = focus.totalSeconds;
    }

    $('#focusTaskTitle').textContent = task ? task.title : 'Добавь задачу и начни';
    $('#focusMicroStep').textContent = task ? task.micro : 'Никакого марафона. Только один ограниченный кусок.';
    $('#timerMainButton').textContent = focus.running ? 'Пауза' : focus.remainingSeconds < focus.totalSeconds ? 'Продолжить' : VIEW_COPY[state.tone].start;
    $('#timerStopButton').disabled = !focus.running && focus.remainingSeconds === focus.totalSeconds;
    $$('#durationPicker button').forEach(button => button.classList.toggle('is-active', Number(button.dataset.minutes) === duration));
    updateTimerUI();

    const panel = $('#selectedTaskPanel');
    if (!task) {
      panel.innerHTML = `<p class="eyebrow">ТЕКУЩАЯ ЗАДАЧА</p><h3>Пока пусто</h3><p>Добавь один конкретный шаг. Не проект, а действие.</p><button class="button button-primary full" data-action="new-task">Добавить</button>`;
      return;
    }
    panel.innerHTML = `
      <p class="eyebrow">В ЭТОМ РАУНДЕ</p>
      <h3>${escapeHtml(task.title)}</h3>
      <p>${escapeHtml(task.micro)}</p>
      <div class="task-meta">${taskMetaHtml(task)}</div>
      <button class="button button-ghost full" data-action="edit-task" data-task-id="${task.id}" style="margin-top:14px">Разобрать мельче</button>`;
  }

  function formatTimer(seconds) {
    const min = Math.floor(seconds / 60);
    const sec = seconds % 60;
    return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }

  function updateTimerUI() {
    $('#timerDisplay').textContent = formatTimer(Math.max(0, focus.remainingSeconds));
    $('#timerStatus').textContent = focus.running ? 'в фокусе' : focus.remainingSeconds < focus.totalSeconds ? 'пауза' : 'готов';
    const completed = focus.totalSeconds ? 1 - focus.remainingSeconds / focus.totalSeconds : 0;
    $('#timerRing').style.setProperty('--progress', `${completed * 360}deg`);
  }

  function startTimer() {
    if (!ensureFocusTask()) {
      openTaskEditor();
      return;
    }
    if (focus.running) return;
    focus.running = true;
    focus.startedAt ||= Date.now();
    focus.interval = window.setInterval(() => {
      focus.remainingSeconds -= 1;
      updateTimerUI();
      if (focus.remainingSeconds <= 0) completeRound(false);
    }, 1000);
    renderFocus();
  }

  function pauseTimer() {
    if (!focus.running) return;
    clearInterval(focus.interval);
    focus.interval = null;
    focus.running = false;
    renderFocus();
  }

  function stopTimer(openOutcome = true) {
    clearInterval(focus.interval);
    focus.interval = null;
    const elapsed = focus.totalSeconds - focus.remainingSeconds;
    focus.running = false;
    if (openOutcome && elapsed >= 15 && focus.taskId) {
      completeRound(true);
      return;
    }
    focus.startedAt = null;
    focus.remainingSeconds = focus.totalSeconds;
    updateTimerUI();
  }

  function completeRound(stoppedEarly) {
    clearInterval(focus.interval);
    focus.interval = null;
    focus.running = false;
    const elapsedSeconds = Math.max(15, focus.totalSeconds - Math.max(0, focus.remainingSeconds));
    pendingSession = {
      taskId: focus.taskId,
      elapsedSeconds,
      plannedMinutes: Math.round(focus.totalSeconds / 60),
      stoppedEarly
    };
    focus.remainingSeconds = 0;
    updateTimerUI();
    if ('vibrate' in navigator) navigator.vibrate?.([80, 50, 120]);
    openModal('roundModal');
  }

  function recordRound(outcome) {
    if (!pendingSession) return;
    const task = getTask(pendingSession.taskId);
    const minutes = Math.max(1, Math.round(pendingSession.elapsedSeconds / 60));
    const session = {
      id: uid(),
      taskId: pendingSession.taskId,
      taskTitle: task?.title || 'Удалённая задача',
      minutes,
      plannedMinutes: pendingSession.plannedMinutes,
      outcome,
      date: localDateKey(),
      createdAt: nowIso()
    };
    state.sessions.push(session);

    if (outcome === 'done' && task) {
      task.done = true;
      task.completedAt = nowIso();
      state.proofs.unshift({ id: uid(), text: `Закрыл: ${task.title}`, type: 'task', taskId: task.id, date: localDateKey(), createdAt: nowIso() });
      state.plans[localDateKey()] = generatePlan(false);
    } else {
      state.proofs.unshift({
        id: uid(),
        text: `${outcome === 'again' ? 'Сделал раунд по задаче' : 'Сделал часть'}: ${task?.title || 'задача'}`,
        type: task?.fear > 0 ? 'brave' : 'session',
        taskId: task?.id || null,
        date: localDateKey(),
        createdAt: nowIso()
      });
    }

    saveState();
    closeModal('roundModal');
    const repeat = outcome === 'again';
    pendingSession = null;
    focus.startedAt = null;
    focus.remainingSeconds = focus.totalSeconds;

    if (repeat && task && !task.done) {
      startTimer();
      showToast('Ещё один раунд. Без повышения ставки.');
    } else {
      renderAll();
      navigate('proof');
      showToast(outcome === 'done' ? 'Задача закрыта. Факт записан.' : 'Частичное выполнение засчитано.');
    }
  }

  function renderFocusTaskPicker() {
    const tasks = sortedCandidates('main');
    $('#focusTaskPicker').innerHTML = tasks.length
      ? tasks.map(task => `<button class="picker-task" data-action="pick-focus-task" data-task-id="${task.id}"><b>${escapeHtml(task.title)}</b><span>${escapeHtml(task.micro)} · ${task.duration} мин</span></button>`).join('')
      : `<div class="empty-state"><h3>Нет открытых задач</h3><p>Добавь один шаг и возвращайся.</p></div>`;
  }

  function proofIcon(type) {
    return ({ task: '✓', brave: '△', session: '◉', manual: '◆' })[type] || '·';
  }

  function renderProof() {
    const sessions = state.sessions;
    const totalMinutes = sessions.reduce((sum, session) => sum + (session.minutes || 0), 0);
    const doneTasks = state.tasks.filter(task => task.done).length;
    const brave = state.proofs.filter(proof => proof.type === 'brave').length + Object.values(state.ladder).filter(Boolean).length;
    const stats = [
      ['Раундов', sessions.length, 'раз появился'],
      ['Минут фокуса', totalMinutes, 'реальных минут'],
      ['Задач закрыто', doneTasks, 'без учёта частичных'],
      ['Смелых шагов', brave, 'навстречу страху']
    ];
    $('#statsGrid').innerHTML = stats.map(([label, value, hint]) => `<article class="stat-card"><span>${label}</span><strong>${value}</strong><small>${hint}</small></article>`).join('');

    const days = [];
    for (let offset = 6; offset >= 0; offset -= 1) {
      const date = new Date();
      date.setDate(date.getDate() - offset);
      const key = localDateKey(date);
      const daySessions = state.sessions.filter(session => session.date === key);
      const dayProofs = state.proofs.filter(proof => proof.date === key);
      days.push({ date, key, count: daySessions.length + dayProofs.length, minutes: daySessions.reduce((sum, session) => sum + (session.minutes || 0), 0) });
    }
    $('#weekStrip').innerHTML = days.map(day => `
      <div class="day-proof ${day.count ? 'has-proof' : ''} ${day.key === localDateKey() ? 'is-today' : ''}">
        <b>${new Intl.DateTimeFormat('ru-RU', { weekday: 'short' }).format(day.date)}</b>
        <strong>${day.count}</strong>
        <small>${day.minutes ? `${day.minutes} мин` : 'пусто — и ладно'}</small>
      </div>`).join('');

    const proofs = [...state.proofs].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
    $('#proofList').innerHTML = proofs.length
      ? proofs.map(proof => `
          <div class="proof-item">
            <span class="proof-item-icon">${proofIcon(proof.type)}</span>
            <div><b>${escapeHtml(proof.text)}</b><p>${new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(proof.createdAt))}</p></div>
          </div>`).join('')
      : `<div class="empty-state"><h3>Лента пока пустая</h3><p>Первый фокус-раунд появится здесь как доказательство.</p></div>`;

    $('#fearLadder').innerHTML = FEAR_LADDER_DEFAULT.map((step, index) => {
      const done = Boolean(state.ladder[step.id]);
      return `
        <div class="ladder-step ${done ? 'is-done' : ''}">
          <span>${done ? '✓' : index + 1}</span>
          <div><b>${escapeHtml(step.title)}</b><small>${escapeHtml(step.hint)}</small></div>
          <button data-action="toggle-ladder" data-step-id="${step.id}" aria-label="${done ? 'Отменить' : 'Отметить'}">${done ? '↶' : '○'}</button>
        </div>`;
    }).join('');
  }


  const DVIZH_WEEK_WEB_V1 = true;

  const DVIZH_WEEK_EDITOR_V1 = true;
  const WEEK_EDITOR_DAY_LABELS = ['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'];

  function weekStateObject() {
    if (!state.weeklySchedule || typeof state.weeklySchedule !== 'object') {
      state.weeklySchedule = { version: 1, timezone: 'Europe/Moscow', items: [], occurrences: [], webCommands: [] };
    }
    if (!Array.isArray(state.weeklySchedule.items)) state.weeklySchedule.items = [];
    if (!Array.isArray(state.weeklySchedule.occurrences)) state.weeklySchedule.occurrences = [];
    if (!Array.isArray(state.weeklySchedule.webCommands)) state.weeklySchedule.webCommands = [];
    return state.weeklySchedule;
  }

  function weekCommandId() {
    return `web-week-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function weekEnqueue(action, payload = {}) {
    const weekly = weekStateObject();
    const command = { id: weekCommandId(), action, ...payload, createdAt: nowIso() };
    weekly.webCommands = [...weekly.webCommands.slice(-19), command];
    weekly.webUpdatedAt = nowIso();
    saveState();
    return command;
  }

  function weekDateInCurrentRange(key) {
    const start = weekLocalKey(0);
    const end = weekLocalKey(6);
    return key >= start && key <= end;
  }

  function weekItemApplies(item, key) {
    const d = parseLocalDate(key);
    if (!item || item.enabled === false) return false;
    if (item.recurrence === 'once') return item.dateLocal === key;
    const mask = Number(item.weekdaysMask || 0);
    return Boolean(mask & (1 << d.getDay() === 0 ? 6 : d.getDay() - 1));
  }

  function weekWeekdayIndexFromKey(key) {
    const d = parseLocalDate(key);
    const js = d.getDay();
    return js === 0 ? 6 : js - 1;
  }

  function weekRuleApplies(item, key) {
    if (!item || item.enabled === false) return false;
    if (item.recurrence === 'once') return item.dateLocal === key;
    const mask = Number(item.weekdaysMask || 0);
    return Boolean(mask & (1 << weekWeekdayIndexFromKey(key)));
  }

  function weekRebuildOptimisticOccurrences(item) {
    const weekly = weekStateObject();
    const keep = weekly.occurrences.filter(occ => String(occ.scheduleItemId) !== String(item.id) || occ.status !== 'pending');
    const blocked = new Set(keep.filter(occ => String(occ.scheduleItemId) === String(item.id) && occ.status !== 'pending').map(occ => occ.dueDate));
    const added = [];
    for (let offset = 0; offset < 7; offset += 1) {
      const dueDate = weekLocalKey(offset);
      if (!weekRuleApplies(item, dueDate) || blocked.has(dueDate)) continue;
      added.push({
        id: `web-pending-occ-${item.id}-${dueDate}`,
        scheduleItemId: item.id,
        title: item.title,
        kind: item.kind,
        kindLabel: (WEEK_KIND[item.kind] || WEEK_KIND.other)[1],
        dueDate,
        startLocal: item.startLocal,
        durationMinutes: Number(item.durationMinutes || 0),
        reminderMinutes: Number(item.reminderMinutes || 0),
        status: 'pending',
        source: 'web-pending'
      });
    }
    weekly.occurrences = keep.concat(added);
  }

  function weekOptimisticCreate(command) {
    const weekly = weekStateObject();
    const item = {
      id: `web-temp-${command.id}`,
      title: command.title,
      kind: command.kind,
      kindLabel: (WEEK_KIND[command.kind] || WEEK_KIND.other)[1],
      recurrence: command.recurrence,
      dateLocal: command.dateLocal || null,
      weekdaysMask: command.weekdaysMask || null,
      startLocal: command.startLocal,
      durationMinutes: Number(command.durationMinutes),
      reminderMinutes: Number(command.reminderMinutes),
      enabled: true,
      source: 'web-pending'
    };
    weekly.items.push(item);
    weekRebuildOptimisticOccurrences(item);
  }

  function weekOptimisticUpdate(command) {
    const weekly = weekStateObject();
    const item = weekly.items.find(row => String(row.id) === String(command.itemId));
    if (!item) return;
    Object.assign(item, {
      title: command.title, kind: command.kind, recurrence: command.recurrence,
      dateLocal: command.dateLocal || null, weekdaysMask: command.weekdaysMask || null,
      startLocal: command.startLocal, durationMinutes: Number(command.durationMinutes),
      reminderMinutes: Number(command.reminderMinutes)
    });
    weekRebuildOptimisticOccurrences(item);
  }

  function weekOptimisticEnabled(itemId, enabled) {
    const weekly = weekStateObject();
    const item = weekly.items.find(row => String(row.id) === String(itemId));
    if (!item) return;
    item.enabled = Boolean(enabled);
    weekRebuildOptimisticOccurrences(item);
  }

  function weekOptimisticDelete(itemId) {
    const weekly = weekStateObject();
    weekly.items = weekly.items.filter(item => String(item.id) !== String(itemId));
    weekly.occurrences = weekly.occurrences.filter(item => String(item.scheduleItemId) !== String(itemId));
  }

  function weekEditorToggleRecurrence() {
    const recurrence = $('#weekEditorRecurrence')?.value || 'once';
    const once = $('#weekEditorDateField');
    const weekly = $('#weekEditorWeekdaysField');
    if (once) once.hidden = recurrence !== 'once';
    if (weekly) weekly.hidden = recurrence !== 'weekly';
  }

  function weekEditorResetDays(mask = 0) {
    document.querySelectorAll('#weekEditorWeekdaysField [data-weekday]').forEach(input => {
      input.checked = Boolean(Number(mask || 0) & (1 << Number(input.dataset.weekday)));
    });
  }

  function weekEditorOpen(itemId = '') {
    const panel = $('#weekEditorPanel');
    const form = $('#weekEditorForm');
    if (!panel || !form) return;
    form.reset();
    $('#weekEditorItemId').value = '';
    $('#weekEditorTime').value = '18:00';
    $('#weekEditorDuration').value = '60';
    $('#weekEditorReminder').value = '30';
    $('#weekEditorDate').value = weekLocalKey(0);
    weekEditorResetDays(0);
    let item = null;
    if (itemId) item = weekStateObject().items.find(row => String(row.id) === String(itemId));
    if (item) {
      $('#weekEditorItemId').value = item.id;
      $('#weekEditorName').value = item.title || '';
      $('#weekEditorKind').value = item.kind || 'other';
      $('#weekEditorRecurrence').value = item.recurrence || 'once';
      $('#weekEditorDate').value = item.dateLocal || weekLocalKey(0);
      $('#weekEditorTime').value = item.startLocal || '18:00';
      $('#weekEditorDuration').value = String(item.durationMinutes || 60);
      $('#weekEditorReminder').value = String(item.reminderMinutes ?? 30);
      weekEditorResetDays(item.weekdaysMask || 0);
      $('#weekEditorTitle').textContent = 'Редактировать событие';
    } else {
      $('#weekEditorTitle').textContent = 'Новое событие';
    }
    weekEditorToggleRecurrence();
    panel.hidden = false;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    setTimeout(() => $('#weekEditorName')?.focus(), 150);
  }

  function weekEditorClose() {
    const panel = $('#weekEditorPanel');
    if (panel) panel.hidden = true;
  }

  function weekEditorPayload() {
    const recurrence = $('#weekEditorRecurrence').value;
    const title = $('#weekEditorName').value.trim();
    if (!title) throw new Error('Напиши название события.');
    const duration = Number($('#weekEditorDuration').value);
    if (!Number.isFinite(duration) || duration < 5 || duration > 720) throw new Error('Длительность: от 5 до 720 минут.');
    let weekdaysMask = null;
    let dateLocal = null;
    if (recurrence === 'once') {
      dateLocal = $('#weekEditorDate').value;
      if (!dateLocal) throw new Error('Выбери дату.');
    } else {
      weekdaysMask = 0;
      document.querySelectorAll('#weekEditorWeekdaysField [data-weekday]:checked').forEach(input => {
        weekdaysMask |= 1 << Number(input.dataset.weekday);
      });
      if (!weekdaysMask) throw new Error('Выбери хотя бы один день недели.');
    }
    return {
      title,
      kind: $('#weekEditorKind').value,
      recurrence,
      dateLocal,
      weekdaysMask,
      startLocal: $('#weekEditorTime').value,
      durationMinutes: duration,
      reminderMinutes: Number($('#weekEditorReminder').value)
    };
  }

  function weekEditorSubmit() {
    try {
      const payload = weekEditorPayload();
      const itemId = $('#weekEditorItemId').value;
      if (itemId) {
        if (String(itemId).startsWith('web-temp-')) {
          showToast('Подожди несколько секунд: это событие ещё сохраняется на сервере.');
          return;
        }
        const command = weekEnqueue('update', { itemId, ...payload });
        weekOptimisticUpdate(command);
        showToast('Изменение отправлено в Telegram.');
      } else {
        const command = weekEnqueue('create', payload);
        weekOptimisticCreate(command);
        showToast('Событие создано. Telegram подхватит его автоматически.');
      }
      saveState();
      weekEditorClose();
      renderWeek();
    } catch (error) {
      showToast(error?.message || 'Проверь поля события.');
    }
  }

  function weekDaysDescription(mask) {
    const value = Number(mask || 0);
    if (value === 127) return 'каждый день';
    return WEEK_EDITOR_DAY_LABELS.filter((_, index) => value & (1 << index)).join(' · ') || 'дни не выбраны';
  }

  function renderWeekEditorManager() {
    const root = $('#weekScheduleRules');
    if (!root) return;
    const weekly = weekStateObject();
    const queue = $('#weekEditorQueueStatus');
    if (queue) {
      const count = weekly.webCommands.length;
      queue.textContent = count ? `${count} изм. отправлено · обычно до 20 секунд` : 'Изменения с сайта уходят в Telegram и напоминания автоматически.';
    }
    const items = weekly.items.slice().sort((a, b) => String(a.startLocal || '').localeCompare(String(b.startLocal || '')));
    if (!items.length) {
      root.innerHTML = '<div class="week-empty">Расписание пока пустое. Добавь первое событие здесь или в Telegram.</div>';
      return;
    }
    root.innerHTML = items.map(item => {
      const [icon, kind] = WEEK_KIND[item.kind] || WEEK_KIND.other;
      const recurrence = item.recurrence === 'once'
        ? `один раз · ${escapeHtml(item.dateLocal || '—')}`
        : `еженедельно · ${escapeHtml(weekDaysDescription(item.weekdaysMask))}`;
      const pending = String(item.id).startsWith('web-temp-');
      const disabled = item.enabled === false;
      return `<article class="week-rule ${disabled ? 'is-disabled' : ''} ${pending ? 'is-pending' : ''}">
        <div class="week-rule-main"><span class="week-rule-icon">${icon}</span><div><b>${escapeHtml(item.title || 'Событие')}</b><small>${escapeHtml(kind)} · ${recurrence}<br>${escapeHtml(item.startLocal || '--:--')} · ${Number(item.durationMinutes || 0)} мин · ${Number(item.reminderMinutes || 0) ? `напомнить −${Number(item.reminderMinutes)} мин` : 'в момент начала'}</small></div></div>
        <div class="week-rule-actions">
          ${pending ? '<span class="week-rule-saving">сохраняется…</span>' : `
          <button type="button" data-week-rule-edit="${escapeHtml(item.id)}">Изменить</button>
          <button type="button" data-week-rule-toggle="${escapeHtml(item.id)}" data-enabled="${disabled ? '1' : '0'}">${disabled ? 'Включить' : 'Пауза'}</button>
          <button type="button" class="danger" data-week-rule-delete="${escapeHtml(item.id)}">Удалить</button>`}
        </div>
      </article>`;
    }).join('');
  }

  const WEEK_KIND = {
    work: ['💼', 'Работа'],
    rest: ['🛋', 'Отдых'],
    friend: ['🤝', 'Встреча'],
    errand: ['📍', 'Дела'],
    documents: ['📄', 'Документы'],
    health: ['🩺', 'Здоровье'],
    gym: ['🏋️', 'Зал'],
    volleyball: ['🏐', 'Волейбол'],
    social: ['📱', 'Соцсети'],
    other: ['•', 'Разное']
  };

  function getWeeklySchedule() {
    const value = state.weeklySchedule;
    if (!value || typeof value !== 'object') {
      return { timezone: 'Europe/Moscow', occurrences: [], syncedAt: null };
    }
    return {
      timezone: value.timezone || 'Europe/Moscow',
      occurrences: Array.isArray(value.occurrences) ? value.occurrences : [],
      syncedAt: value.syncedAt || value.updatedAt || null
    };
  }

  function weekLocalKey(offset = 0) {
    const date = new Date();
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() + offset);
    return localDateKey(date);
  }

  function renderWeek() {
    const root = $('#weekScheduleGrid');
    if (!root) return;
    const weekly = getWeeklySchedule();
    const occurrences = weekly.occurrences;
    const byDay = new Map();
    occurrences.forEach(item => {
      if (!item || !item.dueDate) return;
      if (!byDay.has(item.dueDate)) byDay.set(item.dueDate, []);
      byDay.get(item.dueDate).push(item);
    });

    const days = Array.from({ length: 7 }, (_, offset) => {
      const key = weekLocalKey(offset);
      const date = parseLocalDate(key);
      const items = (byDay.get(key) || []).sort((a, b) => String(a.startLocal || '').localeCompare(String(b.startLocal || '')));
      const weekday = new Intl.DateTimeFormat('ru-RU', { weekday: 'short' }).format(date).replace('.', '').toUpperCase();
      const dayMonth = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(date);
      const cards = items.length ? items.map(item => {
        const [icon, kind] = WEEK_KIND[item.kind] || WEEK_KIND.other;
        const status = item.status || 'pending';
        const statusLabel = status === 'done' ? 'готово' : status === 'skipped' ? 'пропущено' : '';
        const actions = status === 'pending' ? `
          <div class="week-event-actions">
            <button data-action="week-event-done" data-schedule-occurrence-id="${escapeHtml(item.id)}">✓ Готово</button>
            <button data-action="week-event-skip" data-schedule-occurrence-id="${escapeHtml(item.id)}">— Пропустить</button>
          </div>` : `<span class="week-event-status">${status === 'done' ? '✓' : '—'} ${statusLabel}</span>`;
        return `
          <article class="week-event is-${escapeHtml(status)}" data-kind="${escapeHtml(item.kind || 'other')}">
            <div class="week-event-time">${escapeHtml(item.startLocal || '--:--')}</div>
            <div class="week-event-body">
              <div class="week-event-kind">${icon} ${escapeHtml(kind)}</div>
              <b>${escapeHtml(item.title || 'Событие')}</b>
              <small>${Number(item.durationMinutes || 0)} мин${item.reminderMinutes ? ` · напоминание −${Number(item.reminderMinutes)} мин` : ''}</small>
              ${actions}
            </div>
          </article>`;
      }).join('') : `<div class="week-empty">Свободно. Не нужно заполнять день ради заполнения.</div>`;
      return `
        <section class="week-day ${offset === 0 ? 'is-today' : ''}">
          <header><span>${weekday}</span><b>${dayMonth}</b></header>
          <div class="week-day-events">${cards}</div>
        </section>`;
    }).join('');

    root.innerHTML = days;
    const status = $('#weekSyncStatus');
    if (status) {
      if (!weekly.syncedAt) status.textContent = 'ждём первую синхронизацию';
      else {
        const when = new Date(weekly.syncedAt);
        status.textContent = Number.isNaN(when.getTime())
          ? 'синхронизировано'
          : `обновлено ${new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(when)}`;
      }
    }
  }


  const renderWeekWithoutEditor = renderWeek;
  renderWeek = function renderWeekWithEditor() {
    renderWeekWithoutEditor();
    renderWeekEditorManager();
  };

  document.addEventListener('click', event => {
    const target = event.target.closest('button');
    if (!target) return;
    if (target.id === 'weekEditorNew') {
      event.preventDefault(); weekEditorOpen(); return;
    }
    if (target.id === 'weekEditorCancel') {
      event.preventDefault(); weekEditorClose(); return;
    }
    if (target.dataset.weekRuleEdit) {
      event.preventDefault(); weekEditorOpen(target.dataset.weekRuleEdit); return;
    }
    if (target.dataset.weekRuleToggle) {
      event.preventDefault();
      const itemId = target.dataset.weekRuleToggle;
      const enabled = target.dataset.enabled === '1';
      weekEnqueue('set_enabled', { itemId, enabled });
      weekOptimisticEnabled(itemId, enabled);
      saveState(); renderWeek();
      showToast(enabled ? 'Событие снова активно.' : 'Пауза: новые напоминания выключены.');
      return;
    }
    if (target.dataset.weekRuleDelete) {
      event.preventDefault();
      const itemId = target.dataset.weekRuleDelete;
      const item = weekStateObject().items.find(row => String(row.id) === String(itemId));
      if (!confirm(`Удалить «${item?.title || 'событие'}» целиком?`)) return;
      weekEnqueue('delete', { itemId });
      weekOptimisticDelete(itemId);
      saveState(); renderWeek();
      showToast('Событие удаляется из общего расписания.');
    }
  });

  document.addEventListener('change', event => {
    if (event.target?.id === 'weekEditorRecurrence') weekEditorToggleRecurrence();
  });

  document.addEventListener('submit', event => {
    if (event.target?.id !== 'weekEditorForm') return;
    event.preventDefault();
    weekEditorSubmit();
  });

  function setWeekOccurrenceStatus(id, status) {
    if (!['done', 'skipped'].includes(status)) return;
    if (!state.weeklySchedule || !Array.isArray(state.weeklySchedule.occurrences)) return;
    const occurrence = state.weeklySchedule.occurrences.find(item => String(item.id) === String(id));
    if (!occurrence || occurrence.status !== 'pending') return;
    occurrence.status = status;
    occurrence.webUpdatedAt = nowIso();
    state.weeklySchedule.webUpdatedAt = nowIso();
    saveState();
    renderWeek();
    showToast(status === 'done' ? 'Блок отмечен выполненным.' : 'Пропущен только этот экземпляр.');
  }


  const DVIZH_TRAINING_WEB_V1 = true;
  const TRAINING_DAY_NAMES = ['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'];
  const TRAINING_ACTIVITY_NAMES = {upper_a:'Верх A',lower_a:'Низ A',upper_b:'Верх B',lower_b:'Низ B',volleyball:'Волейбол',recovery:'Восстановление',other:'Другая'};

  function trainingHub() {
    if (!state.trainingHub || typeof state.trainingHub !== 'object') {
      state.trainingHub = {version:1,profile:{planEnabled:false},planSlots:[],sessions:[],upcoming:[],metrics:{load7d:0,baselineWeeklyLoad:null,lowerLoad36h:0},readiness:null,webCommands:[],commandResults:[]};
    }
    if (!Array.isArray(state.trainingHub.webCommands)) state.trainingHub.webCommands = [];
    if (!Array.isArray(state.trainingHub.planSlots)) state.trainingHub.planSlots = [];
    if (!Array.isArray(state.trainingHub.sessions)) state.trainingHub.sessions = [];
    if (!Array.isArray(state.trainingHub.upcoming)) state.trainingHub.upcoming = [];
    return state.trainingHub;
  }

  function trainingCommandId() { return `web-training-${Date.now()}-${Math.random().toString(36).slice(2,9)}`; }
  function trainingEnqueue(action, payload={}) {
    const hub=trainingHub();
    const command={id:trainingCommandId(),action,...payload,createdAt:nowIso()};
    hub.webCommands=[...hub.webCommands.slice(-19),command];
    hub.webUpdatedAt=nowIso();
    saveState();
    return command;
  }

  function trainingClientReadiness(input) {
    let score=100; const reasons=[]; let stop=false; let urgent=false;
    const sleep=Number(input.sleepHours||0), sq=Number(input.sleepQuality||0), energy=Number(input.energy||0), sore=Number(input.soreness||0), pain=Number(input.pain||0), stress=Number(input.stress||0);
    if (input.redFlag) { stop=true; urgent=true; reasons.push('Есть опасный симптом: тренировку не начинать.'); }
    if (input.illness==='systemic') { stop=true; reasons.push('Температура, ломота или выраженная слабость.'); }
    else if (input.illness==='mild') { score-=12; reasons.push('Лёгкая простуда: только лёгкая нагрузка.'); }
    if (pain>=3) { stop=true; reasons.push('Сильная или ограничивающая движение боль.'); } else if (pain===2) { score-=24; reasons.push('Заметная боль.'); } else if (pain===1) score-=8;
    if (sleep<5) { score-=30; reasons.push('Сна меньше 5 часов.'); } else if (sleep<6) { score-=20; reasons.push('Сна меньше 6 часов.'); } else if (sleep<7) { score-=10; reasons.push('Сна меньше 7 часов.'); }
    score-=(3-sq)*6; score-=({0:32,1:20,2:7,3:0}[energy]||0); score-=({0:0,1:5,2:15,3:27}[sore]||0); score-=({0:0,1:3,2:9,3:16}[stress]||0);
    if (energy<=1) reasons.push('Энергии мало.'); if (sore>=2) reasons.push('Мышцы заметно не восстановились.'); if (stress>=2) reasons.push('Высокая психическая нагрузка.');
    const context=trainingHub().todayContext||{}, metrics=trainingHub().metrics||{};
    if (context.volleyball_today && context.lower_today) { score-=14; reasons.push('Волейбол и низ попали на один день.'); }
    if (context.volleyball_today && Number(metrics.lowerLoad36h||0)>=450) { score-=22; reasons.push('Высокая нагрузка на ноги за 36 часов.'); }
    else if (context.volleyball_today && Number(metrics.lowerLoad36h||0)>=250) { score-=12; reasons.push('Ноги уже нагружались за 36 часов.'); }
    score=Math.max(0,Math.min(100,Math.round(score)));
    let status,label,strength_text,volleyball_text,rpe_cap,volume_factor;
    if (stop||score<45) { status='red';label='Красный день';strength_text='Без тяжёлой силовой. Отдых или очень лёгкое восстановление без боли.';volleyball_text='Полноценный волейбол и прыжковую работу сегодня пропусти.';rpe_cap=3;volume_factor=0; }
    else if (score<75) { status='yellow';label='Жёлтый день';strength_text='Убери 30–50% объёма, без отказа и максимумов.';volleyball_text='Техника/приём/подача или короткая игра; сократи прыжки.';rpe_cap=6;volume_factor=.6; }
    else { status='green';label='Зелёный день';strength_text='Можно плановую силовую, оставляя запас и не работая через боль.';volleyball_text='Можно играть по плану, контролируя самочувствие.';rpe_cap=8;volume_factor=1; }
    if (!reasons.length) reasons.push('Сон, энергия, боль и недавняя нагрузка выглядят нормально.');
    return {score,status,label,strength_text,volleyball_text,rpe_cap,volume_factor,reasons:reasons.slice(0,8),urgent};
  }

  function renderTraining() {
    const hub=trainingHub(); const readiness=hub.readiness?.result||hub.optimisticReadiness||null;
    const card=$('#trainingReadinessCard'), title=$('#trainingReadinessTitle'), score=$('#trainingReadinessScore');
    if (card) card.dataset.status=readiness?.status||'unknown';
    if (title) title.textContent=readiness?.label||'Ещё не проверена';
    if (score) score.textContent=readiness?`${Number(readiness.score||0)}/100`:'—';
    const strength=$('#trainingStrengthAdvice'); if (strength) strength.textContent=readiness?`Силовая: ${readiness.strength_text||'—'}`:'Одна минута на сон, энергию, боль и забитость — затем ДВИЖ даст предел нагрузки.';
    const volley=$('#trainingVolleyballAdvice'); if (volley) volley.textContent=readiness?`Волейбол: ${readiness.volleyball_text||'—'}`:'';
    const reasons=$('#trainingReasons'); if (reasons) reasons.innerHTML=readiness?`<b>Предел: RPE ${Number(readiness.rpe_cap||0)}/10</b>${(readiness.reasons||[]).map(x=>`<span>• ${escapeHtml(x)}</span>`).join('')}`:'';
    const metrics=hub.metrics||{}; if ($('#trainingLoad7d')) $('#trainingLoad7d').textContent=String(metrics.load7d||0); if ($('#trainingBaseline')) $('#trainingBaseline').textContent=metrics.baselineWeeklyLoad==null?'—':String(metrics.baselineWeeklyLoad); if ($('#trainingLower36')) $('#trainingLower36').textContent=String(metrics.lowerLoad36h||0);
    const planEnabled=Boolean(hub.profile?.planEnabled); const planButton=$('#trainingPlanButton'); if (planButton) { planButton.textContent=planEnabled?'Пауза':'Включить'; planButton.dataset.trainingAction=planEnabled?'disable-plan':'enable-plan'; }
    const slots=$('#trainingPlanSlots'); if (slots) slots.innerHTML=(hub.planSlots||[]).length?(hub.planSlots||[]).map(slot=>`<div class="training-plan-row"><b>${escapeHtml(TRAINING_DAY_NAMES[Number(slot.weekday||0)]||'—')} ${escapeHtml(slot.startLocal||'')}</b><span>${escapeHtml(slot.title||slot.code)} · ${Number(slot.durationMinutes||0)} мин</span></div>`).join(''):'<div class="training-empty">План ещё не включён.</div>';
    const upcoming=$('#trainingUpcoming'); if (upcoming) upcoming.innerHTML=(hub.upcoming||[]).filter(x=>x.status==='pending').slice(0,8).map(x=>`<div class="training-upcoming-row"><b>${escapeHtml(x.dueDate||'')} · ${escapeHtml(x.title||'')}</b><span>${x.kind==='volleyball'?'🏐':'🏋️'} ${escapeHtml(x.code||'')}</span></div>`).join('')||'<div class="training-empty">На ближайшие дни спортивных блоков нет.</div>';
    const history=$('#trainingHistory'); if (history) history.innerHTML=(hub.sessions||[]).slice(0,12).map(x=>`<div class="training-history-row"><div><b>${escapeHtml(x.activityLabel||TRAINING_ACTIVITY_NAMES[x.activity]||x.activity)}</b><span>${escapeHtml(x.date||'')} · ${Number(x.durationMinutes||0)} мин · RPE ${Number(x.rpe||0)}</span></div><strong>${Number(x.load||0)} AU</strong></div>`).join('')||'<div class="training-empty">Пока нет записанных тренировок.</div>';
    const sync=$('#trainingSyncStatus'); if (sync) { const pending=(hub.webCommands||[]).length; sync.textContent=pending?`сохраняю: ${pending}`:(hub.syncedAt?'синхронизировано':'ждём синхронизацию'); }
  }

  function trainingOpen(id, open=true) { const el=$(id); if (el) { el.hidden=!open; if (open) el.scrollIntoView({behavior:'smooth',block:'nearest'}); } }
  function trainingDefaultPlan() { return [{code:'upper_a',title:'Силовая · Верх A',weekday:0,startLocal:'19:00',durationMinutes:75},{code:'lower_a',title:'Силовая · Низ A',weekday:1,startLocal:'19:00',durationMinutes:75},{code:'upper_b',title:'Силовая · Верх B',weekday:3,startLocal:'19:00',durationMinutes:75},{code:'lower_b',title:'Силовая · Низ B',weekday:5,startLocal:'14:00',durationMinutes:75}]; }

  document.addEventListener('click', event => {
    const button=event.target.closest('[data-training-action]'); if (!button) return;
    const action=button.dataset.trainingAction;
    if (action==='open-readiness') trainingOpen('#trainingReadinessFormPanel',true);
    else if (action==='close-readiness') trainingOpen('#trainingReadinessFormPanel',false);
    else if (action==='open-session') trainingOpen('#trainingSessionFormPanel',true);
    else if (action==='close-session') trainingOpen('#trainingSessionFormPanel',false);
    else if (action==='enable-plan') { const hub=trainingHub(); trainingEnqueue('plan_enable'); hub.profile={...(hub.profile||{}),planEnabled:true}; if (!(hub.planSlots||[]).length) hub.planSlots=trainingDefaultPlan(); saveState(); renderTraining(); showToast('План 4× включается. Дни и время можно менять в «Неделе».'); }
    else if (action==='disable-plan') { const hub=trainingHub(); trainingEnqueue('plan_disable'); hub.profile={...(hub.profile||{}),planEnabled:false}; saveState(); renderTraining(); showToast('План поставлен на паузу.'); }
  });

  document.addEventListener('submit', event => {
    if (event.target?.id==='trainingReadinessForm') {
      event.preventDefault(); const payload={sleepHours:Number($('#trainingSleepHours').value),sleepQuality:Number($('#trainingSleepQuality').value),energy:Number($('#trainingEnergy').value),soreness:Number($('#trainingSoreness').value),pain:Number($('#trainingPain').value),stress:Number($('#trainingStress').value),illness:$('#trainingIllness').value,redFlag:Boolean($('#trainingRedFlag').checked)};
      if (!Number.isFinite(payload.sleepHours)||payload.sleepHours<0||payload.sleepHours>16) return showToast('Проверь часы сна.');
      const result=trainingClientReadiness(payload); const hub=trainingHub(); trainingEnqueue('readiness_save',payload); hub.optimisticReadiness=result; hub.readiness={localDate:localDateKey(new Date()),result,updatedAt:nowIso(),source:'web-pending'}; saveState(); trainingOpen('#trainingReadinessFormPanel',false); renderTraining(); showToast(result.status==='red'?'Сегодня не давим нагрузку.':'Готовность рассчитана.');
    }
    if (event.target?.id==='trainingSessionForm') {
      event.preventDefault(); const activity=$('#trainingActivity').value,durationMinutes=Number($('#trainingDuration').value),rpe=Number($('#trainingRpe').value),result=$('#trainingResult').value,painAfter=Number($('#trainingPainAfter').value),jumps=$('#trainingJumps').value===''?null:Number($('#trainingJumps').value);
      if (!Number.isFinite(durationMinutes)||durationMinutes<1||durationMinutes>720||!Number.isFinite(rpe)||rpe<0||rpe>10) return showToast('Проверь минуты и RPE.');
      const command=trainingEnqueue('session_log',{activity,durationMinutes,rpe,result,painAfter,jumps}); const hub=trainingHub(); hub.sessions=[{id:`web-temp-${command.id}`,activity,activityLabel:TRAINING_ACTIVITY_NAMES[activity]||activity,date:localDateKey(new Date()),durationMinutes,rpe,load:result==='skipped'?0:durationMinutes*rpe,result,painAfter,jumps,createdAt:nowIso(),source:'web-pending'},...(hub.sessions||[])]; saveState(); trainingOpen('#trainingSessionFormPanel',false); renderTraining(); showToast('Тренировка записывается.');
    }
  });


  const DVIZH_JUMP_LAB_V1 = true;
  const JUMP_DAY_NAMES = {upper_a:'Верх A',lower_a:'Низ A · сила и приземление',upper_b:'Верх B',lower_b:'Низ B · мощность и разбег',volleyball:'Волейбол',recovery:'Восстановление'};
  const JUMP_CATEGORY_NAMES = {warmup:'Разминка',landing:'Приземление',jump:'Прыжок',strength:'Сила',unilateral:'Односторонняя сила',posterior_chain:'Задняя цепь',calf:'Стопа / голень',core:'Корпус',upper_strength:'Верх тела',prehab:'Профилактика',mobility:'Мобильность',recovery:'Восстановление',volleyball_skill:'Волейбольный навык'};

  function jumpHub() {
    if (!state.jumpLab || typeof state.jumpLab !== 'object') state.jumpLab={version:1,profile:{},progress:{},exercises:[],measurements:[],today:{dayCode:'recovery',exercises:[]},webCommands:[],commandResults:[]};
    const hub=state.jumpLab;
    if (!Array.isArray(hub.webCommands)) hub.webCommands=[];
    if (!Array.isArray(hub.exercises)) hub.exercises=[];
    if (!Array.isArray(hub.measurements)) hub.measurements=[];
    if (!hub.profile || typeof hub.profile!=='object') hub.profile={};
    if (!hub.progress || typeof hub.progress!=='object') hub.progress={};
    if (!hub.today || typeof hub.today!=='object') hub.today={dayCode:'recovery',exercises:[]};
    return hub;
  }

  function jumpCommandId() { return `web-jump-${Date.now()}-${Math.random().toString(36).slice(2,9)}`; }
  function jumpEnqueue(action,payload={}) {
    const hub=jumpHub(); const command={id:jumpCommandId(),action,...payload,createdAt:nowIso()};
    hub.webCommands=[...hub.webCommands.slice(-29),command]; hub.webUpdatedAt=nowIso(); saveState(); return command;
  }
  function jumpValue(id,value='') { const el=$(id); if (el && document.activeElement!==el) el.value=value==null?'':String(value); }
  function jumpText(id,value='—') { const el=$(id); if (el) el.textContent=value==null?'—':String(value); }
  function jumpNumber(value,fallback=0) { const n=Number(value); return Number.isFinite(n)?n:fallback; }
  function jumpCurrentDay() { const hub=jumpHub(); return hub.selectedDay||hub.today?.dayCode||'lower_a'; }
  function jumpExerciseById(id) { return jumpHub().exercises.find(row=>String(row.id)===String(id)); }

  function renderJumpLab() {
    const root=$('#jumpLab'); if (!root) return;
    const hub=jumpHub(), p=hub.profile||{}, progress=hub.progress||{}, today=hub.today||{};
    jumpText('#jumpCurrentCm',jumpNumber(progress.currentApproachJumpCm,p.currentApproachJumpCm||80).toFixed(0));
    jumpText('#jumpTargetCm',jumpNumber(progress.targetApproachJumpCm,p.targetApproachJumpCm||140).toFixed(0));
    jumpText('#jumpNextMilestone',jumpNumber(progress.nextMilestoneCm,85).toFixed(0));
    jumpText('#jumpNextMilestoneText',`${jumpNumber(progress.nextMilestoneCm,85).toFixed(0)} см`);
    jumpText('#jumpWeightMetric',`${jumpNumber(progress.currentWeightKg,p.currentWeightKg||47).toFixed(1)} → ${jumpNumber(progress.weightTargetKg,p.weightTargetKg||50).toFixed(1)}`);
    jumpText('#jumpSquatMetric',`≈${jumpNumber(progress.estimatedSquat1rmKg,0).toFixed(0)}`);
    jumpText('#jumpRelativeSquat',`${jumpNumber(progress.estimatedSquat1rmPerKg,0).toFixed(2)}×`);
    jumpText('#jumpProgramWeek',`${jumpNumber(p.programWeek,1)}/4`);

    const reviewed=Boolean(p.programReviewed), medical=p.medicalStatus||'unknown';
    jumpText('#jumpReviewTitle',reviewed?`Проверена: ${p.reviewedBy||'тренер'}`:'Программа пока черновик');
    jumpText('#jumpReviewText',reviewed
      ? `${p.reviewedRole||'тренер'} · ${p.reviewedAt?new Date(p.reviewedAt).toLocaleDateString('ru-RU'):''}. Любое изменение упражнения снова снимает отметку.`
      : `Медицинский статус: ${medical==='cleared'?'допуск отмечен':medical==='restrictions'?'ограничения внесены':'ограничения не внесены'}. Максимальные упражнения 🧑‍🏫 удерживаются до очной проверки.`);
    const safety=$('#jumpSafetyCard'); if (safety) safety.dataset.reviewed=reviewed?'yes':'no';

    const readiness=today.readiness||null, status=readiness?.status||'unknown';
    jumpText('#jumpTodayTitle',today.dayLabel||JUMP_DAY_NAMES[today.dayCode]||'Сегодня');
    jumpText('#jumpTodayReadiness',readiness?`${status==='green'?'🟢':status==='yellow'?'🟡':'🔴'} ${jumpNumber(readiness.score,0)}/100`:'⚪️ осторожный режим');
    const todayRoot=$('#jumpTodayExercises');
    if (todayRoot) todayRoot.innerHTML=(today.exercises||[]).map(row=>{
      const held=['skip','review_hold'].includes(row.status); const dose=held?'не выполнять':`${jumpNumber(row.adapted_sets)}×${escapeHtml(row.reps||'')} · RPE ≤${jumpNumber(row.rpe_cap)}`;
      const contacts=!held&&jumpNumber(row.adapted_contacts)>0?` · ${jumpNumber(row.adapted_contacts)} контактов`:'';
      return `<div class="jump-today-row is-${escapeHtml(row.status||'ready')}"><div><b>${held?'⏸':'✓'} ${escapeHtml(row.title||'')}</b><span>${dose}${contacts}</span></div><small>${escapeHtml(row.adaptation_note||row.load_rule||'')}</small></div>`;
    }).join('')||'<div class="jump-empty">На сегодня программа не выбрана.</div>';

    jumpValue('#jumpAge',p.age??19); jumpValue('#jumpHeight',p.heightCm??156); jumpValue('#jumpCurrentWeight',p.currentWeightKg??47); jumpValue('#jumpWeightTarget',p.weightTargetKg??50);
    jumpValue('#jumpCurrentApproach',p.currentApproachJumpCm??80); jumpValue('#jumpTargetApproach',p.targetApproachJumpCm??140); jumpValue('#jumpStandingReach',p.standingReachCm??'');
    jumpValue('#jumpSquatWeight',p.squatWeightKg??80); jumpValue('#jumpSquatReps',p.squatReps??8); jumpValue('#jumpScoliosisGrade',p.scoliosisGrade??2); jumpValue('#jumpCobbAngle',p.cobbAngleDeg??'');
    jumpValue('#jumpPhase',p.phase||'foundation'); jumpValue('#jumpBlockWeek',p.programWeek||1); jumpValue('#jumpMedicalStatus',p.medicalStatus||'unknown');
    jumpValue('#jumpPrimaryRole',p.primaryRole||'outside'); jumpValue('#jumpSecondaryRole',p.secondaryRole||'libero'); jumpValue('#jumpCurvePattern',p.curvePattern||''); jumpValue('#jumpSymptoms',p.symptoms||''); jumpValue('#jumpMedicalNotes',p.medicalNotes||'');
    jumpValue('#jumpVolleyballCoach',p.volleyballCoach||''); jumpValue('#jumpStrengthCoach',p.strengthCoach||''); jumpValue('#jumpCoachNotes',p.coachNotes||'');
    const summary=$('#jumpProfileSummary'); if (summary) summary.innerHTML=`<span>Рост <b>${jumpNumber(p.heightCm,156)} см</b></span><span>Вес <b>${jumpNumber(p.currentWeightKg,47)} кг</b></span><span>Прыжок <b>${jumpNumber(p.currentApproachJumpCm,80)} см</b></span><span>Сколиоз <b>${jumpNumber(p.scoliosisGrade,2)} ст.</b></span><span>Фаза <b>${escapeHtml(p.phase||'foundation')}</b></span>`;

    const measuredDate=$('#jumpMeasuredDate'); if (measuredDate&&!measuredDate.value) measuredDate.value=localDateKey(new Date());
    const metric=$('#jumpMetric'); if (metric) { const squat=metric.value==='squat_set'; const wrap=$('#jumpSecondaryWrap'); if (wrap) wrap.hidden=!squat; }
    const measurementRoot=$('#jumpMeasurements'); if (measurementRoot) measurementRoot.innerHTML=(hub.measurements||[]).slice(0,12).map(row=>`<div><span>${escapeHtml(row.date||'')} · ${escapeHtml(row.label||row.metric||'')}</span><b>${jumpNumber(row.value)}${row.secondaryValue!=null?`×${jumpNumber(row.secondaryValue)}`:''} ${escapeHtml(row.unit||'')}</b></div>`).join('')||'<div class="jump-empty">Пока нет замеров.</div>';

    const day=jumpCurrentDay(); const daySelect=$('#jumpDaySelect'); if (daySelect) daySelect.value=day;
    const exerciseRoot=$('#jumpExerciseList'); const rows=(hub.exercises||[]).filter(row=>row.dayCode===day).sort((a,b)=>jumpNumber(a.sortOrder)-jumpNumber(b.sortOrder));
    if (exerciseRoot) exerciseRoot.innerHTML=rows.map(row=>{ const pending=String(row.id||'').startsWith('web-temp-'); const actions=pending?'<span class="soft-label">сохраняется</span>':`<button type="button" class="ghost small" data-jump-action="edit-exercise" data-id="${escapeHtml(row.id)}">Изменить</button><button type="button" class="ghost small" data-jump-action="toggle-exercise" data-id="${escapeHtml(row.id)}">${row.enabled?'Пауза':'Включить'}</button><button type="button" class="ghost small danger" data-jump-action="delete-exercise" data-id="${escapeHtml(row.id)}">Удалить</button>`; return `<article class="jump-exercise ${row.enabled?'':'is-paused'}"><div class="jump-exercise-main"><span class="jump-order">${jumpNumber(row.sortOrder)}</span><div><div class="jump-exercise-meta">${escapeHtml(row.categoryLabel||JUMP_CATEGORY_NAMES[row.category]||row.category)}${row.reviewRequired?' · 🧑‍🏫 очная проверка':''}</div><b>${escapeHtml(row.title||'')}</b><p>${jumpNumber(row.sets)}×${escapeHtml(row.reps||'')} · RPE ${jumpNumber(row.rpeMin)}–${jumpNumber(row.rpeMax)} · отдых ${jumpNumber(row.restSeconds)} сек${jumpNumber(row.impactContacts)>0?` · ${jumpNumber(row.impactContacts)} контактов`:''}</p><small>${escapeHtml(row.loadRule||'')}${row.stopRule?` · Стоп: ${escapeHtml(row.stopRule)}`:''}</small></div></div><div class="jump-exercise-actions">${actions}</div></article>`; }).join('')||'<div class="jump-empty">В этом дне пока нет упражнений.</div>';

    jumpValue('#jumpReviewer',p.reviewedBy||p.strengthCoach||p.volleyballCoach||''); jumpValue('#jumpReviewerRole',p.reviewedRole||'ОФП / S&C тренер'); jumpValue('#jumpReviewNotes',p.coachNotes||'');
    const sync=$('#jumpSyncStatus'); if (sync) { const pending=(hub.webCommands||[]).length; sync.textContent=pending?`сохраняю: ${pending}`:(hub.syncedAt?'синхронизировано':'ждём синхронизацию'); }
  }

  function jumpOpen(id,open=true) { const el=$(id); if (el) { el.hidden=!open; if (open) el.scrollIntoView({behavior:'smooth',block:'nearest'}); } }
  function jumpFillExercise(row=null) {
    jumpValue('#jumpExerciseId',row?.id??''); jumpValue('#jumpExerciseDay',row?.dayCode||jumpCurrentDay()); jumpValue('#jumpExerciseTitle',row?.title||''); jumpValue('#jumpExerciseCategory',row?.category||'strength');
    jumpValue('#jumpExerciseSets',row?.sets??3); jumpValue('#jumpExerciseReps',row?.reps||'6–8'); jumpValue('#jumpExerciseRpeMin',row?.rpeMin??5); jumpValue('#jumpExerciseRpeMax',row?.rpeMax??7); jumpValue('#jumpExerciseRest',row?.restSeconds??120); jumpValue('#jumpExerciseContacts',row?.impactContacts??0); jumpValue('#jumpExerciseOrder',row?.sortOrder??100);
    jumpValue('#jumpExerciseLoad',row?.loadRule||''); jumpValue('#jumpExerciseStop',row?.stopRule||'Остановиться при боли или ухудшении техники.'); jumpValue('#jumpExerciseNotes',row?.notes||'');
    const review=$('#jumpExerciseReview'); if (review) review.checked=Boolean(row?.reviewRequired); const enabled=$('#jumpExerciseEnabled'); if (enabled) enabled.checked=row?Boolean(row.enabled):true;
    jumpText('#jumpExerciseFormTitle',row?'Изменить упражнение':'Добавить упражнение'); jumpOpen('#jumpExerciseForm',true);
  }
  function jumpExercisePayload() { return {day_code:$('#jumpExerciseDay').value,title:$('#jumpExerciseTitle').value.trim(),category:$('#jumpExerciseCategory').value,sets:jumpNumber($('#jumpExerciseSets').value),reps:$('#jumpExerciseReps').value.trim(),load_rule:$('#jumpExerciseLoad').value.trim(),rpe_min:jumpNumber($('#jumpExerciseRpeMin').value),rpe_max:jumpNumber($('#jumpExerciseRpeMax').value),rest_seconds:jumpNumber($('#jumpExerciseRest').value),impact_contacts:jumpNumber($('#jumpExerciseContacts').value),sort_order:jumpNumber($('#jumpExerciseOrder').value),stop_rule:$('#jumpExerciseStop').value.trim(),notes:$('#jumpExerciseNotes').value.trim(),review_required:Boolean($('#jumpExerciseReview').checked),enabled:Boolean($('#jumpExerciseEnabled').checked)}; }

  document.addEventListener('change',event=>{
    if (event.target?.id==='jumpDaySelect') { const hub=jumpHub(); hub.selectedDay=event.target.value; renderJumpLab(); }
    if (event.target?.id==='jumpMetric') { const wrap=$('#jumpSecondaryWrap'); if (wrap) wrap.hidden=event.target.value!=='squat_set'; }
    if (event.target?.id==='jumpImportFile' && event.target.files?.[0]) {
      const file=event.target.files[0], reader=new FileReader(); reader.onload=()=>{ try { const bundle=JSON.parse(String(reader.result)); if(!Array.isArray(bundle.exercises)) throw new Error('Нет exercises'); jumpEnqueue('program_import',{bundle}); showToast('Программа отправлена на импорт. Перед заменой создаётся резервная версия.'); } catch(error) { showToast(`Не удалось импортировать JSON: ${error.message}`); } finally { event.target.value=''; } }; reader.readAsText(file,'utf-8');
    }
  });

  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-jump-action]'); if (!button) return; const action=button.dataset.jumpAction;
    if (action==='toggle-profile') jumpOpen('#jumpProfileForm',$('#jumpProfileForm')?.hidden);
    else if (action==='new-exercise') jumpFillExercise(null);
    else if (action==='close-exercise') jumpOpen('#jumpExerciseForm',false);
    else if (action==='edit-exercise') { const row=jumpExerciseById(button.dataset.id); if (row) jumpFillExercise(row); }
    else if (action==='toggle-exercise') { const row=jumpExerciseById(button.dataset.id); if (!row) return; jumpEnqueue('exercise_toggle',{exerciseId:row.id,enabled:!row.enabled}); row.enabled=!row.enabled; state.jumpLab.profile.programReviewed=false; saveState(); renderJumpLab(); }
    else if (action==='delete-exercise') { const row=jumpExerciseById(button.dataset.id); if (!row||!confirm(`Удалить «${row.title}»?`)) return; jumpEnqueue('exercise_delete',{exerciseId:row.id}); jumpHub().exercises=jumpHub().exercises.filter(x=>String(x.id)!==String(row.id)); state.jumpLab.profile.programReviewed=false; saveState(); renderJumpLab(); }
    else if (action==='clear-review') { jumpEnqueue('coach_unreview'); jumpHub().profile.programReviewed=false; saveState(); renderJumpLab(); }
    else if (action==='reset') { if(!confirm('Сохранить текущую версию и вернуть осторожный фундаментальный шаблон?')) return; jumpEnqueue('program_reset'); showToast('Запрошен сброс к фундаменту. Текущая версия сохранится.'); }
    else if (action==='export') { const hub=jumpHub(), payload=hub.coachPacket||{schema:'dvizh-jump-program-v1',profile:hub.profile,exercises:hub.exercises,measurements:hub.measurements}; const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}); const url=URL.createObjectURL(blob), link=document.createElement('a'); link.href=url; link.download=`dvizh-jump-program-${localDateKey(new Date())}.json`; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); }
  });

  document.addEventListener('submit',event=>{
    if (event.target?.id==='jumpProfileForm') {
      event.preventDefault(); const profile={age:jumpNumber($('#jumpAge').value),height_cm:jumpNumber($('#jumpHeight').value),current_weight_kg:jumpNumber($('#jumpCurrentWeight').value),weight_target_kg:jumpNumber($('#jumpWeightTarget').value),current_approach_jump_cm:jumpNumber($('#jumpCurrentApproach').value),target_approach_jump_cm:jumpNumber($('#jumpTargetApproach').value),standing_reach_cm:$('#jumpStandingReach').value===''?null:jumpNumber($('#jumpStandingReach').value),squat_weight_kg:jumpNumber($('#jumpSquatWeight').value),squat_reps:jumpNumber($('#jumpSquatReps').value),scoliosis_grade:jumpNumber($('#jumpScoliosisGrade').value),cobb_angle_deg:$('#jumpCobbAngle').value===''?null:jumpNumber($('#jumpCobbAngle').value),phase:$('#jumpPhase').value,program_week:jumpNumber($('#jumpBlockWeek').value),medical_status:$('#jumpMedicalStatus').value,primary_role:$('#jumpPrimaryRole').value.trim(),secondary_role:$('#jumpSecondaryRole').value.trim(),curve_pattern:$('#jumpCurvePattern').value.trim(),symptoms:$('#jumpSymptoms').value.trim(),medical_notes:$('#jumpMedicalNotes').value.trim(),volleyball_coach:$('#jumpVolleyballCoach').value.trim(),strength_coach:$('#jumpStrengthCoach').value.trim(),coach_notes:$('#jumpCoachNotes').value.trim()};
      jumpEnqueue('profile_update',{profile}); const p=jumpHub().profile; Object.assign(p,{age:profile.age,heightCm:profile.height_cm,currentWeightKg:profile.current_weight_kg,weightTargetKg:profile.weight_target_kg,currentApproachJumpCm:profile.current_approach_jump_cm,targetApproachJumpCm:profile.target_approach_jump_cm,standingReachCm:profile.standing_reach_cm,squatWeightKg:profile.squat_weight_kg,squatReps:profile.squat_reps,scoliosisGrade:profile.scoliosis_grade,cobbAngleDeg:profile.cobb_angle_deg,phase:profile.phase,programWeek:profile.program_week,medicalStatus:profile.medical_status,primaryRole:profile.primary_role,secondaryRole:profile.secondary_role,curvePattern:profile.curve_pattern,symptoms:profile.symptoms,medicalNotes:profile.medical_notes,volleyballCoach:profile.volleyball_coach,strengthCoach:profile.strength_coach,coachNotes:profile.coach_notes}); saveState(); jumpOpen('#jumpProfileForm',false); renderJumpLab(); showToast('Профиль цели сохраняется.');
    }
    if (event.target?.id==='jumpMeasurementForm') {
      event.preventDefault(); const metric=$('#jumpMetric').value,value=jumpNumber($('#jumpMeasurementValue').value,NaN),secondaryValue=metric==='squat_set'?jumpNumber($('#jumpMeasurementSecondary').value,NaN):null; if(!Number.isFinite(value)||(metric==='squat_set'&&!Number.isFinite(secondaryValue))) return showToast('Проверь значение замера.');
      const row={id:`web-temp-${Date.now()}`,date:$('#jumpMeasuredDate').value,metric,label:$('#jumpMetric').selectedOptions[0]?.textContent||metric,value,secondaryValue,unit:'',method:$('#jumpMeasurementMethod').value.trim(),notes:$('#jumpMeasurementNotes').value.trim(),source:'web-pending',createdAt:nowIso()}; jumpEnqueue('measurement_add',{metric,value,secondaryValue,measuredDate:row.date,method:row.method,notes:row.notes}); jumpHub().measurements=[row,...jumpHub().measurements]; saveState(); event.target.reset(); $('#jumpMeasuredDate').value=localDateKey(new Date()); renderJumpLab(); showToast('Замер сохраняется.');
    }
    if (event.target?.id==='jumpExerciseForm') {
      event.preventDefault(); const payload=jumpExercisePayload(); if(!payload.title||!payload.reps||payload.rpe_min>payload.rpe_max) return showToast('Проверь название, повторы и диапазон RPE.'); const id=$('#jumpExerciseId').value, hub=jumpHub();
      if (id) { const row=jumpExerciseById(id); if(!row) return; jumpEnqueue('exercise_update',{exerciseId:row.id,exercise:payload}); Object.assign(row,{dayCode:payload.day_code,title:payload.title,category:payload.category,categoryLabel:JUMP_CATEGORY_NAMES[payload.category],sets:payload.sets,reps:payload.reps,loadRule:payload.load_rule,rpeMin:payload.rpe_min,rpeMax:payload.rpe_max,restSeconds:payload.rest_seconds,impactContacts:payload.impact_contacts,sortOrder:payload.sort_order,stopRule:payload.stop_rule,notes:payload.notes,reviewRequired:payload.review_required,enabled:payload.enabled}); }
      else { const command=jumpEnqueue('exercise_add',{exercise:payload}); hub.exercises.push({id:`web-temp-${command.id}`,exerciseKey:`web-temp-${command.id}`,dayCode:payload.day_code,dayLabel:JUMP_DAY_NAMES[payload.day_code],title:payload.title,category:payload.category,categoryLabel:JUMP_CATEGORY_NAMES[payload.category],sets:payload.sets,reps:payload.reps,loadRule:payload.load_rule,rpeMin:payload.rpe_min,rpeMax:payload.rpe_max,restSeconds:payload.rest_seconds,impactContacts:payload.impact_contacts,sortOrder:payload.sort_order,stopRule:payload.stop_rule,notes:payload.notes,reviewRequired:payload.review_required,enabled:payload.enabled}); }
      hub.profile.programReviewed=false; hub.selectedDay=payload.day_code; saveState(); jumpOpen('#jumpExerciseForm',false); renderJumpLab(); showToast('Программа сохраняется; отметка проверки снята.');
    }
    if (event.target?.id==='jumpCoachReviewForm') { event.preventDefault(); const reviewer=$('#jumpReviewer').value.trim(); if(!reviewer) return showToast('Укажи имя специалиста.'); jumpEnqueue('coach_review',{reviewer,role:$('#jumpReviewerRole').value,notes:$('#jumpReviewNotes').value.trim()}); Object.assign(jumpHub().profile,{programReviewed:true,reviewedBy:reviewer,reviewedRole:$('#jumpReviewerRole').value,coachNotes:$('#jumpReviewNotes').value.trim(),reviewedAt:nowIso()}); saveState(); renderJumpLab(); showToast('Версия отмечается проверенной.'); }
  });


  const DVIZH_SOCIAL_HUB_V1 = true;
  const SOCIAL_STAGES = ['idea','script','record','edit','scheduled','published'];
  const SOCIAL_STAGE_LABELS = {idea:'Идея',script:'Сценарий',record:'Снять',edit:'Монтаж',scheduled:'Запланировано',published:'Опубликовано',archived:'Архив'};
  const SOCIAL_PLATFORM_LABELS = {tiktok:'TikTok',instagram:'Instagram',youtube:'YouTube / Shorts',vk:'VK',telegram:'Telegram',other:'Другая'};
  const SOCIAL_FORMAT_LABELS = {short_video:'Короткое видео',story:'История / сторис',post:'Пост',carousel:'Карусель',long_video:'Длинное видео',live:'Эфир',other:'Другое'};
  const SOCIAL_COURAGE = {1:'Записать один сырой дубль и никому не показывать.',2:'Показать черновик одному безопасному человеку.',3:'Опубликовать без продвижения и не проверять реакции до окна.',4:'Опубликовать обычный ролик в основной аккаунт.',5:'Опубликовать с лицом, личным мнением или уязвимой историей.'};
  let socialUiBound = false;
  const socialSeenResults = new Set();

  function socialHub() {
    if (!state.socialHub || typeof state.socialHub !== 'object') {
      state.socialHub = {version:1,profile:{weeklyGoal:2,courageLevel:1,defaultPlatform:'tiktok',defaultFormat:'short_video',commentWindow1:'13:00',commentWindow2:'20:00',reminderMinutes:30},metrics:{active:0,publishedThisWeek:0,weeklyGoal:2,scheduled:0,courageLevel:1,stageCounts:{}},content:[],exposures:[],nextAction:{contentId:null,title:'Новый материал',stage:'idea',action:'Запиши одну идею одним предложением.',minutes:3,reason:'Конвейер пуст.',courageStep:1},webCommands:[],commandResults:[]};
    }
    const hub=state.socialHub;
    if (!hub.profile || typeof hub.profile!=='object') hub.profile={weeklyGoal:2,courageLevel:1,defaultPlatform:'tiktok',defaultFormat:'short_video',commentWindow1:'13:00',commentWindow2:'20:00',reminderMinutes:30};
    if (!hub.metrics || typeof hub.metrics!=='object') hub.metrics={active:0,publishedThisWeek:0,weeklyGoal:2,scheduled:0,courageLevel:1,stageCounts:{}};
    if (!Array.isArray(hub.content)) hub.content=[];
    if (!Array.isArray(hub.exposures)) hub.exposures=[];
    if (!Array.isArray(hub.webCommands)) hub.webCommands=[];
    if (!Array.isArray(hub.commandResults)) hub.commandResults=[];
    return hub;
  }

  function socialCommandId() { return `web-social-${Date.now()}-${Math.random().toString(36).slice(2,9)}`; }
  function socialEnqueue(action,payload={}) {
    const hub=socialHub();
    const command={id:socialCommandId(),action,...payload,createdAt:nowIso()};
    hub.webCommands=[...hub.webCommands.slice(-39),command];
    hub.webUpdatedAt=nowIso();
    saveState();
    return command;
  }

  function socialLocalId() { return -Math.floor(Date.now()+Math.random()*1000); }
  function socialById(id) { return socialHub().content.find(row=>String(row.id)===String(id)); }
  function socialDueLabel(row) { return row.publishDate ? `${row.publishDate}${row.publishTime ? ` · ${row.publishTime}` : ''}` : 'без даты'; }
  function socialSafeLink(value) { try { const url=new URL(String(value||'')); return ['http:','https:'].includes(url.protocol) ? url.href : ''; } catch (_) { return ''; } }

  function socialRenderPipeline() {
    const root=$('#socialPipeline'); if (!root) return;
    const hub=socialHub();
    root.innerHTML=SOCIAL_STAGES.map(stage=>{
      const rows=hub.content.filter(row=>row && row.stage===stage).sort((a,b)=>String(a.publishDate||'9999').localeCompare(String(b.publishDate||'9999')));
      const cards=rows.length ? rows.map(row=>{
        const next=stage==='published' ? '' : `<button type="button" class="ghost tiny" data-social-action="advance" data-content-id="${escapeHtml(row.id)}">${stage==='scheduled'?'✓ Опубликовано':'→ Дальше'}</button>`;
        const safeLink=socialSafeLink(row.link);
        const link=safeLink ? `<a href="${escapeHtml(safeLink)}" target="_blank" rel="noopener noreferrer">ссылка</a>` : '';
        return `<article class="social-content-card" data-stage="${escapeHtml(stage)}">
          <div class="social-content-head"><b>${escapeHtml(row.title||'Без названия')}</b><button type="button" class="icon-button" data-social-action="edit-content" data-content-id="${escapeHtml(row.id)}">•••</button></div>
          <div class="social-content-meta"><span>${escapeHtml(SOCIAL_PLATFORM_LABELS[row.platform]||row.platform||'')}</span><span>страх ${Number(row.fearLevel||0)}/5</span></div>
          <p>${escapeHtml(row.minimumStep||'Один маленький шаг.')}</p>
          <small>${escapeHtml(socialDueLabel(row))} ${link}</small>
          <div class="social-card-actions">${next}<button type="button" class="ghost tiny" data-social-action="archive" data-content-id="${escapeHtml(row.id)}">архив</button></div>
        </article>`;
      }).join('') : '<div class="social-column-empty">пусто</div>';
      return `<section class="social-column"><header><b>${SOCIAL_STAGE_LABELS[stage]}</b><span>${rows.length}</span></header><div>${cards}</div></section>`;
    }).join('');
  }

  function socialRenderCourage() {
    const hub=socialHub(), level=Number(hub.profile.courageLevel||1);
    const title=$('#socialCourageTitle'); if (title) title.textContent=`Уровень ${level}/5`;
    const root=$('#socialCourageLadder');
    if (root) root.innerHTML=Object.entries(SOCIAL_COURAGE).map(([key,text])=>`<li class="${Number(key)===level?'is-current':Number(key)<level?'is-done':''}"><b>${key}</b><span>${escapeHtml(text)}</span></li>`).join('');
    const history=$('#socialExposureHistory');
    if (history) {
      const rows=hub.exposures.slice(0,8);
      history.innerHTML=rows.length ? `<p class="eyebrow">ПОСЛЕДНИЕ ШАГИ</p>`+rows.map(row=>`<div><span>${escapeHtml(String(row.createdAt||'').slice(0,10))} · уровень ${Number(row.step||1)}</span><b>${Number(row.fearBefore||0)} → ${row.fearAfter===null||row.fearAfter===undefined?'—':Number(row.fearAfter)}</b></div>`).join('') : '';
    }
  }

  function socialFillForm(row=null) {
    const hub=socialHub(), p=hub.profile;
    $('#socialContentId').value=row ? row.id : '';
    $('#socialContentFormTitle').textContent=row ? 'Редактировать материал' : 'Новый материал';
    $('#socialTitle').value=row?.title||'';
    $('#socialPlatform').value=row?.platform||p.defaultPlatform||'tiktok';
    $('#socialFormat').value=row?.contentFormat||p.defaultFormat||'short_video';
    $('#socialStage').value=row?.stage||'idea';
    $('#socialFear').value=Number(row?.fearLevel??2);
    $('#socialCourageStep').value=String(row?.courageStep||p.courageLevel||1);
    $('#socialPublishDate').value=row?.publishDate||'';
    $('#socialPublishTime').value=row?.publishTime||'';
    $('#socialReminder').value=String(row?.reminderMinutes??p.reminderMinutes??30);
    $('#socialMinimumStep').value=row?.minimumStep||'Записать один сырой дубль или тезис за 5 минут.';
    $('#socialNormalStep').value=row?.normalStep||'Подготовить и опубликовать готовый материал.';
    $('#socialLink').value=row?.link||'';
    $('#socialNotes').value=row?.notes||'';
    $('#socialResultNote').value=row?.resultNote||'';
    $('#socialDeleteButton').hidden=!row || Number(row.id)<0;
    $('#socialContentFormPanel').hidden=false;
    $('#socialContentFormPanel').scrollIntoView({behavior:'smooth',block:'start'});
  }

  function socialContentPayload() {
    return {
      title:$('#socialTitle').value.trim(),
      platform:$('#socialPlatform').value,
      contentFormat:$('#socialFormat').value,
      stage:$('#socialStage').value,
      fearLevel:Number($('#socialFear').value),
      courageStep:Number($('#socialCourageStep').value),
      publishDate:$('#socialPublishDate').value||null,
      publishTime:$('#socialPublishTime').value||null,
      reminderMinutes:Number($('#socialReminder').value),
      minimumStep:$('#socialMinimumStep').value.trim(),
      normalStep:$('#socialNormalStep').value.trim(),
      link:$('#socialLink').value.trim(),
      notes:$('#socialNotes').value.trim(),
      resultNote:$('#socialResultNote').value.trim()
    };
  }

  function socialOptimisticCreate(payload) {
    const hub=socialHub();
    const now=nowIso();
    const row={id:socialLocalId(),...payload,createdAt:now,updatedAt:now};
    hub.content=[row,...hub.content];
    hub.metrics.active=Number(hub.metrics.active||0)+(payload.stage==='published'||payload.stage==='archived'?0:1);
    return row;
  }

  function socialAdvance(id) {
    const row=socialById(id); if (!row) return;
    if (Number(row.id)<0) { showToast('Идея ещё синхронизируется. Подожди несколько секунд.'); return; }
    const next={idea:'script',script:'record',record:'edit',edit:'scheduled',scheduled:'published'}[row.stage];
    if (!next) return;
    if (row.stage==='edit' && (!row.publishDate || !row.publishTime)) {
      socialFillForm(row); showToast('Сначала назначь дату и время публикации.'); return;
    }
    socialEnqueue(next==='published'?'content_publish':'content_advance',{contentId:Number(row.id)});
    row.stage=next; row.updatedAt=nowIso(); if (next==='published') row.publishedAt=nowIso();
    saveState(); renderSocial(); showToast(next==='published'?'Материал отмечен опубликованным.':'Этап обновлён.');
  }

  function socialArchive(id) {
    const row=socialById(id); if (!row) return;
    if (Number(row.id)>0) socialEnqueue('content_archive',{contentId:Number(row.id)});
    row.stage='archived'; row.updatedAt=nowIso(); saveState(); renderSocial(); showToast('Материал убран в архив.');
  }

  function socialBind() {
    if (socialUiBound) return; socialUiBound=true;
    const quick=$('#socialQuickIdeaForm');
    if (quick) quick.addEventListener('submit',event=>{
      event.preventDefault(); const title=$('#socialQuickTitle').value.trim(); if (!title) return;
      const payload={title,platform:$('#socialQuickPlatform').value,contentFormat:'short_video',stage:'idea',fearLevel:Number($('#socialQuickFear').value),courageStep:Number(socialHub().profile.courageLevel||1),minimumStep:'Записать один сырой дубль или тезис за 5 минут.',normalStep:'Подготовить и опубликовать готовый материал.',publishDate:null,publishTime:null,reminderMinutes:Number(socialHub().profile.reminderMinutes||30),link:'',notes:'',resultNote:''};
      socialOptimisticCreate(payload); socialEnqueue('content_create',{content:payload}); quick.reset(); $('#socialQuickFear').value='2'; renderSocial(); showToast('Идея сохранена. Не нужно развивать её прямо сейчас.');
    });
    const form=$('#socialContentForm');
    if (form) form.addEventListener('submit',event=>{
      event.preventDefault(); const payload=socialContentPayload(); if (!payload.title||!payload.minimumStep||!payload.normalStep) return;
      if (Boolean(payload.publishDate)!==Boolean(payload.publishTime)) { showToast('Дата и время публикации задаются вместе.'); return; }
      const id=$('#socialContentId').value;
      if (id && Number(id)>0) {
        socialEnqueue('content_update',{contentId:Number(id),content:payload}); Object.assign(socialById(id)||{},payload,{updatedAt:nowIso()});
      } else { socialOptimisticCreate(payload); socialEnqueue('content_create',{content:payload}); }
      $('#socialContentFormPanel').hidden=true; saveState(); renderSocial(); showToast('Материал сохранён.');
    });
    const settings=$('#socialSettingsForm');
    if (settings) settings.addEventListener('submit',event=>{
      event.preventDefault(); const profile={weeklyGoal:Number($('#socialWeeklyGoal').value),courageLevel:Number($('#socialProfileCourage').value),commentWindow1:$('#socialWindow1').value,commentWindow2:$('#socialWindow2').value};
      Object.assign(socialHub().profile,profile); socialEnqueue('profile_update',{profile}); saveState(); renderSocial(); showToast('Настройки сохранены.');
    });
    const exposure=$('#socialExposureForm');
    if (exposure) exposure.addEventListener('submit',event=>{
      event.preventDefault(); const hub=socialHub(), step=Number(hub.profile.courageLevel||1), fearBefore=Number($('#socialFearBefore').value), fearAfter=Number($('#socialFearAfter').value);
      socialEnqueue('exposure_log',{step,fearBefore,fearAfter,exposureResult:'done'});
      hub.exposures=[{id:socialLocalId(),step,action:SOCIAL_COURAGE[step],fearBefore,fearAfter,result:'done',createdAt:nowIso()},...hub.exposures]; exposure.hidden=true; saveState(); renderSocial(); showToast('Шаг смелости записан. Уровень не повышен автоматически.');
    });
    document.addEventListener('click',event=>{
      const button=event.target.closest('[data-social-action]'); if (!button) return;
      const action=button.dataset.socialAction, id=button.dataset.contentId;
      if (action==='new-content') socialFillForm();
      else if (action==='close-content') $('#socialContentFormPanel').hidden=true;
      else if (action==='edit-content') socialFillForm(socialById(id));
      else if (action==='advance') socialAdvance(id);
      else if (action==='archive') socialArchive(id);
      else if (action==='next-done') { const next=socialHub().nextAction; if (next?.mode==='courage') { $('#socialExposureForm').hidden=false; $('#socialExposureForm').scrollIntoView({behavior:'smooth',block:'center'}); } else if (next&&next.contentId) socialAdvance(next.contentId); else socialFillForm(); }
      else if (action==='open-courage') { $('#socialExposureForm').hidden=false; $('#socialExposureForm').scrollIntoView({behavior:'smooth',block:'center'}); }
      else if (action==='focus-settings') $('#socialSettingsForm').scrollIntoView({behavior:'smooth',block:'center'});
      else if (action==='delete-content') {
        const contentId=Number($('#socialContentId').value); if (!contentId||!confirm('Удалить материал без возможности восстановления?')) return;
        socialEnqueue('content_delete',{contentId}); socialHub().content=socialHub().content.filter(row=>Number(row.id)!==contentId); $('#socialContentFormPanel').hidden=true; saveState(); renderSocial(); showToast('Материал удалён.');
      }
    });
  }

  function renderSocial() {
    const root=$('#view-social'); if (!root) return;
    const hub=socialHub(), metrics=hub.metrics||{}, profile=hub.profile||{}, next=hub.nextAction||{};
    socialBind();
    const status=$('#socialSyncStatus');
    if (status) status.textContent=hub.syncedAt ? `обновлено ${new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit'}).format(new Date(hub.syncedAt))}` : 'ждём первую синхронизацию';
    $('#socialActiveMetric').textContent=Number(metrics.active||0);
    $('#socialPublishedMetric').textContent=`${Number(metrics.publishedThisWeek||0)}/${Number(metrics.weeklyGoal||profile.weeklyGoal||2)}`;
    $('#socialScheduledMetric').textContent=Number(metrics.scheduled||0);
    $('#socialCourageMetric').textContent=`${Number(metrics.courageLevel||profile.courageLevel||1)}/5`;
    $('#socialNextTitle').textContent=next.title||'Новый материал';
    $('#socialNextMinutes').textContent=`${Number(next.minutes||5)} мин`;
    $('#socialNextAction').textContent=next.action||'Запиши одну идею одним предложением.';
    $('#socialNextReason').textContent=next.reason||'';
    $('#socialReactionWindows').textContent=`${profile.commentWindow1||'13:00'} и ${profile.commentWindow2||'20:00'}`;
    $('#socialQuickPlatform').value=profile.defaultPlatform||'tiktok';
    $('#socialWeeklyGoal').value=Number(profile.weeklyGoal||2);
    $('#socialProfileCourage').value=String(profile.courageLevel||1);
    $('#socialWindow1').value=profile.commentWindow1||'13:00';
    $('#socialWindow2').value=profile.commentWindow2||'20:00';
    for (const result of hub.commandResults||[]) {
      const key=String(result?.id||'');
      if (!key || socialSeenResults.has(key)) continue;
      socialSeenResults.add(key);
      if (result.result==='error') showToast(`Не удалось сохранить: ${result.detail||'ошибка команды'}`);
    }
    socialRenderPipeline(); socialRenderCourage();
  }



  const DVIZH_AI_APPROVAL_UI_V1 = true;

  function aiApprovalEsc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  function aiApprovalActionLabel(action) {
    return ({
      task_create: 'Новая задача',
      task_complete: 'Завершить задачу',
      schedule_move: 'Перенести событие',
      day_plan: 'План дня'
    })[action] || 'Изменение';
  }

  function aiApprovalDetail(proposal) {
    const p = proposal && typeof proposal.payload === 'object' ? proposal.payload : {};
    if (proposal.action === 'task_create') return p.title ? `Добавить «${p.title}»` : proposal.summary;
    if (proposal.action === 'task_complete') {
      const tasks = Array.isArray(state.tasks) ? state.tasks : [];
      const task = tasks.find(item => item && String(item.id) === String(p.task_id));
      return task ? `Отметить «${task.title}» выполненной` : proposal.summary;
    }
    if (proposal.action === 'schedule_move') return p.start_local ? `Новое время: ${p.start_local}` : proposal.summary;
    if (proposal.action === 'day_plan') {
      const count = Array.isArray(p.blocks) ? p.blocks.length : 0;
      return count ? `${count} блоков на день` : proposal.summary;
    }
    return proposal.summary || '';
  }

  function aiApprovalEnsureRoot() {
    let root = document.getElementById('aiProposalPanel');
    if (root) return root;
    const home = document.getElementById('view-home');
    if (!home) return null;
    root = document.createElement('section');
    root.id = 'aiProposalPanel';
    root.className = 'panel ai-proposal-panel';
    root.hidden = true;
    root.setAttribute('aria-live', 'polite');
    const hero = home.querySelector('.hero, .home-hero, .section-heading');
    if (hero && hero.parentElement === home) hero.insertAdjacentElement('afterend', root);
    else home.prepend(root);
    return root;
  }

  function aiApprovalPendingCommand(proposalId) {
    const commands = Array.isArray(state.aiProposalCommands) ? state.aiProposalCommands : [];
    return commands.some(command => command && String(command.proposalId) === String(proposalId));
  }

  function renderAiProposals() {
    if (typeof state === 'undefined' || !state) return;
    const root = aiApprovalEnsureRoot();
    if (!root) return;
    const proposals = Array.isArray(state.aiProposals) ? state.aiProposals.filter(p => p && p.status === 'pending') : [];
    if (!proposals.length) {
      root.hidden = true;
      root.innerHTML = '';
      return;
    }
    root.hidden = false;
    const cards = proposals.slice(0, 4).map(proposal => {
      const pending = aiApprovalPendingCommand(proposal.id);
      const label = aiApprovalActionLabel(proposal.action);
      const summary = proposal.summary || aiApprovalDetail(proposal);
      const detail = aiApprovalDetail(proposal);
      return `<article class="ai-proposal-card" data-ai-proposal-id="${aiApprovalEsc(proposal.id)}">
        <div class="ai-proposal-card-head">
          <div><span class="ai-proposal-kicker">${aiApprovalEsc(label)}</span><h3>${aiApprovalEsc(summary)}</h3></div>
          <span class="ai-proposal-source">Hermes</span>
        </div>
        ${detail && detail !== summary ? `<p>${aiApprovalEsc(detail)}</p>` : ''}
        <div class="ai-proposal-actions">
          <button type="button" class="primary" data-ai-proposal-decision="approve" data-ai-proposal-id="${aiApprovalEsc(proposal.id)}" ${pending ? 'disabled' : ''}>${pending ? 'Отправлено…' : 'Принять'}</button>
          <button type="button" class="ghost" data-ai-proposal-decision="reject" data-ai-proposal-id="${aiApprovalEsc(proposal.id)}" ${pending ? 'disabled' : ''}>Отклонить</button>
        </div>
      </article>`;
    }).join('');
    root.innerHTML = `<div class="ai-proposal-heading">
      <div><p class="eyebrow">ИИ ПРЕДЛАГАЕТ</p><h2>Подтверди изменение</h2></div>
      <span>${proposals.length}</span>
    </div>${cards}`;
  }

  function aiApprovalSend(proposalId, decision) {
    if (typeof state === 'undefined' || !state || typeof saveState !== 'function') return;
    const token = String(state.aiProposalUiToken || '');
    if (token.length < 24 || token === '[REDACTED]') {
      if (typeof showToast === 'function') showToast('Подтверждение ещё синхронизируется. Попробуй через пару секунд.');
      return;
    }
    if (!['approve','reject'].includes(decision)) return;
    const commands = Array.isArray(state.aiProposalCommands) ? state.aiProposalCommands.filter(item => item && typeof item === 'object') : [];
    if (commands.some(command => String(command.proposalId) === String(proposalId))) return;
    const command = {
      id: `ai-ui-${Date.now()}-${Math.random().toString(36).slice(2,9)}`,
      proposalId: String(proposalId),
      decision,
      token,
      createdAt: typeof nowIso === 'function' ? nowIso() : new Date().toISOString()
    };
    state.aiProposalCommands = [...commands.slice(-19), command];
    saveState();
    renderAiProposals();
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-ai-proposal-decision]');
    if (!button) return;
    event.preventDefault();
    aiApprovalSend(button.getAttribute('data-ai-proposal-id'), button.getAttribute('data-ai-proposal-decision'));
  });

  window.setInterval(renderAiProposals, 1400);
  window.addEventListener('focus', renderAiProposals);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', renderAiProposals, {once:true});
  else queueMicrotask(renderAiProposals);

  function renderSettings() {
    document.body.dataset.tone = state.tone;
    $$('#tonePicker button').forEach(button => button.classList.toggle('is-active', button.dataset.tone === state.tone));
    $('#installButton').disabled = !deferredInstallPrompt;
    if (deferredInstallPrompt) $('#installHint').textContent = 'Браузер готов установить ДВИЖ отдельным приложением.';
  }

  function renderAll() {
    renderHeader();
    renderCheckin();
    renderSuggestion();
    renderDailyPlan();
    renderTasks();
    renderFocus();
    renderProof();
    renderWeek();
    renderTraining();
    renderJumpLab();
    renderSocial();
    renderSettings();
  }

  function openTaskEditor(taskId = null) {
    const task = taskId ? getTask(taskId) : null;
    $('#taskId').value = task?.id || '';
    $('#taskTitle').value = task?.title || '';
    $('#taskMicro').value = task?.micro || '';
    $('#taskArea').innerHTML = AREAS.map(area => `<option value="${escapeHtml(area)}">${AREA_EMOJI[area]} ${escapeHtml(area)}</option>`).join('');
    $('#taskArea').value = task?.area || 'Разное';
    $('#taskDuration').value = task?.duration || 8;
    $('#taskEnergy').value = task?.energy || 1;
    $('#taskFear').value = task?.fear || 0;
    $('#taskPriority').value = task?.priority || 2;
    $('#taskModalTitle').textContent = task ? 'Изменить следующий шаг' : 'Новый следующий шаг';
    $('#deleteTaskButton').hidden = !task;
    openModal('taskModal');
    setTimeout(() => $('#taskTitle').focus(), 50);
  }

  function saveTaskFromForm(event) {
    event.preventDefault();
    const id = $('#taskId').value;
    const payload = {
      title: $('#taskTitle').value.trim(),
      micro: $('#taskMicro').value.trim(),
      area: $('#taskArea').value,
      duration: clamp(Number($('#taskDuration').value), 2, 180),
      energy: clamp(Number($('#taskEnergy').value), 1, 3),
      fear: clamp(Number($('#taskFear').value), 0, 3),
      priority: clamp(Number($('#taskPriority').value), 1, 3)
    };
    if (!payload.title || !payload.micro) return;

    if (id) {
      const task = getTask(id);
      if (task) Object.assign(task, payload, { updatedAt: nowIso() });
      showToast('Задача обновлена.');
    } else {
      const task = { id: uid(), ...payload, done: false, createdAt: nowIso() };
      state.tasks.unshift(task);
      state.selectedFocusTaskId ||= task.id;
      focus.taskId ||= task.id;
      showToast('Задача выгружена из головы.');
    }
    state.plans[localDateKey()] = generatePlan(false);
    saveState();
    closeModal('taskModal');
    renderAll();
  }

  function deleteCurrentTask() {
    const id = $('#taskId').value;
    const task = getTask(id);
    if (!task) return;
    if (!window.confirm(`Удалить задачу «${task.title}»?`)) return;
    state.tasks = state.tasks.filter(item => item.id !== id);
    if (focus.taskId === id) focus.taskId = null;
    if (state.selectedFocusTaskId === id) state.selectedFocusTaskId = null;
    state.plans[localDateKey()] = generatePlan(false);
    saveState();
    closeModal('taskModal');
    renderAll();
    showToast('Задача удалена.');
  }

  function toggleTask(taskId) {
    const task = getTask(taskId);
    if (!task) return;
    task.done = !task.done;
    task.completedAt = task.done ? nowIso() : null;
    if (task.done) {
      state.proofs.unshift({ id: uid(), text: `Закрыл: ${task.title}`, type: task.fear > 0 ? 'brave' : 'task', taskId: task.id, date: localDateKey(), createdAt: nowIso() });
      showToast('Готово. Это записано как факт.');
    } else {
      state.proofs = state.proofs.filter(proof => !(proof.taskId === task.id && proof.type !== 'manual'));
      showToast('Задача возвращена. Без наказаний.');
    }
    state.plans[localDateKey()] = generatePlan(false);
    saveState();
    renderAll();
  }

  function replacePlanSlot(slot) {
    const key = localDateKey();
    const plan = getTodayPlan();
    const used = Object.entries(plan).filter(([name]) => ['main', 'easy', 'brave'].includes(name) && name !== slot).map(([, id]) => id).filter(Boolean);
    const mode = slot === 'easy' ? 'easy' : slot === 'brave' ? 'brave' : 'main';
    const candidates = sortedCandidates(mode, used);
    if (!candidates.length) {
      showToast('Другого подходящего шага пока нет.');
      return;
    }
    const currentIndex = candidates.findIndex(task => task.id === plan[slot]);
    plan[slot] = candidates[(currentIndex + 1) % candidates.length].id;
    state.plans[key] = plan;
    saveState();
    renderDailyPlan();
  }

  function openRescue() {
    rescueRemaining = 90;
    $('#rescueTimer').textContent = rescueRemaining;
    const task = getSuggestedTask();
    $('#rescueMicro').textContent = task?.micro || 'Запиши один маленький следующий шаг.';
    clearInterval(rescueInterval);
    rescueInterval = setInterval(() => {
      rescueRemaining -= 1;
      $('#rescueTimer').textContent = Math.max(0, rescueRemaining);
      if (rescueRemaining <= 0) clearInterval(rescueInterval);
    }, 1000);
    openModal('rescueModal');
  }

  function closeRescue() {
    clearInterval(rescueInterval);
    rescueInterval = null;
    closeModal('rescueModal');
  }

  function rescueToFocus() {
    const task = getSuggestedTask();
    closeRescue();
    if (task) setFocusTask(task.id, 5);
    navigate('focus');
    showToast('Только пять минут. Потом можно остановиться.');
  }

  function addQuickTask(event) {
    event.preventDefault();
    const input = $('#quickAddInput');
    const title = input.value.trim();
    if (!title) return;
    state.tasks.unshift({
      id: uid(), title,
      micro: 'Открыть задачу и сделать первый очевидный шаг в течение 2–5 минут',
      area: 'Разное', energy: 1, fear: 0, priority: 1, duration: 5,
      done: false, createdAt: nowIso()
    });
    input.value = '';
    state.plans[localDateKey()] = generatePlan(false);
    saveState();
    renderAll();
    showToast('Выгружено. Сейчас разбирать не обязательно.');
  }

  function addManualProof(event) {
    event.preventDefault();
    const text = $('#proofText').value.trim();
    if (!text) return;
    state.proofs.unshift({ id: uid(), text, type: 'manual', date: localDateKey(), createdAt: nowIso() });
    $('#proofText').value = '';
    saveState();
    closeModal('proofModal');
    renderProof();
    showToast('Факт записан.');
  }

  function toggleLadder(stepId) {
    const step = FEAR_LADDER_DEFAULT.find(item => item.id === stepId);
    if (!step) return;
    state.ladder[stepId] = !state.ladder[stepId];
    if (state.ladder[stepId]) {
      state.proofs.unshift({ id: uid(), text: `Смелый шаг: ${step.title}`, type: 'brave', date: localDateKey(), createdAt: nowIso() });
      showToast('Смелый шаг записан.');
    } else {
      state.proofs = state.proofs.filter(proof => proof.text !== `Смелый шаг: ${step.title}`);
    }
    saveState();
    renderProof();
  }

  function exportData() {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `dvizh-backup-${localDateKey()}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast('Резервная копия скачана.');
  }

  function importData(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.tasks)) throw new Error('Неверный формат');
        state = { ...createDefaultState(), ...parsed };
        saveState();
        focus.taskId = state.selectedFocusTaskId;
        focus.totalSeconds = (state.focusDuration || 8) * 60;
        focus.remainingSeconds = focus.totalSeconds;
        renderAll();
        showToast('Данные восстановлены.');
      } catch (error) {
        window.alert('Не получилось импортировать файл. Нужна резервная копия ДВИЖ в формате JSON.');
      }
      $('#importFile').value = '';
    };
    reader.readAsText(file);
  }

  async function installApp() {
    if (!deferredInstallPrompt) {
      showToast('Используй меню браузера → «Добавить на главный экран».');
      return;
    }
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    renderSettings();
  }

  function resetApp() {
    if (!window.confirm('Точно удалить все задачи, отметки и историю ДВИЖ на сервере и всех устройствах?')) return;
    localStorage.removeItem(STORAGE_KEY);
    state = createDefaultState();
    focus.taskId = null;
    focus.totalSeconds = 8 * 60;
    focus.remainingSeconds = focus.totalSeconds;
    saveState();
    renderAll();
    openModal('introModal');
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      const nav = event.target.closest('[data-nav]');
      if (nav) {
        navigate(nav.dataset.nav);
        return;
      }

      const checkinButton = event.target.closest('[data-checkin] button');
      if (checkinButton) {
        setTodayCheckin(checkinButton.closest('[data-checkin]').dataset.checkin, checkinButton.dataset.value);
        return;
      }

      const areaFilter = event.target.closest('[data-area-filter]');
      if (areaFilter) {
        taskAreaFilter = areaFilter.dataset.areaFilter;
        renderTasks();
        return;
      }

      const outcome = event.target.closest('[data-outcome]');
      if (outcome) {
        recordRound(outcome.dataset.outcome);
        return;
      }

      const actionButton = event.target.closest('[data-action]');
      if (!actionButton) return;
      const action = actionButton.dataset.action;
      const taskId = actionButton.dataset.taskId;

      const actions = {
        'jump-checkin': () => { navigate('home'); setTimeout(() => $('#checkinCard').scrollIntoView({ behavior: 'smooth', block: 'center' }), 50); },
        'reset-checkin': () => {
          state.checkins[localDateKey()] = { energy: null, pain: null, fear: null, updatedAt: nowIso() };
          state.plans[localDateKey()] = generatePlan(false);
          saveState(); renderAll();
        },
        'shuffle-suggestion': () => { suggestionOffset += 1; renderSuggestion(); },
        'regenerate-plan': () => { state.plans[localDateKey()] = generatePlan(true); saveState(); renderDailyPlan(); showToast('План пересобран под текущий заряд.'); },
        'new-task': () => openTaskEditor(),
        'edit-task': () => openTaskEditor(taskId),
        'close-task-modal': () => closeModal('taskModal'),
        'delete-task': deleteCurrentTask,
        'toggle-task': () => toggleTask(taskId),
        'start-task': () => { setFocusTask(taskId); navigate('focus'); },
        'start-plan-task': () => { setFocusTask(taskId); navigate('focus'); },
        'replace-plan-slot': () => replacePlanSlot(actionButton.dataset.slot),
        'start-suggested': () => { setFocusTask(taskId, Number(actionButton.dataset.duration)); navigate('focus'); },
        'open-rescue': openRescue,
        'close-rescue': closeRescue,
        'rescue-to-focus': rescueToFocus,
        'choose-focus-task': () => { renderFocusTaskPicker(); openModal('taskPickerModal'); },
        'close-picker': () => closeModal('taskPickerModal'),
        'pick-focus-task': () => { setFocusTask(taskId); closeModal('taskPickerModal'); },
        'toggle-timer': () => focus.running ? pauseTimer() : startTimer(),
        'stop-timer': () => stopTimer(true),
        'add-proof': () => openModal('proofModal'),
        'close-proof-modal': () => closeModal('proofModal'),
        'toggle-ladder': () => toggleLadder(actionButton.dataset.stepId),
        'finish-intro': () => { state.hasSeenIntro = true; saveState(); closeModal('introModal'); },
        'export-data': exportData,
        'import-data': () => $('#importFile').click(),
        'install-app': installApp,
        'week-event-done': () => setWeekOccurrenceStatus(actionButton.dataset.scheduleOccurrenceId, 'done'),
        'week-event-skip': () => setWeekOccurrenceStatus(actionButton.dataset.scheduleOccurrenceId, 'skipped'),
        'reset-app': resetApp
      };
      actions[action]?.();
    });

    $('#taskForm').addEventListener('submit', saveTaskFromForm);
    $('#quickAddForm').addEventListener('submit', addQuickTask);
    $('#proofForm').addEventListener('submit', addManualProof);
    $('#taskSort').addEventListener('change', renderTasks);
    $('#importFile').addEventListener('change', event => importData(event.target.files?.[0]));

    $('#durationPicker').addEventListener('click', event => {
      const button = event.target.closest('[data-minutes]');
      if (!button || focus.running) return;
      state.focusDuration = Number(button.dataset.minutes);
      focus.totalSeconds = state.focusDuration * 60;
      focus.remainingSeconds = focus.totalSeconds;
      saveState();
      renderFocus();
    });

    $('#tonePicker').addEventListener('click', event => {
      const button = event.target.closest('[data-tone]');
      if (!button) return;
      state.tone = button.dataset.tone;
      saveState();
      renderAll();
      showToast(state.tone === 'direct' ? 'Говорим прямо.' : 'Перешли на спокойный тон.');
    });

    $$('.modal-backdrop').forEach(backdrop => {
      backdrop.addEventListener('mousedown', event => {
        if (event.target !== backdrop) return;
        if (backdrop.id === 'introModal' || backdrop.id === 'roundModal') return;
        if (backdrop.id === 'rescueModal') closeRescue();
        else closeModal(backdrop.id);
      });
    });

    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      const open = $$('.modal-backdrop:not([hidden])').at(-1);
      if (!open || open.id === 'introModal' || open.id === 'roundModal') return;
      if (open.id === 'rescueModal') closeRescue();
      else closeModal(open.id);
    });

    window.addEventListener('beforeinstallprompt', event => {
      event.preventDefault();
      deferredInstallPrompt = event;
      renderSettings();
    });
  }

  function init() {
    bindEvents();
    document.body.dataset.tone = state.tone;
    if (!focus.taskId) {
      const suggested = getSuggestedTask();
      focus.taskId = suggested?.id || null;
      state.selectedFocusTaskId = focus.taskId;
      saveState();
    }
    renderAll();
    if (!state.hasSeenIntro) openModal('introModal');

    if ('serviceWorker' in navigator && location.protocol !== 'file:') {
      navigator.serviceWorker.register('./sw.js').catch(error => console.warn('Service worker:', error));
    }
  }

  init();
})();

const DVIZH_MINIMAL_UI_V1 = true;
(() => {
  const STORAGE_KEY = 'dvizh:minimal-ui:v1';
  const root = document.documentElement;
  let observerQueued = false;

  function readEnabled() {
    try { return localStorage.getItem(STORAGE_KEY) !== 'off'; }
    catch (_) { return true; }
  }

  function writeEnabled(enabled) {
    try { localStorage.setItem(STORAGE_KEY, enabled ? 'on' : 'off'); }
    catch (_) {}
  }

  function updateToggle() {
    const button = document.getElementById('minimalUiToggle');
    if (!button) return;
    const enabled = root.classList.contains('dvizh-minimal-ui');
    const label = enabled ? 'Включён' : 'Выключен';
    if (button.textContent !== label) button.textContent = label;
    button.setAttribute('aria-pressed', String(enabled));
    button.title = enabled ? 'Показать полный интерфейс' : 'Включить спокойный интерфейс';
  }

  function markSecondary() {
    const selectors = [
      '#view-training .training-load-card',
      '#view-training .training-lower-grid',
      '#view-training .training-history-panel',
      '#view-training .jump-editor-grid',
      '#view-training .jump-program-card',
      '#view-training .jump-coach-grid',
      '#view-social .social-metrics-card',
      '#view-social .social-window-card',
      '#view-social .social-lower-layout'
    ];
    selectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(node => {
        node.setAttribute('data-minimal-secondary', 'true');
      });
    });
  }

  function ensureDetailsButton(viewSelector, headingSelector) {
    const view = document.querySelector(viewSelector);
    if (!view) return;
    const heading = view.querySelector(headingSelector);
    if (!heading || heading.querySelector('.minimal-details-toggle')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ghost small minimal-details-toggle';
    button.setAttribute('data-minimal-details-toggle', 'true');
    button.textContent = view.dataset.minimalDetails === 'open' ? 'Скрыть детали' : 'Детали';
    heading.appendChild(button);
  }

  function ensureStructure() {
    markSecondary();
    ensureDetailsButton('#view-training', '.training-heading');
    ensureDetailsButton('#view-social', '.social-heading');
    updateToggle();
  }

  function apply(enabled) {
    root.classList.toggle('dvizh-minimal-ui', Boolean(enabled));
    writeEnabled(Boolean(enabled));
    ensureStructure();
  }

  function toggleDetails(button) {
    const view = button.closest('.view');
    if (!view) return;
    const open = view.dataset.minimalDetails !== 'open';
    view.dataset.minimalDetails = open ? 'open' : 'closed';
    button.textContent = open ? 'Скрыть детали' : 'Детали';
  }

  function handleClick(event) {
    const toggle = event.target.closest('#minimalUiToggle');
    if (toggle) {
      event.preventDefault();
      apply(!root.classList.contains('dvizh-minimal-ui'));
      return;
    }

    const details = event.target.closest('[data-minimal-details-toggle]');
    if (details) {
      event.preventDefault();
      toggleDetails(details);
      return;
    }

    const shortcut = event.target.closest('[data-minimal-nav]');
    if (shortcut) {
      event.preventDefault();
      const view = shortcut.getAttribute('data-minimal-nav');
      if (view && typeof navigate === 'function') navigate(view);
    }
  }

  function queueEnsure() {
    if (observerQueued) return;
    observerQueued = true;
    requestAnimationFrame(() => {
      observerQueued = false;
      ensureStructure();
    });
  }

  function boot() {
    root.classList.toggle('dvizh-minimal-ui', readEnabled());
    ensureStructure();
    document.addEventListener('click', handleClick);
    if (document.body && typeof MutationObserver !== 'undefined') {
      new MutationObserver(queueEnsure).observe(document.body, {childList:true, subtree:true});
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();

