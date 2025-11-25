import asyncio
from typing import Optional, Any, Dict
from contextlib import AsyncExitStack
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
import threading
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
class MCPClientWrapper:
    def __init__(self):
        self.client = MCPClient()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._start_loop, daemon=True).start()
        self.ready = threading.Event()
        threading.Thread(target=self._init_servers, daemon=True).start()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _init_servers(self):
        # 这里假定服务器路径已配置好
        server_paths = [
            '/home/admin1/tools/ais/mymcp/email_sender.py',
            #'/home/admin1/tools/ais/mymcp/psychological_counseling.py'
        ]
        fut = asyncio.run_coroutine_threadsafe(self.client.connect_to_servers(server_paths), self.loop)
        fut.result()
        self.ready.set()

    def process_user_input(self, user_input: str, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理用户输入，返回AI建议
        """
        self.ready.wait()
        query = f"用户心率: {alert_data.get('heart_rate', '未知')}, 用户回复: {user_input}"
        fut = asyncio.run_coroutine_threadsafe(self.client.process_query(query), self.loop)
        result = fut.result()
        # 这里假定AI返回的内容中包含是否需要疏导/发邮件/终止的建议
        # 实际可根据AI返回内容进一步解析
        return {"ai_response": result}

class MCPClient:
    def __init__(self):
        self.sessions: dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.deepseek = OpenAI(
            api_key="sk-995d742a30f34b1a8b86e17fd5be462e",
            base_url="https://api.deepseek.com"
        )

    async def connect_to_servers(self, server_paths: list[str]):
        """连接多个服务器"""
        for server_path in server_paths:
            session_name = os.path.basename(server_path).split('.')[0]  # 去掉扩展名
            session = await self.connect_to_server(server_path)
            if session:
                self.sessions[session_name] = session
                print(f"Connected to {session_name} successfully")

    async def connect_to_server(self, server_script_path: str) -> Optional[ClientSession]:
        """Connect to an MCP server and return the session"""
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        try:
            # 为每个服务器创建新的传输和会话
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            stdio_reader, stdio_writer = stdio_transport
            session = await self.exit_stack.enter_async_context(ClientSession(stdio_reader, stdio_writer))
            
            await session.initialize()
            return session
            
        except Exception as e:
            print(f"Failed to connect to {server_script_path}: {str(e)}")
            return None

    async def process_query(self, query: str) -> str:
        """处理查询，聚合所有服务器的工具"""
        if not self.sessions:
            return "No servers connected. Please connect to servers first."

        # 收集所有服务器的工具
        all_tools = []
        print(f"Available sessions: {list(self.sessions.keys())}")
        
        for session_name, session in self.sessions.items():
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    # 添加服务器标识以避免工具名冲突
                    tool_dict = {
                        "type": "function",
                        "function": {
                            "name": f"{session_name}__{tool.name}",  # 添加前缀
                            "description": f"[{session_name}] {tool.description}",
                            "parameters": tool.inputSchema
                        }
                    }
                    all_tools.append(tool_dict)
            except Exception as e:
                print(f"Error getting tools from {session_name}: {str(e)}")

        messages = [{"role": "user", "content": query}]

        response = self.deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=messages,
            tools=all_tools if all_tools else None
        )

        result_dict = {
            "raw_message": None,
            "tool_results": [],
            "errors": [],
            "result_str": ""
        }
        message = response.choices[0].message
        print(f"Received message: {message}")
        if message.content:
            result_dict["raw_message"] = message.content
            result_dict["result_str"] += message.content + "\n"

        if message.tool_calls:
            for tool_call in message.tool_calls:
                print("tool call", tool_call)
                tool_name = tool_call.function.name
                print("tool name", tool_name)
                try:
                    # 解析工具参数
                    tool_args = json.loads(tool_call.function.arguments)

                    # 从工具名中提取服务器名称
                    server_name = tool_name.split('__')[0]
                    actual_tool_name = tool_name.split('__')[1]

                    if server_name in self.sessions:
                        # 执行工具调用
                        print(f"Calling tool {actual_tool_name} on server {server_name} with args {tool_args}")
                        result = await self.sessions[server_name].call_tool(actual_tool_name, tool_args)
                        if result and hasattr(result, 'content') and result.content:
                            tool_result = result.content[0].text if result.content else "No result"
                            result_dict["tool_results"].append({
                                "tool_name": tool_name,
                                "server_name": server_name,
                                "actual_tool_name": actual_tool_name,
                                "args": tool_args,
                                "result": tool_result
                            })
                            result_dict["result_str"] += f"Tool {tool_name} result: {tool_result}\n"
                    else:
                        error_msg = f"Server {server_name} not found for tool {tool_name}"
                        result_dict["errors"].append(error_msg)
                        result_dict["result_str"] += error_msg + "\n"

                except Exception as e:
                    error_msg = f"Error executing tool {tool_name}: {str(e)}"
                    result_dict["errors"].append(error_msg)
                    result_dict["result_str"] += error_msg + "\n"
        return result_dict

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print(f"Connected to {len(self.sessions)} servers: {list(self.sessions.keys())}")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break
                if query.lower() == 'list':
                    print(f"Connected servers: {list(self.sessions.keys())}")
                    continue

                response = await self.process_query(query)
                print("\nResponse:\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    server_paths = [
        "email_sender.py",
        "translate.py"
    ]
    
    # 检查服务器文件是否存在
    for server_path in server_paths:
        if not os.path.exists(server_path):
            print(f"Warning: Server file {server_path} does not exist")
    
    client = MCPClient()
    try:
        await client.connect_to_servers(server_paths)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
