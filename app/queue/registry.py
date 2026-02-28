"""
Task registry — all procrastinate @app.task decorated functions live here.

This module is imported by the worker process (app/worker.py) to ensure
tasks are registered before the worker starts consuming. The API server
also imports this module at startup to enable task enqueueing.

Tasks are added here in subsequent waves:
    Wave 2: enrich_alert, evaluate_alert_triggers
    Wave 3: run_on_demand_enrichment
    Wave 4: execute_workflow, deliver_agent_webhook

Each task function must:
    - Be decorated with @procrastinate_app.task(queue=..., retry=...)
    - Be idempotent (safe to run more than once)
    - Never raise — catch all errors and log them
"""

from __future__ import annotations

# No tasks registered yet — added in Waves 2–4.
# The procrastinate App instance is accessed via:
#   from app.queue.backends.postgres import ProcrastinateBackend
#   backend = get_queue_backend()
#   assert isinstance(backend, ProcrastinateBackend)
#   procrastinate_app = backend.app
