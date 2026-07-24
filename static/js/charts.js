/**
 * 网络设备监控系统 - 图表模块
 * 版本: v0.0.2
 * 功能: 性能趋势图表、基线分析图表
 */

// 性能趋势图表
class PerformanceCharts {
    constructor() {
        this.charts = {};
        this.colors = {
            cpu: '#2563eb',
            memory: '#10b981',
            traffic: '#f59e0b',
            temperature: '#ef4444'
        };
    }
    
    // 创建CPU使用率趋势图
    createCpuChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'CPU使用率 (%)',
                    data: data.values,
                    borderColor: this.colors.cpu,
                    backgroundColor: this.colors.cpu + '20',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 2,
                    pointHoverRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `CPU: ${context.parsed.y.toFixed(1)}%`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 创建内存使用率趋势图
    createMemoryChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '内存使用率 (%)',
                    data: data.values,
                    borderColor: this.colors.memory,
                    backgroundColor: this.colors.memory + '20',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 2,
                    pointHoverRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 创建端口流量图
    createTrafficChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: '入站流量 (Mbps)',
                        data: data.inbound,
                        borderColor: '#10b981',
                        backgroundColor: '#10b98120',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    },
                    {
                        label: '出站流量 (Mbps)',
                        data: data.outbound,
                        borderColor: '#3b82f6',
                        backgroundColor: '#3b82f620',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `${context.dataset.label}: ${context.parsed.y.toFixed(2)} Mbps`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return value + ' Mbps';
                            }
                        }
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 创建温度趋势图
    createTemperatureChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '温度 (°C)',
                    data: data.values,
                    borderColor: this.colors.temperature,
                    backgroundColor: this.colors.temperature + '20',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 2,
                    pointHoverRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        ticks: {
                            callback: function(value) {
                                return value + '°C';
                            }
                        }
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 创建多指标对比图
    createMultiMetricChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'CPU (%)',
                        data: data.cpu,
                        borderColor: this.colors.cpu,
                        backgroundColor: 'transparent',
                        tension: 0.4,
                        pointRadius: 0,
                        yAxisID: 'y'
                    },
                    {
                        label: '内存 (%)',
                        data: data.memory,
                        borderColor: this.colors.memory,
                        backgroundColor: 'transparent',
                        tension: 0.4,
                        pointRadius: 0,
                        yAxisID: 'y'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 创建基线分析图
    createBaselineChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: '实际值',
                        data: data.actual,
                        borderColor: '#2563eb',
                        backgroundColor: 'transparent',
                        tension: 0.4,
                        pointRadius: 3
                    },
                    {
                        label: '基线 (平均值)',
                        data: data.baseline,
                        borderColor: '#10b981',
                        backgroundColor: 'transparent',
                        borderDash: [5, 5],
                        tension: 0.4,
                        pointRadius: 0
                    },
                    {
                        label: '上限',
                        data: data.upper,
                        borderColor: '#f59e0b',
                        backgroundColor: 'transparent',
                        borderDash: [2, 2],
                        tension: 0.4,
                        pointRadius: 0
                    },
                    {
                        label: '下限',
                        data: data.lower,
                        borderColor: '#f59e0b',
                        backgroundColor: 'transparent',
                        borderDash: [2, 2],
                        tension: 0.4,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 创建柱状图（用于设备对比）
    createBarChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: data.metric || '数值',
                    data: data.values,
                    backgroundColor: data.values.map(v => {
                        if (v > 80) return '#ef4444';
                        if (v > 60) return '#f59e0b';
                        return '#10b981';
                    }),
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 创建饼图（用于状态分布）
    createPieChart(elementId, data) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;
        
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
        }
        
        this.charts[elementId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: data.colors || [
                        '#10b981',
                        '#ef4444',
                        '#f59e0b',
                        '#94a3b8'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom'
                    }
                }
            }
        });
        
        return this.charts[elementId];
    }
    
    // 更新图表数据
    updateChart(elementId, newData) {
        if (this.charts[elementId]) {
            const chart = this.charts[elementId];
            chart.data.labels = newData.labels;
            chart.data.datasets.forEach((dataset, index) => {
                if (newData.datasets && newData.datasets[index]) {
                    dataset.data = newData.datasets[index].data;
                }
            });
            chart.update('none'); // 无动画更新
        }
    }
    
    // 销毁图表
    destroyChart(elementId) {
        if (this.charts[elementId]) {
            this.charts[elementId].destroy();
            delete this.charts[elementId];
        }
    }
    
    // 销毁所有图表
    destroyAll() {
        Object.keys(this.charts).forEach(key => {
            this.destroyChart(key);
        });
    }
}

// 导出
window.PerformanceCharts = PerformanceCharts;
