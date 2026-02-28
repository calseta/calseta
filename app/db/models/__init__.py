"""Import all models to ensure they are registered with SQLAlchemy metadata."""

from app.db.models.activity_event import ActivityEvent
from app.db.models.agent_registration import AgentRegistration
from app.db.models.agent_run import AgentRun
from app.db.models.alert import Alert
from app.db.models.alert_indicator import AlertIndicator
from app.db.models.api_key import APIKey
from app.db.models.context_document import ContextDocument
from app.db.models.detection_rule import DetectionRule
from app.db.models.enrichment_field_extraction import EnrichmentFieldExtraction
from app.db.models.indicator import Indicator
from app.db.models.indicator_field_mapping import IndicatorFieldMapping
from app.db.models.source_integration import SourceIntegration
from app.db.models.workflow import Workflow
from app.db.models.workflow_approval_request import WorkflowApprovalRequest
from app.db.models.workflow_run import WorkflowRun

__all__ = [
    "Alert",
    "AgentRegistration",
    "AgentRun",
    "ActivityEvent",
    "AlertIndicator",
    "APIKey",
    "ContextDocument",
    "DetectionRule",
    "EnrichmentFieldExtraction",
    "Indicator",
    "IndicatorFieldMapping",
    "SourceIntegration",
    "Workflow",
    "WorkflowApprovalRequest",
    "WorkflowRun",
]
