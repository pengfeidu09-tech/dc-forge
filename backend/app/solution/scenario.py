"""确定性场景识别与场景化数据。

根据 ProcessSpec 的业务内容识别场景类型，提供场景化的组件选择、
节点命名、实施步骤和审批理由。不使用 project_id。
"""

from __future__ import annotations

from backend.app.contracts.process import ProcessSpec

# ---------------------------------------------------------------------------
# 场景类型
# ---------------------------------------------------------------------------

SCENARIO_TYPES = (
    "incident_response",
    "fraud_risk",
    "identity_account",
    "dispute_investigation",
    "customer_service",
    "procurement_exception",
    "generic",
)

# ---------------------------------------------------------------------------
# 场景识别
# ---------------------------------------------------------------------------


def identify_scenario(process: ProcessSpec) -> str:
    """根据 ProcessSpec 业务内容识别场景类型。"""
    text = " ".join([
        process.industry,
        process.department,
        process.business_goal,
        " ".join(process.available_data),
        " ".join(process.target_metrics),
        " ".join(pp.description for pp in process.pain_points),
        " ".join(process.existing_systems),
    ])

    # 优先级：从具体到通用
    if any(kw in text for kw in ["采购", "发票", "收货记录", "供应商"]):
        return "procurement_exception"
    if any(kw in text for kw in ["欺诈", "未授权交易", "信用卡申请", "fraud", "盗刷"]):
        return "fraud_risk"
    if any(kw in text for kw in ["姓名变更", "身份变更", "账户资料变更", "身份核验", "身份证明"]):
        return "identity_account"
    if any(kw in text for kw in ["争议", "征信", "信用报告", "调查", "复核", "查询授权", "重新调查"]):
        return "dispute_investigation"
    if any(kw in text for kw in ["故障", "恢复", "不可用", "outage", "中断", "宕机", "告警"]):
        return "incident_response"
    if any(kw in text for kw in ["购物车", "购票", "登录失败", "客户服务", "工单"]):
        return "customer_service"

    return "generic"


# ---------------------------------------------------------------------------
# 场景化组件选择
# ---------------------------------------------------------------------------

_SCENARIO_COMPONENTS: dict[str, dict[str, list[str]]] = {
    "incident_response": {
        "conservative": [
            "anomaly-classification", "ticket-routing", "human-approval",
            "feishu-notification", "audit-log",
        ],
        "balanced": [
            "anomaly-classification", "ticket-routing", "process-monitoring",
            "human-approval", "feishu-notification", "audit-log", "quality-dashboard",
        ],
        "innovative": [
            "anomaly-classification", "ticket-routing", "process-monitoring",
            "human-approval", "feishu-notification", "audit-log",
            "quality-dashboard", "feedback-loop", "enterprise-rag",
        ],
    },
    "fraud_risk": {
        "conservative": [
            "anomaly-classification", "risk-scoring", "rule-engine",
            "human-approval", "audit-log",
        ],
        "balanced": [
            "anomaly-classification", "risk-scoring", "rule-engine",
            "human-approval", "audit-log", "data-masking", "process-monitoring",
        ],
        "innovative": [
            "anomaly-classification", "risk-scoring", "rule-engine",
            "human-approval", "audit-log", "data-masking", "process-monitoring",
            "local-model", "quality-dashboard",
        ],
    },
    "identity_account": {
        "conservative": [
            "document-extraction", "field-completeness-check", "rule-engine",
            "human-approval", "audit-log",
        ],
        "balanced": [
            "document-extraction", "field-completeness-check", "rule-engine",
            "data-masking", "human-approval", "audit-log", "feishu-notification",
        ],
        "innovative": [
            "document-extraction", "field-completeness-check", "rule-engine",
            "data-masking", "human-approval", "audit-log", "feishu-notification",
            "local-model", "feedback-loop",
        ],
    },
    "dispute_investigation": {
        "conservative": [
            "document-extraction", "field-completeness-check", "rule-engine",
            "human-approval", "audit-log",
        ],
        "balanced": [
            "document-extraction", "enterprise-rag", "field-completeness-check",
            "rule-engine", "ticket-routing", "human-approval", "audit-log",
        ],
        "innovative": [
            "document-extraction", "enterprise-rag", "field-completeness-check",
            "rule-engine", "ticket-routing", "human-approval", "audit-log",
            "quality-dashboard", "feedback-loop",
        ],
    },
    "customer_service": {
        "conservative": [
            "enterprise-rag", "ticket-routing", "human-approval",
            "feishu-notification", "audit-log",
        ],
        "balanced": [
            "enterprise-rag", "anomaly-classification", "ticket-routing",
            "human-approval", "feishu-notification", "audit-log", "feedback-loop",
        ],
        "innovative": [
            "enterprise-rag", "anomaly-classification", "ticket-routing",
            "human-approval", "feishu-notification", "audit-log",
            "feedback-loop", "quality-dashboard", "process-monitoring",
        ],
    },
    "procurement_exception": {
        "conservative": [
            "document-extraction", "field-completeness-check", "rule-engine",
            "human-approval", "feishu-notification", "audit-log",
        ],
        "balanced": [
            "document-extraction", "field-completeness-check", "rule-engine",
            "anomaly-classification", "risk-scoring", "ticket-routing",
            "human-approval", "feishu-notification", "audit-log",
        ],
        "innovative": [
            "data-masking", "document-extraction", "enterprise-rag",
            "field-completeness-check", "rule-engine", "anomaly-classification",
            "risk-scoring", "local-model", "human-approval", "feishu-notification",
            "process-monitoring", "quality-dashboard", "audit-log",
        ],
    },
    "generic": {
        "conservative": [
            "field-completeness-check", "rule-engine", "human-approval", "audit-log",
        ],
        "balanced": [
            "field-completeness-check", "rule-engine", "ticket-routing",
            "human-approval", "feishu-notification", "audit-log",
        ],
        "innovative": [
            "field-completeness-check", "rule-engine", "ticket-routing",
            "human-approval", "feishu-notification", "audit-log",
            "process-monitoring", "quality-dashboard", "feedback-loop",
        ],
    },
}


def get_scenario_components(scenario: str, plan_type: str) -> list[str]:
    """获取场景和策略对应的组件 ID 列表。"""
    return list(_SCENARIO_COMPONENTS.get(scenario, _SCENARIO_COMPONENTS["generic"]).get(
        plan_type, _SCENARIO_COMPONENTS["generic"][plan_type]
    ))


# ---------------------------------------------------------------------------
# 场景化节点名称
# ---------------------------------------------------------------------------

_NODE_NAMES: dict[str, dict[str, str]] = {
    "incident_response": {
        "anomaly-classification": "故障类型分类",
        "ticket-routing": "工单创建与路由",
        "process-monitoring": "故障状态监控",
        "human-approval": "人工确认处置方案",
        "feishu-notification": "状态通知",
        "audit-log": "审计记录",
        "quality-dashboard": "故障质量看板",
        "feedback-loop": "故障反馈回流",
        "enterprise-rag": "知识库检索",
        "document-extraction": "事件信息提取",
        "field-completeness-check": "事件信息完整性检查",
        "rule-engine": "故障规则校验",
        "risk-scoring": "影响范围评估",
        "data-masking": "敏感信息脱敏",
        "local-model": "本地模型推理",
    },
    "fraud_risk": {
        "anomaly-classification": "异常交易分类",
        "risk-scoring": "风险评分",
        "rule-engine": "风险规则校验",
        "human-approval": "人工复核高风险交易",
        "audit-log": "审计记录",
        "data-masking": "敏感信息脱敏",
        "process-monitoring": "风险监控",
        "local-model": "本地模型推理",
        "quality-dashboard": "风险质量看板",
        "ticket-routing": "工单路由",
        "feishu-notification": "客户通知",
        "document-extraction": "交易记录提取",
        "field-completeness-check": "交易信息完整性检查",
        "enterprise-rag": "知识库检索",
        "feedback-loop": "反馈回流",
    },
    "identity_account": {
        "document-extraction": "身份材料提取",
        "field-completeness-check": "资料完整性检查",
        "rule-engine": "身份规则校验",
        "data-masking": "敏感信息脱敏",
        "human-approval": "人工确认身份变更",
        "audit-log": "审计记录",
        "feishu-notification": "变更结果通知",
        "local-model": "本地模型推理",
        "feedback-loop": "反馈回流",
        "anomaly-classification": "异常分类",
        "risk-scoring": "风险评分",
        "ticket-routing": "工单路由",
        "process-monitoring": "流程监控",
        "quality-dashboard": "质量看板",
        "enterprise-rag": "知识库检索",
    },
    "dispute_investigation": {
        "document-extraction": "争议材料提取",
        "enterprise-rag": "规则和历史记录检索",
        "field-completeness-check": "争议信息完整性检查",
        "rule-engine": "争议规则校验",
        "ticket-routing": "调查工单创建",
        "human-approval": "人工复核调查结论",
        "audit-log": "审计记录",
        "quality-dashboard": "调查质量看板",
        "feedback-loop": "反馈回流",
        "anomaly-classification": "异常分类",
        "risk-scoring": "风险评分",
        "data-masking": "敏感信息脱敏",
        "feishu-notification": "通知",
        "local-model": "本地模型推理",
        "process-monitoring": "流程监控",
    },
    "customer_service": {
        "enterprise-rag": "知识库检索",
        "anomaly-classification": "异常分类",
        "ticket-routing": "工单创建与路由",
        "human-approval": "人工确认处理方案",
        "feishu-notification": "客户通知",
        "audit-log": "审计记录",
        "feedback-loop": "反馈回流",
        "quality-dashboard": "服务质量看板",
        "process-monitoring": "服务流程监控",
        "document-extraction": "信息提取",
        "field-completeness-check": "信息完整性检查",
        "rule-engine": "规则校验",
        "risk-scoring": "风险评分",
        "data-masking": "敏感信息脱敏",
        "local-model": "本地模型推理",
    },
    "procurement_exception": {
        "document-extraction": "单据智能抽取",
        "field-completeness-check": "字段完整性检查",
        "rule-engine": "业务规则引擎",
        "anomaly-classification": "异常分类",
        "risk-scoring": "风险评分",
        "ticket-routing": "工单路由",
        "human-approval": "人工审批",
        "feishu-notification": "飞书通知",
        "audit-log": "审计日志",
        "data-masking": "数据脱敏",
        "enterprise-rag": "企业知识检索",
        "local-model": "本地模型推理",
        "process-monitoring": "流程监控",
        "quality-dashboard": "质量看板",
        "feedback-loop": "反馈闭环",
    },
    "generic": {
        "document-extraction": "信息提取",
        "field-completeness-check": "信息完整性检查",
        "rule-engine": "规则校验",
        "anomaly-classification": "异常分类",
        "risk-scoring": "风险评分",
        "ticket-routing": "工单路由",
        "human-approval": "人工审批",
        "feishu-notification": "通知",
        "audit-log": "审计记录",
        "data-masking": "数据脱敏",
        "enterprise-rag": "知识检索",
        "local-model": "本地模型推理",
        "process-monitoring": "流程监控",
        "quality-dashboard": "质量看板",
        "feedback-loop": "反馈闭环",
    },
}


def get_node_name(scenario: str, component_id: str, fallback: str) -> str:
    """获取场景化的节点名称。"""
    names = _NODE_NAMES.get(scenario, _NODE_NAMES["generic"])
    return names.get(component_id, fallback)


# ---------------------------------------------------------------------------
# 场景化审批理由
# ---------------------------------------------------------------------------

_GATE_REASONS: dict[str, str] = {
    "incident_response": "大范围服务故障的处置方案需要运维负责人确认后继续。",
    "fraud_risk": "高风险或疑似未授权交易需要人工复核后执行处置。",
    "identity_account": "账户身份资料变更需要人工确认申请人身份。",
    "dispute_investigation": "争议调查结论需要人工复核后才能提交。",
    "customer_service": "客户服务处理方案需要人工确认后执行。",
    "procurement_exception": "高风险采购异常需要人工审批后继续。",
    "generic": "关键操作需要人工审批后继续。",
}


def get_gate_reason(scenario: str, process: ProcessSpec) -> str:
    """获取场景化的审批理由。如果输入含 approval 约束则使用约束 statement。"""
    for c in process.constraints:
        if c.type == "approval" and c.hard:
            return c.statement
    return _GATE_REASONS.get(scenario, _GATE_REASONS["generic"])


# ---------------------------------------------------------------------------
# 场景化摘要
# ---------------------------------------------------------------------------

_SUMMARIES: dict[str, dict[str, str]] = {
    "incident_response": {
        "conservative": "优先快速恢复和人工可控，自动化范围最小，保留人工确认和审计环节。",
        "balanced": "在故障恢复速度、自动化程度和风险之间综合权衡，保留关键人工确认。",
        "innovative": "自动化和监控程度最高，引入知识检索和反馈回流，仍保留人工确认。",
    },
    "fraud_risk": {
        "conservative": "优先风险可控和人工复核，自动化范围最小。",
        "balanced": "在风险识别、自动化和人工复核之间综合权衡。",
        "innovative": "自动化和风险监控程度最高，引入本地模型和质量看板，仍保留人工复核。",
    },
    "identity_account": {
        "conservative": "优先身份安全和人工确认，自动化范围最小。",
        "balanced": "在身份核验效率、数据安全和人工确认之间综合权衡。",
        "innovative": "自动化和身份核验程度最高，引入本地模型和反馈回流，仍保留人工确认。",
    },
    "dispute_investigation": {
        "conservative": "优先调查准确性和人工复核，自动化范围最小。",
        "balanced": "在调查效率、规则覆盖和人工复核之间综合权衡。",
        "innovative": "自动化和调查质量监控程度最高，引入质量看板和反馈回流，仍保留人工复核。",
    },
    "customer_service": {
        "conservative": "优先客户体验和人工确认，自动化范围最小。",
        "balanced": "在响应速度、自动化和人工确认之间综合权衡。",
        "innovative": "自动化和监控程度最高，引入质量看板和流程监控，仍保留人工确认。",
    },
    "procurement_exception": {
        "conservative": "优先低风险和人工可控，自动化范围最小，保留人工审批和审计环节。",
        "balanced": "风险、成本和自动化程度平衡，引入异常分类、风险评分和工单路由，保留高风险人工审批。",
        "innovative": "自动化和流程重构程度最高，引入知识检索、本地模型、流程监控和质量看板，仍保留人工审批。",
    },
    "generic": {
        "conservative": "优先低风险和人工可控，自动化范围最小。",
        "balanced": "在自动化程度、实施成本和风险之间综合权衡。",
        "innovative": "自动化和扩展能力更强，但实施复杂度更高。",
    },
}


def get_summary(scenario: str, plan_type: str) -> str:
    """获取场景化的方案摘要。"""
    return _SUMMARIES.get(scenario, _SUMMARIES["generic"]).get(
        plan_type, _SUMMARIES["generic"][plan_type]
    )


# ---------------------------------------------------------------------------
# 场景化实施步骤
# ---------------------------------------------------------------------------


def get_implementation_steps(scenario: str, process: ProcessSpec, plan_type: str) -> list[str]:
    """根据场景和 ProcessSpec 真实字段生成实施步骤。"""
    data_str = "、".join(process.available_data[:4]) if process.available_data else "业务数据"
    systems_str = "、".join(process.existing_systems[:3]) if process.existing_systems else "现有系统"
    goal = process.business_goal
    industry = process.industry

    if plan_type == "conservative":
        return _conservative_steps(scenario, data_str, systems_str, goal, industry)
    elif plan_type == "balanced":
        return _balanced_steps(scenario, data_str, systems_str, goal, industry)
    else:
        return _innovative_steps(scenario, data_str, systems_str, goal, industry)


def _conservative_steps(scenario: str, data: str, systems: str, goal: str, industry: str) -> list[str]:
    base = {
        "incident_response": [
            f"接入{data}",
            f"对接{systems}获取告警和工单数据",
            "配置故障分类规则和影响评估条件",
            "设置运维人工确认节点",
            "部署状态通知和审计记录",
        ],
        "fraud_risk": [
            f"接入{data}",
            f"对接{systems}获取交易和案件数据",
            "配置异常交易规则和风险评分阈值",
            "设置高风险人工复核流程",
            "部署审计记录",
        ],
        "identity_account": [
            f"接入{data}",
            f"对接{systems}",
            "配置身份材料提取和字段校验规则",
            "设置人工确认身份变更流程",
            "部署审计记录",
        ],
        "dispute_investigation": [
            f"接入{data}",
            f"对接{systems}",
            "配置争议材料提取和规则校验",
            "设置人工复核调查结论流程",
            "部署审计记录",
        ],
        "customer_service": [
            f"接入{data}",
            f"对接{systems}",
            "配置知识检索和工单路由规则",
            "设置人工确认处理方案",
            "部署通知和审计记录",
        ],
        "procurement_exception": [
            f"接入{data}",
            f"对接{systems}",
            "配置单据抽取和字段完整性检查规则",
            "配置业务规则引擎校验条件",
            "设置人工审批流程",
            "部署审计日志",
        ],
        "generic": [
            f"接入{data}",
            f"对接{systems}",
            "配置信息校验规则",
            "设置人工审批流程",
            "部署审计记录",
        ],
    }
    return base.get(scenario, base["generic"])


def _balanced_steps(scenario: str, data: str, systems: str, goal: str, industry: str) -> list[str]:
    base = {
        "incident_response": [
            f"接入{data}",
            f"对接{systems}获取告警和工单数据",
            "配置故障分类规则和影响范围评估",
            "部署工单自动路由",
            "设置运维人工确认节点",
            "配置状态通知和审计记录",
            "部署故障质量看板",
        ],
        "fraud_risk": [
            f"接入{data}",
            f"对接{systems}获取交易和案件数据",
            "配置异常交易规则和风险评分模型",
            "部署敏感信息脱敏",
            "设置高风险人工复核流程",
            "配置风险监控和审计记录",
        ],
        "identity_account": [
            f"接入{data}",
            f"对接{systems}",
            "配置身份材料提取和字段校验规则",
            "部署敏感信息脱敏",
            "设置人工确认身份变更流程",
            "配置变更通知和审计记录",
        ],
        "dispute_investigation": [
            f"接入{data}",
            f"对接{systems}",
            "配置争议材料提取和规则校验",
            "接入规则和历史记录检索",
            "创建调查工单并路由",
            "设置人工复核调查结论流程",
            "部署审计记录",
        ],
        "customer_service": [
            f"接入{data}",
            f"对接{systems}",
            "配置知识检索和异常分类规则",
            "部署工单自动路由",
            "设置人工确认处理方案",
            "配置客户通知和审计记录",
            "部署反馈回流",
        ],
        "procurement_exception": [
            f"接入{data}",
            f"对接{systems}",
            "配置单据抽取和字段完整性检查规则",
            "部署异常分类和风险评分模型",
            "配置低风险工单自动路由",
            "配置高风险人工审批流程",
            "接入通知和审计日志",
        ],
        "generic": [
            f"接入{data}",
            f"对接{systems}",
            "配置信息校验和规则引擎",
            "部署工单自动路由",
            "设置人工审批流程",
            "配置通知和审计记录",
        ],
    }
    return base.get(scenario, base["generic"])


def _innovative_steps(scenario: str, data: str, systems: str, goal: str, industry: str) -> list[str]:
    base = {
        "incident_response": [
            f"接入{data}",
            f"对接{systems}获取告警和工单数据",
            "配置故障分类规则和影响范围评估",
            "接入知识库增强故障处置依据",
            "部署工单自动路由和故障监控",
            "设置运维人工确认节点",
            "部署故障质量看板和反馈回流",
            "部署审计记录",
        ],
        "fraud_risk": [
            f"接入{data}",
            f"对接{systems}获取交易和案件数据",
            "配置异常交易规则和风险评分模型",
            "部署敏感信息脱敏",
            "部署本地模型满足数据安全要求",
            "设置高风险人工复核流程",
            "配置风险监控和质量看板",
            "部署审计记录",
        ],
        "identity_account": [
            f"接入{data}",
            f"对接{systems}",
            "配置身份材料提取和字段校验规则",
            "部署敏感信息脱敏",
            "部署本地模型满足数据安全要求",
            "设置人工确认身份变更流程",
            "配置变更通知和审计记录",
            "部署反馈回流",
        ],
        "dispute_investigation": [
            f"接入{data}",
            f"对接{systems}",
            "配置争议材料提取和规则校验",
            "接入规则和历史记录检索",
            "部署调查工单自动路由",
            "设置人工复核调查结论流程",
            "部署调查质量看板和反馈回流",
            "部署审计记录",
        ],
        "customer_service": [
            f"接入{data}",
            f"对接{systems}",
            "配置知识检索和异常分类规则",
            "部署工单自动路由和服务流程监控",
            "设置人工确认处理方案",
            "配置客户通知和审计记录",
            "部署服务质量看板和反馈回流",
        ],
        "procurement_exception": [
            f"接入{data}",
            f"对接{systems}",
            "部署数据脱敏组件保护敏感字段",
            "配置单据抽取和字段完整性检查规则",
            "接入企业知识库增强异常处理依据",
            "配置规则引擎和风险评分联合判断",
            "部署本地模型满足数据安全要求",
            "配置低风险自动处理和高风险人工审批",
            "接入流程监控和质量看板",
            "部署审计日志和反馈回流",
        ],
        "generic": [
            f"接入{data}",
            f"对接{systems}",
            "配置信息校验和规则引擎",
            "部署工单自动路由和流程监控",
            "设置人工审批流程",
            "配置通知和审计记录",
            "部署质量看板和反馈回流",
        ],
    }
    return base.get(scenario, base["generic"])


# ---------------------------------------------------------------------------
# 场景化 required_data
# ---------------------------------------------------------------------------

# 非采购场景的 required_data 映射
# procurement_exception 返回 None 表示使用 capabilities.json 原始数据
_REQUIRED_DATA: dict[str, dict[str, list[str]]] = {
    "incident_response": {
        "anomaly-classification": ["故障事件记录", "网络告警记录", "客服工单记录"],
        "ticket-routing": ["故障事件记录", "工单处理人信息"],
        "process-monitoring": ["流程状态", "节点执行记录", "网络告警状态"],
        "human-approval": ["故障影响评估", "处置方案", "审批记录"],
        "feishu-notification": ["通知接收人", "故障状态信息"],
        "audit-log": ["操作记录", "执行者信息"],
        "quality-dashboard": ["故障指标数据", "处理统计"],
        "feedback-loop": ["处理结果", "用户反馈"],
        "enterprise-rag": ["运维知识库", "历史故障案例"],
        "document-extraction": ["故障报告", "事件描述"],
        "field-completeness-check": ["事件信息字段", "故障描述"],
        "rule-engine": ["故障规则", "事件数据"],
        "risk-scoring": ["影响范围", "故障严重度"],
        "data-masking": ["客户联系方式", "敏感配置信息"],
        "local-model": ["模型权重", "推理输入数据"],
    },
    "fraud_risk": {
        "anomaly-classification": ["交易记录", "客户申诉记录"],
        "risk-scoring": ["交易记录", "风险特征", "历史风险记录"],
        "rule-engine": ["风险规则", "交易数据"],
        "human-approval": ["风险评分结果", "异常交易信息", "复核记录"],
        "audit-log": ["操作记录", "执行者信息"],
        "data-masking": ["客户敏感信息", "账户或交易数据"],
        "process-monitoring": ["风险监控状态", "交易异常告警"],
        "local-model": ["模型权重", "推理输入数据"],
        "quality-dashboard": ["风险指标数据", "处置统计"],
        "ticket-routing": ["风险事件记录", "处理人信息"],
        "feishu-notification": ["通知接收人", "风险处置结果"],
        "document-extraction": ["交易凭证", "申诉材料"],
        "field-completeness-check": ["交易字段", "案件信息"],
        "enterprise-rag": ["反欺诈规则", "历史案件"],
        "feedback-loop": ["处置结果", "客户反馈"],
    },
    "identity_account": {
        "document-extraction": ["身份证明材料", "资料变更申请"],
        "field-completeness-check": ["身份材料", "申请字段"],
        "rule-engine": ["身份规则", "申请数据"],
        "data-masking": ["客户身份信息", "敏感个人信息"],
        "human-approval": ["身份核验结果", "资料变更申请", "审批记录"],
        "audit-log": ["操作记录", "执行者信息"],
        "feishu-notification": ["通知接收人", "变更结果"],
        "local-model": ["模型权重", "推理输入数据"],
        "feedback-loop": ["处理结果", "客户反馈"],
        "anomaly-classification": ["申请记录", "异常标记"],
        "risk-scoring": ["申请风险特征", "历史记录"],
        "ticket-routing": ["申请记录", "处理人信息"],
        "process-monitoring": ["流程状态", "申请处理记录"],
        "quality-dashboard": ["处理指标", "申请统计"],
        "enterprise-rag": ["身份核验规则", "历史案例"],
    },
    "dispute_investigation": {
        "document-extraction": ["争议申请材料", "征信或调查记录"],
        "enterprise-rag": ["业务规则", "历史调查记录", "处理政策"],
        "field-completeness-check": ["争议字段", "申请信息"],
        "rule-engine": ["争议规则", "调查数据"],
        "ticket-routing": ["争议记录", "调查人员信息"],
        "human-approval": ["调查结论", "争议材料", "人工复核记录"],
        "audit-log": ["操作记录", "执行者信息"],
        "quality-dashboard": ["调查指标", "争议处理统计"],
        "feedback-loop": ["处理结果", "消费者反馈"],
        "anomaly-classification": ["争议记录", "异常分类"],
        "risk-scoring": ["争议风险", "历史记录"],
        "data-masking": ["消费者敏感信息", "征信数据"],
        "feishu-notification": ["通知接收人", "调查结果"],
        "local-model": ["模型权重", "推理输入数据"],
        "process-monitoring": ["调查流程状态", "案件记录"],
    },
    "customer_service": {
        "enterprise-rag": ["客服知识库", "客户对话记录", "历史工单"],
        "anomaly-classification": ["客户问题记录", "异常分类"],
        "ticket-routing": ["客户问题记录", "工单分类", "处理人信息"],
        "human-approval": ["处理方案", "客户问题记录", "审批记录"],
        "feishu-notification": ["通知接收人", "处理结果"],
        "audit-log": ["操作记录", "执行者信息"],
        "feedback-loop": ["处理结果", "客户满意度"],
        "quality-dashboard": ["服务指标", "工单统计"],
        "process-monitoring": ["服务流程状态", "工单记录"],
        "document-extraction": ["客户对话记录", "问题描述"],
        "field-completeness-check": ["问题字段", "客户信息"],
        "rule-engine": ["服务规则", "问题数据"],
        "risk-scoring": ["问题风险", "客户历史"],
        "data-masking": ["客户个人信息", "联系方式"],
        "local-model": ["模型权重", "推理输入数据"],
    },
    "generic": {
        "document-extraction": ["业务记录", "事件描述"],
        "field-completeness-check": ["业务字段", "记录信息"],
        "rule-engine": ["业务规则", "记录数据"],
        "anomaly-classification": ["业务记录", "异常标记"],
        "risk-scoring": ["风险特征", "历史记录"],
        "ticket-routing": ["业务记录", "处理人信息"],
        "human-approval": ["处理方案", "审批记录"],
        "feishu-notification": ["通知接收人", "处理结果"],
        "audit-log": ["操作记录", "执行者信息"],
        "data-masking": ["敏感信息", "业务数据"],
        "enterprise-rag": ["业务知识库", "历史记录"],
        "local-model": ["模型权重", "推理输入数据"],
        "process-monitoring": ["流程状态", "执行记录"],
        "quality-dashboard": ["指标数据", "流程统计"],
        "feedback-loop": ["处理结果", "用户反馈"],
    },
}


def get_required_data(scenario: str, component_id: str, original: list[str]) -> list[str]:
    """获取场景化的 required_data。

    Args:
        scenario: 场景类型
        component_id: 组件 ID
        original: capabilities.json 中的原始 required_data

    Returns:
        场景化的 required_data 列表。procurement_exception 返回原始数据。
    """
    if scenario == "procurement_exception":
        return list(original)
    mapping = _REQUIRED_DATA.get(scenario, _REQUIRED_DATA["generic"])
    return list(mapping.get(component_id, _REQUIRED_DATA["generic"].get(component_id, ["业务数据"])))
