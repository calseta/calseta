"""Import all models to ensure they are registered with SQLAlchemy metadata."""

from app.db.models.activity_event import ActivityEvent
from app.db.models.agent_action import AgentAction
from app.db.models.agent_api_key import AgentAPIKey
from app.db.models.agent_instruction_file import AgentInstructionFile
from app.db.models.agent_invocation import AgentInvocation
from app.db.models.agent_issue import AgentIssue
from app.db.models.agent_issue_comment import AgentIssueComment
from app.db.models.agent_registration import AgentRegistration
from app.db.models.agent_routine import AgentRoutine
from app.db.models.agent_run import AgentRun
from app.db.models.agent_task_session import AgentTaskSession
from app.db.models.agent_tool import AgentTool
from app.db.models.alert import Alert
from app.db.models.alert_assignment import AlertAssignment
from app.db.models.alert_indicator import AlertIndicator
from app.db.models.api_key import APIKey
from app.db.models.campaign import Campaign
from app.db.models.campaign_item import CampaignItem
from app.db.models.context_document import ContextDocument
from app.db.models.cost_event import CostEvent
from app.db.models.detection_rule import DetectionRule
from app.db.models.enrichment_field_extraction import EnrichmentFieldExtraction
from app.db.models.enrichment_provider import EnrichmentProvider
from app.db.models.heartbeat_run import HeartbeatRun
from app.db.models.indicator import Indicator
from app.db.models.indicator_field_mapping import IndicatorFieldMapping
from app.db.models.llm_integration import LLMIntegration
from app.db.models.routine_run import RoutineRun
from app.db.models.routine_trigger import RoutineTrigger
from app.db.models.secret import Secret, SecretVersion
from app.db.models.source_integration import SourceIntegration
from app.db.models.user_validation_rule import UserValidationRule
from app.db.models.user_validation_template import UserValidationTemplate
from app.db.models.workflow import Workflow
from app.db.models.workflow_approval_request import WorkflowApprovalRequest
from app.db.models.workflow_code_version import WorkflowCodeVersion
from app.db.models.workflow_run import WorkflowRun

__all__ = [
    "ActivityEvent",
    "AgentAction",
    "AgentIssue",
    "AgentIssueComment",
    "AgentAPIKey",
    "AgentInvocation",
    "AgentInstructionFile",
    "AgentRegistration",
    "AgentRun",
    "AgentTaskSession",
    "AgentTool",
    "Alert",
    "AlertAssignment",
    "AlertIndicator",
    "APIKey",
    "ContextDocument",
    "CostEvent",
    "DetectionRule",
    "EnrichmentFieldExtraction",
    "EnrichmentProvider",
    "HeartbeatRun",
    "Indicator",
    "IndicatorFieldMapping",
    "LLMIntegration",
    "Secret",
    "SecretVersion",
    "SourceIntegration",
    "UserValidationRule",
    "UserValidationTemplate",
    "Workflow",
    "WorkflowApprovalRequest",
    "WorkflowCodeVersion",
    "WorkflowRun",
    "AgentRoutine",
    "RoutineTrigger",
    "RoutineRun",
    "Campaign",
    "CampaignItem",
]
