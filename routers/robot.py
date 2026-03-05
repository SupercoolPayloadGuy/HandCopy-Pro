import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.robot_service import (get_robot_status, home_robot, stop_robot,
                                    pause_robot, resume_robot, send_gcode, RobotError)
import config

router = APIRouter(prefix="/robot", tags=["Robot"])


class RawPayload(BaseModel):
    gcode: str


class RobotConfig(BaseModel):
    ip:           str
    port:         int
    pen_down_cmd: str
    pen_up_cmd:   str
    feed_rate:    int
    rapid_rate:   int


def _save_env(values: dict):
    """Write key=value pairs to .env, creating it if it doesn't exist.
    Existing keys are updated in-place; new keys are appended."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    # Update existing lines
    updated = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=")[0].strip()
            if key in values:
                new_lines.append(f"{key}={values[key]}\n")
                updated.add(key)
                continue
        new_lines.append(line)

    # Append any keys that weren't already in the file
    for key, val in values.items():
        if key not in updated:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)


# ── Config endpoints ──────────────────────────────────────────────────────────

@router.get("/config", response_model=RobotConfig)
async def get_config():
    return RobotConfig(
        ip=config.ESP32_IP,
        port=config.ESP32_PORT,
        pen_down_cmd=config.PEN_DOWN_CMD,
        pen_up_cmd=config.PEN_UP_CMD,
        feed_rate=config.DEFAULT_FEED,
        rapid_rate=config.RAPID_FEED,
    )


@router.post("/config")
async def save_config(body: RobotConfig):
    """Update ESP32 connection + motion settings. Takes effect immediately, also saved to .env."""
    # Apply to live config module — takes effect without restart
    config.ESP32_IP      = body.ip.strip()
    config.ESP32_PORT    = body.port
    config.PEN_DOWN_CMD  = body.pen_down_cmd.strip().upper()
    config.PEN_UP_CMD    = body.pen_up_cmd.strip().upper()
    config.DEFAULT_FEED  = body.feed_rate
    config.RAPID_FEED    = body.rapid_rate

    # Persist to .env so it survives a restart
    _save_env({
        "ESP32_IP":       config.ESP32_IP,
        "ESP32_PORT":     str(config.ESP32_PORT),
        "PEN_DOWN_CMD":   config.PEN_DOWN_CMD,
        "PEN_UP_CMD":     config.PEN_UP_CMD,
        "DEFAULT_FEED":   str(config.DEFAULT_FEED),
        "RAPID_FEED":     str(config.RAPID_FEED),
    })

    return {"message": "Config saved", "ip": config.ESP32_IP, "port": config.ESP32_PORT}


@router.post("/config/test")
async def test_connection(body: RobotConfig):
    """Test reachability of a given IP/port without saving it."""
    import httpx
    base = f"http://{body.ip.strip()}:{body.port}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(base+"/status")
            r.raise_for_status()
            data = r.json()
            return {"ok": True, "message": f"Connected — robot state: {data.get('state','?')}", "data": data}
    except httpx.ConnectError:
        return {"ok": False, "message": f"No response from {base} — check IP and that the ESP32 is on the same WiFi"}
    except httpx.TimeoutException:
        return {"ok": False, "message": f"Timed out connecting to {base}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── Control endpoints ─────────────────────────────────────────────────────────

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
