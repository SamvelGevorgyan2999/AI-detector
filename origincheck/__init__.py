"""OriginCheck — local AI-content detector for image and PDF files."""

from origincheck.detector import ENGINE_NAME, DetectionReport, analyze_file

__all__ = ["ENGINE_NAME", "DetectionReport", "analyze_file"]


