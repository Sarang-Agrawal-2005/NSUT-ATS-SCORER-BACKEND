from pydantic import BaseModel
from typing import Dict, List

class Suggestion(BaseModel):
    title: str
    description: str
    priority: str  # "high", "medium", "low"

class ResumeAnalysis(BaseModel):
    filename: str
    overall_score: int
    section_scores: Dict[str, int]
    keywords_found: int
    sections_detected: int
    format_score: int
    suggestions: List[Suggestion]
