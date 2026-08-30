from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGE = "dvizh_training_test"

if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    assert spec.loader
    spec.loader.exec_module(module)
