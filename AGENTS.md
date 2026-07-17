# DCForge Agent 规则

## 成员 B 主要修改范围

- `backend/app/solution/`
- `data/capabilities.json`
- `tests/solution/`
- `spec/`

## 未经团队确认禁止修改

- `backend/app/contracts/`
- `backend/app/process/`
- `backend/app/runtime/`
- `data/fixtures/`
- `frontend/`

## 业务任务流程

所有业务任务必须：

1. 先写 spec；
2. 先写失败测试；
3. 再写最小实现；
4. 运行新测试；
5. 运行 `tests/test_contracts.py`；
6. 检查 `git diff`；
7. 不把重构、修 bug 和新功能混在一起。

## 诚实性要求

不得把模拟指标描述成真实业务成果。
