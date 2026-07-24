/**
 * 网络设备监控系统 - 主JavaScript文件
 * 版本: v0.0.2
 */

// 全局配置
const CONFIG = {
    API_BASE: '/api',
    REFRESH_INTERVAL: 30000, // 30秒
    CHART_COLORS: {
        primary: '#2563eb',
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#3b82f6'
    }
};

// Toast通知系统
const Toast = {
    container: null,
    
    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },
    
    show(message, type = 'info', duration = 3000) {
        this.init();
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span>${this.getIcon(type)}</span>
            <span>${message}</span>
        `;
        
        this.container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },
    
    getIcon(type) {
        const icons = {
            success: '✓',
            error: '✗',
            warning: '⚠',
            info: 'ℹ'
        };
        return icons[type] || icons.info;
    },
    
    success(message) { this.show(message, 'success'); },
    error(message) { this.show(message, 'error'); },
    warning(message) { this.show(message, 'warning'); },
    info(message) { this.show(message, 'info'); }
};

// API请求封装
const API = {
    async get(url, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;
        
        const response = await fetch(fullUrl, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    },
    
    async post(url, data = {}) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    },
    
    async delete(url) {
        const response = await fetch(url, {
            method: 'DELETE',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    }
};

// 模态框管理
const Modal = {
    open(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    
    close(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        }
    },
    
    closeAll() {
        document.querySelectorAll('.modal-overlay').forEach(modal => {
            modal.classList.remove('active');
        });
        document.body.style.overflow = '';
    }
};

// 表格组件
class DataTable {
    constructor(elementId, options = {}) {
        this.element = document.getElementById(elementId);
        this.options = {
            pageSize: 10,
            sortable: true,
            searchable: true,
            ...options
        };
        this.data = [];
        this.filteredData = [];
        this.currentPage = 1;
        this.sortColumn = null;
        this.sortDirection = 'asc';
        
        this.init();
    }
    
    init() {
        if (!this.element) return;
        this.render();
    }
    
    setData(data) {
        this.data = data;
        this.filteredData = [...data];
        this.currentPage = 1;
        this.render();
    }
    
    filter(searchTerm) {
        if (!searchTerm) {
            this.filteredData = [...this.data];
        } else {
            const term = searchTerm.toLowerCase();
            this.filteredData = this.data.filter(row => {
                return Object.values(row).some(val => 
                    String(val).toLowerCase().includes(term)
                );
            });
        }
        this.currentPage = 1;
        this.render();
    }
    
    sort(column) {
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortDirection = 'asc';
        }
        
        this.filteredData.sort((a, b) => {
            let aVal = a[column];
            let bVal = b[column];
            
            if (typeof aVal === 'string') {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }
            
            if (aVal < bVal) return this.sortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return this.sortDirection === 'asc' ? 1 : -1;
            return 0;
        });
        
        this.render();
    }
    
    render() {
        // 这里应该根据实际表格结构渲染
        // 简化版本，实际使用时需要自定义
    }
    
    getPaginatedData() {
        const start = (this.currentPage - 1) * this.options.pageSize;
        const end = start + this.options.pageSize;
        return this.filteredData.slice(start, end);
    }
    
    getTotalPages() {
        return Math.ceil(this.filteredData.length / this.options.pageSize);
    }
}

// 图表组件（基于Chart.js）
class ChartManager {
    constructor(elementId, type, options = {}) {
        this.element = document.getElementById(elementId);
        this.type = type;
        this.options = options;
        this.chart = null;
        
        if (this.element && typeof Chart !== 'undefined') {
            this.init();
        }
    }
    
    init() {
        const ctx = this.element.getContext('2d');
        this.chart = new Chart(ctx, {
            type: this.type,
            data: {
                labels: [],
                datasets: []
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                ...this.options
            }
        });
    }
    
    update(labels, datasets) {
        if (!this.chart) return;
        
        this.chart.data.labels = labels;
        this.chart.data.datasets = datasets;
        this.chart.update();
    }
    
    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }
}

// 设备状态刷新
class DeviceMonitor {
    constructor() {
        this.interval = null;
        this.callbacks = [];
    }
    
    start(interval = CONFIG.REFRESH_INTERVAL) {
        if (this.interval) return;
        
        this.interval = setInterval(() => {
            this.refresh();
        }, interval);
    }
    
    stop() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }
    
    async refresh() {
        try {
            const data = await API.get('/api/devices/status');
            this.callbacks.forEach(cb => cb(data));
        } catch (error) {
            console.error('Refresh failed:', error);
        }
    }
    
    onUpdate(callback) {
        this.callbacks.push(callback);
    }
}

// 表单验证
const FormValidator = {
    rules: {
        required(value) {
            return value && value.trim() !== '';
        },
        
        ip(value) {
            const pattern = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
            return pattern.test(value);
        },
        
        port(value) {
            const port = parseInt(value);
            return port >= 1 && port <= 65535;
        },
        
        mac(value) {
            const pattern = /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/;
            return pattern.test(value);
        },
        
        email(value) {
            const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return pattern.test(value);
        }
    },
    
    validate(formElement) {
        const errors = [];
        const inputs = formElement.querySelectorAll('[data-validate]');
        
        inputs.forEach(input => {
            const rules = input.dataset.validate.split(',');
            const value = input.value;
            
            rules.forEach(rule => {
                if (!this.rules[rule](value)) {
                    errors.push({
                        field: input.name,
                        message: input.dataset.errorMessage || `Invalid ${rule}`
                    });
                    input.classList.add('error');
                } else {
                    input.classList.remove('error');
                }
            });
        });
        
        return {
            valid: errors.length === 0,
            errors
        };
    }
};

// 工具函数
const Utils = {
    formatDate(date, format = 'YYYY-MM-DD HH:mm:ss') {
        const d = new Date(date);
        const pad = (n) => n.toString().padStart(2, '0');
        
        return format
            .replace('YYYY', d.getFullYear())
            .replace('MM', pad(d.getMonth() + 1))
            .replace('DD', pad(d.getDate()))
            .replace('HH', pad(d.getHours()))
            .replace('mm', pad(d.getMinutes()))
            .replace('ss', pad(d.getSeconds()));
    },
    
    formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
    },
    
    formatDuration(seconds) {
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        
        if (days > 0) return `${days}天${hours}小时`;
        if (hours > 0) return `${hours}小时${minutes}分钟`;
        return `${minutes}分钟`;
    },
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },
    
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },
    
    generateId() {
        return Math.random().toString(36).substr(2, 9);
    },
    
    copyToClipboard(text) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text);
        } else {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    }
};

// 侧边栏切换
function initSidebar() {
    const toggleBtn = document.getElementById('sidebarToggle');
    const sidebar = document.querySelector('.sidebar');
    
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }
}

// 搜索功能
function initSearch() {
    const searchInputs = document.querySelectorAll('[data-search]');
    
    searchInputs.forEach(input => {
        const target = input.dataset.search;
        const table = document.querySelector(target);
        
        if (table) {
            input.addEventListener('input', Utils.debounce(() => {
                const term = input.value.toLowerCase();
                const rows = table.querySelectorAll('tbody tr');
                
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(term) ? '' : 'none';
                });
            }, 300));
        }
    });
}

// 确认对话框
function confirmAction(message, onConfirm) {
    if (confirm(message)) {
        onConfirm();
    }
}

// 初始化
function init() {
    initSidebar();
    initSearch();
    
    // 关闭模态框
    document.querySelectorAll('.modal-close, [data-close-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modal = btn.closest('.modal-overlay');
            if (modal) {
                modal.classList.remove('active');
            }
        });
    });
    
    // 点击遮罩关闭
    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
}

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 导出全局对象
window.NetworkMonitor = {
    CONFIG,
    Toast,
    API,
    Modal,
    DataTable,
    ChartManager,
    DeviceMonitor,
    FormValidator,
    Utils,
    confirmAction
};
