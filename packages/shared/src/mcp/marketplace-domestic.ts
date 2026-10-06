/**
 * 国产 MCP Marketplace（首批 10 个预置条目）
 *
 * 2026-10-06 提出（zenlearning-integration-plan.md 上下文）。
 * 与 zenskill/runtime/agent/providers _REGISTRY 命名对齐（volc=qwen=mimo=moonshot=minimax=glm）。
 *
 * 加新条目时按 tier 标注：
 *   A-tier：文档齐、探活可证 → GUI Marketplace 直接挂
 *   B-tier：文档不全 → 仅占位条目，warn 用户
 *   C-tier：待官方发布 → 仅占位，不实接
 */

export type McpTransport = 'stdio' | 'sse' | 'http'
export type McpRisk = 'safe' | 'warn' | 'danger'

export interface McpMarketplaceEntry {
  /** 唯一 id（DOMESTIC_MCP_MARKETPLACE key） */
  id: string
  /** 关联 engine provider name（与 zenskill/runtime/agent/providers _REGISTRY 对齐） */
  provider: string
  /** GUI 显示名 */
  displayName: string
  /** 用途描述 */
  description: string
  /** 传输方式 */
  transport: McpTransport
  /** HTTP/SSE endpoint（transport=http|sse 时必填） */
  endpoint?: string
  /** stdio 命令（transport=stdio 时必填） */
  command?: string
  /** stdio 参数 */
  args?: string[]
  /** 需要的 key 环境变量列表（注入到 server 进程 env） */
  envVars: { name: string; description: string; required: boolean }[]
  /** 厂商主页 */
  homepage: string
  /** MCP 文档 URL */
  docsUrl: string
  /** 标签（GUI 过滤） */
  tags: string[]
  /** 安全分级 */
  risk: McpRisk
  /** tier：A=可接、B=仅占位、C=待发布 */
  tier: 'A' | 'B' | 'C'
}

/**
 * 国产 MCP 首批预置（10 个）。
 * 探活通过后才激活；不通不挂载（承诺见 docs/DOMESTIC_PROVIDER_AND_MCP_PLAN.md §附录 B）。
 */
export const DOMESTIC_MCP_MARKETPLACE: McpMarketplaceEntry[] = [
  // ─── A-tier：文档齐、探活可证 ───
  {
    id: 'glm-mcp',
    provider: 'glm',
    displayName: '智谱 GLM 工具集',
    description: '联网搜索 / 代码执行 / 知识库 / GLM 长上下文调用',
    transport: 'sse',
    endpoint: 'https://open.bigmodel.cn/api/mcp',
    envVars: [
      { name: 'GLM_API_KEY', description: '智谱 API Key', required: true },
    ],
    homepage: 'https://open.bigmodel.cn',
    docsUrl: 'https://open.bigmodel.cn/dev/howuse/mcp',
    tags: ['搜索', '代码', '知识库', 'GLM'],
    risk: 'safe',
    tier: 'A',
  },
  {
    id: 'modelscope-mcp',
    provider: 'qwen',
    displayName: 'ModelScope 模型广场',
    description: '阿里 ModelScope MCP：模型检索 / 多模型推理调用',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@modelscope/mcp-server'],
    envVars: [
      { name: 'MODELSCOPE_API_KEY', description: 'ModelScope Access Token', required: true },
    ],
    homepage: 'https://www.modelscope.cn',
    docsUrl: 'https://www.modelscope.cn/docs/mcp',
    tags: ['模型广场', '推理', '检索'],
    risk: 'safe',
    tier: 'A',
  },
  {
    id: 'bailian-mcp',
    provider: 'qwen',
    displayName: '阿里云百炼',
    description: '阿里云百炼 MCP：应用编排 / 智能体调用',
    transport: 'sse',
    endpoint: 'https://dashscope.aliyuncs.com/mcp',
    envVars: [
      { name: 'DASHSCOPE_API_KEY', description: 'DashScope API Key', required: true },
    ],
    homepage: 'https://bailian.console.aliyun.com',
    docsUrl: 'https://help.aliyun.com/zh/model-studio/mcp',
    tags: ['应用编排', '智能体', '百炼'],
    risk: 'safe',
    tier: 'A',
  },
  {
    id: 'kimi-mcp',
    provider: 'moonshot',
    displayName: 'Kimi 长文档解析',
    description: 'Moonshot MCP：长文档解析（>200k tokens）',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@moonshotai/kimi-mcp'],
    envVars: [
      { name: 'MOONSHOT_API_KEY', description: 'Moonshot API Key', required: true },
    ],
    homepage: 'https://platform.moonshot.cn',
    docsUrl: 'https://platform.moonshot.cn/docs/mcp',
    tags: ['文档', '长上下文', 'Kimi'],
    risk: 'safe',
    tier: 'A',
  },
  {
    id: 'volc-mcp',
    provider: 'volc',
    displayName: '火山方舟（豆包）',
    description: '火山方舟 MCP：豆包模型推理 / 多模态工具',
    transport: 'sse',
    endpoint: 'https://ark.cn-beijing.volces.com/api/v3/mcp',
    envVars: [
      { name: 'ARK_API_KEY', description: '火山方舟 API Key', required: true },
    ],
    homepage: 'https://www.volcengine.com/product/ark',
    docsUrl: 'https://www.volcengine.com/docs/82379/mcp',
    tags: ['豆包', '多模态', '推理'],
    risk: 'safe',
    tier: 'A',
  },

  // ─── B-tier：文档不全，先暴露占位条目 ───
  {
    id: 'coze-mcp',
    provider: 'volc',
    displayName: '字节扣子（占位）',
    description: '字节扣子 MCP：Bot / 工作流调用（文档待完善）',
    transport: 'sse',
    endpoint: 'https://api.coze.cn/mcp',
    envVars: [
      { name: 'COZE_PAT', description: '扣子个人访问令牌', required: true },
    ],
    homepage: 'https://www.coze.cn',
    docsUrl: 'https://www.coze.cn/docs/mcp',
    tags: ['Bot', '工作流', '扣子'],
    risk: 'warn',
    tier: 'B',
  },
  {
    id: 'qianfan-mcp',
    provider: 'glm',
    displayName: '百度千帆（占位）',
    description: '百度千帆 MCP：知识库 / 应用（文档待完善）',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@baidu/qianfan-mcp'],
    envVars: [
      { name: 'QIANFAN_API_KEY', description: '百度千帆 Access Key', required: true },
    ],
    homepage: 'https://qianfan.cloud.baidu.com',
    docsUrl: 'https://cloud.baidu.com/doc/qianfan-docs/mcp',
    tags: ['知识库', '应用', '百度'],
    risk: 'warn',
    tier: 'B',
  },

  // ─── C-tier：待官方发布，仅占位 ───
  {
    id: 'minimax-mcp',
    provider: 'minimax',
    displayName: 'MiniMax（待发布）',
    description: 'MiniMax 官方 MCP（多模态：语音/视频/图像，待官方发布）',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@minimax/mcp-server'],
    envVars: [
      { name: 'MINIMAX_API_KEY', description: 'MiniMax API Key', required: true },
    ],
    homepage: 'https://api.minimaxi.com',
    docsUrl: 'https://api.minimaxi.com/docs/mcp',
    tags: ['多模态', '语音', '视频', 'MiniMax'],
    risk: 'warn',
    tier: 'C',
  },
  {
    id: 'mimo-mcp',
    provider: 'mimo',
    displayName: 'Mimo 官方（待发布）',
    description: 'Mimo 官方 MCP 通用工具集（待官方发布）',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@xiaomimimo/mcp-server'],
    envVars: [
      { name: 'MIMO_API_KEY', description: 'Mimo API Key', required: true },
    ],
    homepage: 'https://api.xiaomimimo.com',
    docsUrl: 'https://api.xiaomimimo.com/docs/mcp',
    tags: ['Mimo', '通用工具'],
    risk: 'warn',
    tier: 'C',
  },
  {
    id: 'deepseek-mcp',
    provider: 'deepseek',
    displayName: 'DeepSeek（待发布）',
    description: 'DeepSeek 官方 MCP：代码 / 搜索（待官方发布）',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@deepseek/mcp-server'],
    envVars: [
      { name: 'DEEPSEEK_API_KEY', description: 'DeepSeek API Key', required: true },
    ],
    homepage: 'https://platform.deepseek.com',
    docsUrl: 'https://platform.deepseek.com/docs/mcp',
    tags: ['代码', '搜索', 'DeepSeek'],
    risk: 'warn',
    tier: 'C',
  },
]

/**
 * GUI MCP 添加页面按 id 取条目
 */
export function getMarketplaceEntry(id: string): McpMarketplaceEntry | undefined {
  return DOMESTIC_MCP_MARKETPLACE.find((e) => e.id === id)
}

/**
 * 按 tier 过滤（探活脚本按 tier=A 调用）
 */
export function listMarketplaceByTier(tier: 'A' | 'B' | 'C'): McpMarketplaceEntry[] {
  return DOMESTIC_MCP_MARKETPLACE.filter((e) => e.tier === tier)
}