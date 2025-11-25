import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
import logging


class HeartRateMonitor:
    def __init__(self, base_url: str = "http://192.168.1.104:8080"):
        self.base_url = base_url
        self.heart_rate_endpoint = f"{base_url}/heart-rate"
        
        # 监控配置
        self.monitoring_interval = 5  # 秒
        self.emergency_threshold = 120  # BPM紧急阈值
        self.warning_threshold = 100   # BPM警告阈值
        
        # 数据存储
        self.current_data: Optional[Dict] = None
        self.history: list = []
        self.max_history_size = 1000
        
        # 状态标志
        self.is_monitoring = False
        self.last_update_time = 0
        
        # 设置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("HeartRateMonitor")

    async def fetch_heart_rate(self) -> Optional[Dict]:
        """从设备API获取心率数据"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.heart_rate_endpoint) as response:
                    if response.status == 200:
                        data = await response.json()
                        data['received_timestamp'] = time.time()
                        data['local_timestamp'] = datetime.now().isoformat()
                        return data
                    else:
                        self.logger.error(f"API响应错误: {response.status}")
                        return None
                        
        except aiohttp.ClientError as e:
            self.logger.error(f"网络请求错误: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析错误: {e}")
            return None

    def analyze_heart_rate(self, data: Dict) -> Dict[str, Any]:
        """分析心率数据并返回状态评估"""
        heart_rate = data.get('current_heart_rate', 0)
        status = data.get('status', 'unknown')
        
        analysis = {
            'heart_rate': heart_rate,
            'status': status,
            'risk_level': 'normal',
            'message': '',
            'suggested_action': 'continue_monitoring'
        }
        
        # 风险评估逻辑
        if heart_rate >= self.emergency_threshold:
            analysis['risk_level'] = 'emergency'
            analysis['message'] = f'心率过高: {heart_rate} BPM'
            analysis['suggested_action'] = 'immediate_intervention'
        elif heart_rate >= self.warning_threshold:
            analysis['risk_level'] = 'warning'
            analysis['message'] = f'心率偏高: {heart_rate} BPM'
            analysis['suggested_action'] = 'gentle_intervention'
        elif heart_rate < 50:  # 心动过缓
            analysis['risk_level'] = 'emergency'
            analysis['message'] = f'心率过低: {heart_rate} BPM'
            analysis['suggested_action'] = 'immediate_intervention'
        else:
            analysis['message'] = f'心率正常: {heart_rate} BPM'
            
        return analysis

    def store_data(self, data: Dict, analysis: Dict):
        """存储数据和分析结果"""
        record = {
            'timestamp': data['local_timestamp'],
            'raw_data': data,
            'analysis': analysis
        }
        
        self.history.append(record)
        self.current_data = record
        
        # 限制历史数据大小
        if len(self.history) > self.max_history_size:
            self.history.pop(0)

    async def emergency_alert(self, analysis: Dict, raw_data: Dict):
        """紧急警报处理"""
        self.logger.warning(f"🚨 紧急警报: {analysis['message']}")
        
        # 这里可以集成到LLM决策系统
        alert_data = {
            'type': 'heart_rate_emergency',
            'timestamp': datetime.now().isoformat(),
            'heart_rate': raw_data['current_heart_rate'],
            'risk_level': analysis['risk_level'],
            'message': analysis['message'],
            'raw_data': raw_data
        }
        
        # 触发LLM干预（后续扩展）
        await self.trigger_llm_intervention(alert_data)

    async def trigger_llm_intervention(self, alert_data: Dict):
        """通过HTTP请求调用LLM_inter.py服务"""
        self.logger.info("🚨 触发LLM情感干预（HTTP模式）")
        url = "http://127.0.0.1:5005/intervene"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=alert_data, timeout=600) as resp:
                    result = await resp.json()
                    self.logger.info(f"情感干预完成: {result}")
        except Exception as e:
            self.logger.error(f"情感干预过程中出错: {e}")

    async def monitoring_loop(self):
        """主监控循环"""
        self.is_monitoring = True
        self.logger.info("开始心率监控...")
        
        while self.is_monitoring:
            try:
                # 获取数据
                data = await self.fetch_heart_rate()
                
                if data:
                    # 分析数据
                    analysis = self.analyze_heart_rate(data)
                    
                    # 存储数据
                    self.store_data(data, analysis)
                    
                    # 日志记录
                    self.logger.info(
                        f"心率: {data['current_heart_rate']:.1f} BPM | "
                        f"状态: {analysis['risk_level']} | "
                        f"设备状态: {data.get('status', 'N/A')}"
                    )
                    
                    # 紧急情况处理
                    if analysis['risk_level'] in ['emergency', 'warning']:
                        await self.emergency_alert(analysis, data)
                
                # 等待下一次监控
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                self.logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(self.monitoring_interval)  # 出错后继续

    def get_current_status(self) -> Dict:
        """获取当前状态摘要"""
        if not self.current_data:
            return {'status': 'no_data'}
            
        return {
            'status': 'active',
            'last_update': self.current_data['timestamp'],
            'current_heart_rate': self.current_data['raw_data']['current_heart_rate'],
            'risk_level': self.current_data['analysis']['risk_level'],
            'message': self.current_data['analysis']['message']
        }

    async def start_monitoring(self):
        """启动监控"""
        await self.monitoring_loop()

    async def stop_monitoring(self):
        """停止监控"""
        self.is_monitoring = False
        self.logger.info("心率监控已停止")

# 使用示例
async def main():
    monitor = HeartRateMonitor()
    
    try:
        # 启动监控
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        await monitor.stop_monitoring()
        print("监控程序已退出")

if __name__ == "__main__":
    asyncio.run(main())