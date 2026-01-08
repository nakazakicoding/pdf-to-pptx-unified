"""
PDF to PowerPoint Web Application - UNIFIED VERSION
Combines Normal Mode (Gemini API) and JSON Mode in one service
Includes JSON download step before PPTX generation
Optimized for low-memory environments with page-by-page cleanup
"""
import os
import shutil
import json
import uuid
import asyncio
import gc
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import fitz  # PyMuPDF

# Gemini API
import google.generativeai as genai

# Import conversion modules
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(
    title="PDF to PowerPoint Converter - Unified",
    description="Convert PDF files to editable PowerPoint presentations using AI or JSON",
    version="2.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage for job status
jobs = {}

# Directories
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp_processing"

# Create directories
for d in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)


class JobStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    JSON_READY = "json_ready"  # NEW: JSON is ready for download
    GENERATING = "generating"
    COMPLETED = "completed"
    ERROR = "error"


# Gemini API Setup
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Image Analysis Prompt
IMAGE_ANALYSIS_PROMPT = """
あなたはPDFページ画像からテキスト情報を抽出するアナリストです。以下の画像を分析し、指定されたJSONフォーマットで出力してください。

## 出力フォーマット

```json
{
  "replace_all": true,
  "blocks": [
    {
      "text": "テキスト内容",
      "bbox_1000": [x, y, width, height],
      "font_family": "フォント名",
      "is_bold": true/false,
      "font_size_pt": 数値,
      "colors": [
        {"range": [開始文字位置, 終了文字位置], "rgb": [R, G, B]}
      ]
    }
  ]
}
```

## 詳細ルール

### 座標 (bbox_1000)
- 画像を1000x1000の座標系として扱う
- [x, y, width, height] の形式
- x: 左端からの距離 (0-1000)
- y: 上端からの距離 (0-1000)
- width, height: テキストボックスの幅と高さ

### フォントファミリー (font_family)
以下の8種類から選択：

**日本語フォント:**
- `Noto Sans JP` - ゴシック体
- `Noto Serif JP` - 明朝体
- `Yomogi` - 手書き風
- `Kosugi Maru` - 丸文字

**英語フォント:**
- `Roboto` - サンセリフ（標準）
- `Merriweather` - セリフ
- `Roboto Mono` - 等幅
- `Montserrat` - 太め見出し

### フォントサイズ (font_size_pt)
- PowerPointスライド（幅1376pt × 高さ768pt）基準
- font_size_pt = (テキスト高さ / 画像高さ) × 768

### テキストグループ化ルール
1. 縦方向（Y座標が異なる）→ 必ず別のblock
2. 横方向（同じ行）→ 距離が近ければ同一block
3. 色が異なる場合は`colors`配列で表現
4. 改行は使用禁止、別blockに分割

JSONのみを出力してください。説明文は不要です。
"""


def configure_gemini():
    """Configure Gemini API"""
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        return True
    return False


async def analyze_image_with_gemini(image_path: Path, page_num: int) -> dict:
    """Analyze a single page image with Gemini API"""
    if not configure_gemini():
        raise ValueError("GEMINI_API_KEY not set")
    
    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # Create Gemini model
    model = genai.GenerativeModel("gemini-3-flash-preview")
    
    # Create image part
    image_part = {
        "mime_type": "image/png",
        "data": image_data
    }
    
    # Generate content
    response = model.generate_content([IMAGE_ANALYSIS_PROMPT, image_part])
    
    # Parse response
    response_text = response.text.strip()
    
    # Extract JSON from response
    if "```json" in response_text:
        json_start = response_text.find("```json") + 7
        json_end = response_text.find("```", json_start)
        response_text = response_text[json_start:json_end].strip()
    elif "```" in response_text:
        json_start = response_text.find("```") + 3
        json_end = response_text.find("```", json_start)
        response_text = response_text[json_start:json_end].strip()
    
    try:
        page_data = json.loads(response_text)
        return page_data
    except json.JSONDecodeError as e:
        print(f"JSON parse error for page {page_num}: {e}")
        print(f"Response text: {response_text[:500]}")
        # Return placeholder on error
        return {
            "replace_all": True,
            "blocks": [{
                "text": f"[Page {page_num} - Parse error]",
                "bbox_1000": [50, 50, 900, 100],
                "font_family": "Roboto",
                "is_bold": True,
                "font_size_pt": 32,
                "colors": [{"range": [0, 30], "rgb": [30, 30, 30]}]
            }]
        }


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.post("/api/upload")
async def upload_files(
    pdf_file: UploadFile = File(...),
    json_file: Optional[UploadFile] = File(None),
    mode: str = Form("normal"),  # "normal" or "json"
    converter_mode: str = Form("precision")  # "precision" or "safeguard"
):
    """Upload PDF file (and optionally JSON for JSON mode)"""
    if not pdf_file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="First file must be a PDF")
    
    # JSON mode requires JSON file
    if mode == "json" and (json_file is None or not json_file.filename.endswith('.json')):
        raise HTTPException(status_code=400, detail="JSON mode requires a JSON file")
    
    # Normal mode requires API key
    if mode == "normal" and not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured for normal mode")
    
    job_id = str(uuid.uuid4())
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    # Save PDF
    pdf_path = job_dir / "input.pdf"
    with open(pdf_path, "wb") as f:
        content = await pdf_file.read()
        f.write(content)
    
    # Save JSON if provided
    json_path = None
    if json_file:
        json_path = job_dir / "image_analysis.json"
        with open(json_path, "wb") as f:
            content = await json_file.read()
            f.write(content)
        
        # Validate JSON structure
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            if not isinstance(json_data, dict):
                raise ValueError("JSON must be an object with page keys")
        except json.JSONDecodeError as e:
            shutil.rmtree(job_dir)
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
        except ValueError as e:
            shutil.rmtree(job_dir)
            raise HTTPException(status_code=400, detail=str(e))
    
    jobs[job_id] = {
        "status": JobStatus.PENDING,
        "progress": 0,
        "message": "Files uploaded successfully",
        "pdf_path": str(pdf_path),
        "json_path": str(json_path) if json_path else None,
        "job_dir": str(job_dir),
        "original_filename": pdf_file.filename,
        "total_pages": 0,
        "current_page": 0,
        "mode": mode,  # "normal" or "json"
        "converter_mode": converter_mode  # "precision" or "safeguard"
    }
    
    return {"job_id": job_id, "message": "Upload successful", "mode": mode, "converter_mode": converter_mode}


@app.post("/api/process/{job_id}")
async def start_processing(job_id: str, background_tasks: BackgroundTasks):
    """Start processing the uploaded PDF"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    mode = job.get("mode", "normal")
    
    if mode == "normal":
        # Normal mode: Gemini analysis then stop for JSON download
        background_tasks.add_task(process_pdf_with_gemini_stop_at_json, job_id)
    else:
        # JSON mode: Skip to PPTX generation
        background_tasks.add_task(generate_pptx_only, job_id)
    
    jobs[job_id]["status"] = JobStatus.PROCESSING
    jobs[job_id]["message"] = "Processing started"
    jobs[job_id]["progress"] = 5  # Start at 5%
    
    return {"status": "processing", "message": "Processing started"}


async def process_pdf_with_gemini_stop_at_json(job_id: str):
    """Background task to process PDF with Gemini API, then STOP for JSON download"""
    try:
        job = jobs[job_id]
        job_dir = Path(job["job_dir"])
        pdf_path = Path(job["pdf_path"])
        
        # Step 1: Convert PDF to images
        job["status"] = JobStatus.PROCESSING
        job["message"] = "Converting PDF to images..."
        
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        job["total_pages"] = total_pages
        
        pages_dir = job_dir / "pages"
        pages_dir.mkdir(exist_ok=True)
        
        page_width = doc[0].rect.width
        page_height = doc[0].rect.height
        job["page_width"] = page_width
        job["page_height"] = page_height
        
        # LIGHTWEIGHT: Use 2.0x scale with page-by-page cleanup
        for page_num in range(total_pages):
            page = doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_path = pages_dir / f"page_{page_num + 1}.png"
            pix.save(str(img_path))
            
            # Clean up pixmap to free memory immediately
            del pix
            gc.collect()
            
            job["current_page"] = page_num + 1
            # Progress: 5% (start) to 20% (end of image conversion)
            job["progress"] = 5 + int((page_num + 1) / total_pages * 15)
        
        doc.close()
        del doc
        gc.collect()
        
        # Step 2: Analyze images with Gemini
        job["status"] = JobStatus.ANALYZING
        job["message"] = "Analyzing page content with AI..."
        
        analysis_results = {}
        
        for page_num in range(1, total_pages + 1):
            job["message"] = f"Analyzing page {page_num}/{total_pages}..."
            # Progress: 20% (start) to 60% (end of analysis)
            job["progress"] = 20 + int(page_num / total_pages * 40)
            
            img_path = pages_dir / f"page_{page_num}.png"
            
            try:
                page_data = await analyze_image_with_gemini(img_path, page_num)
                analysis_results[f"page_{page_num}"] = page_data
            except Exception as e:
                print(f"Error analyzing page {page_num}: {e}")
                analysis_results[f"page_{page_num}"] = {
                    "replace_all": True,
                    "blocks": [{
                        "text": f"[Page {page_num} - Analysis error: {str(e)[:50]}]",
                        "bbox_1000": [50, 50, 900, 100],
                        "font_family": "Roboto",
                        "is_bold": True,
                        "font_size_pt": 24,
                        "colors": [{"range": [0, 50], "rgb": [200, 50, 50]}]
                    }]
                }
            
            # Clean up memory after each page analysis
            gc.collect()
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        # Save analysis JSON
        json_path = job_dir / "image_analysis.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(analysis_results, f, ensure_ascii=False, indent=2)
        
        job["json_path"] = str(json_path)
        job["progress"] = 60  # JSON ready at 60%
        
        # STOP HERE - Wait for user to download JSON before continuing
        job["status"] = JobStatus.JSON_READY
        job["message"] = "JSON analysis complete. Please download the JSON file and click 'Continue' to generate PPTX."
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        jobs[job_id]["status"] = JobStatus.ERROR
        jobs[job_id]["message"] = str(e)
        jobs[job_id]["progress"] = 0


@app.post("/api/continue/{job_id}")
async def continue_to_pptx(job_id: str, background_tasks: BackgroundTasks):
    """Continue PPTX generation after JSON download"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job["status"] != JobStatus.JSON_READY:
        raise HTTPException(status_code=400, detail="Job is not ready for continuation")
    
    background_tasks.add_task(generate_pptx_only, job_id)
    jobs[job_id]["status"] = JobStatus.GENERATING
    jobs[job_id]["message"] = "Generating PowerPoint..."
    jobs[job_id]["progress"] = 60  # Explicitly set to 60% when continuing
    
    return {"status": "generating", "message": "PPTX generation started"}


async def generate_pptx_only(job_id: str):
    """Generate PPTX from existing JSON"""
    try:
        job = jobs[job_id]
        job_dir = Path(job["job_dir"])
        pdf_path = Path(job["pdf_path"])
        json_path = Path(job["json_path"])
        
        job["status"] = JobStatus.GENERATING
        job["message"] = "Generating PowerPoint..."
        job["progress"] = 60  # Ensure we start at 60%
        
        output_filename = Path(job["original_filename"]).stem + ".pptx"
        output_path = OUTPUT_DIR / f"{job_id}_{output_filename}"
        
        # Select converter based on mode
        converter_mode = job.get("converter_mode", "precision")
        if converter_mode == "safeguard":
            converter_script = BASE_DIR / "standalone_convert_v4_v43_light_2x.py"
            print(f"Using Safeguard Mode converter (v43 LIGHT 2x)")
        else:
            converter_script = BASE_DIR / "standalone_convert_v43_light_2x.py"
            print(f"Using Precision Mode converter (v43 LIGHT 2x)")
        
        log_path = job_dir / "conversion_log.txt"
        
        # Run converter as subprocess
        import subprocess
        cmd = [
            sys.executable,
            str(converter_script),
            "--pdf", str(pdf_path),
            "--output", str(output_path),
            "--json", str(json_path),
            "--log", str(log_path)
        ]
        
        print(f"Running converter: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(BASE_DIR)
        )
        
        # Wait for completion with progress updates
        while process.poll() is None:
            job["progress"] = min(98, job["progress"] + 1)
            await asyncio.sleep(2)
        
        returncode = process.returncode
        if returncode != 0:
            stderr = process.stderr.read().decode("utf-8", errors="replace")
            raise Exception(f"Converter failed with code {returncode}: {stderr[:500]}")
        
        job["status"] = JobStatus.COMPLETED
        job["progress"] = 100
        job["message"] = "Conversion completed!"
        job["output_path"] = str(output_path)
        job["output_filename"] = output_filename
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        jobs[job_id]["status"] = JobStatus.ERROR
        jobs[job_id]["message"] = str(e)
        jobs[job_id]["progress"] = 0


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/api/download-json/{job_id}")
async def download_json(job_id: str):
    """Download the intermediate JSON file"""
    from urllib.parse import quote
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if not job.get("json_path"):
        raise HTTPException(status_code=400, detail="JSON file not available")
    
    json_path = Path(job["json_path"])
    
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="JSON file not found")
    
    # Create filename based on original PDF name
    original_name = Path(job["original_filename"]).stem
    json_filename = f"{original_name}_analysis.json"
    encoded_filename = quote(json_filename)
    
    return FileResponse(
        path=str(json_path),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@app.get("/api/download/{job_id}")
async def download_result(job_id: str):
    from urllib.parse import quote
    
    # Try to find job in memory first
    if job_id in jobs:
        job = jobs[job_id]
        if job["status"] != JobStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Processing not completed")
        
        output_path = Path(job["output_path"])
        output_filename = job["output_filename"]
    else:
        # Fallback: Search for file in output directory matching job_id
        possible_files = list(OUTPUT_DIR.glob(f"{job_id}*"))
        if not possible_files:
            raise HTTPException(status_code=404, detail="Job not found and no matching file in output directory")
        
        output_path = possible_files[0]
        output_filename = output_path.name
    
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    
    # Handle Japanese filenames for download display
    encoded_filename = quote(output_filename)
    
    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@app.delete("/api/job/{job_id}")
async def cleanup_job(job_id: str):
    if job_id in jobs:
        job_dir = TEMP_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
        del jobs[job_id]
    return {"message": "Job cleaned up"}


# Serve static files
if (BASE_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


if __name__ == "__main__":
    import uvicorn
    print(f"GEMINI_API_KEY configured: {bool(GEMINI_API_KEY)}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
