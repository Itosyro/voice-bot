  // Authorized health-only delta: derived sleep fields are never independent leaves.
  function normalizeHealthSleep(state) {
    const h = state?.healthRecovery;
    if (!h || (h.version !== undefined && h.version !== 1) || !h.sleep || Array.isArray(h.sleep)) return state;
    for (const [day, row] of Object.entries(h.sleep)) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) continue;
      if (row.durationKind === 'reported') {
        for (const key of ['start','end','startDay']) delete row[key];
      } else if (row.durationKind === 'clock' || (!Object.hasOwn(row,'durationKind') && Object.hasOwn(row,'start') && Object.hasOwn(row,'end'))) {
        const clock = value => typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(value) ? +value.slice(0,2)*60 + +value.slice(3) : NaN;
        const a=clock(row.start), b=clock(row.end), minutes=(b-a+1440)%1440;
        const date = new Date(day+'T00:00:00Z');
        if (minutes && /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(+date) && date.toISOString().slice(0,10)===day) {
          row.durationMinutes=minutes;
          row.startDay=new Date(+date-(a>b?86400000:0)).toISOString().slice(0,10);
        } else {
          delete row.durationMinutes;
          delete row.startDay;
        }
      }
    }
    return state;
  }
  function reconcile(base, local, remote) {
    const result = reconcileJSON(base, local, remote);
    const reset = result?.__sync?.resetAt;
    if (reset && reset !== base?.__sync?.resetAt) return normalizeHealthSleep(result);
    const h=result?.healthRecovery;
    if (h && (h.version === undefined || h.version === 1)) {
      const mode = row => row?.durationKind || (row?.start !== undefined && row?.end !== undefined ? 'clock' : 'reported');
      for (const [day,row] of Object.entries(h.sleep || {})) {
        const b=base?.healthRecovery?.sleep?.[day], l=local?.healthRecovery?.sleep?.[day], r=remote?.healthRecovery?.sleep?.[day];
        if (!row || typeof row !== 'object' || Array.isArray(row) || !l || !r || mode(l)===mode(r)) continue;
        // Mode changes select only the temporal bundle. All other leaves retain
        // the existing three-way merge, including note, quality and future fields.
        const winner = mode(l)!==mode(b) ? l : r;
        for (const key of ['durationKind','durationMinutes','start','end','startDay']) {
          if (Object.hasOwn(winner,key)) row[key]=clone(winner[key]);
          else delete row[key];
        }
      }
    }
    return normalizeHealthSleep(result);
  }
