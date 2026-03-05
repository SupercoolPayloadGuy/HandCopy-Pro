from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.robot_service import (get_robot_status, home_robot, stop_robot,
                                    pause_robot, resume_robot, send_gcode, RobotError)

router = APIRouter(prefix="/robot", tags=["Robot"])


class RawPayload(BaseModel):
    gcode: str


@router.get("/status")
async def status():
    return await get_robot_status()

@router.post("/home")
async def home():
    try: return await home_robot()
    except RobotError as e: raise HTTPException(502, str(e))

@router.post("/stop")
async def stop():
    try: return await stop_robot()
    except RobotError as e: raise HTTPException(502, str(e))

@router.post("/pause")
async def pause():
    try: return await pause_robot()
    except RobotError as e: raise HTTPException(502, str(e))

@router.post("/resume")
async def resume():
    try: return await resume_robot()
    except RobotError as e: raise HTTPException(502, str(e))

@router.post("/send-raw")
async def send_raw(body: RawPayload):
    try: return await send_gcode(body.gcode)
    except RobotError as e: raise HTTPException(502, str(e))
