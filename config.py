#!/usr/bin/env python3
"""
网络设备监控系统 - 数据配置模板
版本: v0.0.12
功能: SNMP监控、每10秒自动检查、端口本地备注管理、端口Down实时告警、添加设备自动获取端口
"""

from datetime import datetime

# ==================== 版本信息 ====================
VERSION = "0.0.12"
VERSION_DATE = "2026-04-28"
TEMPLATE_VERSION = "2.1.2"

# ==================== 设备类型 ====================
DEVICE_TYPES = {
    'switch': '交换机',
    'router': '路由器',
    'firewall': '防火墙',
    'ap': '无线AP',
    'server': '服务器',
    'other': '其他'
}

# ==================== 厂商类型 ====================
VENDOR_TYPES = {
    'h3c': '华三(H3C)',
    'huawei': '华为',
    'cisco': '思科(Cisco)',
    'ruijie': '锐捷(Ruijie)',
    'hpe': 'HPE',
    'juniper': 'Juniper',
    'arista': 'Arista',
    'other': '其他'
}

# ==================== SNMP 版本 ====================
SNMP_VERSIONS = {
    'v1': 'SNMP v1',
    'v2c': 'SNMP v2c',
    'v3': 'SNMP v3'
}

# ==================== 端口状态 ====================
PORT_STATUS = {
    'up': {'label': 'Up', 'class': 'success', 'icon': '✓'},
    'down': {'label': 'Down', 'class': 'danger', 'icon': '✗'},
    'admin_down': {'label': 'Admin Down', 'class': 'warning', 'icon': '◯'},
    'unknown': {'label': 'Unknown', 'class': 'secondary', 'icon': '?'}
}

# ==================== 设备状态 ====================
DEVICE_STATUS = {
    'online': {'label': '在线', 'class': 'success', 'badge': 'bg-success'},
    'offline': {'label': '离线', 'class': 'danger', 'badge': 'bg-danger'},
    'unreachable': {'label': '不可达', 'class': 'warning', 'badge': 'bg-warning'},
    'unknown': {'label': '未知', 'class': 'secondary', 'badge': 'bg-secondary'}
}

# ==================== 告警级别 ====================
ALERT_LEVELS = {
    'critical': {'label': '紧急', 'class': 'danger', 'color': '#dc3545'},
    'high': {'label': '重要', 'class': 'warning', 'color': '#ffc107'},
    'medium': {'label': '一般', 'class': 'info', 'color': '#17a2b8'},
    'low': {'label': '提示', 'class': 'secondary', 'color': '#6c757d'}
}

# ==================== 监控指标阈值 ====================
THRESHOLDS = {
    'cpu_high': 80,
    'cpu_critical': 95,
    'mem_high': 80,
    'mem_critical': 95,
    'temp_high': 70,
    'temp_critical': 85,
    'traffic_high': 80,
    'error_rate': 0.01,
}

# ==================== 自动检查间隔配置 ====================
# v0.0.10 新增：每10秒自动检查，实现端口状态准实时检测
MONITOR_INTERVALS = {
    'auto_check': 10,        # 自动检查间隔（秒）- 每10秒检查一次
    'device_status': 10,     # 设备状态检查
    'port_status': 10,       # 端口状态检查
    'performance': 60,       # 性能数据采集
    'mac_learning': 120,     # MAC地址学习
    'vlan_sync': 300,        # VLAN信息同步
    'baseline': 300,         # 基线分析
}

# ==================== SNMP OID 标准 ====================
# 标准 MIB-II OIDs
STANDARD_OIDS = {
    # 系统信息
    'sysDescr': '1.3.6.1.2.1.1.1.0',
    'sysObjectID': '1.3.6.1.2.1.1.2.0',
    'sysUpTime': '1.3.6.1.2.1.1.3.0',
    'sysContact': '1.3.6.1.2.1.1.4.0',
    'sysName': '1.3.6.1.2.1.1.5.0',
    'sysLocation': '1.3.6.1.2.1.1.6.0',
    
    # 接口信息
    'ifNumber': '1.3.6.1.2.1.2.1.0',
    'ifTable': '1.3.6.1.2.1.2.2.1',
    'ifDescr': '1.3.6.1.2.1.2.2.1.2',
    'ifType': '1.3.6.1.2.1.2.2.1.3',
    'ifMtu': '1.3.6.1.2.1.2.2.1.4',
    'ifSpeed': '1.3.6.1.2.1.2.2.1.5',
    'ifPhysAddress': '1.3.6.1.2.1.2.2.1.6',
    'ifAdminStatus': '1.3.6.1.2.1.2.2.1.7',
    'ifOperStatus': '1.3.6.1.2.1.2.2.1.8',
    'ifLastChange': '1.3.6.1.2.1.2.2.1.9',
    
    # 接口流量统计
    'ifInOctets': '1.3.6.1.2.1.2.2.1.10',
    'ifInUcastPkts': '1.3.6.1.2.1.2.2.1.11',
    'ifInNUcastPkts': '1.3.6.1.2.1.2.2.1.12',
    'ifInDiscards': '1.3.6.1.2.1.2.2.1.13',
    'ifInErrors': '1.3.6.1.2.1.2.2.1.14',
    'ifInUnknownProtos': '1.3.6.1.2.1.2.2.1.15',
    'ifOutOctets': '1.3.6.1.2.1.2.2.1.16',
    'ifOutUcastPkts': '1.3.6.1.2.1.2.2.1.17',
    'ifOutNUcastPkts': '1.3.6.1.2.1.2.2.1.18',
    'ifOutDiscards': '1.3.6.1.2.1.2.2.1.19',
    'ifOutErrors': '1.3.6.1.2.1.2.2.1.20',
    
    # IP 信息
    'ipForwarding': '1.3.6.1.2.1.4.1.0',
    'ipDefaultTTL': '1.3.6.1.2.1.4.2.0',
    'ipInReceives': '1.3.6.1.2.1.4.3.0',
    'ipInDelivers': '1.3.6.1.2.1.4.7.0',
    'ipOutRequests': '1.3.6.1.2.1.4.10.0',
    
    # ICMP 统计
    'icmpInMsgs': '1.3.6.1.2.1.5.1.0',
    'icmpOutMsgs': '1.3.6.1.2.1.5.14.0',
    
    # TCP 统计
    'tcpCurrEstab': '1.3.6.1.2.1.6.9.0',
    'tcpInSegs': '1.3.6.1.2.1.6.10.0',
    'tcpOutSegs': '1.3.6.1.2.1.6.11.0',
    
    # SNMP 统计
    'snmpInPkts': '1.3.6.1.2.1.11.1.0',
    'snmpOutPkts': '1.3.6.1.2.1.11.2.0',
    'snmpInGetRequests': '1.3.6.1.2.1.11.13.0',
    'snmpInGetNexts': '1.3.6.1.2.1.11.14.0',
    'snmpInGetResponses': '1.3.6.1.2.1.11.18.0',
    'snmpOutGetRequests': '1.3.6.1.2.1.11.19.0',
    'snmpOutGetResponses': '1.3.6.1.2.1.11.20.0',
}

# 华三(H3C) 私有 OIDs
H3C_OIDS = {
    # CPU 使用率
    'cpuUsage': '1.3.6.1.4.1.25506.2.6.1.1.1.1.6',
    'cpuUsage5Sec': '1.3.6.1.4.1.25506.2.6.1.1.1.1.5',
    'cpuUsage1Min': '1.3.6.1.4.1.25506.2.6.1.1.1.1.6',
    'cpuUsage5Min': '1.3.6.1.4.1.25506.2.6.1.1.1.1.7',
    
    # 内存使用率
    'memUsage': '1.3.6.1.4.1.25506.2.6.1.1.1.1.8',
    'memTotal': '1.3.6.1.4.1.25506.2.6.1.1.1.1.9',
    'memFree': '1.3.6.1.4.1.25506.2.6.1.1.1.1.10',
    
    # 设备信息
    'deviceModel': '1.3.6.1.4.1.25506.1.1.1.1.1',
    'deviceSerial': '1.3.6.1.4.1.25506.1.1.1.1.2',
    'deviceName': '1.3.6.1.4.1.25506.1.1.1.1.3',
    
    # 端口信息
    'portDescr': '1.3.6.1.4.1.25506.2.6.1.2.1.1.2',
    'portStatus': '1.3.6.1.4.1.25506.2.6.1.2.1.1.3',
    
    # VLAN 信息
    'vlanIndex': '1.3.6.1.4.1.25506.2.3.1.1',
    'vlanName': '1.3.6.1.4.1.25506.2.3.1.2',
    
    # MAC 地址表
    'macAddressTable': '1.3.6.1.4.1.25506.2.3.3.1',
    'macAddress': '1.3.6.1.4.1.25506.2.3.3.1.1.2',
    'macPort': '1.3.6.1.4.1.25506.2.3.3.1.1.3',
    'macVlan': '1.3.6.1.4.1.25506.2.3.3.1.1.4',
    
    # 温度
    'temperature': '1.3.6.1.4.1.25506.2.6.1.1.1.1.11',
}

# 华为私有 OIDs
HUAWEI_OIDS = {
    'cpuUsage': '1.3.6.1.4.1.2011.6.3.4.1.1.1',
    'memUsage': '1.3.6.1.4.1.2011.6.3.4.1.1.2',
    'temperature': '1.3.6.1.4.1.2011.6.3.4.1.1.3',
}

# 思科私有 OIDs
CISCO_OIDS = {
    'cpuUsage': '1.3.6.1.4.1.9.2.1.56.0',
    'cpuUsage5Min': '1.3.6.1.4.1.9.9.109.1.1.1.1.5',
    'memUsage': '1.3.6.1.4.1.9.9.48.1.1.1.5',
    'memFree': '1.3.6.1.4.1.9.9.48.1.1.1.6',
}

# MAC 地址相关 OIDs
MAC_OIDS = {
    'dot1dTpFdbTable': '1.3.6.1.2.1.17.4.3.1',
    'dot1dTpFdbAddress': '1.3.6.1.2.1.17.4.3.1.1',
    'dot1dTpFdbPort': '1.3.6.1.2.1.17.4.3.1.2',
    'dot1dTpFdbStatus': '1.3.6.1.2.1.17.4.3.1.3',
    'dot1dBasePortTable': '1.3.6.1.2.1.17.1.4.1',
    'dot1dBasePortIfIndex': '1.3.6.1.2.1.17.1.4.1.2',
}

# VLAN 相关 OIDs
VLAN_OIDS = {
    'dot1qVlanStaticTable': '1.3.6.1.2.1.17.7.1.4.3.1',
    'dot1qVlanStaticName': '1.3.6.1.2.1.17.7.1.4.3.1.1',
    'dot1qVlanStaticEgressPorts': '1.3.6.1.2.1.17.7.1.4.3.1.2',
    'dot1qPvid': '1.3.6.1.2.1.17.7.1.4.5.1.1',
}

# 常见厂商 OUI 前缀
OUI_PREFIXES = {
    '00:00:0C': 'Cisco',
    '00:01:63': 'Cisco',
    '00:05:5E': 'Cisco',
    '00:0A:41': 'Cisco',
    '00:0B:5F': 'Cisco',
    '00:0C:29': 'VMware',
    '00:0D:28': 'Cisco',
    '00:0E:0C': 'Cisco',
    '00:0F:23': 'Cisco',
    '00:10:11': 'Cisco',
    '00:11:20': 'Cisco',
    '00:12:00': 'Cisco',
    '00:13:19': 'Cisco',
    '00:14:1B': 'Cisco',
    '00:15:2B': 'Cisco',
    '00:16:32': 'Cisco',
    '00:17:A2': 'Cisco',
    '00:18:BA': 'Cisco',
    '00:19:2F': 'Cisco',
    '00:1A:A1': 'Cisco',
    '00:1B:21': 'Intel',
    '00:1C:C4': 'Intel',
    '00:1D:70': 'Cisco',
    '00:1E:4A': 'Cisco',
    '00:1E:BD': 'Cisco',
    '00:1F:6B': 'Cisco',
    '00:20:0D': 'Cisco',
    '00:21:1C': 'Cisco',
    '00:22:55': 'Cisco',
    '00:23:04': 'Cisco',
    '00:24:14': 'Cisco',
    '00:25:2C': 'Cisco',
    '00:26:0B': 'Cisco',
    '00:26:99': 'Cisco',
    '00:27:0D': 'Cisco',
    '00:28:5C': 'Cisco',
    '00:29:BD': 'Cisco',
    '00:2A:6A': 'Cisco',
    '00:2B:49': 'Cisco',
    '00:2C:C8': 'Cisco',
    '00:2D:84': 'Cisco',
    '00:2E:8B': 'Cisco',
    '00:50:56': 'VMware',
    '08:00:27': 'VirtualBox',
    '52:54:00': 'QEMU/KVM',
    '00:1A:A1': 'H3C',
    '00:1B:21': 'H3C',
    '00:1E:EC': 'H3C',
    '00:22:3A': 'H3C',
    '00:25:B3': 'H3C',
    '00:26:CB': 'H3C',
    '00:27:19': 'H3C',
    '00:0E:4F': 'Huawei',
    '00:1E:10': 'Huawei',
    '00:18:82': 'Huawei',
    '00:21:E9': 'Huawei',
    '00:25:B5': 'Huawei',
}

# 拓扑图颜色配置
TOPOLOGY_COLORS = {
    'switch': '#2563eb',
    'router': '#f59e0b',
    'firewall': '#ef4444',
    'ap': '#10b981',
    'server': '#8b5cf6',
    'other': '#64748b',
}

# ==================== 权限配置 ====================
PERMISSIONS = ['view', 'add', 'edit', 'delete', 'export', 'admin']

DEFAULT_PERMISSIONS = [
    ('admin', 'view', 1),
    ('admin', 'add', 1),
    ('admin', 'edit', 1),
    ('admin', 'delete', 1),
    ('admin', 'export', 1),
    ('admin', 'admin', 1),
    ('operator', 'view', 1),
    ('operator', 'add', 0),
    ('operator', 'edit', 1),
    ('operator', 'delete', 0),
    ('operator', 'export', 1),
    ('operator', 'admin', 0),
    ('viewer', 'view', 1),
    ('viewer', 'add', 0),
    ('viewer', 'edit', 0),
    ('viewer', 'delete', 0),
    ('viewer', 'export', 0),
    ('viewer', 'admin', 0),
]

# ==================== 导出字段配置 ====================
EXPORT_DEVICE_FIELDS = ['id', 'name', 'ip_address', 'device_type', 'vendor', 'model', 'location', 'status', 'last_check']
EXPORT_DEVICE_HEADERS = {
    'id': 'ID', 'name': '设备名称', 'ip_address': 'IP地址', 
    'device_type': '设备类型', 'vendor': '厂商', 'model': '型号',
    'location': '位置', 'status': '状态', 'last_check': '最后检查时间'
}

EXPORT_PORT_FIELDS = ['id', 'device_name', 'port_name', 'port_type', 'speed', 'admin_status', 'oper_status']
EXPORT_PORT_HEADERS = {
    'id': 'ID', 'device_name': '设备', 'port_name': '端口名称',
    'port_type': '类型', 'speed': '速率', 'admin_status': '管理状态',
    'oper_status': '运行状态'
}

EXPORT_VLAN_FIELDS = ['id', 'vlan_id', 'name', 'device_name', 'port_count']
EXPORT_VLAN_HEADERS = {
    'id': 'ID', 'vlan_id': 'VLAN ID', 'name': '名称',
    'device_name': '设备', 'port_count': '端口数'
}

# ==================== SNMP 配置 ====================
SNMP_DEFAULTS = {
    'port': 161,
    'timeout': 5,
    'retries': 3,
    'community': 'public',
}