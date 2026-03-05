from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ProfileCreate(BaseModel):
    name           : str
    description    : Optional[str]   = None
    slant_deg      : float           = 0.0
    letter_spacing : float           = 1.0
    word_spacing   : float           = 2.5
    baseline_waver : float           = 0.3
    stroke_width   : float           = 0.4


class ProfileUpdate(BaseModel):
    name           : Optional[str]   = None
    description    : Optional[str]   = None
    slant_deg      : Optional[float] = None
    letter_spacing : Optional[float] = None
    word_spacing   : Optional[float] = None
    baseline_waver : Optional[float] = None
    stroke_width   : Optional[float] = None


class ProfileResponse(BaseModel):
    id             : str
    name           : str
    description    : Optional[str]
    slant_deg      : float
    letter_spacing : float
    word_spacing   : float
    baseline_waver : float
    stroke_width   : float
    created_at     : datetime
    glyph_count    : int = 0
    class Config: from_attributes = True


class GlyphCreate(BaseModel):
    character   : str = Field(..., min_length=1, max_length=1)
    strokes     : list[dict]
    width_ratio : float = 0.6


class GlyphResponse(BaseModel):
    id          : str
    character   : str
    strokes     : list[dict]
    width_ratio : float
    class Config: from_attributes = True


class TextBlock(BaseModel):
    text           : str
    x_mm           : float
    y_mm           : float
    max_width_mm   : float           = 170.0
    char_height_mm : Optional[float] = None


class JobResponse(BaseModel):
    id                : str
    profile_id        : str
    status            : str
    source_image_path : Optional[str]
    text_blocks       : list[dict]
    gcode             : Optional[str]
    error_message     : Optional[str]
    created_at        : datetime
    class Config: from_attributes = True


class OCRWord(BaseModel):
    text       : str
    x_mm       : float
    y_mm       : float
    width_mm   : float
    height_mm  : float
    confidence : float
