import os
import tempfile
import subprocess
import shutil
import asyncio
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from jinja2 import Template
import aiofiles
from services.pdf_processor import PDFProcessor
from services.ats_scorer import ATSScorer
from models.resume_models import ResumeAnalysis
import logging


from fastapi.staticfiles import StaticFiles


app = FastAPI(title="NSUT ATS Scorer API", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
pdf_processor = PDFProcessor()
ats_scorer = ATSScorer()

# Ensure upload directory exists
os.makedirs("uploads", exist_ok=True)
os.makedirs("static/images", exist_ok=True)

@app.get("/")
async def root():
    return {"message": "NSUT ATS Scorer API is working"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "pdf_processor": "running",
            "ats_scorer": "running"
        }
    }

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
        if file.size > 5 * 1024 * 1024:  # type: ignore
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
        analysis = ats_scorer.analyze_resume(extracted_text, file.filename)  # type: ignore
        
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

@app.post("/api/compile-resume")
async def compile_resume(resume_data: dict):
    """
    Compile LaTeX resume from form data
    """
    try:
        logger.info("Starting resume compilation")
        logger.info(f"Received data: {resume_data}")
        
        # Validate required data
        if not resume_data.get('personal', {}).get('name'):
            raise HTTPException(status_code=400, detail="Name is required")
        
        # Generate LaTeX code from template
        logger.info("Generating LaTeX code...")
        latex_code = generate_latex_from_data(resume_data)
        logger.info("LaTeX code generated successfully")
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Created temp directory: {temp_dir}")
            
            tex_path = os.path.join(temp_dir, 'resume.tex')
            
            # Write LaTeX file
            logger.info("Writing LaTeX file...")
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(latex_code)
            logger.info(f"LaTeX file written to: {tex_path}")
            
            # Create logo
            logger.info("Creating logo...")
            logo_path = os.path.join(temp_dir, "NSUT_logo.png")
            create_placeholder_logo(logo_path)
            logger.info(f"Logo created at: {logo_path}")
            
            # Try to compile LaTeX
            try:
                logger.info("Starting LaTeX compilation...")
                pdf_path = await compile_latex_to_pdf(tex_path, temp_dir)
                logger.info(f"PDF compiled successfully: {pdf_path}")
                
                # Return PDF
                return FileResponse(
                    pdf_path,
                    media_type='application/pdf',
                    filename=f"{resume_data['personal']['name'].replace(' ', '_')}_NSUT_Resume.pdf"
                )
                
            except Exception as compile_error:
                logger.error(f"LaTeX compilation failed: {str(compile_error)}")
                logger.error(f"Error type: {type(compile_error)}")
                
                # Return LaTeX source as fallback
                return JSONResponse(
                    status_code=200,
                    content={
                        "compilation_failed": True,
                        "error": str(compile_error),
                        "latex_source": latex_code,
                        "message": "LaTeX compilation failed. Use the source code below with Overleaf.",
                        "instructions": [
                            "1. Copy the LaTeX code below",
                            "2. Go to https://www.overleaf.com",
                            "3. Create a new project and paste the code",
                            "4. Upload the NSUT logo image",
                            "5. Compile to generate your PDF"
                        ]
                    }
                )
                
    except Exception as e:
        logger.error(f"Resume compilation failed with error: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Traceback: ", exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Server error during resume compilation",
                "detail": str(e),
                "type": str(type(e).__name__)
            }
        )


async def compile_latex_to_pdf(tex_path: str, temp_dir: str) -> str:
    """Compile LaTeX to PDF using pdflatex"""
    try:
        logger.info(f"Attempting to compile LaTeX file: {tex_path}")
        
        # Check if pdflatex is available
        try:
            check_process = await asyncio.create_subprocess_exec(
                'pdflatex', '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await check_process.communicate()
            if check_process.returncode != 0:
                raise FileNotFoundError("pdflatex not working properly")
        except FileNotFoundError:
            raise Exception("pdflatex is not installed on this server. LaTeX compilation requires a LaTeX distribution.")
        
        # Run pdflatex with non-interactive mode
        for i in range(2):
            logger.info(f"Running pdflatex (attempt {i+1}/2)...")
            
            process = await asyncio.create_subprocess_exec(
                'pdflatex', 
                '-output-directory', temp_dir,
                '-interaction', 'nonstopmode',  # Don't stop for errors
                '-halt-on-error',              # Stop on first error
                tex_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            logger.info(f"pdflatex return code: {process.returncode}")
            logger.info(f"pdflatex stdout: {stdout.decode()[:500]}...")  # First 500 chars
            
            if stderr:
                logger.warning(f"pdflatex stderr: {stderr.decode()[:500]}...")
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else stdout.decode()
                logger.error(f"pdflatex failed on attempt {i+1}: {error_msg}")
                
                if i == 1:  # Last attempt
                    raise Exception(f"LaTeX compilation failed: {error_msg[:1000]}")  # Limit error message length
        
        pdf_path = tex_path.replace('.tex', '.pdf')
        if not os.path.exists(pdf_path):
            raise Exception("PDF file was not created despite successful compilation")
            
        logger.info(f"PDF successfully created: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        logger.error(f"LaTeX compilation error: {str(e)}")
        raise


def create_placeholder_logo(logo_path: str):
    """Create a simple placeholder logo if NSUT logo doesn't exist"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a simple placeholder image
        img = Image.new('RGB', (200, 80), color='white')
        draw = ImageDraw.Draw(img)
        
        # Add text
        try:
            font = ImageFont.load_default()
        except:
            font = None
            
        # Draw NSUT text
        draw.text((50, 20), "NSUT", fill='red', font=font)
        draw.text((20, 45), "Netaji Subhas University", fill='black', font=font)
        draw.text((30, 60), "of Technology", fill='black', font=font)
        
        img.save(logo_path, 'PNG')
        
    except ImportError:
        # If PIL is not available, create a minimal placeholder
        with open(logo_path, 'wb') as f:
            # Write a minimal PNG (1x1 transparent pixel)
            png_data = (
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
                b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
                b'\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
            )
            f.write(png_data)

def generate_latex_from_data(data):
    """Generate LaTeX code from form data - Simple string formatting approach"""
    
    # Extract data with defaults
    personal = data.get('personal', {})
    education = data.get('education', {})
    internships = data.get('internships', [])
    projects = data.get('projects', [])
    positions = data.get('positions', [])
    achievements = data.get('achievements', [])
    skills = data.get('skills', '')
    
    # Personal info with defaults
    name = personal.get('name', 'Your Name')
    phone = personal.get('phone', '+91-9999999999')
    email = personal.get('email', 'your.email@example.com')
    linkedin = personal.get('linkedin', 'https://www.linkedin.com/in/')
    
    # Education info with defaults
    degree = education.get('degree', 'B.Tech (Your Branch)')
    year = education.get('year', '20XX')
    cgpa = education.get('cgpa', '8.00')
    
    # Build LaTeX content using string formatting (no Jinja2)
    latex_content = f"""\\documentclass[11pt,article]{{article}}
\\usepackage[letterpaper,margin=0.5in]{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{booktabs}}
\\usepackage{{url}}
\\usepackage{{enumitem}}
\\usepackage{{palatino}}
\\usepackage{{tabularx}}
\\usepackage[T1]{{fontenc}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{color}}
\\definecolor{{mygrey}}{{gray}}{{0.82}}
\\usepackage{{hyperref}}
\\hypersetup{{
    hidelinks,
    colorlinks=true,
    urlcolor=blue
}}

\\setlength{{\\tabcolsep}}{{0in}}
\\newcommand{{\\isep}}{{-2pt}}
\\newcommand{{\\lsep}}{{-0.5cm}}
\\newcommand{{\\psep}}{{-0.6cm}}
\\renewcommand{{\\labelitemii}}{{$\\circ$}}

\\pagestyle{{empty}}

\\newcommand{{\\resitem}}[1]{{\\item #1 \\vspace{{-2pt}}}}
\\newcommand{{\\resheading}}[1]{{{{\\small \\colorbox{{mygrey}} {{ \\begin{{minipage}}{{0.99\\textwidth}}{{\\textbf{{#1 \\vphantom{{p\\^{{E}}}}}}}}\\end{{minipage}}}}}}}}

\\begin{{document}}
\\begin{{table}}
    \\begin{{minipage}}{{0\\linewidth}}
        \\centering
        \\includegraphics[height=0.8in]{{NSUT_logo.png}}
    \\end{{minipage}}
    \\begin{{minipage}}{{1\\linewidth}}
        \\centering
        \\def\\arraystretch{{1}}
        \\textbf{{\\Large{{{name}}}}}\\\\  \\vspace{{0.4em}}
        {phone} |
        \\href{{mailto:{email}}}{{Email}} |
        \\href{{{linkedin}}}{{LinkedIn}}
    \\end{{minipage}}\\hfill
\\end{{table}}
\\setlength{{\\tabcolsep}}{{18pt}}

\\begin{{table}}
\\centering
\\resheading{{\\textbf{{EDUCATION}} }}\\\\
\\vspace{{0.4em}}
\\begin{{tabular}}{{lllll}}
\\textbf{{Course}}    & \\textbf{{College / University}}     & \\textbf{{Year}}     & \\textbf{{CGPA / \\%}} \\\\ 
\\toprule
{degree}   & Netaji Subhas University of Technology  & {year}   & {cgpa} \\\\"""

    # Add Class XII if provided
    if education.get('class12'):
        school12 = education.get('school12', 'Your School Name')
        year12 = education.get('year12', '20XX')
        marks12 = education.get('marks12', '90')
        latex_content += f"""
Board (Class XII)      & {school12} & {year12} & {marks12}  \\\\"""

    # Add Class X if provided
    if education.get('class10'):
        school10 = education.get('school10', 'Your School Name')
        year10 = education.get('year10', '20XX')
        marks10 = education.get('marks10', '90')
        latex_content += f"""
Board (Class X)        & {school10} & {year10} & {marks10}"""

    latex_content += """
\\vspace{-0.8em}
\\end{tabular}
\\end{table}

"""

    # Add internships if any
    if internships:
        latex_content += """\\noindent
\\resheading{\\textbf{INTERNSHIP} }\\\\[-0.35cm]
\\vspace{-0.4em}
\\begin{itemize}
\\setlength\\itemsep{-0.3em}
"""
        for internship in internships:
            title = internship.get('title', 'Internship Title')
            company = internship.get('company', 'Company Name')
            location = internship.get('location', 'Location')
            duration = internship.get('duration', 'Month Year - Month Year')
            
            latex_content += f"""\\item \\textbf{{{title} | {company} | {location}}}\\hfill \\textbf{{{duration}}} 
\\vspace{{-0.5em}}
\\begin{{itemize}}[noitemsep]
"""
            
            responsibilities = internship.get('responsibilities', [])
            for resp in responsibilities:
                if resp.strip():
                    # Escape special LaTeX characters
                    resp_clean = resp.replace('&', '\\&').replace('%', '\\%').replace('$', '\\$')
                    latex_content += f"    \\item {resp_clean}\n"
            
            latex_content += "\\end{itemize}\n"
        
        latex_content += "\\end{itemize}\n\n"

    # Add projects if any
    if projects:
        latex_content += """\\noindent
\\resheading{\\textbf{PROJECT} }\\\\[-0.35cm]
\\vspace{-0.4em}
\\begin{itemize} [noitemsep]
"""
        for project in projects:
            title = project.get('title', 'Project Title')
            latex_content += f"\\item \\textbf{{{title}}}\n\\vspace{{-0.25em}}\n\\begin{{itemize}} [noitemsep]\n"
            
            descriptions = project.get('descriptions', [])
            for desc in descriptions:
                if desc.strip():
                    # Escape special LaTeX characters
                    desc_clean = desc.replace('&', '\\&').replace('%', '\\%').replace('$', '\\$')
                    latex_content += f"    \\item {desc_clean}\n"
            
            latex_content += "\\end{itemize}\n"
        
        latex_content += "\\end{itemize}\n\n"

    # Add positions if any
    if positions:
        latex_content += """\\noindent
\\resheading{\\textbf{POSITIONS OF RESPONSIBILITY} }\\\\[-0.35cm]
\\vspace{-0.4em}
\\begin{itemize}
\\setlength\\itemsep{-0.28em}
"""
        for position in positions:
            title = position.get('title', 'Position Title')
            organization = position.get('organization', 'Organization')
            duration = position.get('duration', 'Month Year - Month Year')
            
            latex_content += f"""\\item \\textbf{{{title} | {organization}}}\\hfill \\textbf{{{duration}}}
\\vspace{{-0.25em}}
\\begin{{itemize}} [noitemsep,topsep=0pt]
"""
            
            responsibilities = position.get('responsibilities', [])
            for resp in responsibilities:
                if resp.strip():
                    # Escape special LaTeX characters
                    resp_clean = resp.replace('&', '\\&').replace('%', '\\%').replace('$', '\\$')
                    latex_content += f"    \\item {resp_clean}\n"
            
            latex_content += "\\end{itemize}\n\\vspace{0.5em}\n"
        
        latex_content += "\\end{itemize}\n\n"

    # Add achievements if any
    if achievements:
        latex_content += """\\noindent
\\resheading{\\textbf{ACADEMIC ACHIEVEMENTS}}\\\\[-0.35cm]
\\vspace{-0.4em}
\\begin{itemize}[itemsep=1pt]
"""
        for achievement in achievements:
            if achievement.strip():
                # Escape special LaTeX characters
                achievement_clean = achievement.replace('&', '\\&').replace('%', '\\%').replace('$', '\\$')
                latex_content += f"\\item {achievement_clean}\n"
        
        latex_content += "\\end{itemize}\n\n"

    # Add skills
    if skills.strip():
        # Escape special LaTeX characters
        skills_clean = skills.replace('&', '\\&').replace('%', '\\%').replace('$', '\\$')
        latex_content += f"""\\noindent
\\resheading{{\\textbf{{OTHER INFORMATION}}}}\\\\[-0.35cm]
 \\begin{{itemize}}
  \\item \\textbf{{Technical Skills \\& Tools}}: {skills_clean} \\\\[-0.6cm]
\\end{{itemize}}

"""

    latex_content += "\\end{document}\n"
    
    return latex_content



@app.get("/api/latex-status")
async def check_latex_status():
    """Check if LaTeX is available on the server"""
    try:
        process = await asyncio.create_subprocess_exec(
            'pdflatex', '--version',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return {
                "latex_available": True,
                "version": stdout.decode().split('\n')[0] if stdout else "Unknown version"
            }
        else:
            return {
                "latex_available": False,
                "error": stderr.decode() if stderr else "Unknown error"
            }
    except FileNotFoundError:
        return {
            "latex_available": False,
            "error": "pdflatex command not found"
        }
    except Exception as e:
        return {
            "latex_available": False,
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
