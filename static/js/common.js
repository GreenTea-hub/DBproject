/* 公共小工具。负责人：P5。所有页面共用，改这里要提前在群里说。 */

/**
 * 统一请求封装：处理 {code, data, message} 信封。
 * 失败时抛出 Error，页面用 try/catch 接住并提示。
 */
async function apiGet(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  });
  const resp = await fetch(url);
  const body = await resp.json().catch(() => ({ code: resp.status, message: '返回格式异常' }));
  if (body.code !== 0) throw new Error(body.message || `请求失败（${resp.status}）`);
  return body.data;
}

async function apiSend(method, path, payload) {
  const resp = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  const body = await resp.json().catch(() => ({ code: resp.status, message: '返回格式异常' }));
  if (body.code !== 0) throw new Error(body.message || `请求失败（${resp.status}）`);
  return body.data;
}

function esc(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function factionClass(faction) {
  return { '魏': 'wei', '蜀': 'shu', '吴': 'wu' }[faction] || 'qun';
}

function tagHtml(faction) {
  if (!faction) return '';
  return `<span class="tag ${factionClass(faction)}">${esc(faction)}</span>`;
}

function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}
