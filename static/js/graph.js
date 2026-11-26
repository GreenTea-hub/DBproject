/* 全组唯一的图渲染函数。负责人：P5。
 * 所有出图接口返回的都是 7.4 节的结构：{nodes, links, categories}，
 * 因此五个人的接口都调用这一个函数，不要各写一套 ECharts 配置。
 */

const FACTION_COLORS = { '魏': '#1f6fd0', '蜀': '#c0392b', '吴': '#1e8e5a', '群雄': '#7f8c8d' };

let _chart = null;

/**
 * @param {string} domId   容器元素 id
 * @param {object} payload {nodes, links, categories}
 * @param {object} opts    {height, onNodeClick}
 */
function renderGraph(domId, payload, opts = {}) {
  const el = document.getElementById(domId);
  if (!el) return null;
  if (typeof echarts === 'undefined') {
    el.innerHTML = '<p class="empty">ECharts 未加载，请检查 static/vendor/ 或网络连接</p>';
    return null;
  }

  const nodes = (payload.nodes || []).map(n => ({
    id: n.id,
    name: n.label || n.id,
    category: n.category || '群雄',
    value: n.value || 1,
    symbolSize: 12 + Math.min(30, (n.value || 1) * 2),
    label: { show: true, fontSize: 12 },
  }));

  const links = (payload.links || []).map(l => ({
    source: l.source,
    target: l.target,
    value: l.value,
    label: { show: true, formatter: l.label || '', fontSize: 10, color: '#6b7280' },
    lineStyle: { width: Math.max(1, Math.min(4, (l.value || 1) / 25)), curveness: 0.08 },
  }));

  const categories = (payload.categories || []).map(c => ({
    name: c.name,
    itemStyle: { color: FACTION_COLORS[c.name] || FACTION_COLORS['群雄'] },
  }));

  if (_chart) _chart.dispose();
  _chart = echarts.init(el, null, { renderer: 'canvas' });

  _chart.setOption({
    tooltip: {
      formatter: params => {
        if (params.dataType === 'edge') {
          return `${params.data.source} — ${params.data.target}<br/>${params.data.label.formatter || ''}`;
        }
        return `${params.name}`;
      },
    },
    legend: [{ data: categories.map(c => c.name), bottom: 0 }],
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      categories,
      data: nodes,
      links,
      force: { repulsion: 260, edgeLength: [60, 140], gravity: 0.08 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
      lineStyle: { color: '#c7cbd1', opacity: 0.8 },
    }],
  });

  if (opts.onNodeClick) {
    _chart.on('click', params => {
      if (params.dataType === 'node') opts.onNodeClick(params.name);
    });
  }

  window.addEventListener('resize', () => _chart && _chart.resize());
  return _chart;
}

/** 路径结果高亮：把接口返回的节点序列画成一条粗线 */
function renderPath(domId, pathData) {
  const names = pathData.nodes || [];
  const nodes = names.map((n, i) => ({
    name: n,
    category: i === 0 || i === names.length - 1 ? '蜀' : '群雄',
    symbolSize: i === 0 || i === names.length - 1 ? 34 : 24,
    label: { show: true, fontSize: 12 },
  }));
  const links = names.slice(1).map((n, i) => ({
    source: names[i],
    target: n,
    lineStyle: { width: 3, color: '#c0392b' },
  }));
  return renderGraph(domId, { nodes, links, categories: [{ name: '蜀' }, { name: '群雄' }] });
}
