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
from app.db.models.agent_run_event import AgentRunEvent
from app.db.models.agent_task_session import AgentTaskSession
from app.db.models.agent_tool import AgentTool
from app.db.models.agent_workspace import AgentWorkspace
from app.db.models.alert import Alert
from app.db.models.alert_assignment import AlertAssignment
from app.db.models.alert_indicator import AlertIndicator
from app.db.models.api_key import APIKey
from app.db.models.cost_event import CostEvent
from app.db.models.detection_rule import DetectionRule
from app.db.models.enrichment_field_extraction import EnrichmentFieldExtraction
from app.db.models.enrichment_provider import EnrichmentProvider
from app.db.models.health_metric import HealthMetric
from app.db.models.health_metric_config import HealthMetricConfig
from app.db.models.health_source import HealthSource
from app.db.models.heartbeat_run import HeartbeatRun
from app.db.models.indicator import Indicator
from app.db.models.indicator_field_mapping import IndicatorFieldMapping
from app.db.models.issue_category import IssueCategoryDef
from app.db.models.issue_label import IssueLabel
from app.db.models.kb_page import KnowledgeBasePage
from app.db.models.kb_page_link import KBPageLink
from app.db.models.kb_page_revision import KBPageRevision
from app.db.models.llm_integration import LLMIntegration
from app.db.models.routine_run import RoutineRun
from app.db.models.routine_trigger import RoutineTrigger
from app.db.models.secret import Secret, SecretVersion
from app.db.models.skill import Skill
from app.db.models.skill_file import SkillFile
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
    "IssueCategoryDef",
    "IssueLabel",
    "AgentAPIKey",
    "AgentInvocation",
    "AgentInstructionFile",
    "AgentRegistration",
    "AgentWorkspace",
    "AgentRun",
    "AgentRunEvent",
    "AgentTaskSession",
    "AgentTool",
    "Alert",
    "AlertAssignment",
    "AlertIndicator",
    "APIKey",
    "CostEvent",
    "DetectionRule",
    "EnrichmentFieldExtraction",
    "EnrichmentProvider",
    "HealthMetric",
    "HealthMetricConfig",
    "HealthSource",
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
    "KnowledgeBasePage",
    "KBPageRevision",
    "KBPageLink",
    "Skill",
    "SkillFile",
]
