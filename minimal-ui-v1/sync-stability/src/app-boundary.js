  // Remote application is deliberately DOM-free. Existing user render/navigation
  // actions expose refreshed data; no active node, timer or view is replaced.
  const stateCopy = value => JSON.parse(JSON.stringify(value));
  // Immutable legacy sync may run beside a revalidated app. In that case keep
  // the original save/command path; legacy sync still owns its reload behavior.
  const canReconcile = () => typeof window.DVIZH_SYNC?.reconcile === 'function';
  let stateBase = stateCopy(state);
  const formBases = new WeakMap();
  let submitBase = null;
  let submitRemote = null;
  let consumedFields = [];
  function updateStateObject(target, next) {
    for (const key of Object.keys(target)) if (!(key in next)) delete target[key];
    for (const [key, value] of Object.entries(next)) {
      const old = target[key];
      if (Array.isArray(value) && Array.isArray(old)) {
        const byId = new Map(old.filter(row => row?.id != null).map(row => [String(row.id), row]));
        target[key] = value.map(row => {
          const existing = row?.id != null && byId.get(String(row.id));
          if (existing) { updateStateObject(existing, row); return existing; }
          return row;
        });
      } else if (value && old && typeof value === 'object' && typeof old === 'object' && !Array.isArray(value) && !Array.isArray(old)) {
        updateStateObject(old, value);
      } else target[key] = value;
    }
  }
  window.DVIZH_MANUAL_STATE = Object.freeze({
    snapshot: () => stateCopy(state),
    applyRemote(next) {
      if (!canReconcile()) return;
      if (!next || next.version !== 1 || !Array.isArray(next.tasks)) return;
      // Include untouched and blurred forms: focus is not a dirty-state signal.
      for (const form of document.forms) if (!formBases.has(form)) formBases.set(form, stateCopy(state));
      updateStateObject(state, window.DVIZH_SYNC.reconcile(stateBase, state, next));
      stateBase = stateCopy(state);
    }
  });
  document.addEventListener('submit', event => {
    if (!canReconcile()) return;
    const form = event.target;
    submitBase = formBases.get(form) || null;
    submitRemote = stateCopy(state);
    consumedFields = [];
    queueMicrotask(() => { submitBase = null; submitRemote = null; consumedFields = []; });
  }, true);
  // Update commands carry whole form payloads. Rebase their unchanged leaves too,
  // otherwise a server bridge could undo the correctly reconciled local snapshot.
  function rebaseCommand(domain, action, payload) {
    if (!canReconcile()) return;
    if (!submitBase || !submitRemote) return;
    const oldHub = submitBase[domain] || {}, newHub = submitRemote[domain] || {};
    let data, before, after;
    if (action === 'profile_update') { data=payload.profile; before=oldHub.profile; after=newHub.profile; }
    else if (action === 'exercise_update') { data=payload.exercise; before=oldHub.exercises?.find(x=>String(x.id)===String(payload.exerciseId)); after=newHub.exercises?.find(x=>String(x.id)===String(payload.exerciseId)); }
    else if (action === 'content_update') { data=payload.content; before=oldHub.content?.find(x=>String(x.id)===String(payload.contentId)); after=newHub.content?.find(x=>String(x.id)===String(payload.contentId)); }
    else if (domain === 'weeklySchedule' && action === 'update') { data=payload; before=oldHub.items?.find(x=>String(x.id)===String(payload.itemId)); after=newHub.items?.find(x=>String(x.id)===String(payload.itemId)); }
    if (!data || !before || !after) return;
    for (const key of Object.keys(data)) {
      const field = domain === 'jumpLab' ? key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()) : key;
      if (Object.hasOwn(before, field) && Object.hasOwn(after, field)) {
        // Capture the submitted value before rebasing; only consumed edits
        // advance their displayed ancestor after persistence succeeds.
        if (JSON.stringify(data[key]) !== JSON.stringify(before[field])) {
          consumedFields.push({before, field, value: stateCopy(data[key])});
        }
        data[key] = window.DVIZH_SYNC.reconcile(before[field], data[key], after[field]);
      }
    }
  }

  function rememberForm(id) {
    if (!canReconcile()) return;
    const form = document.getElementById(id);
    if (!form) return;
    const base = stateCopy(state);
    // Record each rendered profile field, including defaults. Jump skips only
    // the focused input: retain that field's DISPLAYED ancestor across saves
    // while advancing siblings that were actually repainted. Social fills all fields.
    const fields = id === 'jumpProfileForm' ? jumpProfileFields : id === 'socialSettingsForm' ? {
      socialWeeklyGoal:'weeklyGoal', socialProfileCourage:'courageLevel', socialWindow1:'commentWindow1', socialWindow2:'commentWindow2'
    } : null;
    const profile = id === 'jumpProfileForm' ? base.jumpLab?.profile : base.socialHub?.profile;
    if (fields && profile) for (const [inputId, field] of Object.entries(fields)) {
      const input = document.getElementById(inputId);
      if (!input || !form.contains(input)) continue;
      if (id === 'jumpProfileForm' && input === document.activeElement) {
        const previous = formBases.get(form)?.jumpLab?.profile;
        if (previous && Object.hasOwn(previous, field)) profile[field] = previous[field];
      } else {
        profile[field] = input.type === 'number' || inputId === 'socialProfileCourage' ? (input.value === '' ? null : Number(input.value)) : input.value;
      }
    }
    formBases.set(form, base);
  }
