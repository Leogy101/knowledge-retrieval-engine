"""Run the independently frozen alpha holdout as part of full discovery."""
import importlib.util
from pathlib import Path
p = Path(__file__).resolve().parents[1] / "evaluation/alpha-readiness-v1/test_holdout.py"
spec = importlib.util.spec_from_file_location("kre_alpha_holdout_tests", p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FrozenAlphaHoldout = module.FrozenAlphaHoldout
