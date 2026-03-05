from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models.db_models import HandwritingProfile, Glyph
from models.schemas import ProfileCreate, ProfileUpdate, ProfileResponse, GlyphResponse

router = APIRouter(prefix="/profiles", tags=["Profiles"])


async def _prof(db, pid):
    r = await db.execute(select(HandwritingProfile).where(HandwritingProfile.id == pid))
    p = r.scalar_one_or_none()
    if not p: raise HTTPException(404, "Profile not found")
    return p


@router.get("/", response_model=list[ProfileResponse])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HandwritingProfile).order_by(HandwritingProfile.created_at.desc()))
    out = []
    for p in result.scalars().all():
        cnt = (await db.execute(select(func.count()).where(Glyph.profile_id == p.id))).scalar()
        d = ProfileResponse.model_validate(p); d.glyph_count = cnt or 0; out.append(d)
    return out


@router.post("/", response_model=ProfileResponse, status_code=201)
async def create_profile(body: ProfileCreate, db: AsyncSession = Depends(get_db)):
    p = HandwritingProfile(**body.model_dump()); db.add(p); await db.flush()
    return ProfileResponse.model_validate(p)


@router.get("/{pid}", response_model=ProfileResponse)
async def get_profile(pid: str, db: AsyncSession = Depends(get_db)):
    p   = await _prof(db, pid)
    cnt = (await db.execute(select(func.count()).where(Glyph.profile_id == pid))).scalar()
    d   = ProfileResponse.model_validate(p); d.glyph_count = cnt or 0; return d


@router.patch("/{pid}", response_model=ProfileResponse)
async def update_profile(pid: str, body: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    p = await _prof(db, pid)
    for k, v in body.model_dump(exclude_none=True).items(): setattr(p, k, v)
    await db.flush(); return ProfileResponse.model_validate(p)


@router.delete("/{pid}", status_code=204)
async def delete_profile(pid: str, db: AsyncSession = Depends(get_db)):
    await db.delete(await _prof(db, pid))


# ── Single glyph upload ───────────────────────────────────────────────────────

@router.get("/{pid}/glyphs", response_model=list[GlyphResponse])
async def list_glyphs(pid: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Glyph).where(Glyph.profile_id == pid).order_by(Glyph.character))
    return r.scalars().all()


@router.post("/{pid}/glyphs/upload-image")
async def upload_glyph_image(pid: str, character: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    from services.stroke_service import extract_strokes
    if len(character) != 1: raise HTTPException(400, "character must be exactly 1 character")
    await _prof(db, pid)
    strokes, wr = extract_strokes(await file.read())
    if not strokes: raise HTTPException(422, "No strokes found — use a clear image on a white background")
    await _upsert_glyph(db, pid, character, strokes, wr)
    return {"message": f"'{character}' saved", "stroke_count": len(strokes), "width_ratio": wr}


# ── Calligraphr sheet upload ──────────────────────────────────────────────────

@router.post("/{pid}/glyphs/upload-calligraphr")
async def upload_calligraphr_sheet(pid: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Upload a filled Calligraphr template sheet — all glyphs extracted at once."""
    from services.calligraphr_service import parse_calligraphr_sheet
    await _prof(db, pid)
    content = await file.read()
    results = parse_calligraphr_sheet(content)
    if not results:
        raise HTTPException(422, "No glyphs found. Make sure the sheet is filled, scanned straight, good contrast.")
    saved = 0
    for char, (strokes, wr) in results.items():
        await _upsert_glyph(db, pid, char, strokes, wr)
        saved += 1
    await db.flush()
    return {"message": f"Extracted {saved} glyphs", "saved": saved, "characters": list(results.keys())}


# ── Measure slant from a handwriting photo ───────────────────────────────────

@router.post("/{pid}/measure-slant")
async def measure_slant(pid: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Upload any photo of handwritten text → measures slant angle + wobble → updates profile."""
    from services.stroke_service import measure_style
    p = await _prof(db, pid)
    m = measure_style(await file.read())
    p.slant_deg = m["slant_deg"]; p.baseline_waver = m["baseline_waver"]
    await db.flush()
    return {"slant_deg": m["slant_deg"], "baseline_waver": m["baseline_waver"]}


@router.delete("/{pid}/glyphs/{character}", status_code=204)
async def delete_glyph(pid: str, character: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Glyph).where(Glyph.profile_id == pid, Glyph.character == character))
    g = r.scalar_one_or_none()
    if not g: raise HTTPException(404, "Glyph not found")
    await db.delete(g)


async def _upsert_glyph(db, pid, character, strokes, width_ratio):
    r = await db.execute(select(Glyph).where(Glyph.profile_id == pid, Glyph.character == character))
    g = r.scalar_one_or_none()
    if g:
        g.strokes = strokes; g.width_ratio = width_ratio
    else:
        g = Glyph(profile_id=pid, character=character, strokes=strokes, width_ratio=width_ratio); db.add(g)
