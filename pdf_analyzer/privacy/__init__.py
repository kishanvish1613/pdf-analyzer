"""Privacy and PII Protection Package for PDF Analyzer."""

from pdf_analyzer.privacy.pii_detector import PIIDetector, PIIMatch, RedactionRecord, PIIReport
from pdf_analyzer.privacy.redactor import RedactionEngine, redact_string_with_same_width
from pdf_analyzer.privacy.synthetic import SyntheticDataEngine
from pdf_analyzer.privacy.engine import (
    PrivacyEngine,
    apply_privacy_transform,
    apply_privacy_to_editor_model
)

__all__ = [
    "PIIDetector",
    "PIIMatch",
    "RedactionRecord",
    "PIIReport",
    "RedactionEngine",
    "redact_string_with_same_width",
    "SyntheticDataEngine",
    "PrivacyEngine",
    "apply_privacy_transform",
    "apply_privacy_to_editor_model"
]

