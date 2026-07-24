/**
 * 网络设备监控系统 - 拓扑图模块
 * 版本: v0.0.2
 */

class TopologyGraph {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            width: this.container?.clientWidth || 1200,
            height: 600,
            nodeRadius: 30,
            linkDistance: 150,
            charge: -300,
            ...options
        };
        
        this.nodes = [];
        this.links = [];
        this.simulation = null;
        this.svg = null;
        this.g = null;
        this.zoom = null;
        
        this.colors = {
            switch: '#2563eb',
            router: '#f59e0b',
            firewall: '#ef4444',
            ap: '#10b981',
            server: '#8b5cf6',
            other: '#64748b'
        };
        
        this.statusColors = {
            online: '#10b981',
            offline: '#ef4444',
            unreachable: '#f59e0b',
            unknown: '#94a3b8'
        };
        
        if (this.container && typeof d3 !== 'undefined') {
            this.init();
        }
    }
    
    init() {
        // 清空容器
        this.container.innerHTML = '';
        
        // 创建SVG
        this.svg = d3.select(this.container)
            .append('svg')
            .attr('width', this.options.width)
            .attr('height', this.options.height)
            .attr('viewBox', [0, 0, this.options.width, this.options.height]);
        
        // 添加缩放行为
        this.zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                this.g.attr('transform', event.transform);
            });
        
        this.svg.call(this.zoom);
        
        // 创建主容器
        this.g = this.svg.append('g');
        
        // 添加箭头标记
        this.svg.append('defs').selectAll('marker')
            .data(['end'])
            .enter().append('marker')
            .attr('id', 'arrow')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 35)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('fill', '#94a3b8');
        
        // 初始化力导向模拟
        this.simulation = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(this.options.linkDistance))
            .force('charge', d3.forceManyBody().strength(this.options.charge))
            .force('center', d3.forceCenter(this.options.width / 2, this.options.height / 2))
            .force('collision', d3.forceCollide().radius(this.options.nodeRadius * 1.5));
    }
    
    setData(nodes, links) {
        this.nodes = nodes.map(n => ({...n}));
        this.links = links.map(l => ({...l}));
        this.render();
    }
    
    render() {
        // 清除旧元素
        this.g.selectAll('*').remove();
        
        // 绘制连线
        const link = this.g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(this.links)
            .enter().append('line')
            .attr('stroke', '#94a3b8')
            .attr('stroke-width', 2)
            .attr('marker-end', 'url(#arrow)');
        
        // 绘制节点组
        const node = this.g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(this.nodes)
            .enter().append('g')
            .attr('class', 'node')
            .call(d3.drag()
                .on('start', (event, d) => this.dragstarted(event, d))
                .on('drag', (event, d) => this.dragged(event, d))
                .on('end', (event, d) => this.dragended(event, d)));
        
        // 添加节点圆形
        node.append('circle')
            .attr('r', this.options.nodeRadius)
            .attr('fill', d => this.colors[d.device_type] || this.colors.other)
            .attr('stroke', d => this.statusColors[d.status] || this.statusColors.unknown)
            .attr('stroke-width', 4)
            .style('cursor', 'pointer');
        
        // 添加节点图标
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', 5)
            .attr('font-size', '20px')
            .attr('fill', 'white')
            .text(d => this.getDeviceIcon(d.device_type));
        
        // 添加节点标签
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', this.options.nodeRadius + 20)
            .attr('font-size', '12px')
            .attr('fill', '#334155')
            .attr('font-weight', '500')
            .text(d => d.name);
        
        // 添加IP标签
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', this.options.nodeRadius + 35)
            .attr('font-size', '10px')
            .attr('fill', '#64748b')
            .text(d => d.ip);
        
        // 点击事件
        node.on('click', (event, d) => {
            event.stopPropagation();
            this.onNodeClick(d);
        });
        
        // 双击事件
        node.on('dblclick', (event, d) => {
            event.stopPropagation();
            this.onNodeDblClick(d);
        });
        
        // 更新模拟
        this.simulation
            .nodes(this.nodes)
            .on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);
                
                node.attr('transform', d => `translate(${d.x},${d.y})`);
            });
        
        this.simulation.force('link').links(this.links);
        this.simulation.alpha(1).restart();
    }
    
    getDeviceIcon(type) {
        const icons = {
            switch: '☰',
            router: '⚲',
            firewall: '🛡',
            ap: '📡',
            server: '◈',
            other: '◉'
        };
        return icons[type] || icons.other;
    }
    
    dragstarted(event, d) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    
    dragended(event, d) {
        if (!event.active) this.simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
    
    onNodeClick(node) {
        // 触发节点选择事件
        const event = new CustomEvent('topology:nodeClick', { detail: node });
        this.container.dispatchEvent(event);
    }
    
    onNodeDblClick(node) {
        // 触发节点双击事件
        const event = new CustomEvent('topology:nodeDblClick', { detail: node });
        this.container.dispatchEvent(event);
    }
    
    zoomIn() {
        this.svg.transition().call(this.zoom.scaleBy, 1.2);
    }
    
    zoomOut() {
        this.svg.transition().call(this.zoom.scaleBy, 0.8);
    }
    
    resetZoom() {
        this.svg.transition().call(this.zoom.transform, d3.zoomIdentity);
    }
    
    fitToScreen() {
        const bounds = this.g.node().getBBox();
        const parent = this.svg.node().parentElement;
        const fullWidth = parent.clientWidth;
        const fullHeight = parent.clientHeight;
        
        const width = bounds.width;
        const height = bounds.height;
        const midX = bounds.x + width / 2;
        const midY = bounds.y + height / 2;
        
        if (width === 0 || height === 0) return;
        
        const scale = Math.min(
            fullWidth / width,
            fullHeight / height
        ) * 0.9;
        
        const translate = [
            fullWidth / 2 - scale * midX,
            fullHeight / 2 - scale * midY
        ];
        
        this.svg.transition().call(
            this.zoom.transform,
            d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
        );
    }
    
    highlightNode(nodeId) {
        this.g.selectAll('.node')
            .attr('opacity', d => d.id === nodeId ? 1 : 0.3);
        
        this.g.selectAll('.links line')
            .attr('opacity', d => 
                d.source.id === nodeId || d.target.id === nodeId ? 1 : 0.1
            );
    }
    
    clearHighlight() {
        this.g.selectAll('.node').attr('opacity', 1);
        this.g.selectAll('.links line').attr('opacity', 1);
    }
    
    destroy() {
        if (this.simulation) {
            this.simulation.stop();
        }
        if (this.container) {
            this.container.innerHTML = '';
        }
    }
}

// 拓扑图控制面板
class TopologyControls {
    constructor(graph, containerId) {
        this.graph = graph;
        this.container = document.getElementById(containerId);
        
        if (this.container) {
            this.init();
        }
    }
    
    init() {
        this.container.innerHTML = `
            <div class="topology-controls">
                <button class="btn btn-sm btn-outline" data-action="zoomIn">
                    <span>➕</span> 放大
                </button>
                <button class="btn btn-sm btn-outline" data-action="zoomOut">
                    <span>➖</span> 缩小
                </button>
                <button class="btn btn-sm btn-outline" data-action="reset">
                    <span>⟲</span> 重置
                </button>
                <button class="btn btn-sm btn-outline" data-action="fit">
                    <span>⛶</span> 自适应
                </button>
                <button class="btn btn-sm btn-outline" data-action="refresh">
                    <span>↻</span> 刷新
                </button>
            </div>
        `;
        
        this.container.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                this.executeAction(action);
            });
        });
    }
    
    executeAction(action) {
        switch (action) {
            case 'zoomIn':
                this.graph.zoomIn();
                break;
            case 'zoomOut':
                this.graph.zoomOut();
                break;
            case 'reset':
                this.graph.resetZoom();
                break;
            case 'fit':
                this.graph.fitToScreen();
                break;
            case 'refresh':
                this.refreshTopology();
                break;
        }
    }
    
    async refreshTopology() {
        try {
            const response = await fetch('/api/topology/data');
            const data = await response.json();
            
            if (data.success) {
                this.graph.setData(data.nodes, data.links);
                Toast.success('拓扑图已刷新');
            } else {
                Toast.error(data.message || '刷新失败');
            }
        } catch (error) {
            Toast.error('网络错误');
        }
    }
}

// 导出
window.TopologyGraph = TopologyGraph;
window.TopologyControls = TopologyControls;
