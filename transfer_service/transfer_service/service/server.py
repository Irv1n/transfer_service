from __future__ import annotations

import threading
import io
import zipfile
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, RootModel

from ..drivers.k2182 import Keithley2182, K2182Config
from ..drivers.dp320b import Dataproof320B, DP320BConfig
from ..drivers.lte300 import LTE300, LTE300Config
from ..drivers.mock import Mock2182, Mock320B, MockLTE300, SimConfig
from ..sensors.bme280_env import BME280Env, BME280Config
from ..transfer import PolarityMap, MeasurePlan, CellTempModel, run_transfer_level
from ..io.report_xlsx import save_summary_xlsx
from .standards_store import load_standards, save_standards, get_standard

app = FastAPI()

# Web UI
app.mount('/static', StaticFiles(directory=str(Path(__file__).parent / 'static')), name='static')
templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))

BASE = Path("jobs")
BASE.mkdir(exist_ok=True)

JOBS: Dict[str, Dict[str, Any]] = {}
ENV: Dict[str, Any] = {"t_c": None, "rh_pct": None, "p_kpa": None, "lte_c": None}
_env_lock = threading.Lock()

_bme: Optional[BME280Env] = None
_lte_env: Optional[LTE300] = None


class RefConfig(BaseModel):
    id: str = Field(..., description="ID меры REF (выбирается из справочника standards)")
    # Поля ниже опциональны: если не заданы, будут подставлены из standards.json по (level, ref_id)
    channel: Optional[int] = Field(None, ge=1, le=32, description="Канал 320B (1..32), где висит REF")
    value_v: Optional[float] = Field(None, description="Действительное значение меры (В)")
    u_std_v: Optional[float] = Field(None, description="Стандартная неопределенность ref (В)")
    description: Optional[str] = None
    cal_date: Optional[str] = None



class DutConfig(BaseModel):
    id: str = Field(..., description="Номер/ID меры DUT")
    channel: int = Field(..., ge=1, le=32, description="Канал 320B (1..32), где висит DUT")


class LevelConfig(BaseModel):
    name: str = Field(..., description="Уровень, например '10V' или '1.018V'")
    ref: RefConfig
    duts: List[DutConfig] = Field(..., min_length=1, description="Список DUT для сравнения с REF")
    cell_type: str = "saturated"
    alpha_uV_per_C: Optional[float] = None



class StandardItem(BaseModel):
    channel: int = Field(..., ge=1, le=32)
    value_V: float
    u_ref_V: float
    description: str = ""
    cal_date: str = ""
    active: bool = True

class StandardsPayload(RootModel[Dict[str, Dict[str, StandardItem]]]):
    pass



@app.get("/api/standards")
def api_get_standards() -> Dict[str, Any]:
    return load_standards()

@app.put("/api/standards")
def api_put_standards(payload: StandardsPayload) -> Dict[str, Any]:
    data = payload.root
    for level, items in data.items():
        if level not in ("10V", "1.018V"):
            raise HTTPException(status_code=400, detail=f"Invalid level: {level}")
        for rid, item in items.items():
            if not rid or not isinstance(rid, str):
                raise HTTPException(status_code=400, detail="Invalid ref id")
            if item.u_ref_V <= 0:
                raise HTTPException(status_code=400, detail=f"u_ref_V must be > 0 for {level}:{rid}")

    plain: Dict[str, Dict[str, Any]] = {"10V": {}, "1.018V": {}}
    for level in ("10V", "1.018V"):
        items = data.get(level) or {}
        for rid, item in items.items():
            plain[level][rid] = item.dict()
    save_standards(plain)
    return plain


class StartRequest(BaseModel):
    meter_resource: str
    switch_resource: str
    lte_port: str

    cycles: int = 3
    settle_after_switch_s: float = 60.0
    block_duration_s: float = 120.0
    sample_delay_s: float = 0.0

    # New (v0.0.8): fixed number of samples per polarity within each cycle.
    # This replaces time-based collection and guarantees n_plus == n_minus.
    samples_per_polarity: int = 20

    levels: List[LevelConfig]

    # Simulation mode (emulates 2182 + 320B + LTE-300)
    simulation: bool = False
    sim_offset_uV: float = 0.0
    sim_noise_rms_uV: float = 0.05
    sim_drift_uV_per_min: float = 0.0
    sim_outlier_prob: float = 0.0
    sim_outlier_uV: float = 1.0
    sim_temp_c: float = 23.0

    bme280_address: int = 0x76
def _env_worker():
    global _bme, _lte_env
    while True:
        data: Dict[str, Any] = {}
        try:
            if _bme:
                data.update(_bme.read())
        except Exception:
            pass
        try:
            if _lte_env:
                data["lte_c"] = _lte_env.read_temperature_c()
        except Exception:
            pass

        with _env_lock:
            if "t_c" in data:
                ENV["t_c"] = data.get("t_c")
                ENV["rh_pct"] = data.get("rh_pct")
                ENV["p_kpa"] = data.get("p_kpa")
            if "lte_c" in data:
                ENV["lte_c"] = data.get("lte_c")

        time.sleep(1.0)


def _ensure_env(addr: int, lte_port: str):
    global _bme, _lte_env
    if _bme is None:
        try:
            _bme = BME280Env(BME280Config(address=addr))
        except Exception:
            _bme = None
    if _lte_env is None:
        try:
            _lte_env = LTE300(LTE300Config(port=lte_port))
        except Exception:
            _lte_env = None
    if not getattr(_ensure_env, "_started", False):
        threading.Thread(target=_env_worker, daemon=True).start()
        _ensure_env._started = True  # type: ignore


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._-()" else "_" for c in s)



def _read_env() -> Optional[Dict[str, float]]:
    """Read environment sensors (BME280) if available.

    Returns dict: {'t_c': float, 'rh_pct': float, 'p_kpa': float} or None.
    The env is optional; transfer logic can operate without it.
    """
    try:
        from ..sensors.bme280 import read_bme280  # type: ignore
        return read_bme280()
    except Exception:
        return None

def _worker(job_id: str, req: StartRequest):
    job_dir = BASE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    def progress(p: float, msg: str) -> None:
        JOBS[job_id]["progress"] = float(p)
        JOBS[job_id]["message"] = str(msg)

    meter = None
    switch = None
    lte = None

    try:
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["progress"] = 0.0
        progress(0.0, "Configuring instruments...")

        # Instruments (real or simulation)
        if req.simulation or req.meter_resource.upper().startswith("MOCK") or req.switch_resource.upper().startswith("MOCK"):
            sim = SimConfig(
                offset_uV=req.sim_offset_uV,
                noise_rms_uV=req.sim_noise_rms_uV,
                drift_uV_per_min=req.sim_drift_uV_per_min,
                outlier_prob=req.sim_outlier_prob,
                outlier_uV=req.sim_outlier_uV,
                temp_c=req.sim_temp_c,
            )
            switch = Mock320B()
            meter = Mock2182(sim, switch.current_polarity)
            lte = MockLTE300(sim)
        else:
            meter = Keithley2182(req.meter_resource, K2182Config())
            switch = Dataproof320B(req.switch_resource, DP320BConfig())
            lte = LTE300(LTE300Config(port=req.lte_port))

        # Configure + run
        meter.configure()

        plan = MeasurePlan(
            cycles=req.cycles,
            settle_after_switch_s=req.settle_after_switch_s,
            samples_per_polarity=req.samples_per_polarity,
            sample_delay_s=req.sample_delay_s,
            block_duration_s=req.block_duration_s,  # legacy, unused by v0.0.8+
        )

        # Overall progress across all (level,dut) pairs
        total_pairs = sum(len(lvl.duts) for lvl in req.levels) or 1
        done_pairs = 0  # number of completed pairs

        for lvl in req.levels:
            # Resolve REF from standards.json (selected by ref.id)
            try:
                std = get_standard(lvl.name, lvl.ref.id)
            except KeyError:
                std = None

            if std:
                if lvl.ref.channel is None:
                    lvl.ref.channel = int(std.get("channel"))
                if lvl.ref.value_v is None:
                    lvl.ref.value_v = float(std.get("value_V"))
                if lvl.ref.u_std_v is None:
                    lvl.ref.u_std_v = float(std.get("u_ref_V"))
                lvl.ref.description = lvl.ref.description or str(std.get("description", ""))
                lvl.ref.cal_date = lvl.ref.cal_date or str(std.get("cal_date", ""))

            if lvl.ref.channel is None or lvl.ref.value_v is None or lvl.ref.u_std_v is None:
                raise HTTPException(status_code=400, detail=f"REF not fully specified for level {lvl.name}. Choose REF from Standards.")
            cell = CellTempModel(lvl.cell_type, lvl.alpha_uV_per_C)
            for dut in lvl.duts:
                base = done_pairs / total_pairs
                span = 1.0 / total_pairs
        
                def _pair_progress(frac: float, msg: str, _base=base, _span=span) -> None:
                    progress(_base + _span * max(0.0, min(1.0, float(frac))), msg)
        
                progress(base, f"Starting pair {done_pairs+1}/{total_pairs}: REF ch{lvl.ref.channel:02d} ↔ DUT ch{dut.channel:02d}")
        
                env_snapshot = _read_env()
        
                mapping = PolarityMap(
                    plus_a=lvl.ref.channel, plus_b=dut.channel,
                    minus_a=dut.channel, minus_b=lvl.ref.channel,
                )
        
                raw_csv_path = None  # no CSV output (v0.0.13)
                xlsx_path = job_dir / f"report_{lvl.name}_REF{lvl.ref.id}_ch{lvl.ref.channel:02d}__DUT{dut.id}_ch{dut.channel:02d}.xlsx"
        
                result = run_transfer_level(
                    meter=meter,
                    switch=switch,
                    lte=lte,
                    mapping=mapping,
                    plan=plan,
                    level_v=lvl.ref.value_v,
                    u_ref_v=lvl.ref.value_v,
                    u_ref_std_unc_v=lvl.ref.u_std_v,
                    cell_model=cell,
                    raw_csv_path=raw_csv_path,
                    env_snapshot=env_snapshot,
                    progress_cb=_pair_progress,
                )
        
                meta = {
                    "job_id": job_id,
                    "level": lvl.name,
                    "ref": {"id": lvl.ref.id, "ch": lvl.ref.channel, "value_v": lvl.ref.value_v, "u_std_v": lvl.ref.u_std_v},
                    "dut": {"id": dut.id, "ch": dut.channel},
                    "plan": plan.__dict__,
                    "mapping": mapping.__dict__,
                    "env": env_snapshot,
            "report_xlsx": str(xlsx_path),
                }
                save_summary_xlsx(xlsx_path, [result], meta, raw_rows=result.get("raw_rows"), raw_cycles=result.get("raw_cycles"))
        
                done_pairs += 1
                progress(done_pairs / total_pairs, f"Pair completed ({done_pairs}/{total_pairs})")
        JOBS[job_id]["status"] = "done"
        progress(1.0, "Completed")

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["message"] = repr(e)

    finally:
        # Close resources (best-effort)
        try:
            if meter:
                meter.close()
        except Exception:
            pass
        try:
            if switch:
                switch.close()
        except Exception:
            pass
        try:
            if lte:
                lte.close()
        except Exception:
            pass


@app.post("/start")
def start(req: StartRequest):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "queued", "progress": 0.0, "message": "Queued"}
    if not (req.simulation or req.meter_resource.upper().startswith('MOCK') or req.switch_resource.upper().startswith('MOCK')):
        _ensure_env(req.bme280_address, req.lte_port)
    threading.Thread(target=_worker, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id}


@app.get("/status/{job_id}")
def status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    return {"job_id": job_id, **JOBS[job_id]}


@app.get("/file/{job_id}/{name}")
def file(job_id: str, name: str):
    path = BASE / job_id / name
    if not path.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(str(path))


@app.get("/env")
def env():
    with _env_lock:
        return dict(ENV)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/list/{job_id}")
def list_files(job_id: str):
    job_dir = BASE / job_id
    if not job_dir.exists():
        raise HTTPException(404, "job not found")
    files = sorted([p.name for p in job_dir.iterdir() if p.is_file()])
    return {"job_id": job_id, "files": files}


@app.get("/zip/{job_id}")
def download_zip(job_id: str):
    job_dir = BASE / job_id
    if not job_dir.exists():
        raise HTTPException(404, "job not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in job_dir.iterdir():
            if p.is_file():
                z.write(p, arcname=p.name)
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="job_{job_id}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("transfer_service.service.server:app", host="0.0.0.0", port=8000, reload=False)
