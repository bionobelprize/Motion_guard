import os
from openai import OpenAI
from datetime import datetime
import json

# 初始化OpenAI客户端（假设使用DeepSeek API）
# 请确保已设置环境变量 DEEPSEEK_API_KEY
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-ccdf47624bd94b8ba650ad0286117b45"),
    base_url="https://api.deepseek.com"  # DeepSeek API地址
)

class EmotionalConsultingSystem:
    def __init__(self, user_info):
        self.user_info = user_info
        self.session_history = []
        self.session_start_time = datetime.now()
        
        self.consulting_framework = """
        情感咨询五步法：
        1. 倾听共情：理解用户情绪和处境
        2. 问题分析：识别核心问题和模式
        3. 目标设定：明确咨询期望结果
        4. 策略探讨：共同寻找解决方案
        5. 行动计划：制定具体实施步骤
        """
        
        self.system_prompt = f"""
        # 身份设定
        你是「心语情感咨询中心」的资深咨询师李老师。
        
        # 专业背景
        - 国家二级心理咨询师
        - 专注情感咨询8年
        - 擅长亲密关系、情绪管理、个人成长
        
        # 咨询框架
        {self.consulting_framework}
        
        # 当前用户信息
        用户昵称：{user_info.get('name', '用户')}
        年龄：{user_info.get('age', '未提供')}
        咨询主题：{user_info.get('topic', '情感关系')}
        咨询次数：第{user_info.get('session_count', 1)}次
        
        # 重要原则
        - 每次回复都要体现专业性和共情能力
        - 记住用户提到的重要人际关系和关键事件
        - 保持对话的连续性和进展性
        - 适时总结咨询进展
        """
        
        self.messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # 添加初始欢迎消息
        welcome_msg = f"您好{user_info.get('name', '用户')}，我是李老师。很高兴为您提供情感咨询服务。今天我们来聊聊{user_info.get('topic', '情感关系')}方面的问题，请告诉我您最近的情况。"
        self.messages.append({"role": "assistant", "content": welcome_msg})
    
    def add_consulting_notes(self, notes):
        """添加咨询笔记到系统提示词"""
        notes_section = f"\n# 本次咨询重点记忆\n{notes}"
        self.messages[0]['content'] += notes_section
    
    def consult(self, user_input):
        """执行咨询对话"""
        
        # 添加用户输入
        self.messages.append({"role": "user", "content": user_input})
        
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=self.messages,
                temperature=0.7,
                max_tokens=2000,
                stream=False
            )
            
            ai_response = response.choices[0].message.content
            self.messages.append({"role": "assistant", "content": ai_response})
            
            # 记录对话历史
            self.session_history.append({
                "timestamp": datetime.now().isoformat(),
                "user": user_input,
                "assistant": ai_response
            })
            
            # 管理上下文长度
            self.manage_context()
            
            return ai_response
            
        except Exception as e:
            error_msg = f"咨询系统暂时无法响应，请稍后再试。错误：{str(e)}"
            self.messages.append({"role": "assistant", "content": error_msg})
            return error_msg
    
    def manage_context(self):
        """智能管理上下文，保留重要信息"""
        # 估算token数量（简化版）
        total_chars = sum(len(msg.get('content', '')) for msg in self.messages)
        estimated_tokens = total_chars // 4
        
        if estimated_tokens > 8000:  # 设置一个合理的阈值
            # 保留系统提示词和最近对话
            system_msg = self.messages[0]
            recent_dialogue = self.messages[-16:]  # 保留最近8轮对话
            
            # 创建会话摘要
            if len(self.messages) > 20:
                self.create_session_summary()
            
            # 重新构建消息历史
            self.messages = [system_msg] + recent_dialogue
    
    def create_session_summary(self):
        """创建会话摘要以保持长期记忆"""
        try:
            summary_prompt = {
                "role": "user",
                "content": "请用300字左右总结当前咨询会话的核心内容，包括用户的主要问题、情绪状态、重要事件和已讨论的解决方案。保持客观专业。"
            }
            
            temp_messages = [self.messages[0], summary_prompt]
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=temp_messages,
                temperature=0.3,
                max_tokens=500
            )
            
            summary = response.choices[0].message.content
            # 将摘要添加到系统提示词中
            self.add_consulting_notes(f"\n会话摘要（{datetime.now().strftime('%H:%M')}）: {summary}")
            
        except Exception as e:
            print(f"创建摘要时出错: {e}")
    
    def get_session_progress(self):
        """获取咨询进展摘要"""
        summary_prompt = """
        作为情感咨询师，请用专业且温暖的语言总结：
        1. 当前咨询的主要进展和突破
        2. 用户的核心情感问题和模式
        3. 已经讨论的有效解决方案
        4. 下一步的具体咨询建议和行动计划
        
        请以咨询报告的形式呈现，保持条理清晰。
        """
        
        return self.consult(summary_prompt)
    
    def save_session_log(self, filename=None):
        """保存会话日志到文件"""
        if filename is None:
            timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
            filename = f"consulting_session_{timestamp}.json"
        
        session_data = {
            "user_info": self.user_info,
            "start_time": self.session_start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "session_history": self.session_history,
            "total_turns": len(self.session_history)
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            return f"会话已保存到: {filename}"
        except Exception as e:
            return f"保存会话时出错: {str(e)}"

# 使用示例
if __name__ == "__main__":
    # 初始化情感咨询系统
    user_info = {
        "name": "小明",
        "age": "28",
        "topic": "亲密关系沟通问题",
        "session_count": 3
    }
    
    consultant = EmotionalConsultingSystem(user_info)
    
    # 模拟多轮咨询对话
    dialogues = [
        "老师，我最近和女朋友总是因为小事吵架，觉得很累。",
        "我们在一起两年了，最近半年矛盾特别多。",
        "我尝试过沟通，但总是说不清楚自己的想法。"
    ]
    
    for i, user_say in enumerate(dialogues):
        print(f"\n【用户第{i+1}轮】: {user_say}")
        response = consultant.consult(user_say)
        print(f"【AI咨询师】: {response}")
    
    # 获取咨询进展总结
    print("\n" + "="*50)
    progress = consultant.get_session_progress()
    print(f"【咨询总结】: {progress}")
    
    # 保存会话日志
    save_result = consultant.save_session_log()
    print(f"\n【会话记录】: {save_result}")