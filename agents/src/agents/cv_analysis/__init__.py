"""CV Analysis Agent — L3 Specialist Agent.

Public surface:
    CVAgent          — register via agents.core.agent_registry.registry.register()
    PDFParser        — text-extraction component (injectable in tests)
    CVParser         — LLM-based structured parser (injectable in tests)
    SkillExtractor   — keyword-scan skill collector (injectable in tests)
    SkillNormaliser  — dict + LLM skill normaliser (injectable in tests)
    ReadinessScorer  — LLM readiness scorer (injectable in tests)
    ParsedCV         — structured CV output model
    SkillGraph       — normalised skill graph model
    ReadinessResult  — readiness score + breakdown model
"""
from agents.cv_analysis.cv_agent import CVAgent
from agents.cv_analysis.cv_parser import CVParser
from agents.cv_analysis.models import ParsedCV, ReadinessResult, SkillGraph, SkillNode
from agents.cv_analysis.pdf_parser import PDFParser
from agents.cv_analysis.readiness_scorer import ReadinessScorer
from agents.cv_analysis.skill_extractor import SkillExtractor
from agents.cv_analysis.skill_normaliser import SkillNormaliser

__all__ = [
    "CVAgent",
    "PDFParser",
    "CVParser",
    "SkillExtractor",
    "SkillNormaliser",
    "ReadinessScorer",
    "ParsedCV",
    "SkillGraph",
    "SkillNode",
    "ReadinessResult",
]
