"""
Carbon Emitter Simulator — SteelForge Industries Pvt. Ltd.
Real-time simulation of steel-plant CO₂ emissions for CfoE integration.
Runs on port 8001.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────

SUPPLIER_ID = "SUP-STEELFORGE-001"
SUPPLIER_NAME = "SteelForge Industries Pvt. Ltd."
LOCATION = "Pune, Maharashtra, India"

PROCESSES: List[Dict[str, Any]] = [
    {"name": "Blast Furnace",     "base_co2": 420.0, "weight": 0.45},
    {"name": "Rolling Mill",      "base_co2": 180.0, "weight": 0.20},
    {"name": "Power Generation",  "base_co2":  95.0, "weight": 0.15},
    {"name": "Coking Plant",      "base_co2": 110.0, "weight": 0.12},
    {"name": "Logistics",         "base_co2":  55.0, "weight": 0.08},
]

VIOLATION_TYPES: List[Dict[str, Any]] = [
    {"type": "EPA_FINE",           "severity": "HIGH",   "description": "EPA emission limit fine — exceeded NOx/SOx thresholds",                "fine": 250_000},
    {"type": "COOLING_DISCHARGE",  "severity": "MEDIUM", "description": "Thermal discharge violation — cooling water above permissible limit",  "fine":  75_000},
    {"type": "PERMIT_DEVIATION",   "severity": "LOW",    "description": "Operating outside environmental permit conditions",                    "fine":  25_000},
    {"type": "CPCB_NOTICE",        "severity": "HIGH",   "description": "Central Pollution Control Board show-cause notice",                    "fine": 500_000},
    {"type": "WASTE_DISPOSAL",     "severity": "MEDIUM", "description": "Improper disposal of slag / hazardous by-products",                    "fine": 120_000},
]

TICK_INTERVAL = 3  # seconds
MAX_HISTORY   = 60
MAX_EXPECTED_DAILY_CO2 = sum(p["base_co2"] for p in PROCESSES) * 2.1  # theoretical max with spike

CFOE_AUDIT_URL = "http://localhost:8001/api/audit"
CFOE_HISTORY_URL = "http://localhost:8001/api/audits"

# ── Application ───────────────────────────────────────────────────────

app = FastAPI(title="CfoE Carbon Emitter Simulator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Simulation state ─────────────────────────────────────────────────

class SimulationState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.running: bool = False
        self.tick_count: int = 0
        self.total_co2_today: float = 0.0
        self.process_emissions: Dict[str, float] = {p["name"]: 0.0 for p in PROCESSES}
        self.active_violations: List[Dict[str, Any]] = []
        self.cumulative_violations: int = 0
        self.esg_score: float = 0.0
        self.spike_active: bool = False
        self.spike_remaining: int = 0
        self.spike_multiplier: float = 1.0
        self.history: List[Dict[str, Any]] = []
        self.last_audit_result: Optional[Dict[str, Any]] = None


state = SimulationState()

# ── WebSocket manager ─────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: Dict[str, Any]) -> None:
        dead: List[WebSocket] = []
        for ws in self.active[:]:
            try:
                # Check if websocket is still connected
                if hasattr(ws, 'client_state') and ws.client_state.name != 'CONNECTED':
                    dead.append(ws)
                    continue
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

# ── Helpers ───────────────────────────────────────────────────────────

def _current_shift() -> Tuple[str, float]:
    """Return (shift_name, multiplier) based on IST hour."""
    hour = (datetime.now(timezone.utc).hour + 5) % 24  # rough IST
    if 6 <= hour < 14:
        return "Day", 1.0
    elif 14 <= hour < 22:
        return "Evening", 0.88
    else:
        return "Night", 0.72


def _compute_esg_score() -> float:
    """Mirror CalculationAgent deterministic logic."""
    emissions_ratio = state.total_co2_today / MAX_EXPECTED_DAILY_CO2
    active_count = len(state.active_violations)
    violation_penalty = min(active_count * 0.15 + state.cumulative_violations * 0.01, 0.5)
    return round(min(emissions_ratio * 0.6 + violation_penalty, 1.0), 4)


def _build_snapshot() -> Dict[str, Any]:
    shift_name, shift_mult = _current_shift()
    # Estimated annual = sum of current daily rates × 365
    current_daily_total = sum(state.process_emissions.values())
    estimated_annual_co2 = round(current_daily_total * 365, 2)
    return {
        "type": "tick",
        "supplier_id": SUPPLIER_ID,
        "supplier_name": SUPPLIER_NAME,
        "location": LOCATION,
        "tick": state.tick_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "shift": shift_name,
        "shift_multiplier": shift_mult,
        "running": state.running,
        "total_co2_today": round(state.total_co2_today, 2),
        "current_daily_co2": round(current_daily_total, 2),
        "estimated_annual_co2": estimated_annual_co2,
        "process_emissions": {k: round(v, 2) for k, v in state.process_emissions.items()},
        "esg_score": state.esg_score,
        "spike_active": state.spike_active,
        "spike_remaining": state.spike_remaining,
        "spike_multiplier": round(state.spike_multiplier, 2),
        "active_violations": state.active_violations,
        "active_violation_count": len(state.active_violations),
        "cumulative_violations": state.cumulative_violations,
        "last_audit_result": state.last_audit_result,
    }

# ── Simulation loop ──────────────────────────────────────────────────

async def _simulation_loop() -> None:
    while True:
        if not state.running:
            await asyncio.sleep(0.5)
            continue

        state.tick_count += 1
        shift_name, shift_mult = _current_shift()

        # --- Process emissions ---
        tick_co2 = 0.0
        for proc in PROCESSES:
            noise = random.gauss(1.0, 0.06)  # ±6 %
            daily_rate = proc["base_co2"] * shift_mult * noise

            # Apply spike
            if state.spike_active:
                daily_rate *= state.spike_multiplier

            # Convert daily to per-tick (tick = 3 s ≈ fraction of day)
            per_tick = daily_rate / (86400 / TICK_INTERVAL)
            state.process_emissions[proc["name"]] = daily_rate  # store current daily rate
            tick_co2 += per_tick

        state.total_co2_today += tick_co2

        # --- Spike lifecycle ---
        if state.spike_active:
            state.spike_remaining -= 1
            if state.spike_remaining <= 0:
                state.spike_active = False
                state.spike_multiplier = 1.0
        else:
            if random.random() < 0.08:
                state.spike_active = True
                state.spike_remaining = random.randint(3, 8)
                state.spike_multiplier = round(random.uniform(1.4, 2.1), 2)

        # --- Violation check ---
        if random.random() < 0.05:
            viol = random.choice(VIOLATION_TYPES)
            entry = {
                **viol,
                "id": f"VIO-{uuid4().hex[:8].upper()}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            state.active_violations.append(entry)
            # Keep last 10 for display
            if len(state.active_violations) > 10:
                state.active_violations = state.active_violations[-10:]
            state.cumulative_violations += 1

        # --- ESG score ---
        state.esg_score = _compute_esg_score()

        # --- History ---
        snap = _build_snapshot()
        state.history.append(snap)
        if len(state.history) > MAX_HISTORY:
            state.history = state.history[-MAX_HISTORY:]

        # --- Broadcast ---
        await manager.broadcast(snap)

        await asyncio.sleep(TICK_INTERVAL)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_simulation_loop())

# ── WebSocket endpoint ────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    # Send current snapshot immediately on connect
    await websocket.send_json(_build_snapshot())
    try:
        while True:
            # keep connection alive; ignore incoming data
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ── REST endpoints ────────────────────────────────────────────────────

@app.post("/simulation/start")
async def start_simulation() -> Dict[str, Any]:
    state.running = True
    return {"status": "running"}


@app.post("/simulation/stop")
async def stop_simulation() -> Dict[str, Any]:
    state.running = False
    return {"status": "stopped"}


@app.post("/simulation/reset")
async def reset_simulation() -> Dict[str, Any]:
    state.reset()
    await manager.broadcast(_build_snapshot())
    return {"status": "reset"}


@app.post("/simulation/trigger-spike")
async def trigger_spike() -> Dict[str, Any]:
    state.spike_active = True
    state.spike_remaining = 6
    state.spike_multiplier = round(random.uniform(1.4, 2.1), 2)
    return {"status": "spike_triggered", "multiplier": state.spike_multiplier, "ticks": 6}


@app.post("/simulation/trigger-violation")
async def trigger_violation() -> Dict[str, Any]:
    entry = {
        "type": "EPA_FINE",
        "severity": "HIGH",
        "description": "EPA emission limit fine — exceeded NOx/SOx thresholds",
        "fine": 250_000,
        "id": f"VIO-{uuid4().hex[:8].upper()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state.active_violations.append(entry)
    if len(state.active_violations) > 10:
        state.active_violations = state.active_violations[-10:]
    state.cumulative_violations += 3
    state.esg_score = _compute_esg_score()
    await manager.broadcast(_build_snapshot())
    return {"status": "violation_injected", "violation": entry, "cumulative": state.cumulative_violations}


@app.get("/simulation/snapshot")
async def snapshot() -> Dict[str, Any]:
    return _build_snapshot()


# ── Audit integration ─────────────────────────────────────────────────

@app.post("/audit/run")
async def run_audit() -> Dict[str, Any]:
    """Pull current snapshot and POST to CfoE /api/audit, broadcast result."""
    snap = _build_snapshot()

    # Build payload matching CfoE's AuditRequest schema exactly
    # Use estimated annual CO₂ as the emissions figure for realistic ESG scoring
    payload = {
        "supplier_name": snap["supplier_name"],
        "emissions": snap["estimated_annual_co2"],
        "violations": snap["cumulative_violations"],
        "notes": (
            f"Simulator audit — tick {snap['tick']}, "
            f"shift={snap['shift']}, "
            f"spike={'YES' if snap['spike_active'] else 'NO'}, "
            f"active_violations={snap['active_violation_count']}, "
            f"daily_co2={snap['current_daily_co2']}t, "
            f"annual_est={snap['estimated_annual_co2']}t"
        ),
        "sector": "default",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(CFOE_AUDIT_URL, json=payload)
            resp.raise_for_status()
            audit_result = resp.json()
    except Exception as exc:
        error_msg = {
            "type": "audit_error",
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast(error_msg)
        return error_msg

    state.last_audit_result = audit_result

    broadcast_payload = {
        "type": "audit_result",
        "result": audit_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast(broadcast_payload)
    return audit_result


@app.get("/audit/history")
async def get_audit_history() -> Dict[str, Any]:
    """Fetch audit history from CfoE main system."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(CFOE_HISTORY_URL)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"error": str(exc), "items": [], "count": 0}


# ── Dashboard serving ─────────────────────────────────────────────────

DASHBOARD_PATH = Path(__file__).resolve().parent / "dashboard.html"


@app.get("/")
def serve_dashboard() -> FileResponse:
    return FileResponse(str(DASHBOARD_PATH), media_type="text/html")


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simulator:app", host="0.0.0.0", port=8000, reload=True)
