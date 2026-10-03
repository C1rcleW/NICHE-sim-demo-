// ── I18N ────────────────────────────────────────────────────────────────────
const I18N = {
  zh: {
    'app.title': '家庭ABM仪表板',
    'app.logo': 'Family ABM',
    'tab.setup': '仿真设置',
    'tab.charts': '数据图表',
    'tab.fitting': '曲线拟合',
    'tab.network': '关系网络',
    'status.ready': '就绪',
    'status.running': '运行中...',
    'status.simDone': '仿真完成',
    'status.fitting': '拟合中...',
    'status.fitDone': '拟合完成 (R^2={0})',
    'status.error': '错误',
    'setup.title': '仿真设置',
    'setup.steps': '步数',
    'setup.run': '运行仿真',
    'setup.results': '结果',
    'setup.agents': '成员',
    'setup.family': '家庭',
    'setup.name': '名称',
    'setup.kpi_steps': '步数',
    'setup.kpi_agents': '智能体',
    'setup.kpi_records': '记录条数',
    'charts.warn': '请先运行仿真以查看图表。',
    'charts.timeseries': '时间序列',
    'charts.no_data': '当前选择下没有可绘制的数据（该 agent 没有对应状态量）。',
    'fitting.need_mapping': '该模型的状态名与 ABM 列名没有默认对应关系，无法直接拟合。',
    'fitting.mapping_suffix': ' （需映射）',
    'fitting.manual_suffix': ' （需人工指定映射）',
    'fitting.warn_sentinel': '优化停在失败哨兵：该解未成功积分，R² 无意义。',
    'fitting.warn_bounds': '参数被边界钉住：{0}（该方向可能不可辨识或边界不合适）。',
    'fitting.warn_r2_nonpositive': 'R² 非正：该模型结构不适合这些状态列，Converged 只表示优化器跑完了。',
    'charts.niche': '生境空间',
    'fitting.warn': '请先运行仿真，然后选择模型进行拟合。',
    'fitting.title': 'ODE模型拟合（兰彻斯特型）',
    'fitting.model': '模型',
    'fitting.agent': '智能体（空=聚合）',
    'fitting.aggregate': '— 聚合 —',
    'fitting.run': '拟合模型',
    'fitting.result': '拟合结果',
    'fitting.chart': 'ABM数据 vs ODE拟合',
    'fitting.converged_yes': '是',
    'fitting.converged_no': '否',
    'fitting.data_suffix': ' 数据',
    'fitting.ode_fit': 'ODE拟合',
    'network.warn': '请先运行仿真以查看家庭关系网络。',
    'network.trust': '信任',
    'network.conflict': '冲突',
    'setup.params': '参数设置',
    'setup.reset_params': '恢复默认',
    'param.Education': '教育', 'param.Income': '收入', 'param.Health': '健康',
    'param.Stress': '压力', 'param.Happiness': '幸福', 'param.Noise': '随机扰动',
    'param.education_rate': '学习速率', 'param.income_base': '基础收入',
    'param.income_edu_boost': '教育加成', 'param.income_age_peak': '收入峰值年龄',
    'param.income_age_spread': '年龄跨度', 'param.health_decay_base': '基础衰减',
    'param.health_decay_age': '年龄衰减', 'param.health_edu_protection': '教育保护',
    'param.stress_base': '基础压力', 'param.stress_work_add': '工作压力',
    'param.stress_decay': '衰减速率', 'param.stress_neuro_sensitivity': '神经质敏感',
    'param.happiness_baseline': '基础值', 'param.happiness_health_weight': '健康权重',
    'param.happiness_income_weight': '收入权重', 'param.happiness_edu_weight': '教育权重',
    'param.happiness_stress_penalty': '压力惩罚', 'param.happiness_recovery': '恢复速率',
    'param.randomness': '扰动强度',
    'chart.agent_series': '智能体状态时间序列',
    'chart.time': '时间',
    'chart.value': '数值',
    'chart.niche_title': '社会生境空间',
    'chart.economic': '经济',
    'chart.social': '社会',
    'chart.fit_title': 'ABM数据 vs ODE拟合',
  },
  en: {
    'app.title': 'Family ABM Dashboard',
    'app.logo': 'Family ABM',
    'tab.setup': 'Setup',
    'tab.charts': 'Charts',
    'tab.fitting': 'Fitting',
    'tab.network': 'Network',
    'status.ready': 'Ready',
    'status.running': 'Running...',
    'status.simDone': 'Simulation complete',
    'status.fitting': 'Fitting...',
    'status.fitDone': 'Fit done (R^2={0})',
    'status.error': 'Error',
    'setup.title': 'Simulation Setup',
    'setup.steps': 'Steps',
    'setup.run': 'Run Simulation',
    'setup.results': 'Results',
    'setup.agents': 'Agents',
    'setup.family': 'Family',
    'setup.name': 'Name',
    'setup.kpi_steps': 'Steps',
    'setup.kpi_agents': 'Agents',
    'setup.kpi_records': 'Records',
    'charts.warn': 'Run a simulation first to see charts.',
    'charts.timeseries': 'Time Series',
    'charts.no_data': 'No plottable data for the current selection (this agent has no such state).',
    'fitting.need_mapping': 'This model has no default column mapping and cannot be fitted directly.',
    'fitting.mapping_suffix': ' (needs mapping)',
    'fitting.manual_suffix': ' (manual mapping required)',
    'fitting.warn_sentinel': 'Optimizer stopped on the failure sentinel: the solution never integrated, R^2 is meaningless.',
    'fitting.warn_bounds': 'Parameters pinned at bounds: {0} (that direction may be unidentifiable or the bounds unsuitable).',
    'fitting.warn_r2_nonpositive': 'Non-positive R^2: this model structure does not suit these state columns; Converged only means the optimizer finished.',
    'charts.niche': 'Niche Space',
    'fitting.warn': 'Run a simulation first, then select a model to fit.',
    'fitting.title': 'ODE Model Fitting (Lanchester-type)',
    'fitting.model': 'Model',
    'fitting.agent': 'Agent (empty = aggregate)',
    'fitting.aggregate': '— Aggregate —',
    'fitting.run': 'Fit Model',
    'fitting.result': 'Fit Result',
    'fitting.chart': 'ABM Data vs ODE Fit',
    'fitting.converged_yes': 'Yes',
    'fitting.converged_no': 'No',
    'fitting.data_suffix': ' data',
    'fitting.ode_fit': 'ODE fit',
    'network.warn': 'Run a simulation first to see family networks.',
    'network.trust': 'Trust',
    'network.conflict': 'Conflict',
    'setup.params': 'Parameters',
    'setup.reset_params': 'Reset Defaults',
    'param.Education': 'Education', 'param.Income': 'Income', 'param.Health': 'Health',
    'param.Stress': 'Stress', 'param.Happiness': 'Happiness', 'param.Noise': 'Noise',
    'param.education_rate': 'Learn Rate', 'param.income_base': 'Base Income',
    'param.income_edu_boost': 'Edu Boost', 'param.income_age_peak': 'Peak Age',
    'param.income_age_spread': 'Age Spread', 'param.health_decay_base': 'Base Decay',
    'param.health_decay_age': 'Age Decay', 'param.health_edu_protection': 'Edu Protection',
    'param.stress_base': 'Base Load', 'param.stress_work_add': 'Work Add',
    'param.stress_decay': 'Decay Rate', 'param.stress_neuro_sensitivity': 'Neuro Sens',
    'param.happiness_baseline': 'Baseline', 'param.happiness_health_weight': 'Health Wt',
    'param.happiness_income_weight': 'Income Wt', 'param.happiness_edu_weight': 'Edu Wt',
    'param.happiness_stress_penalty': 'Stress Pen', 'param.happiness_recovery': 'Recovery',
    'param.randomness': 'Noise Level',
    'chart.agent_series': 'Agent State Time Series',
    'chart.time': 'Time',
    'chart.value': 'Value',
    'chart.niche_title': 'Social Niche Space',
    'chart.economic': 'Economic',
    'chart.social': 'Social',
    'chart.fit_title': 'ABM Data vs ODE Fit',
  },
};

const LANG_KEY = 'family_abm_lang';
let currentLang = localStorage.getItem(LANG_KEY) || 'en';

function t(key, ...args) {
  const map = I18N[currentLang] || I18N['en'];
  let s = map[key] || I18N['en'][key] || key;
  args.forEach((a, i) => { s = s.replace('{' + i + '}', a); });
  return s;
}

function refreshI18n() {
  document.documentElement.lang = currentLang;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.getAttribute('data-i18n-title'));
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
  });
  document.title = t('app.title');
  document.querySelectorAll('#langDrop .lang-item').forEach(item => {
    item.classList.toggle('active', item.dataset.lang === currentLang);
    item.textContent = item.dataset.lang === 'zh' ? '简体中文' : 'English';
  });
  if (simData) {
    document.getElementById('agentSelectCard').querySelector('h2').textContent = t('setup.agents');
    document.querySelectorAll('#resultKPIs .label').forEach((el, i) => {
      el.textContent = t(['setup.kpi_steps', 'setup.kpi_agents', 'setup.kpi_records'][i]);
    });
  }
}

function setLang(lang) {
  currentLang = lang;
  localStorage.setItem(LANG_KEY, lang);
  refreshI18n();
  if (simData) buildCharts();
}

// ── State ──────────────────────────────────────────────────────────────────
let simData = null;
const CHART_THEME = {
  paper_bgcolor: '#fff', plot_bgcolor: '#f8fafc',
  font: { family: '-apple-system,BlinkMacSystemFont,sans-serif', size: 11 },
  margin: { l: 50, r: 30, t: 30, b: 50 },
  legend: { orientation: 'h', y: 1.12, font: { size: 10 } },
};

// ── Tabs ───────────────────────────────────────────────────────────────────
document.querySelectorAll('#tabNav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#tabNav button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    onTabSwitch(btn.dataset.tab);
  });
});

function onTabSwitch(tab) {
  if (tab === 'charts' && simData) buildCharts();
  if (tab === 'fitting' && simData) buildFittingView();
  if (tab === 'network' && simData) buildNetwork();
}

// ── Language switcher ──────────────────────────────────────────────────────
document.getElementById('langBtn').addEventListener('click', e => {
  e.stopPropagation();
  document.getElementById('langDrop').classList.toggle('show');
});
document.querySelectorAll('#langDrop .lang-item').forEach(item => {
  item.addEventListener('click', () => {
    setLang(item.dataset.lang);
    document.getElementById('langDrop').classList.remove('show');
  });
});
document.addEventListener('click', () => {
  document.getElementById('langDrop').classList.remove('show');
});

// ── API ────────────────────────────────────────────────────────────────────
async function api(url, opts = {}) {
  try {
    const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
    return await res.json();
  } catch (e) {
    return { error: e.message || 'Network error' };
  }
}

// ── Parameters ─────────────────────────────────────────────────────────────
let paramDefaults = {};
let paramGroups = {};

async function loadParams() {
  const res = await api('/api/params');
  if (res.defaults) paramDefaults = res.defaults;
  if (res.groups) paramGroups = res.groups;
  buildParams();
}

function buildParams() {
  const container = document.getElementById('paramGroups');
  let html = '';
  const enLabels = {
    'Education': 'Education', 'Income': 'Income', 'Health': 'Health',
    'Stress': 'Stress', 'Happiness': 'Happiness', 'Noise': 'Noise',
    'education_rate': 'Learn Rate', 'income_base': 'Base Income', 'income_edu_boost': 'Edu Boost',
    'income_age_peak': 'Peak Age', 'income_age_spread': 'Age Spread', 'health_decay_base': 'Base Decay',
    'health_decay_age': 'Age Decay', 'health_edu_protection': 'Edu Protection', 'stress_base': 'Base Load',
    'stress_work_add': 'Work Add', 'stress_decay': 'Decay Rate', 'stress_neuro_sensitivity': 'Neuro Sens',
    'happiness_baseline': 'Baseline', 'happiness_health_weight': 'Health Wt', 'happiness_income_weight': 'Income Wt',
    'happiness_edu_weight': 'Edu Wt', 'happiness_stress_penalty': 'Stress Pen', 'happiness_recovery': 'Recovery',
    'randomness': 'Noise Level',
  };
  Object.entries(paramGroups).forEach(([group, keys]) => {
    html += `<div class="param-group"><h4 class="param-group-title" data-i18n="param.${group}">${group}</h4><div class="param-items">`;
    keys.forEach(key => {
      const val = paramDefaults[key] !== undefined ? paramDefaults[key] : 0;
      html += `<div class="param-item">
        <label data-i18n="param.${key}">${enLabels[key] || key}</label>
        <input type="number" class="param-input" data-param="${key}" value="${val}" step="0.001" min="0" max="5">
      </div>`;
    });
    html += `</div></div>`;
  });
  container.innerHTML = html;
}

function getParams() {
  const params = {};
  document.querySelectorAll('.param-input').forEach(inp => {
    params[inp.dataset.param] = parseFloat(inp.value) || 0;
  });
  return params;
}

window.resetParams = function() {
  document.querySelectorAll('.param-input').forEach(inp => {
    const key = inp.dataset.param;
    if (paramDefaults[key] !== undefined) inp.value = paramDefaults[key];
  });
};

// ── Simulation ─────────────────────────────────────────────────────────────
const defaultFamilies = [
  { name: 'Smith', members: [
    { name: 'Father', age: 40, gender: 'male', role_name: 'parent' },
    { name: 'Mother', age: 38, gender: 'female', role_name: 'parent' },
    { name: 'Child', age: 10, gender: 'male', role_name: 'child' },
  ]},
  { name: 'Jones', members: [
    { name: 'Mom', age: 35, gender: 'female', role_name: 'parent' },
    { name: 'Daughter', age: 8, gender: 'female', role_name: 'child' },
  ]},
];

function buildFamilyConfigs() {
  const container = document.getElementById('familyConfigs');
  let html = '';
  defaultFamilies.forEach((f, fi) => {
    html += `<div class="family-card"><h3>${f.name} ${t('setup.family')}</h3>`;
    f.members.forEach((m, mi) => {
      html += `<div class="member-line">
        <input value="${m.name}" data-fam="${fi}" data-mem="${mi}" data-key="name" placeholder="${t('setup.name')}">
        <input type="number" value="${m.age}" data-fam="${fi}" data-mem="${mi}" data-key="age" min="0" style="width:60px">
        <select data-fam="${fi}" data-mem="${mi}" data-key="gender">
          <option ${m.gender==='male'?'selected':''}>male</option>
          <option ${m.gender==='female'?'selected':''}>female</option>
        </select>
        <select data-fam="${fi}" data-mem="${mi}" data-key="role_name">
          <option ${m.role_name==='parent'?'selected':''}>parent</option>
          <option ${m.role_name==='child'?'selected':''}>child</option>
          <option ${m.role_name==='adult'?'selected':''}>adult</option>
          <option ${m.role_name==='elder'?'selected':''}>elder</option>
        </select>
      </div>`;
    });
    html += '</div>';
  });
  container.innerHTML = html;
}

function getFamilyConfigs() {
  const families = [];
  document.querySelectorAll('.family-card').forEach(card => {
    const h3 = card.querySelector('h3').textContent;
    const name = h3.replace(' ' + t('setup.family'), '');
    const members = [];
    card.querySelectorAll('.member-line').forEach(line => {
      const inputs = line.querySelectorAll('input');
      const selects = line.querySelectorAll('select');
      members.push({
        name: inputs[0].value,
        age: parseFloat(inputs[1].value) || 25,
        gender: selects[0].value,
        role_name: selects[1].value,
      });
    });
    families.push({ name, members });
  });
  return families;
}

async function runSimulation() {
  setStatus('running', t('status.running'));
  const cfg = {
    steps: parseInt(document.getElementById('simSteps').value) || 120,
    params: getParams(),
    families: getFamilyConfigs(),
  };
  const res = await api('/api/run', { method: 'POST', body: JSON.stringify(cfg) });
  if (res.error) { setStatus('error', res.error); return; }

  const data = await api('/api/data');
  if (data.error) { setStatus('error', data.error); return; }
  simData = data;

  document.getElementById('resultCard').style.display = 'block';
  document.getElementById('agentSelectCard').style.display = 'block';
  document.getElementById('resultKPIs').innerHTML = `
    <div class="result-kpi"><div class="value">${res.steps}</div><div class="label">${t('setup.kpi_steps')}</div></div>
    <div class="result-kpi"><div class="value">${res.agents}</div><div class="label">${t('setup.kpi_agents')}</div></div>
    <div class="result-kpi"><div class="value">${res.observations}</div><div class="label">${t('setup.kpi_records')}</div></div>
  `;

  buildAgentList();
  await loadModelInfo();
  setStatus('ok', t('status.simDone'));
  document.querySelector('#tabNav button[data-tab="charts"]').click();
}

// 模型可映射性：抽象模型（square_law/influence/...）的状态名与 ABM 列名没有默认
// 对应关系，必须显式给出 state_mapping。此前前端只发 model_name/agent_id/robust，
// 导致 7 个模型里有 6 个在界面上永远返回 400。
let modelInfo = {};

async function loadModelInfo() {
  const res = await api('/api/models');
  if (res.error || !res.models) return;
  modelInfo = {};
  res.models.forEach(m => { modelInfo[m.name] = m; });

  const sel = document.getElementById('fitModel');
  const options = res.models.map(m => {
    // 无法直接映射、且候选列不足以自动给出映射的模型：置灰不可选。
    // 此前只标注"需人工指定"但页面上没有映射输入控件，等于给用户一个死路。
    if (m.needs_manual_mapping) {
      return `<option value="${m.name}" disabled>${m.name}${t('fitting.manual_suffix')}</option>`;
    }
    const suffix = m.directly_fittable ? '' : t('fitting.mapping_suffix');
    return `<option value="${m.name}">${m.name}${suffix}</option>`;
  });
  sel.innerHTML = options.join('');
  const preferred = ['wellbeing', 'influence', 'logistic', 'square_law', 'linear_law', 'lotka_volterra', 'resource_competition'];
  const pick = preferred.find(n => modelInfo[n] && !modelInfo[n].needs_manual_mapping);
  if (pick) sel.value = pick;
}

function currentStateMapping(modelName) {
  const info = modelInfo[modelName];
  if (!info) return null;
  if (info.directly_fittable) return null; // 走默认约定即可
  if (info.needs_manual_mapping) return undefined; // 信号：必须人工指定
  return info.suggested_mapping || null;
}

function buildAgentList() {
  if (!simData) return;
  const list = document.getElementById('agentsList');
  list.innerHTML = simData.agents.map(a =>
    `<span class="agent-chip" data-id="${a.id}" onclick="selAgent(this,'${a.id}')">${a.name} (${a.role})</span>`
  ).join('');

  const sel = document.getElementById('fitAgent');
  sel.innerHTML = `<option value="">${t('fitting.aggregate')}</option>` +
    simData.agents.map(a => `<option value="${a.id}">${a.name} (${a.role})</option>`).join('');
}

let selAgentId = null;
function selAgent(el, id) {
  selAgentId = (selAgentId === id) ? null : id;
  document.querySelectorAll('.agent-chip').forEach(c => c.classList.remove('sel'));
  if (selAgentId) el.classList.add('sel');
  buildCharts();
}

// ── Charts ─────────────────────────────────────────────────────────────────
function buildCharts() {
  const warn = document.getElementById('chartWarning');
  if (!simData) { warn.style.display = 'block'; return; }
  warn.style.display = 'none';

  document.getElementById('timeseriesCard').style.display = 'block';
  document.getElementById('nicheCard').style.display = 'block';

  buildTimeSeries();
  buildNicheChart();
}

function buildTimeSeries() {
  const df = simData.data;
  let series = df;
  if (selAgentId) series = series.filter(r => r.agent_id === selAgentId);

  const stateCols = simData.columns.filter(c => c.startsWith('state_'));
  const traces = stateCols.map(col => {
    const byTime = {};
    series.forEach(r => {
      const v = r[col];
      // 缺失值必须是 null（不是 0）：Household 行没有成员状态列，
      // 用 `|| 0` 会把"不存在"伪造成 0，使均值比真实值低约 28.6%。
      if (v === null || v === undefined || Number.isNaN(v)) return;
      byTime[r.time] = byTime[r.time] || [];
      byTime[r.time].push(v);
    });
    const t = Object.keys(byTime).map(Number).sort((a, b) => a - b);
    const vals = t.map(ti => byTime[ti].reduce((a, b) => a + b, 0) / byTime[ti].length);
    if (!t.length) return null;
    return { x: t, y: vals, type: 'scatter', mode: 'lines', name: col.replace('state_', '') };
  }).filter(Boolean);
  if (!traces.length) {
    Plotly.purge('chartTimeSeries');
    document.getElementById('chartTimeSeries').innerHTML =
      `<div class="loading">${t('charts.no_data')}</div>`;
    return;
  }

  Plotly.newPlot('chartTimeSeries', traces, {
    ...CHART_THEME, title: t('chart.agent_series'),
    xaxis: { title: t('chart.time') }, yaxis: { title: t('chart.value'), range: [0, 1] },
  }, { responsive: true });
}

async function buildNicheChart() {
  const res = await api('/api/niche');
  if (res.error || !res.niches) return;

  const roleColors = { parent: '#e74c3c', child: '#3498db', adult: '#f39c12', elder: '#2ecc71' };
  const traces = [{
    x: res.niches.map(n => n.position.economic || 0),
    y: res.niches.map(n => n.position.social || 0),
    text: res.niches.map(n => n.name),
    type: 'scatter', mode: 'markers+text', textposition: 'top center',
    marker: { size: 14, color: res.niches.map(n => roleColors[n.role] || '#95a5a6'), line: { width: 1, color: '#fff' } },
  }];
  Plotly.newPlot('chartNiche', traces, {
    ...CHART_THEME, title: t('chart.niche_title'),
    xaxis: { title: t('chart.economic'), range: [0, 1] }, yaxis: { title: t('chart.social'), range: [0, 1] },
  }, { responsive: true });
}

// ── Fitting ────────────────────────────────────────────────────────────────
function buildFittingView() {
  document.getElementById('fitWarning').style.display = 'none';
  document.getElementById('fitControlCard').style.display = 'block';
}

async function runFitting() {
  setStatus('running', t('status.fitting'));
  const model = document.getElementById('fitModel').value;
  const agent = document.getElementById('fitAgent').value || null;
  const mapping = currentStateMapping(model);
  if (mapping === undefined) {
    // 候选状态列不足以覆盖该模型的状态数：必须由用户显式指定映射，不能瞎猜
    setStatus('error', t('fitting.need_mapping'));
    return;
  }

  const res = await api('/api/fit', {
    method: 'POST',
    body: JSON.stringify({ model_name: model, agent_id: agent, robust: true, state_mapping: mapping }),
  });
  if (res.error) { setStatus('error', res.error); return; }

  document.getElementById('fitResultCard').style.display = 'block';
  document.getElementById('fitChartCard').style.display = 'block';

  const s = res.summary;
  // 告警必须可见：贴边参数表示该方向可能不可辨识；哨兵命中表示解本身无效。
  const warnings = [];
  if (res.warning) warnings.push(res.warning);
  if (s.hit_sentinel) warnings.push(t('fitting.warn_sentinel'));
  if (s.params_at_bounds && s.params_at_bounds.length) {
    warnings.push(t('fitting.warn_bounds', s.params_at_bounds.join(', ')));
  }
  // R² 非正时也要显式提示：converged 只说明优化器跑完了，不代表模型适用
  if (s.r_squared !== null && s.r_squared <= 0) {
    warnings.push(t('fitting.warn_r2_nonpositive'));
  }
  document.getElementById('fitKPIs').innerHTML = `
    <div class="result-kpi"><div class="value">${s.r_squared !== null ? s.r_squared.toFixed(4) : '\u2014'}</div><div class="label">R^2</div></div>
    <div class="result-kpi"><div class="value">${s.converged ? t('fitting.converged_yes') : t('fitting.converged_no')}</div><div class="label">Converged</div></div>
  ` + (warnings.length
    ? `<div class="fit-warning">${warnings.map(w => `<div>\u26a0 ${w}</div>`).join('')}</div>`
    : '');
  document.getElementById('fitParams').innerHTML = Object.entries(s.params).map(([k, v]) =>
    `<span class="fit-param"><span class="key">${k}</span> <span class="val">${typeof v === 'number' ? v.toFixed(4) : v}</span></span>`
  ).join('');

  buildFitChart(res);
  const r2val = s.r_squared !== null ? s.r_squared.toFixed(4) : '\u2014';
  setStatus('ok', t('status.fitDone', r2val));
}

function buildFitChart(res) {
  if (!simData) return;
  const df = simData.data;
  const agentId = document.getElementById('fitAgent').value || null;
  let series = df;
  if (agentId) series = series.filter(r => r.agent_id === agentId);

  const predTraces = res.predict_trace.length > 0;
  const stateCols = simData.columns.filter(c => c.startsWith('state_'));
  const traces = [];

  stateCols.forEach(col => {
    const byTime = {};
    series.forEach(r => {
      const v = r[col];
      // 同 buildTimeSeries：null 表示"该 agent 没有这个状态"，不能当 0 参与均值
      if (v === null || v === undefined || Number.isNaN(v)) return;
      byTime[r.time] = byTime[r.time] || [];
      byTime[r.time].push(v);
    });
    // 变量名不要用 t：它会遮蔽上面的 i18n 函数 t()，导致下面 t('fitting.data_suffix')
    // 抛 "TypeError: t is not a function"（每次成功拟合都在绘图阶段中断）
    const timeKeys = Object.keys(byTime).map(Number).sort((a, b) => a - b);
    if (!timeKeys.length) return;
    const vals = timeKeys.map(ti => byTime[ti].reduce((a, b) => a + b, 0) / byTime[ti].length);
    traces.push({ x: timeKeys, y: vals, type: 'scatter', mode: 'markers',
      name: col.replace('state_', '') + t('fitting.data_suffix'),
      marker: { size: 4 }, opacity: 0.6 });
  });

  if (predTraces) {
    res.predict_trace.forEach(tr => {
      traces.push({ x: tr.t, y: tr.y, type: 'scatter', mode: 'lines',
        name: t('fitting.ode_fit'), line: { width: 2, dash: 'solid' } });
    });
  }

  Plotly.newPlot('chartFit', traces, {
    ...CHART_THEME, title: t('chart.fit_title'),
    xaxis: { title: t('chart.time') }, yaxis: { title: t('chart.value'), range: [0, 1] },
  }, { responsive: true });
}

// ── Network ────────────────────────────────────────────────────────────────
async function buildNetwork() {
  const warn = document.getElementById('netWarning');
  if (!simData) { warn.style.display = 'block'; return; }
  warn.style.display = 'none';

  const res = await api('/api/network');
  if (res.error || !res.networks) return;

  const container = document.getElementById('networkCards');
  container.innerHTML = res.networks.map((net, i) =>
    `<div class="card"><div class="card-header"><h2>${net.name}</h2></div><div class="chart-container" id="networkChart${i}"></div></div>`
  ).join('');

  setTimeout(() => {
    res.networks.forEach((net, i) => {
      const n = net.nodes.length;
      const nodeTrace = {
        x: [], y: [], text: [], type: 'scatter', mode: 'markers+text',
        textposition: 'top center', hoverinfo: 'text',
        marker: { size: 20, color: [], line: { width: 1, color: '#fff' } },
      };
      const roleColors = { parent: '#e74c3c', adult: '#f39c12', child: '#3498db', elder: '#2ecc71' };
      net.nodes.forEach((node, j) => {
        const angle = (2 * Math.PI * j) / n - Math.PI / 2;
        nodeTrace.x.push(Math.cos(angle));
        nodeTrace.y.push(Math.sin(angle));
        nodeTrace.text.push(node.name);
        nodeTrace.marker.color.push(roleColors[node.role] || '#95a5a6');
      });
      const edgeTraces = net.edges.map(e => {
        const si = net.nodes.findIndex(nn => nn.id === e.source);
        const ti = net.nodes.findIndex(nn => nn.id === e.target);
        return si >= 0 && ti >= 0 ? {
          x: [nodeTrace.x[si], nodeTrace.x[ti]], y: [nodeTrace.y[si], nodeTrace.y[ti]],
          type: 'scatter', mode: 'lines',
          line: { width: Math.max(0.5, e.weight * 4),
            color: ['#27ae60', '#e67e22', '#e74c3c'][Math.min(2, Math.floor(e.conflict * 3))] },
          hovertext: `${t('network.trust')}: ${e.trust}, ${t('network.conflict')}: ${e.conflict}`,
        } : null;
      }).filter(Boolean);

      Plotly.newPlot('networkChart' + i, [nodeTrace, ...edgeTraces], {
        ...CHART_THEME, title: net.name,
        xaxis: { visible: false, range: [-1.3, 1.3] },
        yaxis: { visible: false, range: [-1.3, 1.3] },
        showlegend: false,
      }, { responsive: true });
    });
  }, 200);
}

// ── Utils ──────────────────────────────────────────────────────────────────
function setStatus(state, msg) {
  const dot = document.getElementById('statusDot');
  dot.className = 'dot' + (state === 'ok' ? ' ok' : '');
  document.getElementById('statusText').textContent = msg;
}

// ── Init ───────────────────────────────────────────────────────────────────
buildFamilyConfigs();
loadParams();
refreshI18n();
setLang(currentLang);
