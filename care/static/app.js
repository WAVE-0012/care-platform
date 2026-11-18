'use strict';

const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
} [character]));
const money = value => Number(value || 0).toLocaleString('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});
const dateText = value => value ? String(value).replace('T', ' ').slice(0, 16) : '—';
const dateInput = (offset = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
};
const previousMonth = () => {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-01`;
};
let user, csrf, lookups, page = 1,
  keyword = '',
  currentRows = [],
  activeSection = 'overview',
  formAction;
let renderVersion = 0;

const roles = {
  admin: '系统管理员',
  community: '社区管理员',
  family: '家属',
  elderly: '老人',
  worker: '护工',
  agency: '机构负责人',
  street: '街道监管',
  civil: '民政监管'
};
const statuses = {
  ineligible: '待准入',
  pending: '待处理',
  offered: '待接单',
  accepted: '待服务',
  serving: '服务中',
  confirming: '待确认',
  completed: '已完成',
  cancelled: '已取消',
  exception: '异常待处理',
  terminated: '已终止',
  active: '生效',
  paused: '已暂停',
  ended: '已结束',
  draft: '草稿',
  published: '已发布',
  closed: '已关闭',
  open: '待响应',
  handling: '处理中',
  street: '待街道初审',
  civil: '待民政终审',
  returned: '已退回',
  rejected: '未通过',
  approved: '已通过',
  paid: '已拨付',
  clear: '无需整改',
  review: '待复核',
  resolved: '整改完成',
  auto: '自动认定',
  normal: '正常',
  confirmed: '已核实',
  false: '误报',
  sent: '发送成功',
  failed: '待重试',
  manual: '转人工',
  reassigned: '已改派',
  invalid: '已失效',
  timeout: '已超时',
  leave: '休假',
  left: '离职'
};
const abilities = ['能力完好', '轻度失能', '中度失能', '重度失能'];
const auditEntities = {
  order: '服务订单',
  claim: '补贴申报',
  elderly: '老人档案',
  worker: '护工',
  shift: '排班',
  assessment: '能力评估',
  plan: '照护计划',
  emergency: '应急事件',
  quality: '质量抽查',
  policy: '补贴政策',
  work_log: '工时记录',
  scheduler: '系统任务',
  notification: '通知记录',
  user: '用户',
  community: '社区',
  agency: '服务机构'
};
const auditActions = {
  create: '新建',
  update: '修改',
  delete: '删除',
  authorize: '授权变更',
  status: '状态调整',
  cancel: '取消',
  reschedule: '改约',
  dispatch: '派单',
  complete: '完成',
  submit: '提交',
  pay: '拨付',
  review: '复核',
  inspect: '抽查',
  approve: '审核通过',
  reject: '审核驳回',
  return: '退回',
  complaint: '投诉处理',
  exception: '转异常',
  resume: '恢复',
  terminate: '终止',
  respond: '响应',
  arrive: '到场',
  close: '关闭',
  maintenance: '维护执行',
  tick: '系统轮询'
};
const auditActionTone = {
  create: 'success',
  complete: 'success',
  pay: 'success',
  approve: 'success',
  dispatch: 'info',
  submit: 'info',
  review: 'info',
  inspect: 'info',
  respond: 'info',
  arrive: 'info',
  cancel: 'danger',
  terminate: 'danger',
  exception: 'danger',
  reject: 'danger',
  delete: 'danger'
};
const staff = ['admin', 'community', 'agency', 'worker', 'street', 'civil'];
const sections = {
  overview: {
    title: '服务总览',
    symbol: '01',
    description: '在册老人、服务订单、补贴与待办汇总',
    roles: Object.keys(roles)
  },
  elders: {
    title: '老人档案',
    symbol: '02',
    description: '老人档案、联系人、能力评估与照护计划',
    roles: Object.keys(roles),
    columns: [
      ['id', '档案编号'],
      ['name', '姓名'],
      ['community_name', '所属社区'],
      ['identity_mask', '身份证号'],
      ['ability_level', '能力等级', 'ability'],
      ['valid_until', '评估有效期', 'date'],
      ['plan_status', '照护计划', 'badge']
    ]
  },
  orders: {
    title: '服务订单',
    symbol: '03',
    description: '预约、派单、服务确认与结算记录',
    roles: Object.keys(roles),
    columns: [
      ['id', '订单编号'],
      ['elderly_name', '服务对象'],
      ['item_name', '服务项目'],
      ['scheduled_at', '预约时间', 'date'],
      ['worker_name', '服务护工'],
      ['status', '进度', 'badge'],
      ['settlement', '结算金额', 'money']
    ]
  },
  workers: {
    title: '护工管理',
    symbol: '04',
    description: '护工资质、在岗状态、工时与评价',
    roles: staff,
    columns: [
      ['id', '护工编号'],
      ['name', '姓名'],
      ['agency_name', '所属机构'],
      ['status', '在岗状态', 'badge'],
      ['total_hours', '累计工时'],
      ['points', '服务积分'],
      ['rating', '平均评价']
    ]
  },
  shifts: {
    title: '排班管理',
    symbol: '05',
    description: '班次、可接单量与剩余名额',
    roles: staff,
    columns: [
      ['id', '班次编号'],
      ['worker_name', '护工'],
      ['starts_at', '开始时间', 'date'],
      ['ends_at', '结束时间', 'date'],
      ['capacity', '可接单量'],
      ['used_slots', '已使用'],
      ['remaining_slots', '剩余名额'],
      ['status', '状态', 'badge']
    ]
  },
  hours: {
    title: '工时复核',
    symbol: '06',
    description: '签到签退、围栏校验与工时复核',
    roles: staff,
    columns: [
      ['id', '工时编号'],
      ['worker_name', '护工'],
      ['order_id', '订单'],
      ['checkin_at', '签到时间', 'date'],
      ['checkout_at', '签退时间', 'date'],
      ['geofence_ok', '围栏校验', 'yes'],
      ['review_status', '复核进度', 'badge']
    ]
  },
  vitals: {
    title: '健康监测',
    symbol: '07',
    description: '体征采集、阈值告警与核实处置',
    roles: Object.keys(roles),
    columns: [
      ['id', '数据编号'],
      ['elderly_name', '老人'],
      ['device_id', '设备'],
      ['metric', '指标', 'metric'],
      ['value', '采集值'],
      ['unit', '单位'],
      ['collected_at', '采集时间', 'date'],
      ['confirmation', '核实状态', 'badge']
    ]
  },
  events: {
    title: '应急响应',
    symbol: '08',
    description: '求助登记、响应到场与处置结果',
    roles: Object.keys(roles),
    columns: [
      ['id', '事件编号'],
      ['elderly_name', '老人'],
      ['source', '来源'],
      ['level', '等级', 'level'],
      ['occurred_at', '发生时间', 'date'],
      ['responded_at', '响应时间', 'date'],
      ['status', '处置进度', 'badge']
    ]
  },
  claims: {
    title: '补贴申报',
    symbol: '09',
    description: '按月归集、审核与补贴拨付',
    roles: Object.keys(roles),
    columns: [
      ['id', '申报编号'],
      ['elderly_name', '老人'],
      ['item_name', '项目'],
      ['month', '结算月份', 'month'],
      ['order_count', '服务单数'],
      ['amount', '申报金额', 'money'],
      ['status', '审核进度', 'badge']
    ]
  },
  quality: {
    title: '质量监管',
    symbol: '10',
    description: '服务抽查、整改与接单资格恢复',
    roles: staff,
    columns: [
      ['id', '抽查编号'],
      ['worker_name', '护工'],
      ['order_id', '订单'],
      ['method', '抽查方式'],
      ['score', '评分'],
      ['issue', '发现问题'],
      ['status', '整改进度', 'quality']
    ]
  },
  notifications: {
    title: '通知记录',
    symbol: '11',
    description: '应急通知的发送与重试记录',
    roles: ['admin', 'community', 'street', 'civil'],
    columns: [
      ['id', '通知编号'],
      ['event_id', '事件'],
      ['recipient', '接收人'],
      ['stage', '通知阶段', 'stage'],
      ['attempts', '尝试次数'],
      ['status', '发送状态', 'badge']
    ]
  },
  audit: {
    title: '操作留痕',
    symbol: '12',
    description: '关键操作、处理原因与操作人追溯',
    roles: ['admin', 'community', 'agency', 'street', 'civil'],
    columns: [
      ['id', '记录编号'],
      ['entity', '业务对象', 'entity'],
      ['entity_id', '对象编号'],
      ['action', '操作类型', 'action'],
      ['actor_name', '操作人'],
      ['detail', '说明'],
      ['created_at', '记录时间', 'date']
    ]
  },
};

const navGroups = [
  ['工作台', ['overview']],
  ['老人服务', ['elders', 'vitals']],
  ['服务运营', ['orders']],
  ['服务队伍', ['workers', 'shifts', 'hours']],
  ['健康与安全', ['events']],
  ['补贴与监管', ['claims', 'quality']],
  ['系统管理', ['notifications', 'audit']]
];

const NAV_ICONS = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  elders: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  orders: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>',
  workers: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20v-1.5A3.5 3.5 0 0 1 6.5 15h5A3.5 3.5 0 0 1 15 18.5V20"/><circle cx="17" cy="9" r="2.4"/><path d="M16.5 14.2A3 3 0 0 1 21 17v3"/>',
  shifts: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="M8 14h3v3H8z"/>',
  hours: '<circle cx="12" cy="13" r="8"/><path d="M12 13V9M12 13l3 2"/><path d="M9 2h6"/>',
  vitals: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  events: '<path d="M12 3 2.5 20h19L12 3z"/><path d="M12 9v5M12 17h.01"/>',
  claims: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  quality: '<path d="M12 2 4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5l-8-3z"/><path d="m9 12 2 2 4-4"/>',
  notifications: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M10 20h4"/>',
  audit: '<path d="M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-3"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M8 11h8M8 15h8M8 19h5"/>'
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf || '',
      ...options.headers
    }
  });
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') showLogin();
    throw new Error(result.error || '操作未完成');
  }
  return result;
}
const post = (path, data = {}) => api(path, {
  method: 'POST',
  body: JSON.stringify(data)
});
const allowed = (...values) => values.includes(user.role);

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  setTimeout(() => $('#toast').hidden = true, 4000);
}

function showLogin() {
  $('#workspace').hidden = true;
  $('#login-screen').hidden = false;
  $('#login-screen').style.display = '';
  user = null;
}
async function start() {
  const me = await api('/api/me');
  user = me.user;
  csrf = me.csrf;
  lookups = await api('/api/lookups');
  $('#login-screen').style.display = 'none';
  $('#workspace').hidden = false;
  $('#user-label').textContent = `${roles[user.role]} · ${user.username}`;
  $('#avatar').textContent = roles[user.role][0];
  const now = new Date();
  $('#today').textContent =
    `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 星期${'日一二三四五六'[now.getDay()]}`;
  $('#navigation').innerHTML = navGroups.map(([group, keys]) => {
    const items = keys.map(key => [key, sections[key]])
      .filter(([, meta]) => meta && meta.roles.includes(user.role));
    if (!items.length) return '';
    return `<div class="nav-group">${group}</div>` +
      items.map(([key, meta]) => {
        const icon = NAV_ICONS[key]
          ? `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${NAV_ICONS[key]}</svg>`
          : '';
        return `<a class="nav-item" href="#${key}" data-section="${key}" title="${meta.title}">${icon}<span>${meta.title}</span></a>`;
      }).join('');
  }).join('');
  await navigate();
}

/* 枚举中文映射：数据库里存英文/数字，界面必须显示中文业务含义 */
const stages = {
  created: '事件创建',
  escalated: '升级通知',
  arrival: '到场超时'
};
const levels = {
  1: '一级',
  2: '二级',
  3: '三级'
};

function badge(value, kind = '') {  const warning = ['pending', 'ineligible', 'offered', 'confirming', 'street', 'civil', 'open',
  'review'];
  const neutral = ['cancelled', 'ended', 'paused', 'invalid', 'terminated'];
  const error = ['exception', 'failed', 'rejected', 'manual'];
  const color = warning.includes(value) ? 'warning' : neutral.includes(value) ? 'neutral' : error
    .includes(value) ? 'error' : ['serving', 'handling', 'accepted'].includes(value) ? 'blue' : '';
  const label = kind === 'quality' && value === 'open' ? '待整改' : statuses[value] || value || '—';
  return `<span class="badge ${color}">${escapeHtml(label)}</span>`;
}

function cell(row, key, type) {
  const value = row[key];
  if (value === null || value === undefined) return '<span class="muted">—</span>';
  if (type === 'badge' || type === 'quality') return badge(value, type);
  if (type === 'stage') return escapeHtml(stages[value] || value);
  if (type === 'level') return escapeHtml(levels[value] || `第${value}级`);
  if (type === 'money') return '¥ ' + money(value);
  if (type === 'date') return escapeHtml(dateText(value));
  if (type === 'month') return escapeHtml(value.slice(0, 7));
  if (type === 'ability') return escapeHtml(abilities[value]);
  if (type === 'entity') return `<span class="audit-entity">${escapeHtml(auditEntities[value] || value)}</span>`;
  if (type === 'action') {
    const tone = auditActionTone[value] ? ` is-${auditActionTone[value]}` : '';
    return `<span class="audit-action${tone}">${escapeHtml(auditActions[value] || value)}</span>`;
  }
  if (type === 'yes') return value ? '通过' : '未通过';
  if (type === 'metric') return {
    systolic: '收缩压',
    pulse: '脉搏',
    temperature: '体温'
  } [value] || escapeHtml(value);
  if (key === 'id') return `<strong>#${String(value).padStart(4,'0')}</strong>`;
  return escapeHtml(String(value).length > 38 ? String(value).slice(0, 38) + '…' : value);
}

function tableMarkup(rows, columns, kind) {
  return `<table><thead><tr>${columns.map(c=>`<th>${c[1]}</th>`).join('')}<th>操作</th></tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(c=>`<td>${cell(row,...[c[0],c[2]])}</td>`).join('')}<td><button class="row-button" data-kind="${kind}" data-id="${row.id}">详情</button></td></tr>`).join('')}</tbody></table>`;
}
async function navigate() {
  const section = location.hash.slice(1) || 'overview';
  activeSection = sections[section]?.roles.includes(user.role) ? section : 'overview';
  delete $('#workspace').dataset.section;
  page = 1;
  keyword = '';
  $('#search').value = '';
  document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset
    .section === activeSection));
  const meta = sections[activeSection];
  $('#page-title').textContent = meta.title;
  $('#page-description').textContent = meta.description;
  $('#breadcrumb').textContent = '服务工作台 / ' + meta.title;
  $('#overview-content').hidden = activeSection !== 'overview';
  $('#list-content').hidden = activeSection === 'overview';
  $('#page-actions').replaceChildren();
  const actions = topActions(activeSection);
  actions.forEach(([label, handler]) => addButton($('#page-actions'), label, handler, 'primary'));
  if (activeSection === 'overview') await renderOverview();
  else await renderList();
}
async function renderList() {
  const version = ++renderVersion;
  const section = activeSection;
  const meta = sections[section];
  $('#table-title').textContent = meta.title + '列表';
  $('#search').placeholder = ['audit', 'notifications'].includes(section) ? '搜索说明或接收人' : '搜索姓名';
  $('#table-head').innerHTML =
    `<tr>${meta.columns.map(c=>`<th>${c[1]}</th>`).join('')}<th>操作</th></tr>`;
  $('#table-body').innerHTML = `<tr><td colspan="${meta.columns.length+1}" class="empty">正在加载…</td></tr>`;
  const data = await api(`/api/list/${section}?page=${page}&q=${encodeURIComponent(keyword)}`);
  if (version !== renderVersion) return;
  currentRows = data.rows;
  $('#table-body').innerHTML = data.rows.length ? data.rows.map(row =>
    `<tr>${meta.columns.map(c=>`<td>${cell(row,c[0],c[2])}</td>`).join('')}<td><button class="row-button" data-kind="${activeSection}" data-id="${row.id}">详情</button></td></tr>`
    ).join('') : `<tr><td colspan="${meta.columns.length+1}" class="empty"><div class="empty-state"><span class="empty-mark" aria-hidden="true">◌</span><p>${keyword ? '没有匹配「' + escapeHtml(keyword) + '」的记录' : '当前范围内暂无记录'}</p>${keyword ? '<button type="button" class="secondary empty-action" id="clear-search">清除搜索条件</button>' : ''}</div></td></tr>`;
  $('#result-count').textContent = `共 ${data.total} 条记录 · 每页 20 条`;
  $('#page-number').textContent = `${page} / ${Math.max(1,Math.ceil(data.total/20))}`;
  $('#previous').disabled = page === 1;
  $('#next').disabled = page * 20 >= data.total;
  $('#workspace').dataset.section = section;
}
async function renderOverview() {
  const version = ++renderVersion;
  const [summary, ordersData] = await Promise.all([
    api('/api/dashboard'),
    api('/api/list/orders')
  ]);
  if (version !== renderVersion) return;

  const waiting = Number(summary.orders.waiting || 0);
  const due = Array.isArray(summary.reassessment) ? summary.reassessment.length : 0;
  const eventCount = Number(summary.events || 0);
  const todoTotal = eventCount + waiting + due;
  const completed = Number(summary.orders.completed || 0);
  const elders = Number(summary.elders || 0);
  const subsidy = Number(summary.subsidy || 0);

  const stats = [
    {
      key: 'elders',
      name: '在册老人',
      value: elders.toLocaleString('zh-CN'),
      unit: '人',
      note: '当前授权范围内的有效档案',
      icon: '<circle cx="12" cy="8" r="3.2"/><path d="M5 20v-1.4A4.6 4.6 0 0 1 9.6 14h4.8a4.6 4.6 0 0 1 4.6 4.6V20"/>'
    },
    {
      key: 'completed',
      name: '已完成服务',
      value: completed.toLocaleString('zh-CN'),
      unit: '单',
      note: `累计结算 ¥ ${money(summary.orders.amount)}`,
      icon: '<path d="M7 3.8h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20V5.3A1.5 1.5 0 0 1 7.5 3.8Z"/><path d="M14 4v4h4M9 14l2 2 4-4"/>'
    },
    {
      key: 'waiting',
      name: '待调度与接单',
      value: waiting.toLocaleString('zh-CN'),
      unit: '单',
      note: '待派单、待接单和待确认',
      icon: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.2 2"/>'
    },
    {
      key: 'subsidy',
      name: '已核定补贴',
      value: money(subsidy),
      unit: '元',
      note: '终审通过及已拨付金额',
      icon: '<rect x="3.5" y="6" width="17" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6.5 9h.01M17.5 15h.01"/>'
    }
  ];

  const trend = Array.isArray(summary.trend) ? summary.trend : [];
  const chartRows = trend.slice(-6);
  const maxOrders = Math.max(1, ...chartRows.map(item => Math.max(0, Number(item.orders || 0))));
  const totalOrders = trend.reduce((sum, item) => sum + Number(item.orders || 0), 0);
  const totalCompleted = trend.reduce((sum, item) => sum + Number(item.completed || 0), 0);
  const totalRate = totalOrders ? Math.round(totalCompleted / totalOrders * 100) : 0;

  const chartMarkup = chartRows.length
    ? chartRows.map(item => {
      const orders = Math.max(0, Number(item.orders || 0));
      const done = Math.max(0, Number(item.completed || 0));
      const orderHeight = orders ? Math.max(4, Math.round(orders / maxOrders * 100)) : 0;
      const doneHeight = done ? Math.max(4, Math.round(done / maxOrders * 100)) : 0;
      const month = String(item.month || '—');
      return `<div class="trend-chart-column" title="${escapeHtml(month)}：预约 ${orders} 单，已完成 ${done} 单">
        <div class="trend-bars" aria-hidden="true">
          <span class="trend-bar trend-bar--orders" style="height:${orderHeight}%"></span>
          <span class="trend-bar trend-bar--completed" style="height:${doneHeight}%"></span>
        </div>
        <span class="trend-month">${escapeHtml(month)}</span>
        <span class="trend-detail">${done}/${orders}</span>
      </div>`;
    }).join('')
    : '<p class="empty trend-empty">暂无服务趋势数据</p>';

  const tasks = [
    {
      key: 'events',
      title: '应急处置跟进',
      description: '响应、到场和处置结果待记录',
      count: eventCount,
      href: '#events',
      icon: '<path d="M12 3 3.3 19h17.4L12 3Z"/><path d="M12 9v4M12 16h.01"/>'
    },
    {
      key: 'orders',
      title: '服务调度与接单',
      description: '待派单、待接单和待确认的订单',
      count: waiting,
      href: '#orders',
      icon: '<path d="M7 3.5h7l4 4v13H6v-15a2 2 0 0 1 1-2Z"/><path d="M14 3.5v4h4M9 13h6M9 16.5h4"/>'
    },
    {
      key: 'elders',
      title: '评估到期与复评',
      description: '七日内到期或尚未评估的老人档案',
      count: due,
      href: '#elders',
      icon: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 9h16M8 13h3M8 16h6"/>'
    }
  ];

  const recent = (ordersData.rows || []).slice(0, 5);
  currentRows = recent;

  $('#overview-content').innerHTML = `
    <section class="dashboard-hero" aria-label="工作台欢迎信息">
      <div class="dashboard-hero-main">
        <div class="dashboard-hero-meta">
          <span class="dashboard-eyebrow">ANLIN · COMMUNITY CARE</span>
          <span class="dashboard-role">${escapeHtml(roles[user.role] || '平台用户')}</span>
        </div>
        <h2>让每一次照护，都有温度可寻</h2>
        <p>集中掌握老人服务、业务履约、健康安全与补贴监管情况。</p>
      </div>
      <div class="dashboard-hero-aside">
        <span>待跟进事项</span>
        <strong>${todoTotal.toLocaleString('zh-CN')}</strong>
        <small>应急 · 订单 · 评估</small>
      </div>
    </section>

    <section class="kpi-panel" aria-label="核心业务指标">
      ${stats.map(stat => `
        <article class="kpi kpi--${stat.key}">
          <div class="kpi-topline">
            <span class="kpi-label">${stat.name}</span>
            <span class="kpi-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${stat.icon}</svg>
            </span>
          </div>
          <div class="kpi-value">${escapeHtml(stat.value)}<small>${stat.unit}</small></div>
          <div class="kpi-note">${escapeHtml(stat.note)}</div>
        </article>`).join('')}
    </section>

    <div class="overview-grid">
      <section class="panel task-panel">
        <div class="panel-heading">
          <div class="panel-heading-copy">
            <h2>待处理工作</h2>
            <p>根据当前账号权限汇总待跟进事项</p>
          </div>
          <span class="panel-count">共 ${todoTotal.toLocaleString('zh-CN')} 项</span>
        </div>
        <div class="task-list">
          ${tasks.map(task => `
            <a class="task-item task-item--${task.key}" href="${task.href}">
              <span class="task-symbol" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${task.icon}</svg>
              </span>
              <span class="task-copy">
                <strong>${task.title}</strong>
                <small>${task.description}</small>
              </span>
              <span class="task-count">${task.count.toLocaleString('zh-CN')}</span>
              <span class="task-arrow" aria-hidden="true">›</span>
            </a>`).join('')}
        </div>
        ${allowed('admin', 'community', 'family', 'elderly') ? `
        <div class="task-quickbook">
          <button type="button" class="quickbook-button" data-action="quick-book">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
            <span>预约上门服务</span>
            <small>快速为新服务创建订单</small>
          </button>
        </div>` : ''}
      </section>

      <section class="panel trend-panel">
        <div class="panel-heading">
          <div class="panel-heading-copy">
            <h2>服务量趋势</h2>
            <p>按预约月份统计</p>
          </div>
          <span class="panel-period">${chartRows.length ? `最近 ${chartRows.length} 个月` : '暂无数据'}</span>
        </div>
        <div class="trend-legend">
          <span><i class="trend-legend-dot trend-legend-dot--orders"></i>预约订单</span>
          <span><i class="trend-legend-dot trend-legend-dot--completed"></i>已完成</span>
        </div>
        <div class="trend-chart-scroll">
          <div class="trend-chart" role="img" aria-label="服务量趋势柱状图，按月份比较预约订单和已完成订单">
            ${chartMarkup}
          </div>
        </div>
        <div class="trend-summary">
          <div><span>预约订单</span><strong>${totalOrders.toLocaleString('zh-CN')}</strong></div>
          <div><span>已完成</span><strong>${totalCompleted.toLocaleString('zh-CN')}</strong></div>
          <div><span>完成率</span><strong>${totalRate}%</strong></div>
        </div>
        <p class="panel-note">统计口径：按预约月份归集；完成率 = 已完成 ÷ 预约订单。</p>
      </section>
    </div>

    <section class="panel recent-orders-panel">
      <div class="panel-heading">
        <div class="panel-heading-copy">
          <h2>近期服务订单</h2>
          <p>查看当前授权范围内的服务履约记录</p>
        </div>
        <a class="inline-link" href="#orders">查看全部订单 <span aria-hidden="true">→</span></a>
      </div>
      <div class="table-scroll">${recent.length
        ? tableMarkup(recent, sections.orders.columns, 'orders')
        : '<p class="empty">暂无订单</p>'}</div>
    </section>`;

  $('#workspace').dataset.section = 'overview';
}
function addButton(parent, label, handler, className = 'secondary') {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = className;
  button.textContent = label;
  button.addEventListener('click', () => Promise.resolve(handler()).catch(error => toast(error
  .message)));
  parent.append(button);
}
const options = (rows, label = 'name') => rows.map(row => [row.id, `#${row.id} ${row[label]}`]);
const field = (name, label, type = 'text', extra = {}) => ({
  name,
  label,
  type,
  ...extra
});
const select = (name, label, values, extra = {}) => field(name, label, 'select', {
  options: values,
  ...extra
});
const elderSelect = () => select('elderly_id', '老人档案', options(lookups.elders));
const itemSelect = () => select('item_id', '服务项目', options(lookups.items));
const workerSelect = () => select('worker_id', '服务护工', options(lookups.workers));
const textArea = (name, label, extra = {}) => field(name, label, 'textarea', {
  full: true,
  ...extra
});

function showForm(title, fields, handler, description = '') {
  $('#form-title').textContent = title;
  $('#form-description').textContent = description;
  $('#form-error').textContent = '';
  $('#form-fields').innerHTML = fields.map(f => {
    let input;
    const common =
      `name="${f.name}" ${f.optional?'':'required'} ${f.min!==undefined?`min="${f.min}"`:''} ${f.max!==undefined?`max="${f.max}"`:''}`;
    if (f.type === 'select') input =
      `<select ${common}>${f.options.map(([value,label])=>`<option value="${escapeHtml(value)}" ${String(value)===String(f.value)?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>`;
    else if (f.type === 'textarea') input =
      `<textarea ${common}>${escapeHtml(f.value||'')}</textarea>`;
    else input =
      `<input type="${f.type}" ${common} value="${escapeHtml(f.value??'')}" ${f.type==='number'?'step="any"':''} ${f.type==='checkbox'&&f.value?'checked':''} ${f.placeholder?`placeholder="${escapeHtml(f.placeholder)}"`:''}>`;
    return `<label class="${f.full?'full':''} ${f.type==='checkbox'?'checkbox':''}">${escapeHtml(f.label)}${input}</label>`;
  }).join('');
  formAction = async () => {
    const data = {};
    for (const f of fields) {
      const input = $(`#action-form [name="${f.name}"]`);
      data[f.name] = f.type === 'checkbox' ? input.checked : f.type === 'number' ? (input.value ===
        '' ? null : Number(input.value)) : input.value;
    }
    return handler(data);
  };
  $('#form-dialog').showModal();
}

function routeForm(title, fields, path, description = '', transform = data => data) {
  showForm(title, fields, data => post(path, transform(data)), description);
}

function openBookingForm() {
  return routeForm('预约上门服务', [
    elderSelect(), itemSelect(), field('scheduled_at', '预约时间', 'datetime-local', {
      value: dateInput(1) + 'T10:00'
    }), field('duration_minutes', '预约时长（分钟）', 'number', {
      value: 60,
      min: 1,
      max: 720
    })
  ], '/api/orders', '按次项目沿用标准时长；订单保存下单时的地址和价格。', data => ({
    ...data,
    request_key: crypto.randomUUID()
  }));
}

function topActions(kind) {
  const result = [];
  if (kind === 'overview' && allowed('admin', 'community', 'family', 'elderly')) result.push([
    '＋ 预约服务', openBookingForm
  ]);
  if (kind === 'overview' && allowed('admin')) result.push(['更新业务待办', async () => {
    await post('/api/maintenance');
    toast('到期、超时与通知待办已更新');
    await renderOverview();
  }]);
  if (kind === 'elders' && allowed('admin', 'community')) result.push(['＋ 新建档案', () => routeForm(
    '新建老人档案', [
      field('name', '姓名'), field('identity', '身份证号'), field('birth_date', '出生日期', 'date'), select(
        'community_id', '所属社区', options(lookups.communities)),
      textArea('address', '居住地址'), field('contact_name', '主联系人'), field('contact_phone', '联系电话'),
      field('relationship', '与老人关系', 'text', {
        value: '子女'
      }),
      field('living_alone', '独居', 'checkbox', {
        optional: true
      }), field('disabled', '失能', 'checkbox', {
        optional: true
      }), field('low_income', '低保', 'checkbox', {
        optional: true
      })
    ], '/api/elders')]);
  if (kind === 'orders' && allowed('admin', 'community', 'family', 'elderly')) result.push(['＋ 预约服务',
  () => routeForm('预约上门服务', [
      elderSelect(), itemSelect(), field('scheduled_at', '预约时间', 'datetime-local', {
        value: dateInput(1) + 'T10:00'
      }), field('duration_minutes', '预约时长（分钟）', 'number', {
        value: 60,
        min: 1,
        max: 720
      })
    ], '/api/orders', '按次项目沿用标准时长；订单保存下单时的地址和价格。', data => ({
      ...data,
      request_key: crypto.randomUUID()
    }))
  ]);
  if (kind === 'shifts' && allowed('admin', 'agency')) result.push(['＋ 发布班次', () => routeForm('发布护工班次', [
    workerSelect(), field('capacity', '可接单量', 'number', {
      value: 4,
      min: 1
    }), field('starts_at', '开始时间', 'datetime-local', {
      value: dateInput(8) + 'T08:00'
    }), field('ends_at', '结束时间', 'datetime-local', {
      value: dateInput(8) + 'T18:00'
    })
  ], '/api/shifts')]);
  if (kind === 'workers' && allowed('admin', 'agency')) result.push(['登记资质', () => certificateForm()]);
  if (kind === 'workers' && allowed('admin', 'agency')) result.push(['＋ 登记护工', () => routeForm(
    '登记护工和服务账号', [
      field('name', '护工姓名'), field('username', '登录账号'), field('password', '初始密码', 'password'),
      field('agency_id', '所属机构编号', 'number', {
        value: user.agency_id || 1,
        min: 1
      }), field('trained_on', '培训完成日期', 'date', {
        value: dateInput()
      }), field('item_ids', '可服务项目编号', 'text', {
        value: '1,4'
      }), field('community_ids', '服务社区编号', 'text', {
        value: '1'
      })
    ], '/api/workers', '项目和社区编号用英文逗号分隔。', data => ({
      ...data,
      item_ids: data.item_ids.split(',').map(Number),
      community_ids: data.community_ids.split(',').map(Number)
    }))]);
  if (kind === 'vitals' && allowed('admin', 'community')) result.push(['上传体征', () => routeForm('上传设备体征',
    [
      field('device_id', '设备编号', 'number', {
        min: 1
      }), select('metric', '指标', [
        ['systolic', '收缩压'],
        ['pulse', '脉搏'],
        ['temperature', '体温']
      ]), field('value', '指标值', 'number'), field('collected_at', '采集时间', 'datetime-local', {
        value: dateInput() + 'T09:00'
      })
    ], '/api/vitals/batch', '按采集时刻的绑定记录确定老人归属。', data => ({
      records: [data]
    }))]);
  if (kind === 'vitals' && allowed('admin', 'community')) result.push(['设备换绑', () => routeForm('调整设备绑定',
    [
      field('device_id', '设备编号', 'number', {
        min: 1
      }), elderSelect(), field('bound_at', '新绑定开始时间', 'datetime-local', {
        value: dateInput() + 'T10:00'
      })
    ], '/api/device-bindings')]);
  if (kind === 'vitals' && allowed('admin', 'community')) result.push(['登记设备', () => routeForm('登记监测设备',
    [
      field('serial_number', '设备序列号'), field('device_type', '设备类型', 'text', {
        value: '血压计'
      }), elderSelect(), field('location', '安装位置', 'text', {
        value: '居家客厅'
      })
    ], '/api/devices')]);
  if (kind === 'events' && allowed('admin', 'community', 'family', 'elderly', 'worker')) result.push([
    '＋ 登记求助', () => eventForm()
  ]);
  if (kind === 'claims' && allowed('admin', 'community')) result.push(['＋ 月度申报', () => routeForm(
    '按月归集补贴申报', [
      elderSelect(), itemSelect(), field('month', '结算月份首日', 'date', {
        value: previousMonth()
      }), textArea('evidence', '证明材料说明', {
        value: '关联订单中的服务记录、确认信息、工时及评估计划。'
      })
    ], '/api/claims', '同一老人、项目、月份只保留一份申报，重复请求返回原申报。')]);
  if (kind === 'quality' && allowed('street', 'civil')) result.push(['＋ 服务抽查', () => qualityForm()]);
  if (kind === 'claims' && allowed('civil')) result.push(['发布政策', () => routeForm('发布补贴政策版本', [
    field('name', '政策名称'), itemSelect(), select('ability_level', '适用能力等级', abilities.map((label,
      i) => [i, label])), field('rate', '每次或每小时补贴金额', 'number', {
      min: 0
    }), field('starts_on', '生效月份首日', 'date'), field('ends_on', '失效月份末日', 'date'), field(
      'low_income_only', '仅适用于低保对象', 'checkbox', {
        optional: true
      })
  ], '/api/policies')]);
  return result;
}

function certificateForm(workerId) {
  routeForm('登记护工资质', [select('worker_id', '服务护工', options(lookups.workers), {
    value: workerId
  }), field('certificate_type', '证书类型', 'text', {
    value: '养老护理员'
  }), select('level', '证书等级', [
    [1, '初级'],
    [2, '中级'],
    [3, '高级']
  ]), field('number', '证书编号'), field('issued_on', '发证日期', 'date', {
    value: dateInput()
  }), field('valid_until', '有效期截止', 'date', {
    value: dateInput(365)
  })], '/api/certificates');
}

function eventForm(row) {
  routeForm('登记紧急求助', [select('elderly_id', '老人', options(lookups.elders), {
    value: row?.elderly_id
  }), select('level', '事件等级', [
    [1, '一级 · 一般关注'],
    [2, '二级 · 尽快响应'],
    [3, '三级 · 紧急响应']
  ], {
    value: 2
  }), textArea('description', '求助情况')], '/api/events', '应急事件与照护计划是否有效独立处理。', data => ({
    ...data,
    request_key: crypto.randomUUID(),
    vital_id: row?.id
  }));
}

function qualityForm() {
  routeForm('记录服务质量抽查', [field('order_id', '已完成订单编号', 'number', {
    min: 1
  }), select('method', '抽查方式', [
    ['电话回访', '电话回访'],
    ['上门核查', '上门核查']
  ]), select('score', '评分', [
    [5, '5 分'],
    [4, '4 分'],
    [3, '3 分'],
    [2, '2 分'],
    [1, '1 分']
  ]), field('issue', '发现问题', 'text', {
    optional: true
  }), textArea('requirement', '整改要求', {
    optional: true
  }), field('due_on', '整改期限', 'date', {
    optional: true
  }), field('restrict_agency', '限制整个机构', 'checkbox', {
    optional: true
  })], '/api/quality', '无问题时保留问题与整改字段为空；有问题时填写整改要求和期限。', data => ({
    ...data,
    order_id: Number(data.order_id)
  }));
}

async function detail(kind, id) {
  let row = currentRows.find(item => item.id === id);
  if (!row || activeSection !== kind && activeSection !== 'overview') row = (await api(
    `/api/list/${kind}`)).rows.find(item => item.id === id);
  if (!row) throw new Error('请刷新列表后查看记录');
  const meta = sections[kind];
  $('#detail-title').textContent = `${meta.title} #${String(id).padStart(4,'0')}`;
  $('#detail-body').innerHTML =
    `<div class="detail-grid">${meta.columns.map(c=>`<div class="detail-item"><small>${c[1]}</small><span>${cell(row,c[0],c[2])}</span></div>`).join('')}</div>`;
  $('#detail-actions').replaceChildren();
  if (kind === 'orders') {
    const result = await api(`/api/orders/${id}`);
    row = result.order;
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>服务地址与费用</h3><p>${escapeHtml(row.address)}<br><span class="muted">成交单价 ¥ ${money(row.unit_price)} / ${row.price_unit==='hour'?'小时':'次'} · 预约 ${row.duration_minutes} 分钟</span></p></div><div class="detail-section"><h3>派单与服务记录</h3>${result.timeline.filter(t=>t.assignment_id).map(t=>`<div class="timeline-entry"><p><strong>${escapeHtml(t.worker_name)}</strong> ${badge(t.assignment_status)} <span class="muted">派单 #${t.assignment_id}</span></p><small>派出 ${dateText(t.assigned_at)} · 接单 ${dateText(t.accepted_at)}</small><p>签到 ${dateText(t.checkin_at)} / 签退 ${dateText(t.checkout_at)} · 认定工时 ${t.valid_hours??'—'} 小时</p><p>${escapeHtml(t.service_record||'尚未填写服务记录')}</p><small>服务确认 ${dateText(t.confirmed_at)}</small></div>`).join('')||'<p class="notice">等待社区安排护工。</p>'}</div>`
      );
    if (result.costs) $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>费用明细</h3><p>服务费用 ¥ ${money(result.costs.settlement)} · 核定补贴 ¥ ${money(result.costs.approved_subsidy)} · 当前自付 ¥ ${money(result.costs.payable)}</p></div>`
      );
    if (row.complaint) $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>投诉与处理</h3><p>${escapeHtml(row.complaint)}</p><p>${escapeHtml(row.complaint_result||'等待社区处理')}</p></div>`
      );
    orderActions(row);
  } else if (kind === 'elders') {
    const result = await api(`/api/elders/${id}`);
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>联系人与授权</h3>${result.contacts.map(c=>`<p>#${c.id} ${escapeHtml(c.name)} · ${escapeHtml(c.relationship)} · ${c.phone_mask} <span class="muted">授权终止 ${dateText(c.authorized_until)}</span></p>`).join('')}</div><div class="detail-section"><h3>能力评估记录</h3>${result.assessments.map(a=>`<p>${a.assessed_on} · ${a.scale} ${a.score} 分 · ${abilities[a.ability_level]} · 有效至 ${a.valid_until}</p>`).join('')||'<p class="notice">尚未登记评估。</p>'}</div><div class="detail-section"><h3>照护计划</h3>${result.plans.map(p=>`<p>#${p.id} ${escapeHtml(p.package_name)} ${badge(p.status)}<br><span class="muted">${p.starts_on} 至 ${p.ends_on} · 责任护工 #${p.worker_id}</span></p>`).join('')||'<p class="notice">尚未制定照护计划。</p>'}</div>`
      );
    if (allowed('admin', 'community')) {
      action('登记评估', () => routeForm('登记能力评估', [select('scale', '评估量表', [
        ['ADL', 'ADL'],
        ['MMSE', '简易智能状态']
      ]), field('score', '得分', 'number', {
        value: 75,
        min: 0,
        max: 100
      }), select('ability_level', '能力等级', abilities.map((label, i) => [i, label])), field(
        'assessed_on', '评估日期', 'date', {
          value: dateInput()
        }), field('valid_until', '有效期截止', 'date', {
        value: dateInput(180)
      })], `/api/elders/${id}/assess`));
      action('制定计划', () => routeForm('制定照护计划', [select('package_id', '服务包', options(lookups.packages)),
        workerSelect(), field('starts_on', '开始日期', 'date', {
          value: dateInput()
        }), field('ends_on', '结束日期', 'date', {
          value: dateInput(180)
        })
      ], `/api/elders/${id}/plan`));
      if (result.plans.length) action('调整计划状态', () => routeForm('调整照护计划状态', [select('plan_id', '照护计划',
        result.plans.map(p => [p.id, `#${p.id} ${p.package_name}`])), select('status', '计划状态',
        [
          ['paused', '暂停'],
          ['active', '恢复生效'],
          ['ended', '结束']
        ])], `/api/elders/${id}/plan-state`));
      action('更新档案', () => routeForm('更新老人档案', [textArea('address', '居住地址', {
        value: row.address
      }), field('living_alone', '独居', 'checkbox', {
        value: row.living_alone,
        optional: true
      }), field('disabled', '失能', 'checkbox', {
        value: row.disabled,
        optional: true
      }), field('low_income', '低保', 'checkbox', {
        value: row.low_income,
        optional: true
      }), field('reason', '变更说明', 'text', {
        value: '更新老人档案'
      })], `/api/elders/${id}/update`));
      action('家属授权', () => routeForm('设置家属授权', [select('contact_id', '联系人', options(result.contacts)),
        field('user_id', '家属账号编号', 'number', {
          optional: true
        }), field('revoke', '撤销此联系人的代办授权', 'checkbox', {
          optional: true
        })
      ], `/api/elders/${id}/authorize`));
    }
  } else if (kind === 'claims') {
    const result = await api(`/api/claims/${id}`);
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>申报明细</h3>${result.items.map(i=>`<p>订单 #${i.order_id} · ${escapeHtml(i.policy_name)}<br><span class="muted">服务费 ¥ ${money(i.settlement)} · 补贴 ¥ ${money(i.amount)}</span></p>`).join('')}</div><div class="detail-section"><h3>历次审核</h3>${result.reviews.map(r=>`<p>${r.stage==='street'?'街道初审':'民政终审'} · ${escapeHtml(r.reviewer_name)} · ${{approve:'通过',return:'退回',reject:'不通过'}[r.decision]}<br><span class="muted">${dateText(r.reviewed_at)} ${escapeHtml(r.note)}</span></p>`).join('')||'<p class="notice">等待审核。</p>'}</div>`
      );
    if (allowed('street', 'civil') && row.status === user.role) action('审核申报', () => routeForm(
      '审核补贴申报', [select('decision', '审核结论', [
        ['approve', '通过'],
        ['return', '退回补充材料'],
        ['reject', '不通过']
      ]), textArea('note', '审核意见')], `/api/claims/${id}/review`));
    if (allowed('civil') && row.status === 'approved') action('登记拨付', () => routeForm('登记补贴拨付', [field(
      'reference', '拨付凭证号')], `/api/claims/${id}/pay`));
  } else if (kind === 'events' && allowed('admin', 'community', 'street', 'civil') && row.status !==
    'closed') {
    if (!row.responded_at) action('记录响应', () => simpleAction(`/api/events/${id}/process`, {
      action: 'respond'
    }));
    if (row.responded_at && !row.arrived_at) action('记录到场', () => simpleAction(
      `/api/events/${id}/process`, {
        action: 'arrive'
      }));
    action('关闭事件', () => routeForm('填写处置结果', [textArea('result', '处置结果或误报说明')],
      `/api/events/${id}/process`, '', data => ({
        ...data,
        action: 'close'
      })));
  } else if (kind === 'vitals' && row.abnormal && allowed('admin', 'community')) action('建立应急事件', () =>
    eventForm(row));
  else if (kind === 'workers' && allowed('admin', 'agency')) {
    action('登记资质', () => certificateForm(id));
    action('更新在岗与培训', () => routeForm('更新护工状态', [select('status', '在岗状态', [
      ['active', '在岗'],
      ['leave', '休假'],
      ['left', '离职']
    ], {
      value: row.status
    }), field('trained_on', '培训完成日期', 'date', {
      value: row.trained_on || dateInput()
    })], `/api/workers/${id}/update`));
  } else if (kind === 'shifts' && allowed('admin', 'agency') && !row.used_slots) action('删除未使用班次',
  () => showForm('删除未使用班次', [], () => api(`/api/shifts/${id}`, {
      method: 'DELETE'
    }), '确认删除此未使用班次。已有派单的班次会保留。'));
  else if (kind === 'hours' && allowed('admin', 'agency')) action('复核工时', () => routeForm('核验异常工时', [
    field('hours', '认定工时（小时）', 'number', {
      min: 0.01
    }), textArea('note', '核验依据和凭证说明')
  ], `/api/hours/${id}/review`));
  else if (kind === 'quality') {
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><p>整改要求：${escapeHtml(row.requirement||'无')}<br>整改结果：${escapeHtml(row.result||'尚未提交')}</p></div>`
      );
    if (allowed('agency') && row.status === 'open') action('提交整改', () => routeForm('提交整改结果', [textArea(
      'result', '整改内容和证据')], `/api/quality/${id}/rectify`, '', data => ({
      ...data,
      action: 'submit'
    })));
    if (allowed('street', 'civil') && row.status === 'review') action('复核通过', () => simpleAction(
      `/api/quality/${id}/rectify`, {
        action: 'approve'
      }));
  }
  $('#detail-dialog').showModal();
}
const action = (label, handler) => addButton($('#detail-actions'), label, handler);
async function simpleAction(path, data) {
  await post(path, data);
  $('#detail-dialog').close();
  toast('操作已保存');
  await refresh();
}
async function refresh() {
  lookups = await api('/api/lookups');
  if (activeSection === 'overview') await renderOverview();
  else await renderList();
}

function orderActions(row) {
  const id = row.id;
  if (allowed('admin', 'community') && ['pending', 'ineligible', 'offered', 'accepted'].includes(row
      .status)) action('推荐与派单', async () => {
    const candidates = (await api(`/api/orders/${id}/candidates`)).rows;
    if (!candidates.length) {
      toast('暂无符合资质、区域与时段的护工，请先补齐评估、计划或排班。');
      return;
    }
    routeForm('选择服务护工', [select('shift_id', '可用护工与班次', candidates.map(c => [c.shift_id,
      `${c.name} · 班次 #${c.shift_id} · 剩余 ${c.remaining_slots} 名额${c.priority===0?' · 责任护工':''}`
    ])), field('reason', '派单或改派说明', 'text', {
      value: '按服务时间与资质安排护工'
    })], `/api/orders/${id}/dispatch`);
  });
  if (allowed('worker') && row.status === 'offered') {
    action('接受任务', () => simpleAction(`/api/orders/${id}/accept`, {}));
    action('拒绝任务', () => routeForm('拒绝服务任务', [field('reason', '拒单原因')], `/api/orders/${id}/accept`, '',
      data => ({
        ...data,
        reject: true
      })));
  }
  if (allowed('worker') && row.status === 'accepted') action('签到开始服务', () => routeForm('服务签到', [field(
    'longitude', '签到经度', 'number', {
      value: row.longitude,
      min: -180,
      max: 180
    }), field('latitude', '签到纬度', 'number', {
    value: row.latitude,
    min: -90,
    max: 90
  })], `/api/orders/${id}/checkin`, '签到时间由服务器记录，请填写实际位置。'));
  if (allowed('worker') && row.status === 'serving') action('签退并填写记录', () => routeForm('服务签退', [field(
    'longitude', '签退经度', 'number', {
      value: row.longitude,
      min: -180,
      max: 180
    }), field('latitude', '签退纬度', 'number', {
    value: row.latitude,
    min: -90,
    max: 90
  }), textArea('service_record', '实际服务内容')], `/api/orders/${id}/checkout`));
  if (allowed('family', 'elderly') && row.status === 'confirming') action('确认服务完成', () => showForm(
      '确认本次服务', [], () => post(`/api/orders/${id}/confirm`, {}), '请核对服务记录、签到签退时间与服务内容，确认后保存当前账号及确认时间。'
      ));
  if (allowed('admin', 'community', 'agency') && row.status === 'confirming') action('核验并结算', () =>
    simpleAction(`/api/orders/${id}/finish`, {}));
  if (allowed('admin', 'community', 'family', 'elderly') && ['pending', 'ineligible', 'offered',
      'accepted'
    ].includes(row.status)) {
    action('调整预约', () => routeForm('调整预约时间', [field('scheduled_at', '预约时间', 'datetime-local', {
      value: dateInput(2) + 'T10:00'
    }), field('duration_minutes', '预约时长（分钟）', 'number', {
      value: row.duration_minutes,
      min: 1
    })], `/api/orders/${id}/reschedule`));
    action('取消预约', () => routeForm('取消服务预约', [field('reason', '取消原因')], `/api/orders/${id}/cancel`));
  }
  if (allowed('admin', 'community') && ['serving', 'confirming', 'exception'].includes(row.status))
    action('异常处理', () => routeForm('记录异常处理', [select('action', '处理动作', row.status === 'exception' ? [
      ['resume', '恢复待确认'],
      ['terminate', '终止服务']
    ] : [
      ['exception', '转入异常处理']
    ]), textArea('reason', '处理依据和原因')], `/api/orders/${id}/resolve`));
  if (allowed('family', 'elderly') && row.status === 'completed') action('评价或投诉', () => routeForm('服务反馈',
    [select('rating', '服务评分', [
      [5, '5 分'],
      [4, '4 分'],
      [3, '3 分'],
      [2, '2 分'],
      [1, '1 分']
    ]), textArea('feedback', '评价内容', {
      optional: true
    }), textArea('complaint', '投诉内容', {
      optional: true
    })], `/api/orders/${id}/feedback`));
  if (allowed('admin', 'community') && row.complaint) action('处理投诉', () => routeForm('记录投诉处理', [textArea(
    'reason', '处理结果')], `/api/orders/${id}/resolve`, '', data => ({
    ...data,
    action: 'complaint'
  })));
}

$('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('#login-error').textContent = '';
  const button = event.submitter;
  button.disabled = true;
  try {
    const data = Object.fromEntries(new FormData(event.target));
    await post('/api/login', data);
    await start();
  } catch (error) {
    $('#login-error').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$('#logout').addEventListener('click', async () => {
  await post('/api/logout');
  showLogin();
});
$('#search-form').addEventListener('submit', event => {
  event.preventDefault();
  keyword = $('#search').value.trim();
  page = 1;
  renderList().catch(error => toast(error.message));
});
$('#previous').addEventListener('click', () => {
  page--;
  renderList().catch(error => toast(error.message));
});
$('#next').addEventListener('click', () => {
  page++;
  renderList().catch(error => toast(error.message));
});
document.addEventListener('click', event => {
  const close = event.target.closest('.close-dialog');
  if (close) close.closest('dialog').close();
  const rowButton = event.target.closest('.row-button');
  if (rowButton) detail(rowButton.dataset.kind, Number(rowButton.dataset.id)).catch(error => toast(
    error.message));
  const clearSearch = event.target.closest('#clear-search');
  if (clearSearch) {
    keyword = '';
    page = 1;
    $('#search').value = '';
    renderList().catch(error => toast(error.message));
  }
  const quickBook = event.target.closest('[data-action="quick-book"]');
  if (quickBook) openBookingForm();
});
$('#action-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $('#form-error').textContent = '';
  try {
    await formAction();
    $('#form-dialog').close();
    $('#detail-dialog').close();
    toast('操作已保存');
    await refresh();
  } catch (error) {
    $('#form-error').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
window.addEventListener('hashchange', () => {
  if (user) navigate().catch(error => toast(error.message));
});
start().catch(() => showLogin());
