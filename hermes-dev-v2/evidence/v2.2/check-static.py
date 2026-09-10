"""Run only the existing non-installer workflow checks; never invoke installers."""
from pathlib import Path
import subprocess

workflow = Path('.github/workflows/dvizh-hermes-autopilot-v2-tests.yml').read_text()
for name in (
    'Syntax and static security boundary',
    'Generic Hermes branch CI must repeat path isolation and AI browser smoke',
    'Confirm no unrestricted root or Git surface',
):
    section = workflow.split('- name: ' + name + '\n', 1)[1]
    block = section.split('        run: |\n', 1)[1]
    lines = []
    for line in block.splitlines():
        if line and not line.startswith('          '):
            break
        lines.append(line[10:])
    result = subprocess.run(['bash', '-c', '\n'.join(lines)], capture_output=True, text=True)
    print(f'{name}: exit {result.returncode}')
    print(result.stdout, end=''); print(result.stderr, end='')
    if result.returncode:
        raise SystemExit(result.returncode)
