# Transfer Service v0.0.7

Standalone metrological **transfer service**.

## Instruments
- **Keithley 2182/2182A**: `:SENS:DATA:FRESH?`, DFIL toggled before each block.
- **Dataproof 320B**: `Axx`/`Bxx`, **A00+B00** before every close, **>=200 ms** between actuations.
- **LTE-300** (USB-serial): temperature **per sample** (`d<CR>`).
- **BME280** (bme280pi): ambient T/RH/P (pressure in **kPa**).

## Architecture
- `transfer_service/drivers/` — instruments only (SCPI/serial).
- `transfer_service/math/` — calculations only (delta, Allan, uncertainty, 20°C reduction).
- `transfer_service/io/` — raw CSV and XLSX summary.
- `transfer_service/transfer.py` — measurement procedure (`+ - + - + -`).
- `transfer_service/service/server.py` — FastAPI service (run on RPi).
- `transfer_service/client/win_gui.py` — Windows GUI client (Tkinter).

Version: **0.0.7** (2026-02-26)

## Reduction to 20°C
- Saturated: polynomial (ГОСТ coefficients) in `math/ne_temp.py`
- Unsaturated: linear using passport **alpha in µV/°C**

## Run on RPi
```bash
cd transfer_service
python3 -m pip install -r requirements.txt
uvicorn transfer_service.service.server:app --host 0.0.0.0 --port 8000
```

## Run Windows GUI
```bash
pip install requests
python transfer_service/client/win_gui.py
```

## LTE-300 port recommendation
Use stable path:
- `/dev/serial/by-id/usb-FTDI_...-if00-port0`

Or use selector:
- `by-id:FT4QUE2F`

## Output files (per job)
RPi folder `jobs/<job_id>/`.

For **each pair** (REF vs DUT) you get separate files named with **measure IDs and channels**:
- `raw_<LEVEL>_REF<ref_id>_chXX__DUT<dut_id>_chYY.csv`
- `report_<LEVEL>_REF<ref_id>_chXX__DUT<dut_id>_chYY.xlsx`

Example:
- `raw_10V_REFREF10-01_ch03__DUTDUT10-05_ch05.csv`
- `report_10V_REFREF10-01_ch03__DUTDUT10-05_ch05.xlsx`



## Simulation mode (no instruments)
To test without real 2182/320B/LTE-300:
- Enable **Simulation** in GUI, or send `"simulation": true` in `/start` request.
The service will generate synthetic data and still produce per-pair CSV/XLSX outputs.



## Web UI
Run the server and open the browser:

```bash
uvicorn transfer_service.service.server:app --host 0.0.0.0 --port 8000
```

Open:
- `http://127.0.0.1:8000/` — Web UI
- `http://127.0.0.1:8000/docs` — API docs

Extra endpoints:
- `GET /list/{job_id}` — list job files
- `GET /zip/{job_id}` — download all job files as ZIP



## v0.0.9.2 measurement mode (fixed samples)
Time-based acquisition was replaced by a fixed number of samples per polarity.

- `cycles` — number of reversal cycles
- `samples_per_polarity` — number of measurements for "+" and for "-" inside each cycle

Total samples:
- `n_plus = cycles * samples_per_polarity`
- `n_minus = cycles * samples_per_polarity`

Legacy `block_duration_s` is kept for backward compatibility but is not used in v0.0.9.2.
