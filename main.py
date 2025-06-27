from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import aiofiles
from services.pdf_processor import PDFProcessor
from services.ats_scorer import ATSScorer
from models.resume_models import ResumeAnalysis
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="NSUT ATS Scorer API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
pdf_processor = PDFProcessor()
ats_scorer = ATSScorer()

# Ensure upload directory exists
os.makedirs("uploads", exist_ok=True)

@app.get("/")
async def root():
    return {"message": "NSUT ATS Scorer API is running"}

@app.post("/upload-resume", response_model=ResumeAnalysis)
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload and analyze a resume file
    """
    try:
        # Validate file type
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Validate file size (5MB limit)
        if file.size > 5 * 1024 * 1024: #type: ignore
            raise HTTPException(status_code=400, detail="File size must be less than 5MB")
        
        # Save uploaded file
        file_path = f"uploads/{file.filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Process PDF and extract text
        logger.info(f"Processing file: {file.filename}")
        extracted_text = pdf_processor.extract_text(file_path)
        
        if not extracted_text:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
        
        # Analyze resume with ATS scorer
        analysis = ats_scorer.analyze_resume(extracted_text, file.filename) #type: ignore
        
        # Clean up uploaded file
        os.remove(file_path)
        
        logger.info(f"Analysis completed for: {file.filename}")
        return analysis
        
    except Exception as e:
        logger.error(f"Error processing resume: {str(e)}")
        # Clean up file if it exists
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "pdf_processor": "running",
            "ats_scorer": "running"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
