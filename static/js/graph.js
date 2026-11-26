/* 全组唯一的图渲染函数。负责人：P5。
 *
 * 所有出图接口返回的都是 7.4 节的结构：{nodes, links, categories}，
 * 因此五个人的接口都调用这一个函数，不要各写一套 ECharts 配置。
 *
 * 对外只暴露四个函数：
 *   renderGraph(domId, payload, opts)  画关系图（含工具栏、阵营配色、点击聚焦）
 *   renderPath(domId, pathData)        画最短路结果（端点加重）
 *   graphAction(domId, action)         工具栏动作，一般不用手动调
 *   disposeGraph(domId)                页面卸载时释放实例
 */

const FACTION_COLORS = { '魏': '#1f6fd0', '蜀': '#c0392b', '吴': '#1e8e5a', '群雄': '#7f8c8d' };

const GRAPH_ACTION_LABEL = {
  reset: '重置视图',
  zoomIn: '放大',
  zoomOut: '缩小',
  export: '导出 PNG',
  fullscreen: '全屏',
};

/* domId -> ECharts 实例。复用实例，避免每次刷新都 dispose 造成闪烁和缩放丢失 */
const _charts = new Map();

let _resizeBound = false;
let _resizeTimer = null;

function _factionColor(name) {
  return FACTION_COLORS[name] || FACTION_COLORS['群雄'];
}

/** 容器尺寸变化后统一重排所有图（只绑定一次，避免每次渲染叠加监听器） */
function _bindGlobalResize() {
  if (_resizeBound) return;
  _resizeBound = true;

  const resizeAll = () => _charts.forEach(chart => chart && !chart.isDisposed() && chart.resize());
  window.addEventListener('resize', () => {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(resizeAll, 120);
  });
  document.addEventListener('fullscreenchange', () => setTimeout(resizeAll, 80));
}

/** 工具栏：注入到图表容器内部，模板无需改动 */
function _ensureToolbar(el, domId) {
  let bar = el.querySelector('.graph-toolbar');
  if (!bar) {
    bar = document.createElement('div');
    bar.className = 'graph-toolbar';
    el.appendChild(bar);
  }
  bar.innerHTML = Object.entries(GRAPH_ACTION_LABEL)
    .map(([act, text]) => `<button type="button" class="ghost" data-act="${act}">${text}</button>`)
    .join('');
  bar.onclick = ev => {
    const btn = ev.target.closest('button[data-act]');
    if (btn) graphAction(domId, btn.dataset.act);
  };
  return bar;
}

function _buildNodes(payload) {
  return (payload.nodes || []).map(n => {
    const id = n.id || n.label || n.name;
    const value = Number(n.value) || 1;
    const node = {
      id,
      name: n.label || n.name || id,
      category: n.category || '群雄',
      value,
      symbolSize: n.symbolSize || (16 + Math.min(26, value * 1.5)),
      itemStyle: n.itemStyle || {},
      // 名字写在节点右侧并加白色描边，避免压在深色圆点上读不清
      label: {
        show: true,
        position: 'right',
        fontSize: 12,
        color: '#23272f',
        textBorderColor: 'rgba(255,255,255,.9)',
        textBorderWidth: 2,
      },
    };
    if (n.x !== undefined && n.y !== undefined) { node.x = n.x; node.y = n.y; }
    return node;
  });
}

function _buildLinks(payload) {
  return (payload.links || []).map(l => ({
    source: l.source,
    target: l.target,
    value: Number(l.value) || 1,
    label: { show: !!l.label, formatter: l.label || '', fontSize: 10, color: '#6b7280' },
    lineStyle: Object.assign(
      { width: Math.max(1, Math.min(4, (Number(l.value) || 1) / 25)), curveness: 0.08 },
      l.lineStyle || {},
    ),
  }));
}

/* 力导向参数随节点数自适应：节点少时斥力大一些，否则整张图会挤在容器中央一小团 */
function _forceBySize(count) {
  if (count <= 8) return { repulsion: 620, edgeLength: [110, 200], gravity: 0.06 };
  if (count <= 20) return { repulsion: 420, edgeLength: [90, 180], gravity: 0.07 };
  return { repulsion: 260, edgeLength: [70, 150], gravity: 0.09 };
}

function _buildOption(payload, opts) {
  const nodes = _buildNodes(payload);
  const links = _buildLinks(payload);
  const categories = (payload.categories || []).map(c => ({
    name: c.name,
    itemStyle: { color: _factionColor(c.name) },
  }));
  const legendData = opts.legend === false ? [] : categories.map(c => c.name);
  const layout = opts.layout || 'force';

  const series = {
    type: 'graph',
    layout,
    roam: true,
    draggable: true,
    zoom: opts.zoom || 1,
    categories,
    data: nodes,
    links,
    emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    blur: { itemStyle: { opacity: 0.25 }, lineStyle: { opacity: 0.1 } },
    lineStyle: { color: '#c7cbd1', opacity: 0.8, width: 1.2 },
  };
  if (layout === 'force') series.force = _forceBySize(nodes.length);

  return {
    tooltip: {
      confine: true,
      formatter: params => {
        if (params.dataType === 'edge') {
          const type = (params.data.label && params.data.label.formatter) || '未知';
          return `${params.data.source} — ${params.data.target}<br/>关系：${type}<br/>权重：${params.data.value}`;
        }
        return `<strong>${params.name}</strong><br/>阵营：${params.data.category}<br/>关系数：${params.data.value}`;
      },
    },
    legend: legendData.length
      ? [{
          data: legendData, bottom: 4, icon: 'circle', itemWidth: 10, itemHeight: 10,
          textStyle: { color: '#6b7280', fontSize: 12 },
        }]
      : undefined,
    series: [series],
  };
}

/**
 * 画关系图。
 * @param {string} domId   容器元素 id
 * @param {object} payload {nodes, links, categories}
 * @param {object} opts    {onNodeClick, zoom, toolbar}
 */
function renderGraph(domId, payload, opts = {}) {
  const el = document.getElementById(domId);
  if (!el) return null;

  if (typeof echarts === 'undefined') {
    el.innerHTML = '<p class="empty">ECharts 未加载：请确认 static/vendor/echarts.min.js 存在</p>';
    return null;
  }

  if (!payload || !(payload.nodes || []).length) {
    disposeGraph(domId);
    el.innerHTML = '<p class="empty">当前条件下没有可展示的人物</p>';
    return null;
  }

  _bindGlobalResize();

  // 复用已有实例：只更新数据，保留用户的拖拽与缩放
  let chart = echarts.getInstanceByDom(el);
  if (!chart || chart.isDisposed()) {
    el.innerHTML = '';
    chart = echarts.init(el, null, { renderer: 'canvas' });
  }
  _charts.set(domId, chart);

  chart.setOption(_buildOption(payload, opts), true);

  if (opts.toolbar !== false) _ensureToolbar(el, domId);

  chart.off('click');
  chart.on('click', params => {
    if (params.dataType !== 'node') return;
    if (opts.onNodeClick) {
      opts.onNodeClick(params.name, params.data);
      return;
    }
    // 没有跳转需求时：点击节点聚焦其邻居
    chart.dispatchAction({ type: 'focusNodeAdjacency', seriesIndex: 0, dataIndex: params.dataIndex });
  });

  // 点空白处取消聚焦
  chart.getZr().off('click');
  chart.getZr().on('click', ev => {
    if (!ev.target) chart.dispatchAction({ type: 'unfocusNodeAdjacency', seriesIndex: 0 });
  });

  return chart;
}

/** 路径结果：横向排成一条链，起点红、终点蓝，边统一描粗 */
function renderPath(domId, pathData) {
  const names = (pathData && pathData.nodes) || [];
  if (!names.length) return null;

  const el = document.getElementById(domId);
  const width = (el && el.clientWidth) || 900;
  const height = (el && el.clientHeight) || 560;
  const last = names.length - 1;
  const padX = Math.max(100, width * 0.12);
  const step = last > 0 ? (width - padX * 2) / last : 0;
  const y = Math.round(height / 2);

  const nodes = names.map((name, i) => ({
    id: name,
    label: name,
    category: '群雄',
    value: 1,
    x: Math.round(padX + step * i),
    y,
    symbolSize: i === 0 || i === last ? 36 : 26,
    itemStyle: i === 0
      ? { color: '#c0392b', borderColor: '#8e2a20', borderWidth: 2 }
      : (i === last ? { color: '#1f6fd0', borderColor: '#15508f', borderWidth: 2 } : {}),
  }));

  const links = names.slice(1).map((name, i) => ({
    source: names[i],
    target: name,
    value: 100,
    label: '',
    lineStyle: { width: 3.5, color: '#c0392b', curveness: 0 },
  }));

  return renderGraph(
    domId,
    { nodes, links, categories: [] },
    { layout: 'none', legend: false, toolbar: true },
  );
}

/** 工具栏动作 */
function graphAction(domId, action) {
  const el = document.getElementById(domId);
  const chart = _charts.get(domId);
  if (!el || !chart || chart.isDisposed()) return;

  if (action === 'reset') {
    chart.setOption({ series: [{ zoom: 1 }] });
    chart.dispatchAction({ type: 'unfocusNodeAdjacency', seriesIndex: 0 });
    chart.resize();
  } else if (action === 'zoomIn' || action === 'zoomOut') {
    const zoom = (chart.getOption().series[0].zoom || 1);
    const next = action === 'zoomIn' ? Math.min(4, zoom * 1.25) : Math.max(0.35, zoom / 1.25);
    chart.setOption({ series: [{ zoom: next }] });
  } else if (action === 'export') {
    const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' });
    const link = document.createElement('a');
    link.href = url;
    link.download = `人物关系图-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.png`;
    link.click();
  } else if (action === 'fullscreen') {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (el.requestFullscreen) el.requestFullscreen();
  }
}

function disposeGraph(domId) {
  const chart = _charts.get(domId);
  if (chart && !chart.isDisposed()) chart.dispose();
  _charts.delete(domId);
}
