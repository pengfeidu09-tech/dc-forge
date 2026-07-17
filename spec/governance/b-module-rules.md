# B 模块规则

## 输入输出

- B 模块输入为 `ProcessSpec`（来自成员 A）。
- B 模块最终输出为 `SolutionBundle`（供成员 C 消费）。

## 检索策略

- 第一阶段检索采用确定性规则（关键词 + 字段匹配评分）。
- 后续可替换为 Embedding、Hybrid Search 和 Rerank。

## 接口边界

- 外部接口不能依赖 A 模块的 Prompt、函数和内部变量。
- B 模块只读取 `ProcessSpec` 公共合同对象。

## 领域模型

- `CapabilityCapsule` 是 B 模块内部领域模型，不放入公共 `contracts/`。
- 公共合同变更必须单独提出，不得在业务任务中顺手修改。
