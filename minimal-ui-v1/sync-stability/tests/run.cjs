// node:test also runs directly in one process (works in restricted VMs).
require('./sync.test.cjs');
require('./dom.test.cjs');
require('./contracts.test.cjs');
require('./mixed-cache.test.cjs');
// Mandatory safety gate: known mixed-version data loss must fail the full run.
require('./reverse-cache-diagnostic.cjs');

require('./protective.test.cjs');
