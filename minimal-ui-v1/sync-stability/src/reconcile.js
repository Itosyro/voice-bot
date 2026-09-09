  // Three-way JSON reconciliation. Local changed leaves win simultaneous edits;
  // deletion of an existing record wins over edits. Identity arrays merge by id.
  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === 'object') return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, canonical(value[key])]));
    return value;
  }
  const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  function reconcile(base, local, remote, entity = false) {
    const localReset = local?.__sync?.resetAt;
    const remoteReset = remote?.__sync?.resetAt;
    const baseReset = base?.__sync?.resetAt;
    if (remoteReset && remoteReset !== baseReset && parseTime(remoteReset) >= parseTime(localReset)) return clone(remote);
    if (localReset && localReset !== baseReset && parseTime(localReset) > parseTime(remoteReset)) return clone(local);
    if (same(local, base)) return clone(remote);
    if (same(remote, base) || same(local, remote)) return clone(local);
    if (local === undefined || (entity && base !== undefined && remote === undefined)) return undefined;
    const identified = (value, key) => Array.isArray(value) && value.every(row => row && typeof row === 'object' && row[key] != null)
      && new Set(value.map(row => String(row[key]))).size === value.length;
    const identity = ['id', 'commandId', 'code', 'exerciseKey'].find(key => identified(local, key) && identified(remote, key) && (base === undefined || identified(base, key)));
    if (identity) {
      const index = rows => new Map((rows || []).map(row => [String(row[identity]), row]));
      const b=index(base), l=index(local), r=index(remote);
      return [...new Set([...l.keys(), ...r.keys()])].map(id => reconcile(b.get(id),l.get(id),r.get(id), true)).filter(row => row !== undefined);
    }
    const record = value => value && typeof value === 'object' && !Array.isArray(value);
    if (record(local) && record(remote) && (base === undefined || record(base))) {
      const result = {};
      for (const key of new Set([...Object.keys(base || {}), ...Object.keys(local), ...Object.keys(remote)])) {
        const value = reconcile(base?.[key], local[key], remote[key]);
        if (value !== undefined) Object.defineProperty(result,key,{value,enumerable:true,writable:true,configurable:true});
      }
      return result;
    }
    return clone(local);
  }
  // One-time upgrade: older clients did not retain a common ancestor. Keep the
  // legacy core timestamp merge, but never use its settings winner for projections.
  function upgradeMerge(localInput, remoteInput) {
    const local = normalizeState(localInput), remote = normalizeState(remoteInput);
    const merged = mergeStates(local, remote);
    if (!local || !remote) return merged;
    if (parseTime(local.__sync.resetAt) > parseTime(remote.__sync.updatedAt) || parseTime(remote.__sync.resetAt) > parseTime(local.__sync.updatedAt)) return merged;
    const core = new Set(['version','createdAt','hasSeenIntro','tone','focusDuration','selectedFocusTaskId','tasks','sessions','proofs','checkins','plans','ladder','__sync']);
    for (const key of Object.keys(remote)) if (!core.has(key)) merged[key] = clone(remote[key]);
    for (const key of ['trainingHub','jumpLab','weeklySchedule','socialHub']) {
      if (!local[key] && !remote[key]) continue;
      const results = remote[key]?.commandResults || [];
      const acknowledged = new Set(results.flatMap(row => [row.id, row.commandId]).filter(id => id != null).map(String));
      const commands = reconcile([], local[key]?.webCommands || [], remote[key]?.webCommands || []).filter(row => !acknowledged.has(String(row.id)));
      merged[key] ||= {};
      if (commands.length || remote[key]?.webCommands) merged[key].webCommands = commands;
    }
    if (local.aiProposalCommands || remote.aiProposalCommands) merged.aiProposalCommands = reconcile([], local.aiProposalCommands || [], remote.aiProposalCommands || []);
    return merged;
  }
