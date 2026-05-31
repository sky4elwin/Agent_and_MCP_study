# 智能信息查询系统 - LangChain Agent + FastMCP Server (stdio 版本)

## 项目介绍

这是一个基于 LangChain Agent 与 MCP Server 的智能信息查询系统，支持：
- **天气查询**：通过 Open-Meteo 免费 API 获取指定城市的当前天气
- **股票查询**：通过 yfinance (Yahoo Finance) 免费 API 获取股票实时信息

Agent 使用 DeepSeek LLM，通过 stdio 协议自动发现并调用 MCP Server 提供的工具。

## 项目结构

```
weather_agent_demo/
├── requirements.txt      # 依赖包声明
├── mcp_server.py         # FastMCP Server (stdio) — 提供 get_weather + get_stock_info 工具
├── agent_app.py          # LangChain Agent — 自动发现 MCP 工具，ReAct 推理
├── tests/
│   └── test_mcp.py       # 单元测试
├── run_server.bat        # (可选) 单独启动 Server 的批处理文件
└── run_agent.bat         # (可选) 启动 Agent 的批处理文件
```

## 使用步骤

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行 Agent

Agent 会自动启动 MCP Server 作为子进程，无需单独启动 Server：

```bash
python agent_app.py
```

按照提示输入城市名或股票代码即可查询。

## 示例交互

### 天气查询

```
正在初始化智能查询 Agent...
初始化完成！
输入城市名查天气，或输入股票代码查股票信息（输入 'quit' 退出）
  示例: 北京 / Tokyo / AAPL / 000300.SS / 0700.HK

> 查询: 北京

────────────────────────────────────────
🔄 第 1 轮
🔧 Action: get_weather('北京')
👁️ Observation: 工具已返回数据

────────────────────────────────────────
🔄 第 2 轮

💭 Thought: 已获取到北京天气数据：温度22.5°C，大部晴朗，湿度60%，风速3.2m/s。

✅ Final Answer: 北京当前天气 🌤️ **大部晴朗**
- 🌡️ 温度：22.5°C
- 💧 湿度：60%
- 💨 风速：3.2 m/s

==================================================
📋 最终结果:
北京当前天气大部晴朗，温度22.5°C...
```

### 股票查询

```
> 查询: AAPL

────────────────────────────────────────
🔄 第 1 轮
🔧 Action: get_stock_info('AAPL')
👁️ Observation: 工具已返回数据

────────────────────────────────────────
🔄 第 2 轮

💭 Thought: 已获取到 Apple Inc. 的股票数据：当前价格185.50 USD，上涨+1.37%，PE 30.5。

✅ Final Answer: 📈 **Apple Inc. (AAPL)**
- 💵 当前价格：$185.50
- 📊 涨跌：+$2.50 (+1.37%)
- 📈 市盈率：30.5
- 💰 市值：$2.90T
...
```

## MCP 工具说明

| 工具 | 输入 | 数据来源 | 说明 |
|------|------|----------|------|
| `get_weather` | `city: str` — 城市名（中/英） | Open-Meteo API | 获取指定城市的温度、天气描述、湿度、风速 |
| `get_stock_info` | `symbol: str` — 股票代码 | yfinance (Yahoo Finance) | 获取股票价格、涨跌幅、成交量、市值、市盈率等 |

### get_weather 响应示例

```json
{
  "city": "北京",
  "temperature": 22.5,
  "weather_description": "大部晴朗",
  "humidity": 60,
  "wind_speed": 3.2
}
```

### get_stock_info 响应示例

```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "current_price": 185.50,
  "previous_close": 183.00,
  "change": 2.50,
  "change_percent": "+1.37%",
  "volume": 55000000,
  "market_cap": 2900000000000,
  "pe_ratio": 30.5,
  "day_high": 186.00,
  "day_low": 183.50,
  "fifty_two_week_high": 200.00,
  "fifty_two_week_low": 140.00,
  "currency": "USD"
}
```

## 股票代码格式

| 市场 | 后缀 | 示例 |
|------|------|------|
| 美股 | 无 | AAPL, MSFT, GOOGL |
| 中国 A 股（上海） | `.SS` | 600000.SS |
| 中国 A 股（深圳） | `.SZ` | 000001.SZ |
| 香港 | `.HK` | 0700.HK, 9988.HK |
| 日本 | `.T` | 7203.T, 6758.T |

## 技术栈

| 组件 | 技术 |
|------|------|
| MCP 框架 | FastMCP (stdio 传输) |
| LLM 框架 | LangChain + langchain-mcp-adapters |
| LLM | DeepSeek-Chat (OpenAI API 兼容) |
| Agent 推理 | ReAct 模式（System Prompt + Middleware） |
| 天气数据 | Open-Meteo (免费, 无需 API Key) |
| 股票数据 | yfinance / Yahoo Finance (免费, 无需 API Key) |
| 测试 | pytest + monkeypatch |

## 运行测试

```bash
python -m pytest tests/test_mcp.py -v
```
