"""Deterministic retrieval of SolutionAsset candidates without Fit assessment."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution_intelligence import AIGene, AssetCandidate, SolutionAsset
from backend.app.solution.asset_repository import AssetRepository


@dataclass(frozen=True)
class RetrievalWeights:
    """B-M8.2 retrieval-only ranking weights; these are not FitScore weights."""

    action_process: float = 30.0
    scenario_pain: float = 20.0
    industry: float = 15.0
    role: float = 10.0
    data_knowledge: float = 10.0
    system_tool: float = 5.0
    official_evidence: float = 10.0


WEIGHTS = RetrievalWeights()
_OFFICIAL_SOURCE_TYPES = {"official_solution", "official_case", "official_bluebook"}
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_SEPARATORS = re.compile(r"[^\w\u4e00-\u9fff]+", flags=re.UNICODE)
_IGNORED_NGRAMS = {"人员", "部门", "系统", "业务", "场景", "助手", "智能", "案例", "生成", "处理", "信息", "数据"}
_CONNECTIVE_CHARS = "与和及或的在对从将并"


def _normalize(value: str) -> str:
    return _SEPARATORS.sub("", unicodedata.normalize("NFKC", value).lower()).strip()


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _cjk_ngrams(value: str) -> set[str]:
    ngrams: set[str] = set()
    for run in _CJK_RUN.findall(value):
        for size in range(2, len(run) + 1):
            ngrams.update(run[index : index + size] for index in range(len(run) - size + 1))
    return ngrams


def _clean_match(value: str) -> str:
    return value.strip(_CONNECTIVE_CHARS)


def _matched_terms(asset_values: Iterable[str], query_values: Iterable[str]) -> list[str]:
    asset_terms = _unique(asset_values)
    query_terms = _unique(query_values)
    direct_matches: set[str] = set()

    for asset_term in asset_terms:
        for query_term in query_terms:
            if asset_term in query_term or query_term in asset_term:
                direct_matches.add(asset_term if len(asset_term) <= len(query_term) else query_term)
    if direct_matches:
        return sorted(direct_matches)

    ngram_matches: set[str] = set()
    for asset_term in asset_terms:
        for query_term in query_terms:
            shared = _cjk_ngrams(asset_term) & _cjk_ngrams(query_term)
            if shared:
                longest = max(len(term) for term in shared)
                ngram_matches.update(term for term in shared if len(term) == longest)
    return sorted(
        {
            cleaned
            for match in ngram_matches
            if (cleaned := _clean_match(match)) not in _IGNORED_NGRAMS and len(cleaned) >= 2
        }
    )


def _module_values(asset: SolutionAsset, field_name: str) -> list[str]:
    values: list[str] = []
    for module in asset.modules:
        values.extend(getattr(module, field_name))
    return values


def _asset_action_terms(asset: SolutionAsset) -> list[str]:
    return (
        list(asset.processes)
        + [module.name for module in asset.modules]
        + [gene.action_name for gene in asset.action_genes]
        + list(asset.standards_and_rules)
        + _module_values(asset, "required_rules")
    )


def _query_action_terms(process: ProcessSpec, genes: list[AIGene]) -> list[str]:
    return (
        [node.name for node in process.as_is_nodes]
        + [node.description for node in process.as_is_nodes]
        + [gene.action_name for gene in genes]
        + [process.department]
        + [process.business_goal]
        + [constraint.statement for constraint in process.constraints]
    )


def _official_evidence_refs(asset: SolutionAsset) -> list[str]:
    return [
        evidence.evidence_id
        for evidence in asset.evidence
        if evidence.verified and evidence.source_type in _OFFICIAL_SOURCE_TYPES
    ]


@dataclass(frozen=True)
class _ScoredAsset:
    asset: SolutionAsset
    score: float
    matched_terms: list[str]
    matched_gene_ids: list[str]


class AssetRetriever:
    """Rank possible SolutionAssets for later Fit assessment; never makes a final recommendation."""

    def __init__(self, repository: AssetRepository) -> None:
        self._repository = repository

    def retrieve(
        self,
        process: ProcessSpec,
        genes: list[AIGene],
        top_k: int = 5,
    ) -> list[AssetCandidate]:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")

        scored = [self._score_asset(process, genes, asset) for asset in self._repository.list_assets()]
        positive = [item for item in scored if item.score > 0]
        positive.sort(key=lambda item: (-item.score, item.asset.asset_id))

        return [
            AssetCandidate(
                asset_id=item.asset.asset_id,
                retrieval_score=item.score,
                matched_terms=item.matched_terms,
                matched_gene_ids=item.matched_gene_ids,
                evidence_refs=[evidence.evidence_id for evidence in item.asset.evidence],
            )
            for item in positive[:top_k]
        ]

    def _score_asset(
        self,
        process: ProcessSpec,
        genes: list[AIGene],
        asset: SolutionAsset,
    ) -> _ScoredAsset:
        action_terms = _matched_terms(_asset_action_terms(asset), _query_action_terms(process, genes))
        scenario_terms = _matched_terms(
            list(asset.scenarios) + list(asset.pain_points),
            [process.business_goal]
            + [pain.description for pain in process.pain_points]
            + list(process.target_metrics),
        )
        industry_terms = _matched_terms(asset.industries, [process.industry])
        role_terms = _matched_terms(
            list(asset.target_roles) + [role for gene in asset.action_genes for role in gene.role],
            list(process.roles) + [role for gene in genes for role in gene.role],
        )
        data_terms = _matched_terms(
            list(asset.supported_data)
            + list(asset.supported_knowledge)
            + _module_values(asset, "required_data")
            + _module_values(asset, "required_knowledge"),
            list(process.available_data)
            + [value for gene in genes for value in gene.data_and_knowledge],
        )
        system_terms = _matched_terms(
            list(asset.supported_systems)
            + _module_values(asset, "required_systems")
            + _module_values(asset, "required_tools"),
            list(process.existing_systems) + [tool for gene in genes for tool in gene.tools],
        )

        business_relevance = sum(
            (
                WEIGHTS.action_process if action_terms else 0.0,
                WEIGHTS.scenario_pain if scenario_terms else 0.0,
                WEIGHTS.industry if industry_terms else 0.0,
                WEIGHTS.role if role_terms else 0.0,
                WEIGHTS.data_knowledge if data_terms else 0.0,
                WEIGHTS.system_tool if system_terms else 0.0,
            )
        )
        evidence_bonus = (
            WEIGHTS.official_evidence
            if business_relevance > 0 and _official_evidence_refs(asset)
            else 0.0
        )
        score = business_relevance + evidence_bonus

        asset_action_terms = _asset_action_terms(asset)
        matched_gene_ids = [
            gene.gene_id
            for gene in genes
            if _matched_terms(asset_action_terms, [gene.action_name])
        ]
        return _ScoredAsset(
            asset=asset,
            score=min(100.0, score),
            matched_terms=sorted(
                set(action_terms + scenario_terms + industry_terms + role_terms + data_terms + system_terms)
            ),
            matched_gene_ids=matched_gene_ids,
        )
