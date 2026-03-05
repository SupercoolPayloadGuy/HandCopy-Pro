"""Robot Service — HTTP calls to ESP32"""
import httpx, logging
import config

log = logging.getLogger(__name__)
BASE = f"http://{config.ESP32_IP}:{config.ESP32_PORT}"


class RobotError(Exception):
    pass


async def _post(path, timeout=10.0, **kw):
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(BASE+path, **kw)
            r.raise_for_status()
            return {"ok": True, "message": r.text}
    except httpx.ConnectError:
        raise RobotError(f"Can't reach robot at {BASE} — is the ESP32 powered and on the same WiFi?")
    except httpx.HTTPStatusError as e:
        raise RobotError(f"Robot returned error {e.response.status_code}")
    except httpx.TimeoutException:
        raise RobotError("Connection timed out")


async def get_robot_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(BASE+"/status")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"state": "disconnected", "pos": {"x": 0.0, "y": 0.0}, "error": str(e)}


async def send_gcode(gcode: str):
    return await _post("/print", timeout=120.0, content=gcode.encode(), headers={"Content-Type":"text/plain"})

async def home_robot():   return await _post("/home",   timeout=30.0)
async def stop_robot():   return await _post("/stop",   timeout=5.0)
async def pause_robot():  return await _post("/pause",  timeout=5.0)
async def resume_robot(): return await _post("/resume", timeout=5.0)
