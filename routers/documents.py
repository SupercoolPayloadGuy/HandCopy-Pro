import os, uuid, aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.db_models import WritingJob, HandwritingProfile, Glyph, JobStatus
from models.schemas import JobResponse
from services.ocr_service import process_document, group_into_lines
from services.gcode_service import compile_gcode
from services.robot_service import send_gcode, RobotError
import config

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/scan-preview")
async def scan_preview(file: UploadFile = File(...), dpi: int = 300):
    """Upload a document image → get OCR text + line positions back."""
    content = await file.read()
    words, full_text, w, h = await process_document(content, dpi=dpi)
    lines = group_into_lines(words)
    return {
        "word_count": len(words),
        "line_count": len(lines),
        "full_text":  full_text,
        "image_size": {"width_px": w, "height_px": h,
                       "width_mm":  round(w*25.4/dpi, 1),
                       "height_mm": round(h*25.4/dpi, 1)},
        "text_blocks": [{"text": l["text"], "x_mm": l["x_mm"],
                         "y_mm": l["y_mm"], "max_width_mm": 170.0} for l in lines],
    }


class TextJobRequest(BaseModel):
    profile_id: str
    text: str
    x_mm: float = 20.0
    y_mm: float = 20.0
    max_width_mm: float = 170.0
    char_height_mm: float = 5.0


@router.post("/jobs/from-text")
async def create_job_from_text(body: TextJobRequest, db: AsyncSession = Depends(get_db)):
    """Create a print job directly from typed text — no scanning needed."""
    pr = (await db.execute(select(HandwritingProfile).where(HandwritingProfile.id == body.profile_id))).scalar_one_or_none()
    if not pr: raise HTTPException(404, "Profile not found")
    if not body.text.strip(): raise HTTPException(400, "Text cannot be empty")

    blocks = [{"text": body.text.strip(), "x_mm": body.x_mm, "y_mm": body.y_mm,
               "max_width_mm": body.max_width_mm, "char_height_mm": body.char_height_mm}]
    job = WritingJob(profile_id=body.profile_id, text_blocks=blocks, status=JobStatus.pending)
    db.add(job); await db.flush()
    return {"job_id": job.id, "status": job.status, "text": body.text.strip()}


@router.post("/jobs/from-scan")
async def create_job_from_scan(profile_id: str, file: UploadFile = File(...),
                                dpi: int = 300, db: AsyncSession = Depends(get_db)):
    """One shot: upload scan → OCR → create job."""
    pr = (await db.execute(select(HandwritingProfile).where(HandwritingProfile.id == profile_id))).scalar_one_or_none()
    if not pr: raise HTTPException(404, "Profile not found")

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(config.UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
    content = await file.read()
    async with aiofiles.open(path, "wb") as f: await f.write(content)

    words, full_text, _, _ = await process_document(content, dpi=dpi)
    if not words: raise HTTPException(422, "No text found — check image quality and lighting")

    lines = group_into_lines(words)
    blocks = [{"text": l["text"], "x_mm": l["x_mm"], "y_mm": l["y_mm"],
               "max_width_mm": 170.0, "char_height_mm": None} for l in lines]

    job = WritingJob(profile_id=profile_id, source_image_path=path,
                     scan_dpi=dpi, text_blocks=blocks, status=JobStatus.pending)
    db.add(job); await db.flush()

    return {"job_id": job.id, "status": job.status,
            "words_detected": len(words), "lines_detected": len(lines), "text_blocks": blocks}


@router.post("/jobs/{job_id}/generate")
async def generate_gcode(job_id: str, db: AsyncSession = Depends(get_db)):
    job = (await db.execute(select(WritingJob).where(WritingJob.id == job_id))).scalar_one_or_none()
    if not job: raise HTTPException(404, "Job not found")

    profile = (await db.execute(select(HandwritingProfile).where(HandwritingProfile.id == job.profile_id))).scalar_one_or_none()
    glyphs  = (await db.execute(select(Glyph).where(Glyph.profile_id == job.profile_id))).scalars().all()
    if not glyphs: raise HTTPException(422, "No glyphs in profile — upload character images first")

    glyph_map = {g.character: {"strokes": g.strokes, "width_ratio": g.width_ratio} for g in glyphs}
    profile_params = {"slant_deg": profile.slant_deg, "letter_spacing": profile.letter_spacing,
                      "word_spacing": profile.word_spacing, "baseline_waver": profile.baseline_waver}

    job.status = JobStatus.generating; await db.flush()
    try:
        job.gcode  = compile_gcode(job.text_blocks, glyph_map, profile_params)
        job.status = JobStatus.ready
    except Exception as e:
        job.status = JobStatus.error; job.error_message = str(e); await db.flush()
        raise HTTPException(500, str(e))
    await db.flush()
    return {"job_id": job_id, "status": job.status, "gcode_lines": len(job.gcode.splitlines())}


@router.post("/jobs/{job_id}/print")
async def print_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = (await db.execute(select(WritingJob).where(WritingJob.id == job_id))).scalar_one_or_none()
    if not job:      raise HTTPException(404, "Job not found")
    if not job.gcode: raise HTTPException(409, "Generate G-code first")

    job.status = JobStatus.printing; await db.flush()
    try:
        result = await send_gcode(job.gcode)
        job.status = JobStatus.done; await db.flush()
        return {"job_id": job_id, "status": "done", "robot": result}
    except RobotError as e:
        job.status = JobStatus.error; job.error_message = str(e); await db.flush()
        raise HTTPException(502, str(e))


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(WritingJob).order_by(WritingJob.created_at.desc()).limit(100))
    return r.scalars().all()


@router.get("/jobs/{job_id}/gcode")
async def download_gcode(job_id: str, db: AsyncSession = Depends(get_db)):
    job = (await db.execute(select(WritingJob).where(WritingJob.id == job_id))).scalar_one_or_none()
    if not job or not job.gcode: raise HTTPException(404, "G-code not found")
    return PlainTextResponse(job.gcode, headers={"Content-Disposition": f'attachment; filename="job_{job_id[:8]}.gcode"'})


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = (await db.execute(select(WritingJob).where(WritingJob.id == job_id))).scalar_one_or_none()
    if not job: raise HTTPException(404, "Job not found")
    await db.delete(job)
