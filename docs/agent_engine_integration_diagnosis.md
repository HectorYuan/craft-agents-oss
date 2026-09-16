# agent-engine 集成联调诊断报告（2026-09-15 真机）

> 本轮真机联调在 vendor fork 侧修复两处后 LLM 链路已打通（mermaid 渲染截图验证）。
> 本文记录根因链与主仓库侧的治本建议，供 zenskill 主仓库会话执行。

## 已修复（vendor fork，commits 2d31a4ee / 7aef3640）

### Bug 1：spawn 未注入 OPENAI_API_KEY
- 症状：发消息秒报 `[unknown] Error: Agent error`；agent-engine 会话 JSONL
  记录 `errorMessage: 'missing API key: set OPENAI_API_KEY'`
- 根因：`zenskill-agent.ts spawnSubprocess` 只注入 `DEEPSEEK_API_KEY`；
  engine 侧 deepseek provider（`_REGISTRY` 条目 `api_key_env: 'OPENAI_API_KEY'`）
  走 openai-completions 协议，凭据解析读的是 `OPENAI_API_KEY`
- 修复：env 注入时兜底 `OPENAI_API_KEY`（不覆盖已存在值）

### Bug 2：`--model` 带 craft 前缀导致请求打到 api.openai.com
- 症状：修复 Bug 1 后消息从"秒报错"变为"无限挂起"（RPC `message_start`
  后 60s+ 无事件；engine jsonl 无 assistant 落盘）
- 根因链（`resolve_model` 实测证实）：
  1. craft 传 `--model pi/deepseek-v4-flash`（`pi` 为 craft 侧 providerType）
  2. `_provider_for_model_name`：`pi` 不在注册表（deepseek/anthropic/openai/
     volc/qwen/gemini/mimo/ollama）→ `get_model_info('pi/...')` 也不识别
  3. 走"未知模型名"兜底：`provider=openai`、`base_url=api.openai.com/v1`、
     id 原样带前缀
  4. DeepSeek key 打 OpenAI 官方 → 401 非 SSE 响应体 → `feed_line` 解析
     不出事件 → 挂到 `sock_read 600s`
- 修复：spawn 时剥离宿主前缀（`/^[a-z]+\//i`）；
  `resolve_model('deepseek-v4-flash')` 实测 → provider=deepseek、
  base_url=api.deepseek.com/v1 ✓
- 实测结果：DeepSeek 流式返回，UI 中 mermaid 图渲染成功

## 主仓库侧治本建议（未执行，主仓库禁改范围）

`zenskill/runtime/agent/providers/__init__.py`：

1. **`_provider_for_model_name`：未知 provider 前缀时剥前缀再查模型目录**
   ```python
   if "/" in name:
       provider = name.split("/", 1)[0].strip().lower()
       if provider in _REGISTRY:
           return provider
       # 宿主自定义前缀（如 craft 的 'pi/'）：剥前缀用模型部分查目录
       stripped = name.split("/", 1)[1]
       info = get_model_info(stripped)   # 'deepseek-v4-flash' → deepseek
       ...
   ```
   防御所有宿主以自定义前缀接入 engine 的场景（craft 只是其一）。

2. **openai_completions_stream：非 SSE 响应体不该被静默吞掉**
   `retry_post` 返回 4xx/非 event-stream 响应时应读取 body 前 N 字节
   并编码为 StreamError（如 `upstream 401: {...}`），而不是进入
   `feed_line` 无限等待 `sock_read`（默认 600s）。本次"挂起 10 分钟"
   若有该报错会秒级暴露真实原因（401 model not found）。

3. **模型名前缀约定文档化**：serve `--model` 的可接受格式
   （`provider/model` 中 provider 必须在 `_REGISTRY`；宿主前缀需宿主剥离）
   写入 `docs/runtime_pi_reference*.md`。

## 复现与验证手段（本次实际使用）

- engine 侧真相：`~/.zenskill/agent/sessions/<id>.jsonl` 的
  `data.message.errorMessage`（UI 错误卡片只显示 `[unknown] Error: Agent error`）
- 主进程日志：需 `CRAFT_IS_PACKAGED=false`（`--debug` argv 会撞 Node
  DEP0062 拒启），文件在 `~/.config/@craft-agent/electron/logs/main.log`
- resolve_model 行为验证：`.venv/bin/python -c "from zenskill.runtime.agent.providers import resolve_model; m = resolve_model('pi/deepseek-v4-flash'); print(m.provider, m.base_url, m.id, bool(m.api_key))"`
- 手动驱动 engine：spawn `zenskill agent-engine serve` 后向 stdin 写
  `{"type":"prompt","id":"t1","message":"..."}`，观察 stdout 事件流

## 其他联调发现（低优先级）

- `Model refresh [pi-api-key]: provider fetch failed: Model discovery not
  implemented for provider: zenskill`——模型刷新走 craft 侧 providerType
  ('zenskill') 查 fetcher 未命中，降级用 stale models（无害，但可考虑在
  craft 侧把 piAuthProvider 透传给 fetcher 路由）
- 测试环境备注：headless server smoke 依赖 `~/.craft-agent/.server.lock`
  释放——真机实例未退出时全量测试会假失败（单实例锁设计使然）
