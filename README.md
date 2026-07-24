# 网络监控系统 - Network Monitor

版本: v0.0.13

基于 Flask 的网络设备监控系统，支持 SNMP 协议采集设备状态、流量等信息。

## 功能特性

- 网络设备自动发现与监控
- SNMP 协议设备数据采集
- 网络设备在线状态检测
- 流量与性能数据可视化
- 告警与通知
- 设备配置文件管理

## 技术栈

- **后端**: Python Flask
- **前端**: HTML + JavaScript + Chart.js
- **数据存储**: SQLite
- **协议支持**: SNMP (v2c/v3), ICMP

## 快速开始

### Docker 部署

```bash
docker run -d \
  --name network-monitor \
  -p 5002:5002 \
  -v /data/network_monitor:/app/data \
  --restart unless-stopped \
  network-monitor:v0.0.13
```

### 手动部署

```bash
pip install -r requirements.txt
python app.py
```

## 项目结构

```
v0.0.13/
├── app.py              # 主应用
├── config.py           # 配置文件
├── requirements.txt    # Python 依赖
├── static/             # 静态资源
├── templates/          # HTML 模板
├── data/               # 数据存储目录
└── export/             # 导出目录
```
