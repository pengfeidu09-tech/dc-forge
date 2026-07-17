# Solution Agent 真实 API 配置说明

## 1. 复制 .env.example

```bash
cp .env.example .env
```

## 2. 填写环境变量

编辑 `.env` 文件：

```
LLM_API_KEY=sk-your-actual-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

- `LLM_API_KEY`：你的 API 密钥
- `LLM_BASE_URL`：OpenAI 兼容 API 的基地址（如 `https://api.openai.com/v1`、`https://api.deepseek.com/v1` 等）
- `LLM_MODEL`：模型名称（如 `gpt-4o-mini`、`deepseek-chat` 等）

## 3. 在 PowerShell 临时设置环境变量

如果不想使用 `.env` 文件，可以在 PowerShell 中临时设置：

```powershell
$env:LLM_API_KEY = "sk-your-key"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_MODEL = "gpt-4o-mini"
```

在 Git Bash 中：

```bash
export LLM_API_KEY="sk-your-key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
```

## 4. 运行冒烟测试

```bash
.venv/Scripts/python.exe scripts/smoke_solution_agent.py
```

## 5. 如何判断模型确实调用了工具

查看输出中的"工具调用"部分：

- `compile` 意图应显示 `compile_solution (success)`
- `recompile` 意图应显示 `recompile_solution (success)` 和 `added: ['data-masking', 'local-model']`
- 如果显示"LLM 不可用，已回退到确定性编译"，说明模型 API 未成功调用

## 6. 如何避免泄露 Key

- `.env` 已被 `.gitignore` 忽略，不会被提交
- 不要在代码、测试、日志或聊天中粘贴 API Key
- 错误信息中不包含 API Key（Provider 已做脱敏处理）
- 使用完毕后清除环境变量：

```powershell
Remove-Item Env:LLM_API_KEY
Remove-Item Env:LLM_BASE_URL
Remove-Item Env:LLM_MODEL
```

## 7. 如何检查真实 API 费用

- 登录你的 API 提供商后台查看用量
- 冒烟测试约消耗 2 次 API 调用（compile + recompile）
- 每次调用约 500-1000 tokens（系统提示 + 用户消息 + 响应）
- 使用 `gpt-4o-mini` 等经济模型可降低成本
