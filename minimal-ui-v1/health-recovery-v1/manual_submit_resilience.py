"""Preserve the displayed form ancestor throughout a native submit event."""
from client_resilience import once


def apply_manual_client(text):
    text = once(text, '  let consumedFields = [];',
        '  let consumedFields = [];\n  let submitEpoch = 0;')
    text = once(text,
        '    queueMicrotask(() => { submitBase = null; submitRemote = null; consumedFields = []; });',
        '''    const epoch = ++submitEpoch;
    // Native browser events run a microtask checkpoint between capture and
    // target listeners. Keep the form ancestor until target/bubble processing
    // completes, and never let an older cleanup erase a newer submission.
    setTimeout(() => {
      if (epoch !== submitEpoch) return;
      submitBase = null; submitRemote = null; consumedFields = [];
    }, 0);''')
    return text
