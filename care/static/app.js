'use strict';

const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
} [character]));
const uiText = value => String(value ?? '').replace(/[\u3002\uff0e]/g, '');
const escapeUi = value => escapeHtml(uiText(value));
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
const staff = ['admin', 'community', 'agency', 'worker', 'street', 'civil'];
const sections = {
  overview: {
    title: '服务总览',
    symbol: '◈',
    description: '让每一份照护，都有清晰的进展',
    roles: Object.keys(roles)
  },
  elders: {
    title: '老人档案',
    symbol: '♧',
    description: '管理档案、授权联系人、能力评估与照护计划',
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
    symbol: '▤',
    description: '从预约、派单到确认结算，查看每一次服务的完整记录',
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
    symbol: '♙',
    description: '维护服务人员资质，查看累计工时与服务评价',
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
    symbol: '▦',
    description: '按可服务时段发布班次，名额随派单和释放同步更新',
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
    symbol: '◷',
    description: '核对异常签到、围栏和服务时段，记录工时认定依据',
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
    symbol: '♡',
    description: '按采集时间保留体征归属，核实异常并安排后续处置',
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
    symbol: '⚑',
    description: '记录求助、响应与到场，让处置过程持续可查',
    roles: Object.keys(roles),
    columns: [
      ['id', '事件编号'],
      ['elderly_name', '老人'],
      ['source', '来源'],
      ['level', '等级'],
      ['occurred_at', '发生时间', 'date'],
      ['responded_at', '响应时间', 'date'],
      ['status', '处置进度', 'badge']
    ]
  },
  claims: {
    title: '补贴申报',
    symbol: '￥',
    description: '按自然月归集服务，街道初审、民政终审后登记拨付',
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
    symbol: '✓',
    description: '记录服务抽查与整改，监管复核后恢复接单资格',
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
    symbol: '✉',
    description: '查看应急通知的模拟发送与重试结果',
    roles: ['admin', 'community', 'street', 'civil'],
    columns: [
      ['id', '通知编号'],
      ['event_id', '事件'],
      ['recipient', '接收人'],
      ['stage', '通知阶段'],
      ['attempts', '尝试次数'],
      ['status', '发送状态', 'badge']
    ]
  },
  audit: {
    title: '操作留痕',
    symbol: '≡',
    description: '按业务对象追溯关键操作、处理原因和操作人员',
    roles: ['admin', 'community', 'agency', 'street', 'civil'],
    columns: [
      ['id', '记录编号'],
      ['entity', '业务对象'],
      ['entity_id', '对象编号'],
      ['action', '操作'],
      ['actor_name', '操作人'],
      ['detail', '说明'],
      ['created_at', '记录时间', 'date']
    ]
  },
};

// Presentation groups only; sections remains the source of role permissions.
const navigationGroups = [
  { title: '老人档案与评估', icon: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M20 8v6 M17 11h6', children: ['elders'] },
  { title: '服务下单与派单', icon: 'M9 5H5v16h14V5h-4 M9 3h6v4H9z M8 12h8 M8 16h5', children: ['orders'] },
  { title: '护工与排班', icon: 'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2 M8 18h2', children: ['workers', 'shifts', 'hours'] },
  { title: '健康监测与应急', icon: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8 M3 12h5l2-4 4 8 2-4h5', children: ['vitals', 'events'] },
  { title: '补贴与质量监管', icon: 'M12 3 3 7l9 4 9-4-9-4z M3 12l9 4 9-4 M3 17l9 4 9-4', children: ['claims', 'quality'] },
  { title: '通知与操作记录', icon: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M10 21h4', children: ['notifications', 'audit'] }
];
const navigationLabels = {
  '老人档案与评估': '档案评估',
  '服务下单与派单': '服务派单',
  '护工与排班': '护工排班',
  '健康监测与应急': '健康应急',
  '补贴与质量监管': '补贴监管',
  '通知与操作记录': '通知与记录'
};
const navigationIcon = path => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;

function renderNavigation() {
  const leaf = key => `<a class="nav-item" href="#${key}" data-section="${key}" title="${sections[key].title}"><span>${sections[key].title}</span></a>`;
  const overviewIcon = navigationIcon('M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z');
  const overview = sections.overview.roles.includes(user.role)
    ? `<a class="nav-item nav-home" href="#overview" data-section="overview">${overviewIcon}<span>${sections.overview.title}</span></a>` : '';
  $('#navigation').innerHTML = overview + navigationGroups.map(group => {
    const children = group.children.filter(key => sections[key].roles.includes(user.role));
    if (!children.length) return '';
    return `<details class="nav-section"><summary title="${group.title}">${navigationIcon(group.icon)}<span>${navigationLabels[group.title] || group.title}</span><svg class="nav-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m5 6 3 3 3-3"/></svg></summary><div class="nav-children">${children.map(leaf).join('')}</div></details>`;
  }).join('');
}

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
  $('#toast').textContent = uiText(message);
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
  $('#today').textContent = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long'
  });
  renderNavigation();
  await navigate();
}

function badge(value, kind = '') {
  const warning = ['pending', 'ineligible', 'offered', 'confirming', 'street', 'civil', 'open',
  'review'];
  const neutral = ['cancelled', 'ended', 'paused', 'invalid', 'terminated'];
  const error = ['exception', 'failed', 'rejected', 'manual'];
  const color = warning.includes(value) ? 'warning' : neutral.includes(value) ? 'neutral' : error
    .includes(value) ? 'error' : ['serving', 'handling', 'accepted'].includes(value) ? 'blue' : '';
  const label = kind === 'quality' && value === 'open' ? '待整改' : statuses[value] || value || '—';
  return `<span class="badge ${color}">${escapeUi(label)}</span>`;
}

function cell(row, key, type, fullText = false) {
  const value = row[key];
  if (value === null || value === undefined) return '<span class="muted">—</span>';
  if (type === 'badge' || type === 'quality') return badge(value, type);
  if (type === 'money') return '¥ ' + money(value);
  if (type === 'date') return escapeUi(dateText(value));
  if (type === 'month') return escapeUi(value.slice(0, 7));
  if (type === 'ability') return escapeUi(abilities[value]);
  if (type === 'yes') return value ? '通过' : '未通过';
  if (type === 'metric') return {
    systolic: '收缩压',
    pulse: '脉搏',
    temperature: '体温'
  } [value] || escapeUi(value);
  if (key === 'id') return `<strong>#${String(value).padStart(4,'0')}</strong>`;
  const text = String(value);
  return escapeUi(fullText || text.length <= 38 ? text : text.slice(0, 38) + '…');
}

function tableMarkup(rows, columns, kind) {
  return `<table><thead><tr>${columns.map(c=>`<th>${c[1]}</th>`).join('')}<th>操作</th></tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(c=>`<td>${cell(row,...[c[0],c[2]])}</td>`).join('')}<td><button class="row-button" data-kind="${kind}" data-id="${row.id}">查看详情 →</button></td></tr>`).join('')}</tbody></table>`;
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
  $('#page-description').textContent = uiText(meta.description);
  const group = navigationGroups.find(item => item.children.includes(activeSection));
  document.querySelectorAll('.nav-section').forEach(item => {
    const current = Boolean(item.querySelector('.nav-item.active'));
    item.classList.toggle('current', current);
    item.open = false;
  });
  $('#breadcrumb').textContent = group ? `${group.title} / ${meta.title}` : `服务工作台 / ${meta.title}`;
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
    `<tr>${meta.columns.map(c=>`<td>${cell(row,c[0],c[2])}</td>`).join('')}<td><button class="row-button" data-kind="${activeSection}" data-id="${row.id}">查看 →</button></td></tr>`
    ).join('') : `<tr><td colspan="${meta.columns.length+1}" class="empty">当前范围内暂无记录</td></tr>`;
  $('#result-count').textContent = `共 ${data.total} 条记录 · 每页 20 条`;
  $('#page-number').textContent = `${page} / ${Math.max(1,Math.ceil(data.total/20))}`;
  $('#previous').disabled = page === 1;
  $('#next').disabled = page * 20 >= data.total;
  $('#workspace').dataset.section = section;
}
async function renderOverview() {
  const version = ++renderVersion;
  const [summary, ordersData, eventsData] = await Promise.all([api('/api/dashboard'), api(
    '/api/list/orders'), api('/api/list/events')]);
  if (version !== renderVersion) return;
  const stats = [
    ['在册老人', summary.elders, '人', '当前授权范围内的服务对象', navigationIcon(navigationGroups[0].icon)],
    ['已完成服务', summary.orders.completed || 0, '单',
      `累计服务金额 <span class="accent">¥ ${money(summary.orders.amount)}</span>`, navigationIcon('M5 12l4 4L19 6')
    ],
    ['待调度与接单', summary.orders.waiting || 0, '单', '关注准入条件与接单进展', navigationIcon('M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l3 2')],
    ['已核定补贴', money(summary.subsidy), '元', '包含终审通过与已拨付金额', navigationIcon('M6 4l6 7 6-7 M12 11v10 M6 12h12 M6 16h12')]
  ];
  const maximum = Math.max(1, ...summary.trend.map(t => t.orders));
  const recent = ordersData.rows.slice(0, 5);
  currentRows = recent;
  $('#overview-content').innerHTML =
    `<div class="stats-grid">${stats.map(([name,value,unit,note,icon])=>`<article class="stat-card"><div class="stat-label">${name}<span class="stat-icon">${icon}</span></div><div class="stat-value">${value}<small>${unit}</small></div><div class="stat-note">${note}</div></article>`).join('')}</div>
    <div class="overview-grid"><section class="panel trend-panel"><div class="panel-heading"><h2>服务开展情况</h2><span>按预约月份统计</span></div><div class="chart">${summary.trend.map(t=>`<div class="chart-month"><div class="chart-bar secondary-bar" style="height:${Math.max(2,t.orders/maximum*75)}%"><span>${t.orders}</span></div><div class="chart-bar" style="height:${Math.max(2,t.completed/maximum*75)}%"><span>${t.completed}</span></div><small>${t.month}</small></div>`).join('')||'<p class="muted">暂无服务记录</p>'}</div><div class="legend"><span><i class="pale"></i>全部订单</span><span><i></i>已完成订单</span></div></section>
    <section class="panel"><div class="panel-heading"><h2>今日关注</h2><span>服务待办</span></div><div class="todo-list"><a class="todo" href="#events"><span class="todo-icon">${navigationIcon(navigationGroups[3].icon)}</span><div class="todo-text"><p>持续跟进应急处置</p><small>响应、到场和处置结果及时记录</small></div><span class="count-pill">${summary.events}</span></a><a class="todo" href="#orders"><span class="todo-icon">${navigationIcon(navigationGroups[1].icon)}</span><div class="todo-text"><p>安排服务与跟进接单</p><small>资质、时段和名额同步核验</small></div><span class="count-pill">${summary.orders.waiting||0}</span></a><a class="todo" href="#elders"><span class="todo-icon">${navigationIcon(navigationGroups[0].icon)}</span><div class="todo-text"><p>评估到期与复评</p><small>${summary.reassessment.length?'查看近期到期的老人档案':'当前展示范围内暂无近期到期评估'}</small></div><span class="count-pill">${summary.reassessment.length}</span></a></div></section></div>
    <section class="panel"><div class="table-toolbar"><h2>近期服务订单</h2><a class="inline-link" href="#orders">查看全部订单 →</a></div><div class="table-scroll">${recent.length?tableMarkup(recent,sections.orders.columns,'orders'):'<p class="empty">暂无订单</p>'}</div></section>`;
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
  $('#form-description').textContent = uiText(description);
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

function topActions(kind) {
  const result = [];
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
    ], '/api/orders', '按次项目沿用标准时长；订单保存下单时的地址和价格', data => ({
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
    ], '/api/workers', '项目和社区编号用英文逗号分隔', data => ({
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
    ], '/api/vitals/batch', '按采集时刻的绑定记录确定老人归属', data => ({
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
        value: '关联订单中的服务记录、确认信息、工时及评估计划'
      })
    ], '/api/claims', '同一老人、项目、月份只保留一份申报，重复请求返回原申报')]);
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
  }), textArea('description', '求助情况')], '/api/events', '应急事件与照护计划是否有效独立处理', data => ({
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
  })], '/api/quality', '无问题时保留问题与整改字段为空；有问题时填写整改要求和期限', data => ({
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
    `<div class="detail-grid">${meta.columns.map(c=>`<div class="detail-item"><small>${c[1]}</small><span>${cell(row,c[0],c[2],true)}</span></div>`).join('')}</div>`;
  $('#detail-actions').replaceChildren();
  if (kind === 'orders') {
    const result = await api(`/api/orders/${id}`);
    row = result.order;
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>服务地址与费用</h3><p>${escapeUi(row.address)}<br><span class="muted">成交单价 ¥ ${money(row.unit_price)} / ${row.price_unit==='hour'?'小时':'次'} · 预约 ${row.duration_minutes} 分钟</span></p></div><div class="detail-section"><h3>派单与服务记录</h3>${result.timeline.filter(t=>t.assignment_id).map(t=>`<div class="timeline-entry"><p><strong>${escapeUi(t.worker_name)}</strong> ${badge(t.assignment_status)} <span class="muted">派单 #${t.assignment_id}</span></p><small>派出 ${dateText(t.assigned_at)} · 接单 ${dateText(t.accepted_at)}</small><p>签到 ${dateText(t.checkin_at)} / 签退 ${dateText(t.checkout_at)} · 认定工时 ${t.valid_hours??'—'} 小时</p><p>${escapeUi(t.service_record||'尚未填写服务记录')}</p><small>服务确认 ${dateText(t.confirmed_at)}</small></div>`).join('')||'<p class="notice">等待社区安排护工</p>'}</div>`
      );
    if (result.costs) $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>费用明细</h3><p>服务费用 ¥ ${money(result.costs.settlement)} · 核定补贴 ¥ ${money(result.costs.approved_subsidy)} · 当前自付 ¥ ${money(result.costs.payable)}</p></div>`
      );
    if (row.complaint) $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>投诉与处理</h3><p>${escapeUi(row.complaint)}</p><p>${escapeUi(row.complaint_result||'等待社区处理')}</p></div>`
      );
    orderActions(row);
  } else if (kind === 'elders') {
    const result = await api(`/api/elders/${id}`);
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>联系人与授权</h3>${result.contacts.map(c=>`<p>#${c.id} ${escapeUi(c.name)} · ${escapeUi(c.relationship)} · ${c.phone_mask} <span class="muted">授权终止 ${dateText(c.authorized_until)}</span></p>`).join('')}</div><div class="detail-section"><h3>能力评估记录</h3>${result.assessments.map(a=>`<p>${a.assessed_on} · ${a.scale} ${a.score} 分 · ${abilities[a.ability_level]} · 有效至 ${a.valid_until}</p>`).join('')||'<p class="notice">尚未登记评估</p>'}</div><div class="detail-section"><h3>照护计划</h3>${result.plans.map(p=>`<p>#${p.id} ${escapeUi(p.package_name)} ${badge(p.status)}<br><span class="muted">${p.starts_on} 至 ${p.ends_on} · 责任护工 #${p.worker_id}</span></p>`).join('')||'<p class="notice">尚未制定照护计划</p>'}</div>`
      );
    if (allowed('admin', 'community')) {
      action('登记评估', () => {
        const fields = [
          select('scale', '评估量表', [
            ['ADL', 'ADL'],
            ['MMSE', '简易智能状态']
          ]),
          field('score', '得分', 'number', {
            value: 75,
            min: 0,
            max: 100
          }),
          select('ability_level', '能力等级', abilities.map((label, i) => [i, label])),
          field('assessed_on', '评估日期', 'date', {
            value: dateInput()
          }),
          field('valid_until', '有效期截止', 'date', {
            value: dateInput(180)
          })
        ];
        showForm('登记能力评估', fields, data => post(`/api/elders/${id}/assess`, data));
        // 添加量表切换联动
        const scaleSelect = $('#action-form [name="scale"]');
        const scoreInput = $('#action-form [name="score"]');
        scaleSelect.addEventListener('change', () => {
          if (scaleSelect.value === 'MMSE') {
            scoreInput.max = 30;
            if (parseFloat(scoreInput.value) > 30) scoreInput.value = 30;
          } else {
            scoreInput.max = 100;
          }
        });
      });
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
      `<div class="detail-section"><h3>申报明细</h3>${result.items.map(i=>`<p>订单 #${i.order_id} · ${escapeUi(i.policy_name)}<br><span class="muted">服务费 ¥ ${money(i.settlement)} · 补贴 ¥ ${money(i.amount)}</span></p>`).join('')}</div><div class="detail-section"><h3>历次审核</h3>${result.reviews.map(r=>`<p>${r.stage==='street'?'街道初审':'民政终审'} · ${escapeUi(r.reviewer_name)} · ${{approve:'通过',return:'退回',reject:'不通过'}[r.decision]}<br><span class="muted">${dateText(r.reviewed_at)} ${escapeUi(r.note)}</span></p>`).join('')||'<p class="notice">等待审核</p>'}</div>`
      );
    if (allowed('admin', 'community') && row.status === 'returned') action('重新提交申报', () => routeForm(
      '补充材料并重新提交', [textArea('evidence', '补充证明材料说明', { value: row.evidence || '' })], 
      `/api/claims`, '', data => ({
        elderly_id: row.elderly_id,
        item_id: row.item_id,
        period: row.period,
        evidence: data.evidence
      })));
    if (allowed('street', 'civil') && row.status === user.role) action('审核申报', () => routeForm(
      '审核补贴申报', [select('decision', '审核结论', [
        ['approve', '通过'],
        ['return', '退回补充材料'],
        ['reject', '不通过']
      ]), textArea('note', '审核意见')], `/api/claims/${id}/review`));
    if (allowed('civil') && row.status === 'approved') action('登记拨付', () => routeForm('登记补贴拨付', [field(
      'reference', '拨付凭证号')], `/api/claims/${id}/pay`));
  } else if (kind === 'events' && allowed('admin', 'community', 'street', 'civil')) {
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>处置进度</h3><p>响应人员：${escapeUi(row.responder_name || '待响应')}<br>响应时间：${dateText(row.responded_at)}<br>到场时间：${dateText(row.arrived_at)}<br>处置结果：${escapeUi(row.result || '处理中')}</p></div>`
    );
    if (row.status !== 'closed') {
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
    }
  } else if (kind === 'notifications' && allowed('admin', 'community', 'street', 'civil')) {
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><h3>发送详情</h3><p>失败原因：${escapeUi(row.error || '无')}<br>最近尝试时间：${dateText(row.last_attempt_at)}</p></div>`
    );
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
    }), '确认删除此未使用班次；已有派单的班次会保留'));
  else if (kind === 'hours' && allowed('admin', 'agency')) action('复核工时', () => routeForm('核验异常工时', [
    field('hours', '认定工时（小时）', 'number', {
      min: 0.01
    }), textArea('note', '核验依据和凭证说明')
  ], `/api/hours/${id}/review`));
  else if (kind === 'quality') {
    $('#detail-body').insertAdjacentHTML('beforeend',
      `<div class="detail-section"><p>整改要求：${escapeUi(row.requirement||'无')}<br>整改结果：${escapeUi(row.result||'尚未提交')}</p></div>`
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
      toast('暂无符合资质、区域与时段的护工，请先补齐评估、计划或排班');
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
  })], `/api/orders/${id}/checkin`, '签到时间由服务器记录，请填写实际位置'));
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
      '确认本次服务', [], () => post(`/api/orders/${id}/confirm`, {}), '请核对服务记录、签到签退时间与服务内容，确认后保存当前账号及确认时间'
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
      ['resume', '恢复服务流程'],
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
    ], { value: row.rating || 5 }), textArea('feedback', '评价内容', {
      optional: true,
      value: row.feedback || ''
    }), textArea('complaint', '投诉内容', {
      optional: true,
      value: row.complaint || ''
    })], `/api/orders/${id}/feedback`, '', data => {
      const result = { ...data };
      // 空字符串视为明确清空，未改动则不传递该字段
      if (result.feedback === (row.feedback || '')) delete result.feedback;
      else if (result.feedback === '') result.feedback = null;
      if (result.complaint === (row.complaint || '')) delete result.complaint;
      else if (result.complaint === '') result.complaint = null;
      return result;
    }));
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
    $('#login-error').textContent = uiText(error.message);
  } finally {
    button.disabled = false;
  }
});
// Mobile navigation changes presentation only.
$('#menu-toggle').addEventListener('click', () => {
  const expanded = $('.sidebar').classList.toggle('is-expanded');
  $('#menu-toggle').setAttribute('aria-expanded', String(expanded));
});
// Header menus only change presentation; page permissions remain in sections.
function closeHeaderMenus() {
  document.querySelectorAll('.nav-section[open]').forEach(item => item.open = false);
}
function closeMobileNavigation() {
  $('.sidebar').classList.remove('is-expanded');
  $('#menu-toggle').setAttribute('aria-expanded', 'false');
}
document.addEventListener('click', event => {
  const summary = event.target.closest('#navigation summary');
  if (summary) {
    document.querySelectorAll('.nav-section[open]').forEach(item => {
      if (item !== summary.parentElement) item.open = false;
    });
    return;
  }
  if (event.target.closest('#navigation a') || !event.target.closest('#navigation')) closeHeaderMenus();
  if (event.target.closest('#navigation a')) closeMobileNavigation();
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const summary = document.activeElement.closest('.nav-section')?.querySelector('summary');
  closeHeaderMenus();
  closeMobileNavigation();
  if (summary) {
    if (window.matchMedia('(max-width: 1100px)').matches) $('#menu-toggle').focus();
    else summary.focus();
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
    $('#form-error').textContent = uiText(error.message);
  } finally {
    button.disabled = false;
  }
});
window.addEventListener('hashchange', () => {
  if (user) navigate().catch(error => toast(error.message));
});
$('#login-title').textContent = uiText($('#login-title').textContent);
start().catch(() => showLogin());
