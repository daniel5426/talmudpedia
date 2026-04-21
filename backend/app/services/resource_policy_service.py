from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.published_apps import PublishedApp
from app.db.postgres.models.resource_policies import (
    ResourcePolicyAssignment,
    ResourcePolicyPrincipalType,
    ResourcePolicyQuotaUnit,
    ResourcePolicyQuotaWindow,
    ResourcePolicyResourceType,
    ResourcePolicyRule,
    ResourcePolicyRuleType,
    ResourcePolicySet,
    ResourcePolicySetInclude,
)


class ResourcePolicyError(ValueError):
    pass


class ResourcePolicyAccessDenied(PermissionError):
    def __init__(self, *, resource_type: str, resource_id: str):
        super().__init__(f"Access denied for {resource_type}:{resource_id}")
        self.resource_type = resource_type
        self.resource_id = resource_id


@dataclass
class ResourcePolicyPrincipalRef:
    principal_type: ResourcePolicyPrincipalType
    organization_id: UUID
    user_id: UUID | None = None
    published_app_account_id: UUID | None = None
    embedded_agent_id: UUID | None = None
    external_user_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "principal_type": self.principal_type.value,
            "organization_id": str(self.organization_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "published_app_account_id": str(self.published_app_account_id) if self.published_app_account_id else None,
            "embedded_agent_id": str(self.embedded_agent_id) if self.embedded_agent_id else None,
            "external_user_id": self.external_user_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ResourcePolicyPrincipalRef | None":
        if not isinstance(payload, dict):
            return None
        principal_type = payload.get("principal_type")
        organization_id= payload.get("organization_id")
        if not principal_type or not organization_id:
            return None
        return cls(
            principal_type=ResourcePolicyPrincipalType(str(principal_type)),
            organization_id=UUID(str(organization_id)),
            user_id=UUID(str(payload["user_id"])) if payload.get("user_id") else None,
            published_app_account_id=UUID(str(payload["published_app_account_id"]))
            if payload.get("published_app_account_id")
            else None,
            embedded_agent_id=UUID(str(payload["embedded_agent_id"])) if payload.get("embedded_agent_id") else None,
            external_user_id=str(payload["external_user_id"]) if payload.get("external_user_id") else None,
        )


@dataclass
class ResourcePolicyQuotaRule:
    model_id: str
    limit_tokens: int
    window: str = ResourcePolicyQuotaWindow.MONTHLY.value
    unit: str = ResourcePolicyQuotaUnit.TOKENS.value

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResourcePolicySnapshot:
    principal: ResourcePolicyPrincipalRef | None = None
    direct_policy_set_id: str | None = None
    source_policy_set_ids: list[str] = field(default_factory=list)
    restricted_resource_types: set[str] = field(default_factory=set)
    allowed_agents: set[str] = field(default_factory=set)
    allowed_tools: set[str] = field(default_factory=set)
    allowed_knowledge_stores: set[str] = field(default_factory=set)
    allowed_models: set[str] = field(default_factory=set)
    model_quotas: dict[str, ResourcePolicyQuotaRule] = field(default_factory=dict)

    def has_rules(self) -> bool:
        return bool(self.source_policy_set_ids)

    def is_restricted_for(self, resource_type: ResourcePolicyResourceType | str) -> bool:
        return str(getattr(resource_type, "value", resource_type)) in self.restricted_resource_types

    def can_use(self, resource_type: ResourcePolicyResourceType | str, resource_id: UUID | str) -> bool:
        normalized_type = str(getattr(resource_type, "value", resource_type))
        normalized_id = str(resource_id)
        if normalized_type == ResourcePolicyResourceType.AGENT.value:
            allowed = self.allowed_agents
        elif normalized_type == ResourcePolicyResourceType.TOOL.value:
            allowed = self.allowed_tools
        elif normalized_type == ResourcePolicyResourceType.KNOWLEDGE_STORE.value:
            allowed = self.allowed_knowledge_stores
        elif normalized_type == ResourcePolicyResourceType.MODEL.value:
            allowed = self.allowed_models
        else:
            return True

        if normalized_type not in self.restricted_resource_types:
            return True
        return normalized_id in allowed

    def get_model_quota(self, model_id: UUID | str) -> ResourcePolicyQuotaRule | None:
        return self.model_quotas.get(str(model_id))

    def to_payload(self) -> dict[str, Any]:
        return {
            "principal": self.principal.to_payload() if self.principal else None,
            "direct_policy_set_id": self.direct_policy_set_id,
            "source_policy_set_ids": list(self.source_policy_set_ids),
            "restricted_resource_types": sorted(self.restricted_resource_types),
            "allowed_agents": sorted(self.allowed_agents),
            "allowed_tools": sorted(self.allowed_tools),
            "allowed_knowledge_stores": sorted(self.allowed_knowledge_stores),
            "allowed_models": sorted(self.allowed_models),
            "model_quotas": {key: value.to_payload() for key, value in self.model_quotas.items()},
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ResourcePolicySnapshot | None":
        if not isinstance(payload, dict) or not payload:
            return None
        return cls(
            principal=ResourcePolicyPrincipalRef.from_payload(payload.get("principal")),
            direct_policy_set_id=str(payload["direct_policy_set_id"]) if payload.get("direct_policy_set_id") else None,
            source_policy_set_ids=[str(item) for item in payload.get("source_policy_set_ids") or []],
            restricted_resource_types={str(item) for item in payload.get("restricted_resource_types") or []},
            allowed_agents={str(item) for item in payload.get("allowed_agents") or []},
            allowed_tools={str(item) for item in payload.get("allowed_tools") or []},
            allowed_knowledge_stores={str(item) for item in payload.get("allowed_knowledge_stores") or []},
            allowed_models={str(item) for item in payload.get("allowed_models") or []},
            model_quotas={
                str(key): ResourcePolicyQuotaRule(
                    model_id=str((value or {}).get("model_id") or key),
                    limit_tokens=int((value or {}).get("limit_tokens") or 0),
                    window=str((value or {}).get("window") or ResourcePolicyQuotaWindow.MONTHLY.value),
                    unit=str((value or {}).get("unit") or ResourcePolicyQuotaUnit.TOKENS.value),
                )
                for key, value in (payload.get("model_quotas") or {}).items()
            },
        )


class ResourcePolicyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_execution_snapshot(
        self,
        *,
        organization_id: UUID,
        agent_id: UUID,
        user_id: UUID | None = None,
        published_app_id: UUID | None = None,
        published_app_account_id: UUID | None = None,
        external_user_id: str | None = None,
    ) -> ResourcePolicySnapshot | None:
        principal = await self._resolve_principal(
            organization_id=organization_id,
            agent_id=agent_id,
            user_id=user_id,
            published_app_account_id=published_app_account_id,
            external_user_id=external_user_id,
        )
        if principal is None:
            return None

        policy_set_id = await self._resolve_direct_policy_set_id(principal=principal)
        if policy_set_id is None:
            policy_set_id = await self._resolve_default_policy_set_id(
                principal=principal,
                published_app_id=published_app_id,
                agent_id=agent_id,
            )
        if policy_set_id is None:
            return None
        return await self._build_snapshot(principal=principal, direct_policy_set_id=policy_set_id)

    async def assert_agent_access(
        self,
        *,
        snapshot: ResourcePolicySnapshot | None,
        agent_id: UUID,
    ) -> None:
        if snapshot is None or not snapshot.has_rules():
            return
        if not snapshot.can_use(ResourcePolicyResourceType.AGENT, agent_id):
            raise ResourcePolicyAccessDenied(resource_type=ResourcePolicyResourceType.AGENT.value, resource_id=str(agent_id))

    async def validate_policy_set_graph(self, *, organization_id: UUID, policy_set_id: UUID) -> None:
        await self._expand_policy_sets(organization_id=organization_id, direct_policy_set_id=policy_set_id)

    async def validate_policy_rule(
        self,
        *,
        resource_type: ResourcePolicyResourceType,
        rule_type: ResourcePolicyRuleType,
        quota_limit: int | None = None,
        quota_unit: ResourcePolicyQuotaUnit | None = None,
        quota_window: ResourcePolicyQuotaWindow | None = None,
    ) -> None:
        if rule_type == ResourcePolicyRuleType.ALLOW:
            return
        if resource_type != ResourcePolicyResourceType.MODEL:
            raise ResourcePolicyError("Quota rules are only supported for model resources")
        if quota_unit != ResourcePolicyQuotaUnit.TOKENS:
            raise ResourcePolicyError("Only token quotas are supported in this MVP")
        if quota_window != ResourcePolicyQuotaWindow.MONTHLY:
            raise ResourcePolicyError("Only monthly quotas are supported in this MVP")
        if quota_limit is None or int(quota_limit) <= 0:
            raise ResourcePolicyError("quota_limit must be a positive integer")

    async def _resolve_principal(
        self,
        *,
        organization_id: UUID,
        agent_id: UUID,
        user_id: UUID | None,
        published_app_account_id: UUID | None,
        external_user_id: str | None,
    ) -> ResourcePolicyPrincipalRef | None:
        if published_app_account_id is not None:
            return ResourcePolicyPrincipalRef(
                principal_type=ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT,
                organization_id=organization_id,
                published_app_account_id=published_app_account_id,
            )
        if external_user_id:
            return ResourcePolicyPrincipalRef(
                principal_type=ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER,
                organization_id=organization_id,
                embedded_agent_id=agent_id,
                external_user_id=str(external_user_id),
            )
        if user_id is not None:
            return ResourcePolicyPrincipalRef(
                principal_type=ResourcePolicyPrincipalType.ORGANIZATION_USER,
                organization_id=organization_id,
                user_id=user_id,
            )
        return None

    async def _resolve_direct_policy_set_id(self, *, principal: ResourcePolicyPrincipalRef) -> UUID | None:
        stmt = select(ResourcePolicyAssignment).where(
            ResourcePolicyAssignment.organization_id == principal.organization_id,
            ResourcePolicyAssignment.principal_type == principal.principal_type,
        )
        if principal.principal_type == ResourcePolicyPrincipalType.ORGANIZATION_USER:
            stmt = stmt.where(ResourcePolicyAssignment.user_id == principal.user_id)
        elif principal.principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT:
            stmt = stmt.where(ResourcePolicyAssignment.published_app_account_id == principal.published_app_account_id)
        else:
            stmt = stmt.where(
                ResourcePolicyAssignment.embedded_agent_id == principal.embedded_agent_id,
                ResourcePolicyAssignment.external_user_id == principal.external_user_id,
            )
        result = await self.db.execute(stmt.limit(1))
        assignment = result.scalar_one_or_none()
        return assignment.policy_set_id if assignment is not None else None

    async def _resolve_default_policy_set_id(
        self,
        *,
        principal: ResourcePolicyPrincipalRef,
        published_app_id: UUID | None,
        agent_id: UUID,
    ) -> UUID | None:
        if principal.principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT:
            if published_app_id is None:
                return None
            app = await self.db.get(PublishedApp, published_app_id)
            return getattr(app, "default_policy_set_id", None) if app is not None else None
        if principal.principal_type == ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER:
            agent = await self.db.get(Agent, agent_id)
            return getattr(agent, "default_embed_policy_set_id", None) if agent is not None else None
        return None

    async def _build_snapshot(
        self,
        *,
        principal: ResourcePolicyPrincipalRef,
        direct_policy_set_id: UUID,
    ) -> ResourcePolicySnapshot:
        policy_sets = await self._expand_policy_sets(organization_id=principal.organization_id, direct_policy_set_id=direct_policy_set_id)
        policy_set_ids = [str(item.id) for item in policy_sets]
        rules_result = await self.db.execute(
            select(ResourcePolicyRule).where(ResourcePolicyRule.policy_set_id.in_([item.id for item in policy_sets]))
        )
        rules = list(rules_result.scalars().all())
        snapshot = ResourcePolicySnapshot(
            principal=principal,
            direct_policy_set_id=str(direct_policy_set_id),
            source_policy_set_ids=policy_set_ids,
        )
        seen_model_quotas: set[str] = set()
        for rule in rules:
            resource_type = str(rule.resource_type.value if hasattr(rule.resource_type, "value") else rule.resource_type)
            resource_id = str(rule.resource_id)
            rule_type = rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type)
            if rule_type == ResourcePolicyRuleType.ALLOW.value:
                snapshot.restricted_resource_types.add(resource_type)
                if resource_type == ResourcePolicyResourceType.AGENT.value:
                    snapshot.allowed_agents.add(resource_id)
                elif resource_type == ResourcePolicyResourceType.TOOL.value:
                    snapshot.allowed_tools.add(resource_id)
                elif resource_type == ResourcePolicyResourceType.KNOWLEDGE_STORE.value:
                    snapshot.allowed_knowledge_stores.add(resource_id)
                elif resource_type == ResourcePolicyResourceType.MODEL.value:
                    snapshot.allowed_models.add(resource_id)
                continue

            if resource_type != ResourcePolicyResourceType.MODEL.value:
                raise ResourcePolicyError("Encountered non-model quota rule during snapshot build")
            if resource_id in seen_model_quotas:
                raise ResourcePolicyError(f"Conflicting quota rules detected for model {resource_id}")
            seen_model_quotas.add(resource_id)
            snapshot.model_quotas[resource_id] = ResourcePolicyQuotaRule(
                model_id=resource_id,
                limit_tokens=int(rule.quota_limit or 0),
                window=str(rule.quota_window.value if hasattr(rule.quota_window, "value") else rule.quota_window),
                unit=str(rule.quota_unit.value if hasattr(rule.quota_unit, "value") else rule.quota_unit),
            )
        return snapshot

    async def _expand_policy_sets(
        self,
        *,
        organization_id: UUID,
        direct_policy_set_id: UUID,
    ) -> list[ResourcePolicySet]:
        visited: set[UUID] = set()
        ordered: list[ResourcePolicySet] = []
        path: set[UUID] = set()

        async def _visit(current_id: UUID) -> None:
            if current_id in path:
                raise ResourcePolicyError("Resource policy set include cycle detected")
            if current_id in visited:
                return

            path.add(current_id)
            current = await self.db.get(ResourcePolicySet, current_id)
            if current is None or current.organization_id != organization_id:
                raise ResourcePolicyError("Resource policy set not found")
            ordered.append(current)

            include_result = await self.db.execute(
                select(ResourcePolicySetInclude).where(ResourcePolicySetInclude.parent_policy_set_id == current_id)
            )
            include_rows = list(include_result.scalars().all())
            for include in include_rows:
                if include.included_policy_set_id == current_id:
                    raise ResourcePolicyError("Resource policy set cannot include itself")
                await _visit(include.included_policy_set_id)

            path.remove(current_id)
            visited.add(current_id)

        await _visit(direct_policy_set_id)
        return ordered
