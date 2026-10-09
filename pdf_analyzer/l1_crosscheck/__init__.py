"""
L1 Cross-Check Package for PDF Design Analyzer.
Dual independent 600 DPI renderers (PyMuPDF & pypdfium2), sub-pixel edge fitting,
least-squares affine registration, multi-engine cross-validation, and Gate G1-G3 auditing.
"""

from pdf_analyzer.l1_crosscheck.renderers import DualRenderer, RenderedPage
from pdf_analyzer.l1_crosscheck.subpixel import SubpixelProfileEngine, SubpixelLineFit
from pdf_analyzer.l1_crosscheck.registration import RegistrationEngine, RegistrationResult
from pdf_analyzer.l1_crosscheck.crosscheck import L1CrossCheckEngine, TruthReport
from pdf_analyzer.l1_crosscheck.gates import GateEvaluator, GateReport
from pdf_analyzer.l1_crosscheck.audit import run_l1_audit

__all__ = [
    "DualRenderer",
    "RenderedPage",
    "SubpixelProfileEngine",
    "SubpixelLineFit",
    "RegistrationEngine",
    "RegistrationResult",
    "L1CrossCheckEngine",
    "TruthReport",
    "GateEvaluator",
    "GateReport",
    "run_l1_audit",
]
