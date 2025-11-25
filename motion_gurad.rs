use std::collections::VecDeque;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};
use tokio::time::sleep;
use reqwest::Client;
use anyhow::{Result, anyhow};
use chrono::{DateTime, Utc};
use std::sync::Arc;
use tokio::sync::Mutex;

// 数据结构定义
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeartRateData {
    pub current_heart_rate: f64,
    pub status: String,
    #[serde(skip_deserializing, skip_serializing)]
    pub received_timestamp: u64,
    #[serde(skip_deserializing, skip_serializing)]
    pub local_timestamp: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeartRateAnalysis {
    pub heart_rate: f64,
    pub status: String,
    pub risk_level: String,
    pub message: String,
    pub suggested_action: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonitoringRecord {
    pub timestamp: String,
    pub raw_data: HeartRateData,
    pub analysis: HeartRateAnalysis,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertData {
    pub alert_type: String,
    pub timestamp: String,
    pub heart_rate: f64,
    pub risk_level: String,
    pub message: String,
    pub raw_data: HeartRateData,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatusSummary {
    pub status: String,
    pub last_update: Option<String>,
    pub current_heart_rate: Option<f64>,
    pub risk_level: Option<String>,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrendAnalysis {
    pub trend: String,
    pub average_hr: f64,
    pub max_hr: f64,
    pub min_hr: f64,
    pub data_points: usize,
}

// LLM干预管理器（模拟）
struct LLMInterventionManager;

impl LLMInterventionManager {
    pub fn new() -> Self {
        LLMInterventionManager
    }
    
    pub async fn start_intervention(&self, alert_data: &AlertData) -> Result<String> {
        // 模拟LLM干预过程
        log::info!("Starting LLM intervention for alert: {}", alert_data.message);
        sleep(Duration::from_secs(2)).await; // 模拟处理时间
        Ok("Intervention completed successfully".to_string())
    }
}

// 心率监控器
pub struct HeartRateMonitor {
    base_url: String,
    heart_rate_endpoint: String,
    monitoring_interval: u64,
    emergency_threshold: f64,
    warning_threshold: f64,
    current_data: Arc<Mutex<Option<MonitoringRecord>>>,
    history: Arc<Mutex<VecDeque<MonitoringRecord>>>,
    max_history_size: usize,
    is_monitoring: Arc<Mutex<bool>>,
    client: Client,
}

impl HeartRateMonitor {
    pub fn new(base_url: String) -> Self {
        let heart_rate_endpoint = format!("{}/heart-rate", base_url);
        
        HeartRateMonitor {
            base_url: base_url.clone(),
            heart_rate_endpoint,
            monitoring_interval: 5,
            emergency_threshold: 120.0,
            warning_threshold: 100.0,
            current_data: Arc::new(Mutex::new(None)),
            history: Arc::new(Mutex::new(VecDeque::with_capacity(1000))),
            max_history_size: 1000,
            is_monitoring: Arc::new(Mutex::new(false)),
            client: Client::new(),
        }
    }
    
    pub fn with_thresholds(mut self, emergency: f64, warning: f64) -> Self {
        self.emergency_threshold = emergency;
        self.warning_threshold = warning;
        self
    }
    
    pub fn with_interval(mut self, interval: u64) -> Self {
        self.monitoring_interval = interval;
        self
    }
    
    async fn fetch_heart_rate(&self) -> Result<HeartRateData> {
        let response = self.client
            .get(&self.heart_rate_endpoint)
            .timeout(Duration::from_secs(10))
            .send()
            .await?;
            
        if response.status().is_success() {
            let mut data: HeartRateData = response.json().await?;
            
            // 添加时间戳
            let now = SystemTime::now();
            data.received_timestamp = now.duration_since(UNIX_EPOCH)?.as_secs();
            data.local_timestamp = Utc::now().to_rfc3339();
            
            Ok(data)
        } else {
            Err(anyhow!("API响应错误: {}", response.status()))
        }
    }
    
    fn analyze_heart_rate(&self, data: &HeartRateData) -> HeartRateAnalysis {
        let heart_rate = data.current_heart_rate;
        let status = data.status.clone();
        
        let (risk_level, message, suggested_action) = if heart_rate >= self.emergency_threshold {
            ("emergency".to_string(), 
             format!("心率过高: {:.1} BPM", heart_rate), 
             "immediate_intervention".to_string())
        } else if heart_rate >= self.warning_threshold {
            ("warning".to_string(), 
             format!("心率偏高: {:.1} BPM", heart_rate), 
             "gentle_intervention".to_string())
        } else if heart_rate < 50.0 {
            ("emergency".to_string(), 
             format!("心率过低: {:.1} BPM", heart_rate), 
             "immediate_intervention".to_string())
        } else {
            ("normal".to_string(), 
             format!("心率正常: {:.1} BPM", heart_rate), 
             "continue_monitoring".to_string())
        };
        
        HeartRateAnalysis {
            heart_rate,
            status,
            risk_level,
            message,
            suggested_action,
        }
    }
    
    async fn store_data(&self, data: HeartRateData, analysis: HeartRateAnalysis) {
        let record = MonitoringRecord {
            timestamp: data.local_timestamp.clone(),
            raw_data: data,
            analysis,
        };
        
        let mut current_data = self.current_data.lock().await;
        *current_data = Some(record.clone());
        
        let mut history = self.history.lock().await;
        history.push_back(record);
        
        // 限制历史数据大小
        if history.len() > self.max_history_size {
            history.pop_front();
        }
    }
    
    async fn emergency_alert(&self, analysis: &HeartRateAnalysis, raw_data: &HeartRateData) {
        log::warn!("🚨 紧急警报: {}", analysis.message);
        
        let alert_data = AlertData {
            alert_type: "heart_rate_emergency".to_string(),
            timestamp: Utc::now().to_rfc3339(),
            heart_rate: raw_data.current_heart_rate,
            risk_level: analysis.risk_level.clone(),
            message: analysis.message.clone(),
            raw_data: raw_data.clone(),
        };
        
        self.trigger_llm_intervention(alert_data).await;
    }
    
    async fn trigger_llm_intervention(&self, alert_data: AlertData) {
        log::info!("🚨 触发LLM情感干预（阻塞模式）");
        
        // 保存当前监控状态并暂停监控
        let original_monitoring_state = {
            let monitoring = self.is_monitoring.lock().await;
            *monitoring
        };
        
        {
            let mut monitoring = self.is_monitoring.lock().await;
            *monitoring = false;
        }
        
        // 执行干预
        let intervention_result = async {
            let llm_manager = LLMInterventionManager::new();
            match llm_manager.start_intervention(&alert_data).await {
                Ok(result) => {
                    log::info!("情感干预完成: {}", result);
                    Ok(())
                }
                Err(e) => {
                    log::error!("情感干预过程中出错: {}", e);
                    Err(e)
                }
            }
        }.await;
        
        // 恢复监控状态
        if original_monitoring_state {
            let mut monitoring = self.is_monitoring.lock().await;
            *monitoring = true;
            log::info!("监控已恢复");
        }
        
        sleep(Duration::from_secs(1)).await;
    }
    
    pub async fn start_monitoring(&self) -> Result<()> {
        {
            let mut monitoring = self.is_monitoring.lock().await;
            *monitoring = true;
        }
        
        log::info!("开始心率监控...");
        self.monitoring_loop().await
    }
    
    pub async fn stop_monitoring(&self) {
        let mut monitoring = self.is_monitoring.lock().await;
        *monitoring = false;
        log::info!("心率监控已停止");
    }
    
    async fn monitoring_loop(&self) -> Result<()> {
        loop {
            // 检查是否应该继续监控
            {
                let monitoring = self.is_monitoring.lock().await;
                if !*monitoring {
                    break;
                }
            }
            
            match self.fetch_heart_rate().await {
                Ok(data) => {
                    let analysis = self.analyze_heart_rate(&data);
                    
                    self.store_data(data.clone(), analysis.clone()).await;
                    
                    log::info!(
                        "心率: {:.1} BPM | 状态: {} | 设备状态: {}",
                        data.current_heart_rate,
                        analysis.risk_level,
                        data.status
                    );
                    
                    if analysis.risk_level == "emergency" || analysis.risk_level == "warning" {
                        self.emergency_alert(&analysis, &data).await;
                    }
                }
                Err(e) => {
                    log::error!("获取心率数据错误: {}", e);
                }
            }
            
            sleep(Duration::from_secs(self.monitoring_interval)).await;
        }
        
        Ok(())
    }
    
    pub async fn get_current_status(&self) -> StatusSummary {
        let current_data = self.current_data.lock().await;
        
        match current_data.as_ref() {
            Some(data) => StatusSummary {
                status: "active".to_string(),
                last_update: Some(data.timestamp.clone()),
                current_heart_rate: Some(data.raw_data.current_heart_rate),
                risk_level: Some(data.analysis.risk_level.clone()),
                message: Some(data.analysis.message.clone()),
            },
            None => StatusSummary {
                status: "no_data".to_string(),
                last_update: None,
                current_heart_rate: None,
                risk_level: None,
                message: None,
            },
        }
    }
    
    pub async fn get_trend_analysis(&self, hours: u64) -> TrendAnalysis {
        let history = self.history.lock().await;
        let cutoff_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs() - hours * 3600;
        
        let recent_data: Vec<&MonitoringRecord> = history
            .iter()
            .filter(|h| h.raw_data.received_timestamp >= cutoff_time)
            .collect();
        
        if recent_data.is_empty() {
            return TrendAnalysis {
                trend: "insufficient_data".to_string(),
                average_hr: 0.0,
                max_hr: 0.0,
                min_hr: 0.0,
                data_points: 0,
            };
        }
        
        let heart_rates: Vec<f64> = recent_data
            .iter()
            .map(|h| h.raw_data.current_heart_rate)
            .collect();
            
        let average_hr = heart_rates.iter().sum::<f64>() / heart_rates.len() as f64;
        let max_hr = heart_rates.iter().fold(f64::MIN, |a, &b| a.max(b));
        let min_hr = heart_rates.iter().fold(f64::MAX, |a, &b| a.min(b));
        
        TrendAnalysis {
            trend: "stable".to_string(), // 简化处理
            average_hr,
            max_hr,
            min_hr,
            data_points: recent_data.len(),
        }
    }
}

// 使用示例
#[tokio::main]
async fn main() -> Result<()> {
    // 初始化日志
    env_logger::init();
    
    let monitor = HeartRateMonitor::new("http://192.168.1.104:8080".to_string());
    
    // 设置Ctrl+C处理
    let monitor_clone = Arc::new(monitor);
    let monitor_for_signal = monitor_clone.clone();
    
    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.unwrap();
        monitor_for_signal.stop_monitoring().await;
        println!("监控程序已退出");
    });
    
    // 启动监控
    monitor_clone.start_monitoring().await?;
    
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    async fn test_heart_rate_analysis() {
        let monitor = HeartRateMonitor::new("http://test.com".to_string());
        
        // 测试正常心率
        let normal_data = HeartRateData {
            current_heart_rate: 80.0,
            status: "normal".to_string(),
            received_timestamp: 0,
            local_timestamp: "".to_string(),
        };
        
        let analysis = monitor.analyze_heart_rate(&normal_data);
        assert_eq!(analysis.risk_level, "normal");
        
        // 测试警告心率
        let warning_data = HeartRateData {
            current_heart_rate: 110.0,
            status: "elevated".to_string(),
            received_timestamp: 0,
            local_timestamp: "".to_string(),
        };
        
        let analysis = monitor.analyze_heart_rate(&warning_data);
        assert_eq!(analysis.risk_level, "warning");
        
        // 测试紧急心率
        let emergency_data = HeartRateData {
            current_heart_rate: 130.0,
            status: "high".to_string(),
            received_timestamp: 0,
            local_timestamp: "".to_string(),
        };
        
        let analysis = monitor.analyze_heart_rate(&emergency_data);
        assert_eq!(analysis.risk_level, "emergency");
    }
}