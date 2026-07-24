#!/usr/bin/env python3
"""
网络设备监控系统 - Web 应用
版本: v0.0.12
功能: SNMP 监控（命令行工具）+ SSH 配置备份 + 每10秒自动检查 + 端口本地备注 + 端口Down实时告警
新功能(v0.0.12):
  - 添加设备后自动获取端口列表
  - 端口管理支持本地描述和备注（不同步到交换机）
  - 每10秒检测端口状态，Down时在仪表盘显示告警
"""

from flask import Flask, render_template, request, jsonify, g, session, redirect, url_for, send_file
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import json
import sys
import os
import re
import threading
import time
import subprocess
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict

# 导入配置
from config import (
    VERSION, VERSION_DATE, DEVICE_TYPES, VENDOR_TYPES, SNMP_VERSIONS,
    DEVICE_STATUS, PORT_STATUS, ALERT_LEVELS, THRESHOLDS, MONITOR_INTERVALS,
    STANDARD_OIDS, H3C_OIDS, HUAWEI_OIDS, CISCO_OIDS, MAC_OIDS, VLAN_OIDS,
    PERMISSIONS, DEFAULT_PERMISSIONS, SNMP_DEFAULTS,
    EXPORT_DEVICE_FIELDS, EXPORT_DEVICE_HEADERS, EXPORT_PORT_FIELDS, EXPORT_PORT_HEADERS,
    OUI_PREFIXES, TOPOLOGY_COLORS
)

# 导出 Excel
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

# 获取程序运行目录
def get_base_path():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent

BASE_PATH = get_base_path()
DB_PATH = Path(os.environ.get('DB_PATH', '/data/network_monitor/network_monitor.db'))

app = Flask(__name__,
            template_folder=str(BASE_PATH / "templates"),
            static_folder=str(BASE_PATH / "static"))
app.secret_key = 'network-monitor-secret-key-2026-v5'

# ==================== 模板过滤器 ====================
@app.template_filter('format_bytes')
def format_bytes_filter(bytes):
    """格式化字节大小"""
    if not bytes or bytes == 0:
        return '-'
    bytes = int(bytes)
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    while bytes >= 1024 and i < len(units) - 1:
        bytes /= 1024
        i += 1
    return f'{bytes:.1f} {units[i]}'

@app.template_filter('format_speed')
def format_speed_filter(bps):
    """格式化速率 (bps)"""
    if not bps or bps == 0:
        return '-'
    units = ['bps', 'Kbps', 'Mbps', 'Gbps']
    i = 0
    while bps >= 1000 and i < len(units) - 1:
        bps /= 1000
        i += 1
    return f'{bps:.1f} {units[i]}'

# ==================== 全局变量 ====================
auto_checker = None
auto_checker_running = False

# ==================== 数据库操作 ====================

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    """关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """初始化数据库"""
    db = get_db()
    cursor = db.cursor()
    
    # 创建设备表 (SNMP-only)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ip_address TEXT NOT NULL UNIQUE,
            device_type TEXT NOT NULL,
            vendor TEXT NOT NULL,
            model TEXT,
            location TEXT,
            description TEXT,
            status TEXT DEFAULT 'unknown',
            last_check TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- SSH 配置 (v0.0.5: 仅用于配置备份)
            ssh_port INTEGER DEFAULT 22,
            ssh_username TEXT,
            ssh_password TEXT,
            ssh_enable_password TEXT,
            
            -- SNMP 配置 (v0.0.5: 用于监控和自动检查)
            snmp_version TEXT DEFAULT 'v2c',
            snmp_port INTEGER DEFAULT 161,
            community TEXT DEFAULT 'public',
            snmp_username TEXT,
            snmp_auth_key TEXT,
            snmp_priv_key TEXT,
            
            -- 系统信息 (SNMP 获取)
            sys_descr TEXT,
            sys_uptime INTEGER,
            sys_contact TEXT,
            sys_name TEXT,
            
            -- 性能数据 (SNMP 获取)
            cpu_usage INTEGER,
            mem_usage INTEGER,
            temperature INTEGER
        )
    ''')
    
    # 创建端口表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            port_name TEXT NOT NULL,
            port_index TEXT NOT NULL,
            port_type TEXT,
            speed TEXT,
            mtu INTEGER,
            description TEXT,
            admin_status TEXT DEFAULT 'unknown',
            oper_status TEXT DEFAULT 'unknown',
            last_change TIMESTAMP,
            
            -- 流量统计 (SNMP 获取)
            in_octets INTEGER DEFAULT 0,
            out_octets INTEGER DEFAULT 0,
            in_ucast_pkts INTEGER DEFAULT 0,
            out_ucast_pkts INTEGER DEFAULT 0,
            in_errors INTEGER DEFAULT 0,
            out_errors INTEGER DEFAULT 0,
            in_discards INTEGER DEFAULT 0,
            out_discards INTEGER DEFAULT 0,
            
            -- 速率计算
            in_rate INTEGER DEFAULT 0,
            out_rate INTEGER DEFAULT 0,
            
            -- v0.0.12: 本地描述和备注（不同步到交换机）
            local_description TEXT,
            local_notes TEXT,
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # 创建权限表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            permission TEXT NOT NULL,
            allowed INTEGER DEFAULT 0
        )
    ''')
    
    # 创建操作日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id INTEGER,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 创建监控日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            check_type TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建告警表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            is_resolved INTEGER DEFAULT 0,
            resolved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建性能历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            metric_type TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_unit TEXT,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建MAC地址表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mac_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL,
            vlan_id INTEGER,
            device_id INTEGER NOT NULL,
            port_name TEXT,
            port_index TEXT,
            mac_type TEXT DEFAULT 'learned',
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建VLAN表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vlans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            vlan_id INTEGER NOT NULL,
            vlan_name TEXT,
            vlan_type TEXT DEFAULT 'standard',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
            UNIQUE(device_id, vlan_id)
        )
    ''')
    
    # 创建拓扑链接表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS topology_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_device_id INTEGER NOT NULL,
            target_device_id INTEGER NOT NULL,
            source_port TEXT,
            target_port TEXT,
            link_type TEXT DEFAULT 'lldp',
            link_status TEXT DEFAULT 'up',
            bandwidth TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_device_id) REFERENCES devices(id) ON DELETE CASCADE,
            FOREIGN KEY (target_device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建配置备份表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            config_content TEXT,
            config_type TEXT DEFAULT 'running',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'success',
            size INTEGER,
            changed INTEGER DEFAULT 0,
            diff_content TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建基线统计表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS baseline_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            cpu_avg REAL,
            cpu_max REAL,
            cpu_min REAL,
            cpu_deviation REAL,
            memory_avg REAL,
            memory_max REAL,
            memory_min REAL,
            memory_deviation REAL,
            port_changes INTEGER,
            deviation_score REAL,
            last_compare TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    ''')
    
    # 创建巡检报告表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inspection_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type TEXT DEFAULT 'daily',
            report_date TIMESTAMP,
            total_devices INTEGER,
            online_devices INTEGER,
            offline_devices INTEGER,
            warning_devices INTEGER,
            total_alerts INTEGER,
            critical_alerts INTEGER,
            cpu_avg REAL,
            memory_avg REAL,
            port_changes INTEGER,
            config_changes INTEGER,
            summary TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 数据库迁移：为现有表添加 SSH 字段（v0.0.5 新增）
    try:
        # 检查 ssh_port 字段是否存在
        cursor.execute("SELECT ssh_port FROM devices LIMIT 1")
    except sqlite3.OperationalError:
        # 字段不存在，添加 SSH 相关字段
        print("数据库迁移：添加 SSH 配置字段...")
        cursor.execute("ALTER TABLE devices ADD COLUMN ssh_port INTEGER DEFAULT 22")
        cursor.execute("ALTER TABLE devices ADD COLUMN ssh_username TEXT")
        cursor.execute("ALTER TABLE devices ADD COLUMN ssh_password TEXT")
        cursor.execute("ALTER TABLE devices ADD COLUMN ssh_enable_password TEXT")
        db.commit()
        print("SSH 字段添加完成")
    
    # 数据库迁移：添加 ports.notes 字段（v0.0.11）
    try:
        cursor.execute("SELECT notes FROM ports LIMIT 1")
    except sqlite3.OperationalError:
        print("数据库迁移：添加 ports.notes 字段...")
        cursor.execute("ALTER TABLE ports ADD COLUMN notes TEXT DEFAULT ''")
        db.commit()
        print("ports.notes 字段添加完成")
    
    # 初始化默认用户
    cursor.execute('''
        INSERT OR IGNORE INTO users (id, username, password, role)
        VALUES (1, 'admin', ?, 'admin')
    ''', (generate_password_hash('admin123'),))
    
    # 初始化权限
    for role, perm, allowed in DEFAULT_PERMISSIONS:
        cursor.execute('''
            INSERT OR IGNORE INTO permissions (role, permission, allowed)
            VALUES (?, ?, ?)
        ''', (role, perm, allowed))
    
    db.commit()
    print(f"数据库初始化完成: {DB_PATH}")

# ==================== SNMP 监控类 ====================

class SNMPMonitor:
    """SNMP 监控器 - 使用 snmp 命令行工具（更轻量）"""
    
    def __init__(self):
        self.last_check_time = {}
        self.device_status = {}
        self.port_data = {}
        self.performance_data = {}
    
    def snmp_get(self, ip, oid, community='public', port=161, timeout=5, retries=3):
        """SNMP GET 请求 - 使用 snmpget 命令"""
        try:
            import subprocess
            result = subprocess.run(
                ['snmpget', '-v2c', '-c', community, '-t', str(timeout), '-r', str(retries),
                 f'{ip}:{port}', oid],
                capture_output=True,
                text=True,
                timeout=timeout + 2
            )
            
            if result.returncode != 0:
                return None
            
            # 解析输出：如 "SNMPv2-MIB::sysDescr.0 = STRING: H3C Switch"
            output = result.stdout.strip()
            if 'No Such Instance' in output or 'No Such Object' in output:
                return None
            
            # 提取值部分
            if '=' in output:
                value_part = output.split('=')[1].strip()
                # 去除类型标识
                if ':' in value_part:
                    value = value_part.split(':', 1)[1].strip()
                else:
                    value = value_part
                return value
            return output
        except subprocess.TimeoutExpired:
            return None
        except Exception as e:
            print(f"SNMP GET 错误 {ip} {oid}: {e}")
            return None
    
    def snmp_walk(self, ip, oid, community='public', port=161, timeout=5, retries=3):
        """SNMP WALK 请求 - 使用 snmpwalk 命令"""
        try:
            import subprocess
            result = subprocess.run(
                ['snmpwalk', '-v2c', '-c', community, '-t', str(timeout), '-r', str(retries),
                 f'{ip}:{port}', oid],
                capture_output=True,
                text=True,
                timeout=timeout * 3  # walk 需要更长时间
            )
            
            if result.returncode != 0:
                return []
            
            # 解析输出
            results = []
            for line in result.stdout.strip().split('\n'):
                if not line or 'No Such Instance' in line or 'No Such Object' in line:
                    continue
                
                # 解析格式：OID[index] = TYPE: value
                # 如 "IF-MIB::ifDescr.1 = STRING: GigabitEthernet0/0/1"
                if '=' in line:
                    # 提取索引
                    oid_part = line.split('=')[0].strip()
                    idx = oid_part.split('.')[-1] if '.' in oid_part else '0'
                    
                    # 提取值
                    value_part = line.split('=')[1].strip()
                    if ':' in value_part:
                        value = value_part.split(':', 1)[1].strip()
                    else:
                        value = value_part
                    
                    results.append((idx, value))
            
            return results
        except subprocess.TimeoutExpired:
            return []
        except Exception as e:
            print(f"SNMP WALK 错误 {ip} {oid}: {e}")
            return []
    
    def check_device(self, device, quick_mode=False):
        """检查单个设备状态
        
        Args:
            device: 设备信息字典
            quick_mode: 快速模式，只获取基本状态，不获取端口/VLAN/MAC详细信息
        """
        ip = device['ip_address']
        community = device['community'] or 'public'
        port = device['snmp_port'] or 161
        
        # 快速模式使用更短的超时时间；非快速模式总超时控制在10秒以内
        timeout = 2 if quick_mode else 3
        retries = 1 if quick_mode else 2
        
        result = {
            'status': 'unknown',
            'sys_descr': None,
            'sys_uptime': None,
            'sys_name': None,
            'cpu_usage': None,
            'mem_usage': None,
            'ports': [],
            'vlans': [],
            'macs': [],
            'error': None,
            'quick_mode': quick_mode
        }
        
        # 检查设备可达性 - 获取 sysDescr
        sys_descr = self.snmp_get(ip, STANDARD_OIDS['sysDescr'], community, port, timeout, retries)
        
        if sys_descr:
            result['status'] = 'online'
            result['sys_descr'] = sys_descr
            
            # 获取系统信息
            result['sys_name'] = self.snmp_get(ip, STANDARD_OIDS['sysName'], community, port, timeout, retries)
            uptime_str = self.snmp_get(ip, STANDARD_OIDS['sysUpTime'], community, port, timeout, retries)
            if uptime_str:
                try:
                    result['sys_uptime'] = int(uptime_str) // 100  # 转换为秒
                except:
                    pass
            
            # 根据厂商获取 CPU/内存
            vendor = device['vendor'] or 'other'
            if vendor == 'h3c':
                # 华三 CPU OID 是表结构，需要 WALK 获取第一个值
                cpu_list = self.snmp_walk(ip, H3C_OIDS['cpuUsage'], community, port, timeout, retries)
                mem_list = self.snmp_walk(ip, H3C_OIDS['memUsage'], community, port, timeout, retries)
                cpu = cpu_list[0][1] if cpu_list else None
                mem = mem_list[0][1] if mem_list else None
            elif vendor == 'huawei':
                # 华为 OID 也是表结构
                cpu_list = self.snmp_walk(ip, HUAWEI_OIDS['cpuUsage'], community, port, timeout, retries)
                mem_list = self.snmp_walk(ip, HUAWEI_OIDS['memUsage'], community, port, timeout, retries)
                cpu = cpu_list[0][1] if cpu_list else None
                mem = mem_list[0][1] if mem_list else None
            elif vendor == 'cisco':
                # 思科有单值 OID
                cpu = self.snmp_get(ip, CISCO_OIDS['cpuUsage'], community, port, timeout, retries)
                mem = self.snmp_get(ip, CISCO_OIDS['memUsage'], community, port, timeout, retries)
            else:
                cpu = None
                mem = None
            
            if cpu:
                try:
                    result['cpu_usage'] = int(cpu)
                except:
                    pass
            if mem:
                try:
                    result['mem_usage'] = int(mem)
                except:
                    pass
            
            # 快速模式跳过详细信息采集
            if not quick_mode:
                # 获取端口信息
                result['ports'] = self.get_port_info(ip, community, port)
                
                # 获取 VLAN 信息
                result['vlans'] = self.get_vlan_info(ip, community, port)
                
                # 获取 MAC 地址信息
                result['macs'] = self.get_mac_info(ip, community, port)
            
        else:
            result['status'] = 'offline'
            result['error'] = 'SNMP 无响应'
        
        return result
    
    def get_port_info(self, ip, community, port):
        """获取端口信息"""
        ports = []
        
        # 获取端口描述
        descr_list = self.snmp_walk(ip, STANDARD_OIDS['ifDescr'], community, port)
        if not descr_list:
            return ports
        
        # 获取端口状态
        admin_status_list = self.snmp_walk(ip, STANDARD_OIDS['ifAdminStatus'], community, port)
        oper_status_list = self.snmp_walk(ip, STANDARD_OIDS['ifOperStatus'], community, port)
        speed_list = self.snmp_walk(ip, STANDARD_OIDS['ifSpeed'], community, port)
        
        # 获取流量统计
        in_octets_list = self.snmp_walk(ip, STANDARD_OIDS['ifInOctets'], community, port)
        out_octets_list = self.snmp_walk(ip, STANDARD_OIDS['ifOutOctets'], community, port)
        in_errors_list = self.snmp_walk(ip, STANDARD_OIDS['ifInErrors'], community, port)
        out_errors_list = self.snmp_walk(ip, STANDARD_OIDS['ifOutErrors'], community, port)
        
        status_map = {'1': 'up', '2': 'down', '3': 'testing', '4': 'unknown', '5': 'dormant', '6': 'notPresent', '7': 'lowerLayerDown'}
        
        for idx, descr in descr_list:
            if not descr or descr == 'No Such Instance' or descr == 'No Such Object':
                continue
            
            port_info = {
                'index': idx,
                'name': descr,
                'admin_status': 'unknown',
                'oper_status': 'unknown',
                'speed': None,
                'in_octets': 0,
                'out_octets': 0,
                'in_errors': 0,
                'out_errors': 0
            }
            
            # 管理状态
            for a_idx, a_status in admin_status_list:
                if a_idx == idx:
                    port_info['admin_status'] = status_map.get(a_status, 'unknown')
                    break
            
            # 运行状态
            for o_idx, o_status in oper_status_list:
                if o_idx == idx:
                    port_info['oper_status'] = status_map.get(o_status, 'unknown')
                    break
            
            # 速率
            for s_idx, speed in speed_list:
                if s_idx == idx:
                    try:
                        speed_val = int(speed)
                        if speed_val > 0:
                            port_info['speed'] = f"{speed_val // 1000000} Mbps"
                    except:
                        pass
                    break
            
            # 流量
            for i_idx, in_oct in in_octets_list:
                if i_idx == idx:
                    try:
                        port_info['in_octets'] = int(in_oct)
                    except:
                        pass
                    break
            
            for o_idx, out_oct in out_octets_list:
                if o_idx == idx:
                    try:
                        port_info['out_octets'] = int(out_oct)
                    except:
                        pass
                    break
            
            for i_idx, in_err in in_errors_list:
                if i_idx == idx:
                    try:
                        port_info['in_errors'] = int(in_err)
                    except:
                        pass
                    break
            
            for o_idx, out_err in out_errors_list:
                if o_idx == idx:
                    try:
                        port_info['out_errors'] = int(out_err)
                    except:
                        pass
                    break
            
            # 只保留物理端口（排除虚拟端口）
            if port_info['name'] and not any(x in port_info['name'].lower() for x in ['vlan', 'loopback', 'null', 'cpu', 'stack']):
                ports.append(port_info)
        
        return ports
    
    def get_vlan_info(self, ip, community, port):
        """获取 VLAN 信息"""
        vlans = []
        
        # 尝试获取 VLAN 名称
        vlan_names = self.snmp_walk(ip, VLAN_OIDS['dot1qVlanStaticName'], community, port)
        
        for idx, name in vlan_names:
            try:
                vlan_id = int(idx.split('.')[0])
                if vlan_id > 0 and vlan_id < 4095:
                    vlans.append({
                        'vlan_id': vlan_id,
                        'name': name if name and name != 'No Such Instance' else f'VLAN{vlan_id}'
                    })
            except:
                pass
        
        # 如果没有获取到，尝试华三私有 OID
        if not vlans:
            vlan_index = self.snmp_walk(ip, H3C_OIDS['vlanIndex'], community, port)
            vlan_name = self.snmp_walk(ip, H3C_OIDS['vlanName'], community, port)
            
            for idx, vid in vlan_index:
                try:
                    vlan_id = int(vid)
                    vlan_name_val = None
                    for n_idx, n_val in vlan_name:
                        if n_idx == idx:
                            vlan_name_val = n_val
                            break
                    
                    if vlan_id > 0 and vlan_id < 4095:
                        vlans.append({
                            'vlan_id': vlan_id,
                            'name': vlan_name_val or f'VLAN{vlan_id}'
                        })
                except:
                    pass
        
        return vlans
    
    def get_mac_info(self, ip, community, port):
        """获取 MAC 地址信息"""
        macs = []
        
        # 获取 MAC 地址表
        mac_addresses = self.snmp_walk(ip, MAC_OIDS['dot1dTpFdbAddress'], community, port)
        mac_ports = self.snmp_walk(ip, MAC_OIDS['dot1dTpFdbPort'], community, port)
        
        # 端口映射
        port_if_index = self.snmp_walk(ip, MAC_OIDS['dot1dBasePortIfIndex'], community, port)
        port_map = {p_idx: if_idx for p_idx, if_idx in port_if_index}
        
        # 端口描述映射
        descr_list = self.snmp_walk(ip, STANDARD_OIDS['ifDescr'], community, port)
        descr_map = {idx: descr for idx, descr in descr_list}
        
        for idx, mac_hex in mac_addresses:
            try:
                # 转换 MAC 地址格式
                mac_parts = mac_hex.split()
                if len(mac_parts) == 6:
                    mac_addr = ':'.join([f'{int(x, 16):02X}' for x in mac_parts])
                else:
                    mac_addr = mac_hex
                
                # 获取端口
                port_num = None
                for p_idx, p_val in mac_ports:
                    if p_idx == idx:
                        port_num = p_val
                        break
                
                port_name = None
                if port_num:
                    if_index = port_map.get(port_num)
                    if if_index:
                        port_name = descr_map.get(if_index)
                
                if mac_addr and mac_addr != '00:00:00:00:00:00':
                    macs.append({
                        'mac': mac_addr,
                        'port': port_name or f'Port{port_num}',
                        'vlan': None  # VLAN 信息需要额外查询
                    })
            except:
                pass
        
        return macs

# ==================== SSH 配置获取类 ====================

# SSH 库检查
try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    print("警告: paramiko 未安装，SSH 配置备份功能不可用")

class SSHConfigFetcher:
    """SSH 配置获取器 - 仅用于配置备份"""
    
    # 各厂商获取配置的命令
    CONFIG_COMMANDS = {
        'h3c': 'display current-configuration',
        'huawei': 'display current-configuration',
        'cisco': 'show running-config',
        'ruijie': 'show running-config',
        'hpe': 'show running-config',
        'juniper': 'show configuration | display set',
        'arista': 'show running-config',
        'other': 'show running-config'
    }
    
    # 进入特权模式的命令
    ENABLE_COMMANDS = {
        'cisco': 'enable',
        'ruijie': 'enable',
        'hpe': 'enable'
    }
    
    def __init__(self):
        self.clients = {}
    
    def get_config(self, device):
        """
        通过 SSH 获取设备配置
        
        Args:
            device: 设备信息字典，包含 ip_address, ssh_port, ssh_username, ssh_password, vendor
        
        Returns:
            dict: {'success': bool, 'config': str, 'error': str}
        """
        if not PARAMIKO_AVAILABLE:
            return {'success': False, 'config': None, 'error': 'paramiko 未安装'}
        
        ip = device['ip_address']
        port = device.get('ssh_port', 22) or 22
        username = device.get('ssh_username')
        password = device.get('ssh_password')
        enable_password = device.get('ssh_enable_password')
        vendor = device.get('vendor', 'other')
        
        if not username or not password:
            return {'success': False, 'config': None, 'error': 'SSH 凭证未配置'}
        
        try:
            # 创建 SSH 客户端
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 连接设备
            client.connect(
                hostname=ip,
                port=port,
                username=username,
                password=password,
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            
            # 获取配置命令
            config_cmd = self.CONFIG_COMMANDS.get(vendor, 'show running-config')
            
            # 华三/华为需要特殊处理（分页）
            if vendor in ['h3c', 'huawei']:
                # 先发送取消分页命令
                channel = client.invoke_shell()
                time.sleep(1)
                channel.send('screen-length 0 temporary\n')
                time.sleep(1)
                channel.send(config_cmd + '\n')
                time.sleep(5)
                
                # 读取输出
                output = ''
                while channel.recv_ready():
                    output += channel.recv(65535).decode('utf-8', errors='ignore')
                    time.sleep(0.5)
                
                channel.close()
                config_content = output
            else:
                # 思科/锐捷等可能需要进入特权模式
                if vendor in self.ENABLE_COMMANDS and enable_password:
                    # 使用 shell 方式处理 enable
                    channel = client.invoke_shell()
                    time.sleep(1)
                    channel.send(self.ENABLE_COMMANDS[vendor] + '\n')
                    time.sleep(1)
                    if enable_password:
                        channel.send(enable_password + '\n')
                        time.sleep(1)
                    channel.send(config_cmd + '\n')
                    time.sleep(5)
                    
                    output = ''
                    while channel.recv_ready():
                        output += channel.recv(65535).decode('utf-8', errors='ignore')
                        time.sleep(0.5)
                    
                    channel.close()
                    config_content = output
                else:
                    # 直接执行命令
                    stdin, stdout, stderr = client.exec_command(config_cmd, timeout=60)
                    config_content = stdout.read().decode('utf-8', errors='ignore')
            
            client.close()
            
            # 清理配置内容（去除命令回显、控制字符等）
            config_content = self._clean_config(config_content, vendor)
            
            return {'success': True, 'config': config_content, 'error': None}
            
        except paramiko.AuthenticationException:
            return {'success': False, 'config': None, 'error': 'SSH 认证失败'}
        except paramiko.SSHException as e:
            return {'success': False, 'config': None, 'error': f'SSH 错误: {str(e)}'}
        except Exception as e:
            return {'success': False, 'config': None, 'error': f'连接失败: {str(e)}'}
    
    def _clean_config(self, config, vendor):
        """清理配置内容"""
        # 去除 ANSI 控制字符
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        config = ansi_escape.sub('', config)
        
        # 去除命令回显
        config_cmd = self.CONFIG_COMMANDS.get(vendor, 'show running-config')
        lines = config.split('\n')
        cleaned_lines = []
        skip_next = False
        
        for line in lines:
            # 跳过命令本身
            if config_cmd in line and len(line) < len(config_cmd) + 20:
                skip_next = True
                continue
            if skip_next and line.strip() == '':
                skip_next = False
                continue
            # 跳过提示符
            if line.strip().endswith('#') or line.strip().endswith('>'):
                continue
            if line.strip().startswith('<') and line.strip().endswith('>'):
                continue
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()

# 创建全局 SSH 获取器实例
ssh_fetcher = SSHConfigFetcher()

# ==================== 自动检查线程 ====================

class AutoChecker:
    """自动检查器 - 每分钟自动检查所有设备"""
    
    def __init__(self, interval=60):
        self.interval = interval
        self.running = False
        self.thread = None
        self.monitor = SNMPMonitor()
        self.check_count = 0
        self.last_check_time = None
    
    def start(self):
        """启动自动检查"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._check_loop, daemon=True)
        self.thread.start()
        print(f"自动检查已启动，间隔: {self.interval} 秒")
    
    def stop(self):
        """停止自动检查"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("自动检查已停止")
    
    def _check_loop(self):
        """检查循环"""
        while self.running:
            try:
                self._check_all_devices()
                self.check_count += 1
                self.last_check_time = datetime.now()
            except Exception as e:
                print(f"自动检查错误: {e}")
            
            # 等待下一次检查
            time.sleep(self.interval)
    
    def _check_all_devices(self):
        """检查所有设备"""
        db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        
        try:
            devices = db.execute('SELECT * FROM devices').fetchall()
            
            if not devices:
                return
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 自动检查 {len(devices)} 个设备...")
            
            for device in devices:
                result = self.monitor.check_device(dict(device))
                self._update_device_status(db, device['id'], result)
                self._update_port_data(db, device['id'], result['ports'])
                self._update_vlan_data(db, device['id'], result['vlans'])
                self._update_mac_data(db, device['id'], result['macs'])
                self._save_performance_history(db, device['id'], result)
                
                # 记录检查日志
                status = result['status']
                message = f"SNMP检查完成，状态: {status}"
                if result['error']:
                    message = result['error']
                
                db.execute('''
                    INSERT INTO monitor_logs (device_id, check_type, status, message, created_at)
                    VALUES (?, 'auto_check', ?, ?, ?)
                ''', (device['id'], status, message, datetime.now()))
                
                # 生成告警（如果需要）
                self._check_alerts(db, device['id'], result)
            
            db.commit()
            
        finally:
            db.close()
    
    def _update_device_status(self, db, device_id, result):
        """更新设备状态"""
        db.execute('''
            UPDATE devices SET 
                status = ?, 
                last_check = ?,
                sys_descr = ?,
                sys_uptime = ?,
                sys_name = ?,
                cpu_usage = ?,
                mem_usage = ?,
                updated_at = ?
            WHERE id = ?
        ''', (
            result['status'],
            datetime.now(),
            result['sys_descr'],
            result['sys_uptime'],
            result['sys_name'],
            result['cpu_usage'],
            result['mem_usage'],
            datetime.now(),
            device_id
        ))
    
    def _update_port_data(self, db, device_id, ports):
        """更新端口数据"""
        for port in ports:
            # 检查端口是否已存在
            existing = db.execute(
                'SELECT id FROM ports WHERE device_id = ? AND port_index = ?',
                (device_id, port['index'])
            ).fetchone()
            
            if existing:
                db.execute('''
                    UPDATE ports SET 
                        port_name = ?,
                        admin_status = ?,
                        oper_status = ?,
                        speed = ?,
                        in_octets = ?,
                        out_octets = ?,
                        in_errors = ?,
                        out_errors = ?,
                        updated_at = ?
                    WHERE id = ?
                ''', (
                    port['name'],
                    port['admin_status'],
                    port['oper_status'],
                    port['speed'],
                    port['in_octets'],
                    port['out_octets'],
                    port['in_errors'],
                    port['out_errors'],
                    datetime.now(),
                    existing['id']
                ))
            else:
                db.execute('''
                    INSERT INTO ports (device_id, port_name, port_index, admin_status, oper_status, speed, 
                                       in_octets, out_octets, in_errors, out_errors, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    device_id, port['name'], port['index'], 
                    port['admin_status'], port['oper_status'], port['speed'],
                    port['in_octets'], port['out_octets'], 
                    port['in_errors'], port['out_errors'],
                    datetime.now(), datetime.now()
                ))
    
    def _update_vlan_data(self, db, device_id, vlans):
        """更新 VLAN 数据"""
        for vlan in vlans:
            db.execute('''
                INSERT OR REPLACE INTO vlans (device_id, vlan_id, vlan_name, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (device_id, vlan['vlan_id'], vlan['name'], datetime.now()))
    
    def _update_mac_data(self, db, device_id, macs):
        """更新 MAC 地址数据"""
        for mac in macs:
            existing = db.execute(
                'SELECT id FROM mac_addresses WHERE device_id = ? AND mac_address = ?',
                (device_id, mac['mac'])
            ).fetchone()
            
            if existing:
                db.execute('''
                    UPDATE mac_addresses SET port_name = ?, last_seen = ?
                    WHERE id = ?
                ''', (mac['port'], datetime.now(), existing['id']))
            else:
                db.execute('''
                    INSERT INTO mac_addresses (mac_address, device_id, port_name, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                ''', (mac['mac'], device_id, mac['port'], datetime.now(), datetime.now()))
    
    def _save_performance_history(self, db, device_id, result):
        """保存性能历史"""
        if result['cpu_usage']:
            db.execute('''
                INSERT INTO performance_history (device_id, metric_type, metric_value, metric_unit, collected_at)
                VALUES (?, 'cpu', ?, '%', ?)
            ''', (device_id, result['cpu_usage'], datetime.now()))
        
        if result['mem_usage']:
            db.execute('''
                INSERT INTO performance_history (device_id, metric_type, metric_value, metric_unit, collected_at)
                VALUES (?, 'memory', ?, '%', ?)
            ''', (device_id, result['mem_usage'], datetime.now()))
    
    def _check_alerts(self, db, device_id, result):
        """检查并生成告警"""
        # 设备离线告警
        if result['status'] == 'offline':
            existing = db.execute(
                'SELECT id FROM alerts WHERE device_id = ? AND alert_type = "device_offline" AND is_resolved = 0',
                (device_id,)
            ).fetchone()
            
            if not existing:
                db.execute('''
                    INSERT INTO alerts (device_id, alert_type, severity, message, created_at)
                    VALUES (?, 'device_offline', 'critical', '设备无法通过 SNMP 访问', ?)
                ''', (device_id, datetime.now()))
        
        # CPU 告警
        if result['cpu_usage'] and result['cpu_usage'] > THRESHOLDS['cpu_critical']:
            db.execute('''
                INSERT INTO alerts (device_id, alert_type, severity, message, created_at)
                VALUES (?, 'cpu_critical', 'critical', ?, ?)
            ''', (device_id, f'CPU 使用率过高: {result["cpu_usage"]}%', datetime.now()))
        elif result['cpu_usage'] and result['cpu_usage'] > THRESHOLDS['cpu_high']:
            db.execute('''
                INSERT INTO alerts (device_id, alert_type, severity, message, created_at)
                VALUES (?, 'cpu_high', 'high', ?, ?)
            ''', (device_id, f'CPU 使用率偏高: {result["cpu_usage"]}%', datetime.now()))
        
        # 内存告警
        if result['mem_usage'] and result['mem_usage'] > THRESHOLDS['mem_critical']:
            db.execute('''
                INSERT INTO alerts (device_id, alert_type, severity, message, created_at)
                VALUES (?, 'mem_critical', 'critical', ?, ?)
            ''', (device_id, f'内存使用率过高: {result["mem_usage"]}%', datetime.now()))
        
        # 端口 Down 告警（v0.0.11 新增）
        if result['ports']:
            device = db.execute('SELECT name FROM devices WHERE id = ?', (device_id,)).fetchone()
            device_name = device['name'] if device else 'Unknown'
            
            for port in result['ports']:
                port_name = port.get('port_name', 'Unknown')
                oper_status = port.get('oper_status', 'unknown')
                admin_status = port.get('admin_status', 'unknown')
                
                # 只对管理状态为up但运行状态为down的端口告警（说明是异常down）
                if admin_status == 'up' and oper_status == 'down':
                    # 检查是否已有未解决的该端口告警
                    existing = db.execute(
                        'SELECT id FROM alerts WHERE device_id = ? AND alert_type = "port_down" '
                        'AND message LIKE ? AND is_resolved = 0',
                        (device_id, f'%{port_name}%')
                    ).fetchone()
                    
                    if not existing:
                        db.execute('''
                            INSERT INTO alerts (device_id, alert_type, severity, message, created_at)
                            VALUES (?, 'port_down', 'high', ?, ?)
                        ''', (device_id, f'端口 {port_name} 状态异常 (管理员up但运行down)', datetime.now()))
                        print(f"[告警] {device_name} 端口 {port_name} Down")
                
                # 端口恢复正常时，关闭相关告警
                elif oper_status == 'up':
                    db.execute(
                        'UPDATE alerts SET is_resolved = 1, resolved_at = ? '
                        'WHERE device_id = ? AND alert_type = "port_down" AND message LIKE ? AND is_resolved = 0',
                        (datetime.now(), device_id, f'%{port_name}%')
                    )
    
    def get_status(self):
        """获取自动检查状态"""
        return {
            'running': self.running,
            'check_count': self.check_count,
            'last_check_time': str(self.last_check_time) if self.last_check_time else None,
            'interval': self.interval
        }

# 创建全局自动检查器
auto_checker = AutoChecker(interval=MONITOR_INTERVALS['auto_check'])
monitor = SNMPMonitor()

# ==================== 端口状态监控线程 ====================

class PortStatusMonitor:
    """端口状态监控器 - 每10秒检测端口状态"""
    
    def __init__(self, interval=10):
        self.interval = interval
        self.running = False
        self.thread = None
        self.monitor = SNMPMonitor()
        self.check_count = 0
        self.last_check_time = None
        self.previous_port_status = {}  # 记录上次端口状态
    
    def start(self):
        """启动监控"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print(f"端口状态监控已启动，间隔: {self.interval} 秒")
    
    def stop(self):
        """停止监控"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("端口状态监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                self._check_port_status()
                self.check_count += 1
                self.last_check_time = datetime.now()
            except Exception as e:
                print(f"端口状态监控错误: {e}")
            
            time.sleep(self.interval)
    
    def _check_port_status(self):
        """检测所有设备的端口状态"""
        db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        
        try:
            # 只检测在线设备
            devices = db.execute(
                'SELECT * FROM devices WHERE status = "online"'
            ).fetchall()
            
            if not devices:
                return
            
            for device in devices:
                device_id = device['id']
                device_name = device['name']
                
                # 获取端口状态
                try:
                    result = self.monitor.check_device(dict(device))
                    ports = result.get('ports', [])
                    
                    for port in ports:
                        port_name = port.get('port_name', 'Unknown')
                        port_index = port.get('port_index', '')
                        oper_status = port.get('oper_status', 'unknown')
                        admin_status = port.get('admin_status', 'unknown')
                        
                        # 生成唯一键
                        port_key = f"{device_id}:{port_index}"
                        
                        # 检查状态变化
                        prev_status = self.previous_port_status.get(port_key, {})
                        prev_oper = prev_status.get('oper_status', 'unknown')
                        
                        # 状态从 up 变为 down 时告警（管理员状态为up的情况）
                        if admin_status == 'up' and oper_status == 'down' and prev_oper == 'up':
                            print(f"[端口告警] {device_name} - {port_name} 状态变更为 Down")
                            self._create_port_alert(db, device_id, port_name, 'down')
                        
                        # 状态从 down 变为 up 时，关闭相关告警
                        elif oper_status == 'up' and prev_oper == 'down':
                            print(f"[端口恢复] {device_name} - {port_name} 状态恢复为 Up")
                            self._resolve_port_alert(db, device_id, port_name)
                        
                        # 更新端口状态记录
                        self.previous_port_status[port_key] = {
                            'oper_status': oper_status,
                            'admin_status': admin_status
                        }
                        
                        # 更新数据库中的端口状态
                        db.execute('''
                            UPDATE ports SET oper_status = ?, admin_status = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE device_id = ? AND port_index = ?
                        ''', (oper_status, admin_status, device_id, port_index))
                    
                except Exception as e:
                    print(f"检测设备 {device_name} 端口状态失败: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    def _create_port_alert(self, db, device_id, port_name, status):
        """创建端口告警"""
        # 检查是否已有未解决的该端口告警
        existing = db.execute(
            'SELECT id FROM alerts WHERE device_id = ? AND alert_type = "port_down" '
            'AND message LIKE ? AND is_resolved = 0',
            (device_id, f'%{port_name}%')
        ).fetchone()
        
        if not existing:
            db.execute('''
                INSERT INTO alerts (device_id, alert_type, severity, message, created_at)
                VALUES (?, 'port_down', 'high', ?, ?)
            ''', (device_id, f'端口 {port_name} 状态变更为 Down', datetime.now()))
    
    def _resolve_port_alert(self, db, device_id, port_name):
        """关闭端口告警"""
        db.execute(
            'UPDATE alerts SET is_resolved = 1, resolved_at = ? '
            'WHERE device_id = ? AND alert_type = "port_down" AND message LIKE ? AND is_resolved = 0',
            (datetime.now(), device_id, f'%{port_name}%')
        )
    
    def get_status(self):
        """获取监控状态"""
        return {
            'running': self.running,
            'check_count': self.check_count,
            'last_check_time': str(self.last_check_time) if self.last_check_time else None,
            'interval': self.interval
        }

# 创建全局端口状态监控器
port_status_monitor = PortStatusMonitor(interval=10)

# ==================== 权限检查 ====================

def check_permission(permission):
    """检查用户权限"""
    if 'user_id' not in session:
        return False
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if not user:
        return False
    
    perm = db.execute(
        'SELECT allowed FROM permissions WHERE role = ? AND permission = ?',
        (user['role'], permission)
    ).fetchone()
    
    return perm and perm['allowed'] == 1

def permission_required(permission):
    """权限装饰器"""
    @wraps
    def decorator(f):
        def wrapped(*args, **kwargs):
            if not check_permission(permission):
                return jsonify({'success': False, 'message': '权限不足'}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator

def log_operation(action, target_type=None, target_id=None, details=None):
    """记录操作日志"""
    if 'user_id' in session:
        db = get_db()
        db.execute('''
            INSERT INTO operation_logs (user_id, action, target_type, target_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], action, target_type, target_id, details, datetime.now()))
        db.commit()

# ==================== 路由定义 ====================

@app.route('/')
def index():
    """首页"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            db.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now(), user['id']))
            db.commit()
            
            log_operation('login')
            return redirect(url_for('dashboard'))
        
        return render_template('login.html', error='用户名或密码错误')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """登出"""
    log_operation('logout')
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    """仪表盘"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    
    # 统计数据
    devices = db.execute('SELECT * FROM devices').fetchall()
    ports = db.execute('SELECT * FROM ports').fetchall()
    # v0.0.12: 获取告警时关联设备名称
    alerts = db.execute('''
        SELECT a.*, d.name as device_name, d.ip_address as device_ip
        FROM alerts a
        LEFT JOIN devices d ON a.device_id = d.id
        WHERE a.is_resolved = 0
        ORDER BY a.created_at DESC LIMIT 10
    ''').fetchall()
    logs = db.execute('SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT 10').fetchall()
    
    online_count = len([d for d in devices if d['status'] == 'online'])
    offline_count = len([d for d in devices if d['status'] == 'offline'])
    
    # 设备类型分布
    type_dist = defaultdict(int)
    for d in devices:
        type_dist[d['device_type']] += 1
    
    # 厂商分布
    vendor_dist = defaultdict(int)
    for d in devices:
        vendor_dist[d['vendor']] += 1
    
    # 自动检查状态
    checker_status = auto_checker.get_status()
    
    # 构建 stats 对象
    stats = {
        'total_devices': len(devices),
        'online_devices': online_count,
        'offline_devices': offline_count,
        'total_ports': len(ports),
        'active_alerts': len(alerts)
    }
    
    return render_template('dashboard.html',
        version=VERSION,
        stats=stats,
        total_devices=len(devices),
        online_devices=online_count,
        offline_devices=offline_count,
        total_ports=len(ports),
        active_alerts=len(alerts),
        device_types=dict(type_dist),
        vendors=dict(vendor_dist),
        alerts=[dict(a) for a in alerts],
        logs=[dict(l) for l in logs],
        checker_status=checker_status
    )

@app.route('/devices')
def devices():
    """设备管理"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()
    
    return render_template('devices.html',
        version=VERSION,
        devices=[dict(d) for d in devices],
        device_types=DEVICE_TYPES,
        vendors=VENDOR_TYPES,
        snmp_versions=SNMP_VERSIONS
    )

@app.route('/api/devices', methods=['GET'])
def api_devices():
    """API: 获取设备列表"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()
    
    return jsonify({
        'success': True,
        'devices': [dict(d) for d in devices]
    })

@app.route('/api/devices', methods=['POST'])
def api_device_add():
    """API: 添加设备"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('add'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    
    name = data.get('name')
    ip_address = data.get('ip_address')
    device_type = data.get('device_type', 'switch')
    vendor = data.get('vendor', 'h3c')
    location = data.get('location', '')
    description = data.get('description', '')
    
    # SNMP 配置（用于监控）
    snmp_version = data.get('snmp_version', 'v2c')
    snmp_port = data.get('snmp_port', 161)
    community = data.get('community', 'public')
    
    # SSH 配置（仅用于配置备份）
    ssh_port = data.get('ssh_port', 22)
    ssh_username = data.get('ssh_username', '')
    ssh_password = data.get('ssh_password', '')
    ssh_enable_password = data.get('ssh_enable_password', '')
    
    if not name or not ip_address:
        return jsonify({'success': False, 'message': '名称和IP地址必填'})
    
    db = get_db()
    
    # 检查是否已存在
    existing = db.execute('SELECT id FROM devices WHERE ip_address = ?', (ip_address,)).fetchone()
    if existing:
        return jsonify({'success': False, 'message': '设备IP已存在'})
    
    # 插入设备
    db.execute('''
        INSERT INTO devices (name, ip_address, device_type, vendor, location, description,
                             snmp_version, snmp_port, community,
                             ssh_port, ssh_username, ssh_password, ssh_enable_password,
                             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, ip_address, device_type, vendor, location, description,
          snmp_version, snmp_port, community,
          ssh_port, ssh_username, ssh_password, ssh_enable_password,
          datetime.now(), datetime.now()))
    db.commit()
    
    device_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    log_operation('add_device', 'device', device_id, f"添加设备 {name}")
    
    # v0.0.12: 添加设备后自动获取端口列表信息
    def fetch_ports_async():
        """后台异步获取端口信息"""
        try:
            db_async = sqlite3.connect(str(DB_PATH))
            db_async.row_factory = sqlite3.Row
            
            device = db_async.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
            if device:
                result = monitor.check_device(dict(device), quick_mode=False)
                
                # 保存端口信息
                if result.get('ports'):
                    for port in result['ports']:
                        # 检查端口是否已存在
                        existing_port = db_async.execute(
                            'SELECT id, local_description, local_notes FROM ports WHERE device_id = ? AND port_index = ?',
                            (device_id, port.get('port_index', ''))
                        ).fetchone()
                        
                        if existing_port:
                            # 更新端口信息，但保留本地描述和备注
                            db_async.execute('''
                                UPDATE ports SET 
                                    port_name = ?, port_type = ?, speed = ?, mtu = ?,
                                    description = ?, admin_status = ?, oper_status = ?,
                                    in_octets = ?, out_octets = ?,
                                    in_ucast_pkts = ?, out_ucast_pkts = ?,
                                    in_errors = ?, out_errors = ?,
                                    in_discards = ?, out_discards = ?,
                                    in_rate = ?, out_rate = ?,
                                    updated_at = ?
                                WHERE id = ?
                            ''', (
                                port.get('port_name'), port.get('port_type'), port.get('speed'),
                                port.get('mtu'), port.get('description'),
                                port.get('admin_status', 'unknown'), port.get('oper_status', 'unknown'),
                                port.get('in_octets', 0), port.get('out_octets', 0),
                                port.get('in_ucast_pkts', 0), port.get('out_ucast_pkts', 0),
                                port.get('in_errors', 0), port.get('out_errors', 0),
                                port.get('in_discards', 0), port.get('out_discards', 0),
                                port.get('in_rate', 0), port.get('out_rate', 0),
                                datetime.now(), existing_port['id']
                            ))
                        else:
                            # 插入新端口
                            db_async.execute('''
                                INSERT INTO ports (
                                    device_id, port_name, port_index, port_type, speed, mtu,
                                    description, admin_status, oper_status,
                                    in_octets, out_octets, in_ucast_pkts, out_ucast_pkts,
                                    in_errors, out_errors, in_discards, out_discards,
                                    in_rate, out_rate, created_at, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                device_id, port.get('port_name'), port.get('port_index', ''),
                                port.get('port_type'), port.get('speed'), port.get('mtu'),
                                port.get('description'),
                                port.get('admin_status', 'unknown'), port.get('oper_status', 'unknown'),
                                port.get('in_octets', 0), port.get('out_octets', 0),
                                port.get('in_ucast_pkts', 0), port.get('out_ucast_pkts', 0),
                                port.get('in_errors', 0), port.get('out_errors', 0),
                                port.get('in_discards', 0), port.get('out_discards', 0),
                                port.get('in_rate', 0), port.get('out_rate', 0),
                                datetime.now(), datetime.now()
                            ))
                    
                    db_async.commit()
                    print(f"设备 {name} 端口信息获取完成，共 {len(result['ports'])} 个端口")
                
                # 更新设备状态
                db_async.execute('''
                    UPDATE devices SET status = ?, last_check = ?, updated_at = ?
                    WHERE id = ?
                ''', (result.get('status', 'unknown'), datetime.now(), datetime.now(), device_id))
                db_async.commit()
                
            db_async.close()
        except Exception as e:
            print(f"获取设备 {name} 端口信息失败: {e}")
    
    # 启动后台线程获取端口信息
    thread = threading.Thread(target=fetch_ports_async, daemon=True)
    thread.start()
    
    return jsonify({'success': True, 'device_id': device_id, 'message': '设备添加成功，正在获取端口信息...'})

@app.route('/api/devices/<int:device_id>', methods=['GET'])
def api_device_get(device_id):
    """API: 获取设备详情"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    device = db.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    # 获取端口
    ports = db.execute('SELECT * FROM ports WHERE device_id = ?', (device_id,)).fetchall()
    
    # 获取 VLAN
    vlans = db.execute('SELECT * FROM vlans WHERE device_id = ?', (device_id,)).fetchall()
    
    # 获取 MAC
    macs = db.execute('SELECT * FROM mac_addresses WHERE device_id = ?', (device_id,)).fetchall()
    
    return jsonify({
        'success': True,
        'device': dict(device),
        'ports': [dict(p) for p in ports],
        'vlans': [dict(v) for v in vlans],
        'macs': [dict(m) for m in macs]
    })

@app.route('/api/devices/<int:device_id>', methods=['PUT'])
def api_device_update(device_id):
    """API: 更新设备"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    
    db = get_db()
    device = db.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    # 更新字段
    name = data.get('name', device['name'])
    ip_address = data.get('ip_address', device['ip_address'])
    device_type = data.get('device_type', device['device_type'])
    vendor = data.get('vendor', device['vendor'])
    location = data.get('location', device['location'])
    description = data.get('description', device['description'])
    community = data.get('community', device['community'])
    snmp_port = data.get('snmp_port', device['snmp_port'])
    
    # SSH 配置（仅用于配置备份）
    ssh_port = data.get('ssh_port', device['ssh_port'])
    ssh_username = data.get('ssh_username', device['ssh_username'])
    ssh_password = data.get('ssh_password', device['ssh_password'])
    ssh_enable_password = data.get('ssh_enable_password', device['ssh_enable_password'])
    
    db.execute('''
        UPDATE devices SET 
            name = ?, ip_address = ?, device_type = ?, vendor = ?,
            location = ?, description = ?, community = ?, snmp_port = ?,
            ssh_port = ?, ssh_username = ?, ssh_password = ?, ssh_enable_password = ?,
            updated_at = ?
        WHERE id = ?
    ''', (name, ip_address, device_type, vendor, location, description, 
          community, snmp_port,
          ssh_port, ssh_username, ssh_password, ssh_enable_password,
          datetime.now(), device_id))
    db.commit()
    
    log_operation('edit_device', 'device', device_id, f"更新设备 {name}")
    
    return jsonify({'success': True, 'message': '设备更新成功'})

@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
def api_device_delete(device_id):
    """API: 删除设备"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('delete'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    db = get_db()
    device = db.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    db.execute('DELETE FROM devices WHERE id = ?', (device_id,))
    db.commit()
    
    log_operation('delete_device', 'device', device_id, f"删除设备 {device['name']}")
    
    return jsonify({'success': True, 'message': '设备删除成功'})

@app.route('/api/auto-checker/status')
def api_checker_status():
    """API: 获取自动检查状态"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    return jsonify({
        'success': True,
        'status': auto_checker.get_status()
    })

@app.route('/api/auto-checker/start', methods=['POST'])
def api_checker_start():
    """API: 启动自动检查"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    auto_checker.start()
    log_operation('start_auto_checker')
    
    return jsonify({'success': True, 'message': '自动检查已启动'})

@app.route('/api/auto-checker/stop', methods=['POST'])
def api_checker_stop():
    """API: 停止自动检查"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    auto_checker.stop()
    log_operation('stop_auto_checker')
    
    return jsonify({'success': True, 'message': '自动检查已停止'})

@app.route('/api/devices/<int:device_id>/check', methods=['POST'])
def api_device_check(device_id):
    """API: 手动检查单个设备（快速模式，只获取基本状态）"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    device = db.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    # 使用快速模式检查，只获取基本状态，不获取端口/VLAN/MAC详细信息
    result = monitor.check_device(dict(device), quick_mode=False)
    
    # 更新设备状态
    db.execute('''
        UPDATE devices SET 
            status = ?, last_check = ?, sys_descr = ?, sys_uptime = ?,
            sys_name = ?, cpu_usage = ?, mem_usage = ?, updated_at = ?
        WHERE id = ?
    ''', (
        result['status'], datetime.now(), result['sys_descr'], result['sys_uptime'],
        result['sys_name'], result['cpu_usage'], result['mem_usage'],
        datetime.now(), device_id
    ))
    db.commit()
    
    log_operation('check_device', 'device', device_id)
    
    return jsonify({
        'success': True,
        'result': result,
        'message': f"设备检查完成，状态: {result['status']}"
    })

@app.route('/api/test_connection', methods=['POST'])
def api_test_connection():
    """API: 测试SNMP连接（添加设备前验证）"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    data = request.get_json()
    ip = data.get('ip', '').strip()
    port = data.get('port', 161)
    community = data.get('community', 'public')
    
    if not ip:
        return jsonify({'success': False, 'message': 'IP地址不能为空'}), 400
    
    try:
        # 尝试SNMP GET sysDescr（总超时控制在10秒以内）
        result = monitor.snmp_get(ip, STANDARD_OIDS['sysDescr'], community, port, timeout=8, retries=1)
        if result:
            sys_name = monitor.snmp_get(ip, STANDARD_OIDS['sysName'], community, port, timeout=2, retries=1)
            return jsonify({
                'success': True,
                'message': 'SNMP连接成功',
                'sys_descr': result,
                'sys_name': sys_name
            })
        else:
            return jsonify({
                'success': False,
                'message': '无法获取设备信息，请检查IP、Community和端口是否正确'
            }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'SNMP测试失败: {str(e)}'
        }), 200

@app.route('/ports')
def ports():
    """端口管理"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    # 获取所有设备列表用于筛选
    devices = db.execute('SELECT id, name FROM devices ORDER BY name').fetchall()
    
    # 获取筛选参数
    device_filter = request.args.get('device_id', '')
    status_filter = request.args.get('status', '')
    
    # 构建查询
    query = '''
        SELECT p.*, d.name as device_name, d.ip_address as device_ip
        FROM ports p
        JOIN devices d ON p.device_id = d.id
    '''
    conditions = []
    params = []
    
    if device_filter:
        conditions.append('p.device_id = ?')
        params.append(device_filter)
    
    if status_filter:
        conditions.append('p.oper_status = ?')
        params.append(status_filter)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    query += ' ORDER BY d.name, p.port_name'
    
    ports = db.execute(query, params).fetchall()
    
    return render_template('ports.html',
        version=VERSION,
        ports=[dict(p) for p in ports],
        port_status=PORT_STATUS,
        devices=[dict(d) for d in devices],
        current_device=device_filter,
        current_status=status_filter
    )

@app.route('/api/ports/<int:port_id>', methods=['PUT'])
def api_port_update(port_id):
    """API: 更新端口本地描述和备注（仅本地，不同步到交换机）"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    local_description = data.get('local_description', '').strip()
    local_notes = data.get('local_notes', '').strip()
    
    db = get_db()
    port = db.execute('SELECT * FROM ports WHERE id = ?', (port_id,)).fetchone()
    
    if not port:
        return jsonify({'success': False, 'message': '端口不存在'}), 404
    
    # v0.0.12: 更新本地描述和备注字段（不同步到交换机）
    db.execute('''
        UPDATE ports SET local_description = ?, local_notes = ?, updated_at = ?
        WHERE id = ?
    ''', (local_description, local_notes, datetime.now(), port_id))
    db.commit()
    
    log_operation('edit_port', 'port', port_id, 
                  f"更新端口 {port['port_name']} 本地描述/备注")
    
    return jsonify({
        'success': True,
        'message': '端口本地信息已更新（仅本地保存，不同步到交换机）'
    })

@app.route('/api/ports/<int:port_id>', methods=['GET'])
def api_port_get(port_id):
    """API: 获取端口详情"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    port = db.execute('''
        SELECT p.*, d.name as device_name, d.ip_address as device_ip
        FROM ports p
        JOIN devices d ON p.device_id = d.id
        WHERE p.id = ?
    ''', (port_id,)).fetchone()
    
    if not port:
        return jsonify({'success': False, 'message': '端口不存在'}), 404
    
    return jsonify({'success': True, 'port': dict(port)})

@app.route('/api/ports/batch_update', methods=['POST'])
def api_ports_batch_update():
    """API: 批量更新端口本地描述和备注"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('edit'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    ports_data = data.get('ports', [])
    
    db = get_db()
    updated_count = 0
    
    for p in ports_data:
        port_id = p.get('id')
        local_description = p.get('local_description', '').strip()
        local_notes = p.get('local_notes', '').strip()
        
        if port_id:
            db.execute('''
                UPDATE ports SET local_description = ?, local_notes = ?, updated_at = ?
                WHERE id = ?
            ''', (local_description, local_notes, datetime.now(), port_id))
            updated_count += 1
    
    db.commit()
    
    return jsonify({
        'success': True,
        'message': f'已更新 {updated_count} 个端口信息'
    })

@app.route('/logs')
def logs():
    """监控日志"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    logs = db.execute('''
        SELECT m.*, d.name as device_name
        FROM monitor_logs m
        LEFT JOIN devices d ON m.device_id = d.id
        ORDER BY m.created_at DESC
        LIMIT 100
    ''').fetchall()
    
    return render_template('logs.html',
        version=VERSION,
        logs=[dict(l) for l in logs]
    )

@app.route('/alerts')
def alerts():
    """告警管理"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    alerts = db.execute('''
        SELECT a.*, d.name as device_name, d.ip_address as device_ip
        FROM alerts a
        JOIN devices d ON a.device_id = d.id
        ORDER BY a.created_at DESC
    ''').fetchall()
    
    return render_template('alerts.html',
        version=VERSION,
        alerts=[dict(a) for a in alerts],
        alert_levels=ALERT_LEVELS
    )

@app.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
def api_alert_resolve(alert_id):
    """API: 解决告警"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    db.execute('''
        UPDATE alerts SET is_resolved = 1, resolved_at = ? WHERE id = ?
    ''', (datetime.now(), alert_id))
    db.commit()
    
    return jsonify({'success': True, 'message': '告警已标记为已解决'})

@app.route('/performance')
def performance():
    """性能监控"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices WHERE status = "online"').fetchall()
    
    return render_template('performance.html',
        version=VERSION,
        devices=[dict(d) for d in devices]
    )

@app.route('/api/performance/history/<int:device_id>')
def api_performance_history(device_id):
    """API: 获取性能历史"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    
    # 获取最近 24 小时的数据
    start_time = datetime.now() - timedelta(hours=24)
    
    history = db.execute('''
        SELECT * FROM performance_history 
        WHERE device_id = ? AND collected_at >= ?
        ORDER BY collected_at ASC
    ''', (device_id, start_time)).fetchall()
    
    return jsonify({
        'success': True,
        'history': [dict(h) for h in history]
    })

@app.route('/mac')
def mac():
    """MAC 地址管理"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    macs = db.execute('''
        SELECT m.*, d.name as device_name, d.ip_address as device_ip
        FROM mac_addresses m
        JOIN devices d ON m.device_id = d.id
        ORDER BY m.last_seen DESC
        LIMIT 500
    ''').fetchall()
    
    return render_template('mac.html',
        version=VERSION,
        macs=[dict(m) for m in macs]
    )

@app.route('/vlan')
def vlan():
    """VLAN 管理"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    vlans = db.execute('''
        SELECT v.*, d.name as device_name, d.ip_address as device_ip
        FROM vlans v
        JOIN devices d ON v.device_id = d.id
        ORDER BY v.vlan_id ASC
    ''').fetchall()
    
    return render_template('vlan.html',
        version=VERSION,
        vlans=[dict(v) for v in vlans]
    )

@app.route('/users')
def users():
    """用户管理"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if not check_permission('admin'):
        return render_template('error.html', message='权限不足'), 403
    
    db = get_db()
    users = db.execute('SELECT * FROM users').fetchall()
    
    return render_template('users.html',
        version=VERSION,
        users=[dict(u) for u in users]
    )

@app.route('/api/export/devices')
def api_export_devices():
    """API: 导出设备列表"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    if not check_permission('export'):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    if not EXCEL_AVAILABLE:
        return jsonify({'success': False, 'message': 'Excel 导出功能不可用'}), 500
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "设备列表"
    
    # 写入表头
    headers = [EXPORT_DEVICE_HEADERS.get(f, f) for f in EXPORT_DEVICE_FIELDS]
    ws.append(headers)
    
    # 设置表头样式
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
    
    # 写入数据
    for device in devices:
        row = []
        for field in EXPORT_DEVICE_FIELDS:
            value = device[field]
            if field in ['created_at', 'updated_at', 'last_check'] and value:
                value = str(value)
            row.append(value or '')
        ws.append(row)
    
    # 调整列宽
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # 保存文件
    export_path = f'/tmp/network_devices_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    wb.save(export_path)
    
    log_operation('export_devices', details=f"导出 {len(devices)} 个设备")
    
    return send_file(export_path, as_attachment=True, download_name='network_devices.xlsx')

@app.route('/settings')
def settings():
    """系统设置"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if not check_permission('admin'):
        return render_template('error.html', message='权限不足'), 403
    
    return render_template('settings.html',
        version=VERSION,
        monitor_intervals=MONITOR_INTERVALS,
        thresholds=THRESHOLDS,
        checker_status=auto_checker.get_status()
    )

# ==================== 高级功能路由 ====================

@app.route('/topology')
def topology():
    """网络拓扑图"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices').fetchall()
    links = db.execute('SELECT * FROM topology_links').fetchall()
    
    stats = {
        'total_devices': len(devices),
        'total_links': len(links),
        'active_links': len([l for l in links if l['link_type'] == 'lldp']),
        'down_links': 0
    }
    
    device_list = []
    for d in devices:
        device_list.append({
            'id': d['id'],
            'name': d['name'],
            'ip_address': d['ip_address'],
            'device_type': d['device_type'],
            'status': d['status'] or 'unknown',
            'vendor': d['vendor'],
            'model': d['model'],
            'location': d['location'],
            'cpu_usage': d['cpu_usage'],
            'mem_usage': d['mem_usage']
        })
    
    link_list = []
    for l in links:
        link_list.append({
            'id': l['id'],
            'source_device_id': l['source_device_id'],
            'target_device_id': l['target_device_id'],
            'source_port': l['source_port'],
            'target_port': l['target_port'],
            'link_status': 'up'
        })
    
    return render_template('topology.html', version=VERSION, stats=stats, 
                          devices=device_list, links=link_list)

@app.route('/api/topology')
def api_topology():
    """API: 获取拓扑数据"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices').fetchall()
    nodes = []
    for d in devices:
        nodes.append({
            'id': d['id'],
            'name': d['name'],
            'ip_address': d['ip_address'],
            'device_type': d['device_type'],
            'status': d['status'] or 'unknown',
            'vendor': d['vendor']
        })
    
    links = db.execute('SELECT * FROM topology_links').fetchall()
    edges = []
    for l in links:
        edges.append({
            'id': l['id'],
            'source': l['source_device_id'],
            'target': l['target_device_id'],
            'source_port': l['source_port'],
            'target_port': l['target_port']
        })
    
    return jsonify({'success': True, 'topology': {'nodes': nodes, 'links': edges}})

@app.route('/backup')
def backup():
    """配置备份"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('backup.html', version=VERSION)

@app.route('/api/backups')
def api_backups():
    """API: 获取备份列表"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices').fetchall()
    
    backup_list = []
    total_backups = 0
    last_backup = None
    
    for d in devices:
        backups = db.execute('''
            SELECT * FROM config_backups 
            WHERE device_id = ? 
            ORDER BY created_at DESC
        ''', (d['id'],)).fetchall()
        
        latest = backups[0] if backups else None
        total_backups += len(backups)
        
        if latest:
            if not last_backup or latest['created_at'] > last_backup:
                last_backup = str(latest['created_at'])
        
        backup_list.append({
            'id': d['id'],
            'name': d['name'],
            'ip_address': d['ip_address'],
            'vendor': d['vendor'],
            'backup_status': 'success' if backups else 'none',
            'last_backup': str(latest['created_at']) if latest else None,
            'backup_count': len(backups)
        })
    
    return jsonify({
        'success': True,
        'devices': backup_list,
        'total_backups': total_backups,
        'last_backup': last_backup or '-',
        'changes': 0
    })

@app.route('/api/devices/<int:device_id>/backup', methods=['POST'])
def api_device_backup(device_id):
    """API: 备份设备配置 (使用 SSH 获取真实配置)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    device = db.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    device_dict = dict(device)
    
    # 尝试通过 SSH 获取真实配置
    if device_dict.get('ssh_username') and device_dict.get('ssh_password'):
        result = ssh_fetcher.get_config(device_dict)
        
        if result['success']:
            config_content = result['config']
            status = 'success'
            size = len(config_content)
            message = 'SSH 配置备份成功'
        else:
            # SSH 失败，降级为 SNMP 信息备份
            config_content = f"# SSH 备份失败: {result['error']}\n# 降级为 SNMP 信息备份\n# 时间: {datetime.now()}\n# 设备: {device['name']}\n# IP: {device['ip_address']}\n# 系统描述: {device['sys_descr'] or 'N/A'}\n# CPU: {device['cpu_usage'] or 'N/A'}%\n# 内存: {device['mem_usage'] or 'N/A'}%"
            status = 'partial'
            size = len(config_content)
            message = f'SSH 失败 ({result["error"]})，已保存 SNMP 信息'
    else:
        # 未配置 SSH，使用 SNMP 信息
        config_content = f"# 未配置 SSH 凭证，仅保存 SNMP 信息\n# 时间: {datetime.now()}\n# 设备: {device['name']}\n# IP: {device['ip_address']}\n# 系统描述: {device['sys_descr'] or 'N/A'}\n# CPU: {device['cpu_usage'] or 'N/A'}%\n# 内存: {device['mem_usage'] or 'N/A'}%"
        status = 'snmp_only'
        size = len(config_content)
        message = '未配置 SSH，已保存 SNMP 信息'
    
    db.execute('''
        INSERT INTO config_backups (device_id, config_content, created_at, status, size)
        VALUES (?, ?, ?, ?, ?)
    ''', (device_id, config_content, datetime.now(), status, size))
    db.commit()
    
    log_operation('config_backup', target_type='device', target_id=device_id, details=message)
    
    return jsonify({'success': True, 'message': message, 'status': status, 'size': size})

@app.route('/api/devices/<int:device_id>/backups')
def api_device_backups(device_id):
    """API: 获取设备备份历史"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    backups = db.execute('''
        SELECT * FROM config_backups 
        WHERE device_id = ? 
        ORDER BY created_at DESC
    ''', (device_id,)).fetchall()
    
    return jsonify({
        'success': True,
        'backups': [dict(b) for b in backups]
    })

@app.route('/baseline')
def baseline():
    """基线对比"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('baseline.html', version=VERSION)

@app.route('/api/baseline')
def api_baseline():
    """API: 获取基线数据"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices').fetchall()
    
    baseline_list = []
    normal = 0
    warning = 0
    critical = 0
    no_baseline = 0
    
    for d in devices:
        baseline = db.execute('''
            SELECT * FROM baseline_stats 
            WHERE device_id = ? 
            ORDER BY created_at DESC LIMIT 1
        ''', (d['id'],)).fetchone()
        
        score = baseline['deviation_score'] if baseline else None
        
        if baseline:
            if score < 20:
                normal += 1
            elif score < 50:
                warning += 1
            else:
                critical += 1
        else:
            no_baseline += 1
        
        baseline_list.append({
            'device_id': d['id'],
            'device_name': d['name'],
            'ip_address': d['ip_address'],
            'baseline_time': str(baseline['created_at']) if baseline else None,
            'deviation_score': score,
            'status': 'normal' if baseline and score < 20 else 'warning' if baseline and score < 50 else 'critical' if baseline else 'no_baseline'
        })
    
    return jsonify({
        'success': True,
        'baselines': baseline_list,
        'normal': normal,
        'warning': warning,
        'critical': critical,
        'no_baseline': no_baseline
    })

@app.route('/api/baseline/<int:device_id>')
def api_baseline_device(device_id):
    """API: 获取设备基线详情"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    device = db.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    baseline = db.execute('''
        SELECT * FROM baseline_stats 
        WHERE device_id = ? 
        ORDER BY created_at DESC LIMIT 1
    ''', (device_id,)).fetchone()
    
    return jsonify({
        'success': True,
        'device_name': device['name'],
        'baseline_time': str(baseline['created_at']) if baseline else None,
        'cpu_avg': baseline['cpu_avg'] if baseline else None,
        'memory_avg': baseline['memory_avg'] if baseline else None,
        'deviation_score': baseline['deviation_score'] if baseline else None
    })

@app.route('/report')
def report():
    """巡检报告"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('report.html', version=VERSION)

@app.route('/api/reports')
def api_reports():
    """API: 获取报告列表"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    reports = db.execute('''
        SELECT * FROM inspection_reports 
        ORDER BY created_at DESC
    ''').fetchall()
    
    return jsonify({
        'success': True,
        'reports': [dict(r) for r in reports]
    })

@app.route('/api/reports/create', methods=['POST'])
def api_report_create():
    """API: 创建巡检报告"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    db = get_db()
    devices = db.execute('SELECT * FROM devices').fetchall()
    alerts = db.execute('SELECT * FROM alerts WHERE is_resolved = 0').fetchall()
    
    online = len([d for d in devices if d['status'] == 'online'])
    offline = len([d for d in devices if d['status'] == 'offline'])
    warning = len([d for d in devices if d['status'] == 'unreachable'])
    
    summary = f"巡检报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    summary += f"设备总数: {len(devices)}, 在线: {online}, 离线: {offline}, 异常: {warning}\n"
    summary += f"活跃告警: {len(alerts)}"
    
    db.execute('''
        INSERT INTO inspection_reports 
        (report_type, report_date, total_devices, online_devices, offline_devices, 
         warning_devices, total_alerts, critical_alerts, summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('auto', datetime.now(), len(devices), online, offline, warning, 
          len(alerts), 0, summary, datetime.now()))
    db.commit()
    
    return jsonify({'success': True, 'message': '报告创建成功'})

# ==================== 启动 ====================

if __name__ == '__main__':
    # 确保数据目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # 初始化数据库
    with app.app_context():
        init_db()
    
    # 启动自动检查（设备状态）
    auto_checker.start()
    
    # v0.0.12: 启动端口状态监控（每10秒检测端口Down告警）
    port_status_monitor.start()
    
    try:
        print(f"网络设备监控系统 v{VERSION} 启动中...")
        print(f"数据库: {DB_PATH}")
        print(f"访问地址: http://0.0.0.0:5002")
        print(f"设备状态检查: 每 {MONITOR_INTERVALS['auto_check']} 秒")
        print(f"端口状态监控: 每 {port_status_monitor.interval} 秒 (检测端口Down告警)")
        app.run(host='0.0.0.0', port=5002, debug=False)
    finally:
        auto_checker.stop()
        port_status_monitor.stop()