from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents.middleware import after_model, before_model
from langchain.agents.middleware import ModelCallLimitMiddleware
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession
import asyncio
import os

# ============================================================
# ReAct System Prompt — 教会 LLM 按格式输出
# ============================================================
REACT_SYSTEM_PROMPT = """你是一个智能助手，可以查询天气、股票信息和汇率。你必须严格按照以下格式思考和回复：

## 回复格式要求

当你需要调用工具时，先在思考中说明你要做什么，然后调用工具：
💭 Thought: <你的推理过程，为什么要调用这个工具，以及你期望得到什么数据>

当你收到工具返回的结果后：
👁️ Observation: 简要总结工具返回的关键数据（不要照抄原始JSON，提取用户关心的信息）

当你已经有足够信息回答用户时：
✅ Final Answer: 用中文清晰、完整地回答用户的问题

## 重要规则
- 每次只调用一个工具
- 如果查询失败（返回 error），告诉用户具体原因，并建议用户检查输入
- 股票数据中如果有 None 字段，跳过不展示，不要自己编造
- 温度的原始数据是摄氏度
- 汇率查询需要提供基准货币和目标货币代码（如 CNY、USD、EUR、JPY、HKD）
- 回答要简洁友好，适当使用 emoji
"""

# ============================================================
# ReAct 中间件 — 轮次标记 + 工具调用高亮
# ============================================================
_step_counter = {"count": 0}


@after_model
def highlight_react_steps(state, runtime):
    """每次 LLM 调用后：标记轮次，高亮工具调用"""
    _step_counter["count"] += 1
    print(f"\n{'─' * 40}")
    print(f"🔄 第 {_step_counter['count']} 轮")

    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            args_str = ", ".join(f"{k}={v!r}" for k, v in tc.get("args", {}).items())
            print(f"🔧 Action: {tc['name']}({args_str})")
    return None


@before_model
def prepare_observation_context(state, runtime):
    """每次 LLM 调用前：如果上一轮有工具返回，标记 Observation"""
    for msg in reversed(state["messages"]):
        if hasattr(msg, "type") and msg.type == "tool":
            print(f"👁️ Observation: 工具已返回数据")
            break
    return None


async def main():
    # 检查必需的 API Key
    if "DEEPSEEK_API_KEY" not in os.environ:
        print("❌ 错误：未设置 DEEPSEEK_API_KEY 环境变量")
        print("请先设置: https://platform.deepseek.com/api_keys")
        print()
        print("Windows (CMD):    set DEEPSEEK_API_KEY=你的Key")
        print("Windows (PS):      $env:DEEPSEEK_API_KEY = \"你的Key\"")
        print("Linux/Mac:         export DEEPSEEK_API_KEY=\"你的Key\"")
        return

    print("正在初始化智能查询 Agent...")
    print("连接到 MCP Server (stdio)...")

    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.environ["DEEPSEEK_API_KEY"],
        openai_api_base="https://api.deepseek.com/v1",
        temperature=0
    )

    # MCP Server 配置
    mcp_server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
        env={"PYTHONIOENCODING": "utf-8"}
    )

    # 迭代次数限制：最多 10 轮 LLM 调用
    call_limiter = ModelCallLimitMiddleware(
        run_limit=10,
        exit_behavior="end"
    )

    try:
        # 使用 MCP stdio 客户端连接 MCP Server
        async with stdio_client(mcp_server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # 初始化会话
                await session.initialize()

                # 加载 MCP 工具
                tools = await load_mcp_tools(session)

                # 创建 Agent（注入 system_prompt + 中间件）
                agent = create_agent(
                    llm,
                    tools=tools,
                    system_prompt=REACT_SYSTEM_PROMPT,
                    middleware=[highlight_react_steps, prepare_observation_context, call_limiter]
                )

                print("初始化完成！")
                print("输入城市名查天气，股票代码查股票，或货币代码查汇率（输入 'quit' 退出）")
                print("  示例: 北京 / Tokyo / AAPL / 000300.SS / CNY USD / EUR JPY")

                while True:
                    try:
                        user_input = input("\n> 查询: ").strip()
                        if user_input.lower() in ['quit', 'exit', '退出']:
                            print("再见！")
                            break
                        if not user_input:
                            continue

                        # 重置轮次计数器
                        _step_counter["count"] = 0

                        result = await agent.ainvoke({
                            "messages": [("user", f"请帮我查询: {user_input}。如果是城市名就查天气，如果是股票代码就查股票信息，如果是货币对（如 CNY USD）就查汇率。")]
                        })

                        # 提取最后一条助手的回复
                        assistant_messages = [msg.content for msg in result["messages"] if hasattr(msg, "content") and msg.type == "ai"]
                        if assistant_messages:
                            print(f"\n{'=' * 50}")
                            print(f"📋 最终结果:\n{assistant_messages[-1]}")

                    except KeyboardInterrupt:
                        print("\n再见！")
                        break
                    except Exception as e:
                        print(f"发生错误: {str(e)}")

    except Exception as e:
        print(f"连接 MCP Server 失败: {str(e)}")
        print("请确保 MCP Server 正在运行 (python mcp_server.py)")


if __name__ == "__main__":
    asyncio.run(main())
