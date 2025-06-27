import re
from typing import Dict, List, Tuple
from models.resume_models import ResumeAnalysis, Suggestion
import logging

logger = logging.getLogger(__name__)

class ATSScorer:
    def __init__(self):
        # Define section patterns
        self.section_patterns = {
            'contact_info': [
                r'email', r'phone', r'linkedin', r'github', r'address'
            ],
            'professional_summary': [
                r'summary', r'objective', r'profile', r'about'
            ],
            'experience': [
                r'experience', r'employment', r'work history', r'career'
            ],
            'education': [
                r'education', r'academic', r'degree', r'university', r'college'
            ],
            'skills': [
                r'skills', r'technical skills', r'technologies', r'programming'
            ],
            'projects': [
                r'projects', r'portfolio', r'work samples'
            ],
            'certifications': [
                r'certifications', r'licenses', r'certificates'
            ]
        }
        
        # Common technical keywords
        self.tech_keywords = [
            'python', 'java', 'javascript', 'react', 'node.js', 'sql',
            'html', 'css', 'git', 'github', 'docker', 'kubernetes',
            'aws', 'azure', 'mongodb', 'postgresql', 'mysql',
            'machine learning', 'data science', 'api', 'rest',
            'agile', 'scrum', 'ci/cd', 'jenkins', 'linux'
        ]
        
        # Format indicators
        self.format_indicators = {
            'bullet_points': r'[•·▪▫▸▹‣⁃]|\*\s|\-\s|\d+\.\s',
            'dates': r'\b\d{4}\b|\b\d{1,2}/\d{4}\b|\b\w+\s\d{4}\b',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\b\(\d{3}\)\s?\d{3}[-.]?\d{4}\b',
            'urls': r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        }
    
    def analyze_resume(self, text: str, filename: str) -> ResumeAnalysis:
        """
        Analyze resume text and return ATS score with suggestions
        """
        logger.info(f"Starting analysis for: {filename}")
        
        # Analyze different aspects
        section_scores = self.analyze_sections(text)
        keywords_found = self.count_keywords(text)
        format_score = self.analyze_format(text)
        sections_detected = len([s for s in section_scores.values() if s > 0])
        
        # Calculate overall score
        overall_score = self.calculate_overall_score(
            section_scores, keywords_found, format_score
        )
        
        # Generate suggestions
        suggestions = self.generate_suggestions(
            text, section_scores, keywords_found, format_score
        )
        
        return ResumeAnalysis(
            filename=filename,
            overall_score=overall_score,
            section_scores=section_scores,
            keywords_found=keywords_found,
            sections_detected=sections_detected,
            format_score=format_score,
            suggestions=suggestions
        )
    
    def analyze_sections(self, text: str) -> Dict[str, int]:
        """
        Analyze presence and quality of resume sections
        """
        text_lower = text.lower()
        section_scores = {}
        
        for section, patterns in self.section_patterns.items():
            score = 0
            
            # Check if section exists
            section_found = any(
                re.search(pattern, text_lower) for pattern in patterns
            )
            
            if section_found:
                # Base score for having the section
                score = 60
                
                # Additional scoring based on content quality
                if section == 'contact_info':
                    score += self.score_contact_info(text)
                elif section == 'skills':
                    score += self.score_skills_section(text)
                elif section == 'experience':
                    score += self.score_experience_section(text)
                elif section == 'education':
                    score += self.score_education_section(text)
                
                score = min(score, 100)  # Cap at 100
            
            section_scores[section] = score
        
        return section_scores
    
    def score_contact_info(self, text: str) -> int:
        """Score contact information completeness"""
        score = 0
        if re.search(self.format_indicators['email'], text):
            score += 10
        if re.search(self.format_indicators['phone'], text):
            score += 10
        if 'linkedin' in text.lower():
            score += 10
        if 'github' in text.lower():
            score += 10
        return score
    
    def score_skills_section(self, text: str) -> int:
        """Score technical skills section"""
        tech_count = sum(1 for keyword in self.tech_keywords 
                        if keyword.lower() in text.lower())
        return min(tech_count * 5, 40)  # Max 40 additional points
    
    def score_experience_section(self, text: str) -> int:
        """Score work experience section"""
        score = 0
        # Check for bullet points
        if re.search(self.format_indicators['bullet_points'], text):
            score += 15
        # Check for dates
        if re.search(self.format_indicators['dates'], text):
            score += 15
        # Check for action verbs
        action_verbs = ['developed', 'implemented', 'managed', 'created', 
                       'designed', 'built', 'led', 'optimized']
        verb_count = sum(1 for verb in action_verbs 
                        if verb in text.lower())
        score += min(verb_count * 2, 10)
        
        return score
    
    def score_education_section(self, text: str) -> int:
        """Score education section"""
        score = 0
        education_keywords = ['degree', 'bachelor', 'master', 'phd', 
                             'university', 'college', 'gpa']
        edu_count = sum(1 for keyword in education_keywords 
                       if keyword.lower() in text.lower())
        return min(edu_count * 5, 40)
    
    def count_keywords(self, text: str) -> int:
        """Count relevant technical keywords"""
        return sum(1 for keyword in self.tech_keywords 
                  if keyword.lower() in text.lower())
    
    def analyze_format(self, text: str) -> int:
        """Analyze resume format and structure"""
        score = 0
        
        # Check for proper formatting elements
        if re.search(self.format_indicators['bullet_points'], text):
            score += 25
        if re.search(self.format_indicators['dates'], text):
            score += 25
        if re.search(self.format_indicators['email'], text):
            score += 20
        if re.search(self.format_indicators['phone'], text):
            score += 20
        
        # Check text length (not too short, not too long)
        word_count = len(text.split())
        if 200 <= word_count <= 800:
            score += 10
        
        return min(score, 100)
    
    def calculate_overall_score(self, section_scores: Dict[str, int], 
                               keywords_found: int, format_score: int) -> int:
        """Calculate overall ATS score"""
        # Weight different components
        section_avg = sum(section_scores.values()) / len(section_scores)
        keyword_score = min(keywords_found * 5, 100)
        
        # Weighted average
        overall = (
            section_avg * 0.5 +      # 50% weight on sections
            keyword_score * 0.3 +    # 30% weight on keywords
            format_score * 0.2       # 20% weight on format
        )
        
        return int(overall)
    
    def generate_suggestions(self, text: str, section_scores: Dict[str, int],
                           keywords_found: int, format_score: int) -> List[Suggestion]:
        """Generate improvement suggestions"""
        suggestions = []
        
        # Section-based suggestions
        for section, score in section_scores.items():
            if score == 0:
                suggestions.append(Suggestion(
                    title=f"Add {section.replace('_', ' ').title()} Section",
                    description=f"Your resume is missing a {section.replace('_', ' ')} section. This is essential for ATS systems.",
                    priority="high"
                ))
            elif score < 70:
                suggestions.append(Suggestion(
                    title=f"Improve {section.replace('_', ' ').title()} Section",
                    description=f"Your {section.replace('_', ' ')} section could be enhanced with more relevant details and better formatting.",
                    priority="medium"
                ))
        
        # Keyword suggestions
        if keywords_found < 5:
            suggestions.append(Suggestion(
                title="Add More Technical Keywords",
                description="Include more relevant technical skills and keywords that match the job descriptions you're targeting.",
                priority="high"
            ))
        
        # Format suggestions
        if format_score < 60:
            suggestions.append(Suggestion(
                title="Improve Resume Formatting",
                description="Use bullet points, consistent date formats, and clear section headers to improve ATS readability.",
                priority="medium"
            ))
        
        # Add general suggestions
        suggestions.extend([
            Suggestion(
                title="Quantify Your Achievements",
                description="Add numbers and metrics to your accomplishments (e.g., 'Improved performance by 25%').",
                priority="medium"
            ),
            Suggestion(
                title="Tailor for Each Application",
                description="Customize your resume keywords and content for each job application to improve ATS matching.",
                priority="low"
            )
        ])
        
        return suggestions[:8]  # Limit to 8 suggestions
