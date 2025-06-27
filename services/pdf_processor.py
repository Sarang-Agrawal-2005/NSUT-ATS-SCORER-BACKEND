import PyPDF2
import re
import logging

logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self):
        self.text_cleaning_patterns = [
            (r'\s+', ' '),  # Multiple spaces to single space
            (r'\n+', '\n'),  # Multiple newlines to single newline
            (r'[^\w\s@.,()-]', ''),  # Remove special characters except common ones
        ]
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from PDF file
        """
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text()
                
                # Clean extracted text
                cleaned_text = self.clean_text(text)
                logger.info(f"Extracted {len(cleaned_text)} characters from PDF")
                
                return cleaned_text
                
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            return ""
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text
        """
        # Apply cleaning patterns
        for pattern, replacement in self.text_cleaning_patterns:
            text = re.sub(pattern, replacement, text)
        
        # Remove extra whitespace
        text = text.strip()
        
        return text
