from __future__ import annotations
from typing import Optional
from pathlib import Path
import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..core.environment import Environment
from ..core.scheduler import Scheduler
from ..core.simulation import Simulation
from ..family.family_member import FamilyMember
from ..family.household import Household
from ..family.roles import ROLE_REGISTRY
from ..niche.micro_niche import MicroNiche
from ..ml.recorder import StateRecorder
from ..fitting.fitter import make_fitter
from ..fitting.lanchester import MODEL_REGISTRY, MODEL_STATE_NAMES

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / 'templates'))

app = FastAPI(title='Family ABM Dashboard', version='0.2.0')
app.mount('/static', StaticFiles(directory=str(HERE / 'static')), name='static')

# ── Global simulation state ────────────────────────────────────────────────
_sim_env: Optional[Environment] = None
_sim_df: Optional[pd.DataFrame] = None
_sim_recorder: Optional[StateRecorder] = None
_last_fitter = None

# ── Pydantic models ────────────────────────────────────────────────────────

class SimConfig(BaseModel):
    steps: int = 120
    params: dict = {}
    families: list[dict] = [
        {'name': 'Smith', 'members': [
            {'name': 'Father', 'age': 40, 'gender': 'male', 'role_name': 'parent'},
            {'name': 'Mother', 'age': 38, 'gender': 'female', 'role_name': 'parent'},
            {'name': 'Child',  'age': 10, 'gender': 'male',   'role_name': 'child'},
        ]},
        {'name': 'Jones', 'members': [
            {'name': 'Mom',   'age': 35, 'gender': 'female', 'role_name': 'parent'},
            {'name': 'Daughter', 'age': 8, 'gender': 'female', 'role_name': 'child'},
        ]},
    ]

class FitRequest(BaseModel):
    model_name: str = 'wellbeing'
    agent_id: Optional[str] = None
    robust: bool = True
    # 抽象模型（square_law 的 R1/R2、influence 的 O1/O2 等）与 ABM 状态列之间没有
    # 默认语义对应关系，必须由调用方显式给出；默认 None 表示使用
    # 「状态名 -> state_<状态名>」约定。
    state_mapping: Optional[dict[str, str]] = None


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get('/', response_class=HTMLResponse)
async def dashboard(request: Request):
    template = templates.get_template('index.html')
    return HTMLResponse(
        template.render(request=request, models=list(MODEL_REGISTRY.keys()))
    )


@app.get('/api/params')
async def api_params():
    from ..family.family_member import DEFAULT_PARAMS
    groups = {
        "Education": ["education_rate"],
        "Income": ["income_base", "income_edu_boost", "income_age_peak", "income_age_spread"],
        "Health": ["health_decay_base", "health_decay_age", "health_edu_protection"],
        "Stress": ["stress_base", "stress_work_add", "stress_decay", "stress_neuro_sensitivity"],
        "Happiness": ["happiness_baseline", "happiness_health_weight", "happiness_income_weight", "happiness_edu_weight", "happiness_stress_penalty", "happiness_recovery"],
        "Noise": ["randomness"],
    }
    return JSONResponse({
        'defaults': DEFAULT_PARAMS,
        'groups': groups,
    })


@app.post('/api/run')
async def api_run(cfg: SimConfig):
    global _sim_env, _sim_df, _sim_recorder

    env = Environment()
    env.params = cfg.params
    for fam in cfg.families:
        hh = Household(name=f"{fam['name']} Household")
        env.add_agent(hh)
        for m in fam['members']:
            member = FamilyMember(**m)
            hh.add_member(member)

    recorder = StateRecorder(record_agents=True)
    sim = Simulation(env, scheduler=Scheduler('sequential'))
    sim.add_recorder(recorder)
    sim.run(cfg.steps)

    _sim_env, _sim_recorder = env, recorder
    _sim_df = recorder.to_dataframe()

    return JSONResponse({
        'status': 'ok',
        'steps': cfg.steps,
        'agents': len(env.agents),
        'observations': len(_sim_df),
    })


@app.get('/api/data')
async def api_data():
    global _sim_df, _sim_env
    if _sim_df is None or _sim_env is None:
        return JSONResponse({'error': 'No simulation data. POST /api/run first.'}, 400)

    agents = []
    for a in _sim_env.get_agents():
        if isinstance(a, FamilyMember):
            agents.append({
                'id': a.id,
                'name': a.get_attribute('name'),
                'role': a.get_attribute('role'),
                'age': round(a.get_attribute('age'), 1),
            })

    df = _sim_df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round(4)

    # 缺失值一律传 null，不再 fillna(0)：
    # Household 行没有 state_happiness 等成员状态列，填 0 会让前端聚合值
    # 比真实值低约 28.6%，并与 fitter 自己用的 NaN 跳过均值不是同一序列。
    # pandas 的 NaN 在 json.dumps 中会变成非法的 NaN 字面量，因此显式转成 None。
    records = df.astype(object).where(pd.notna(df), None).to_dict(orient='records')
    statistics = _sim_recorder.to_statistics_dataframe() if _sim_recorder is not None else pd.DataFrame()

    return JSONResponse({
        'agents': agents,
        'columns': list(df.columns),
        'data': records,
        'statistics': statistics.to_dict(orient='records'),
        'steps': int(df['time'].max()) if 'time' in df.columns else 0,
    })


VARIANCE_EPS = 1e-9


def _column_variance_report(df: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    """把 ``state_`` 列分成 (可用于拟合, 常量, 无法验证)。

    判据刻意采用**拟合目标序列**本身（即按 time 聚合后的均值），而不是全表
    pooled 的 min/max：全表跨度会把"每个 agent 各自恒定、但不同 agent 取值不同"
    的列误判为有变化（跨 agent 方差不是时间序列方差），而拟合用的正是按 time
    聚合后的序列。

    - 可用于拟合：按 time 聚合后的均值序列跨度 > VARIANCE_EPS
    - 常量：能算出序列但跨度 ~ 0
    - 无法验证：完全没有有效观测（例如该列全为 NaN），按"不可信"处理
    """
    usable: list[str] = []
    constant: list[str] = []
    unverifiable: list[str] = []
    if df is None or df.empty or 'time' not in df.columns:
        return usable, constant, unverifiable

    for column in sorted(str(c) for c in df.columns if str(c).startswith('state_')):
        series = df[column] if column in df.columns else None
        if series is None:
            unverifiable.append(column)
            continue
        means = series.groupby(df['time']).mean().dropna()
        if means.empty:
            unverifiable.append(column)
            continue
        span = float(means.max() - means.min())
        (usable if span > VARIANCE_EPS else constant).append(column)
    return usable, constant, unverifiable


@app.get('/api/models')
async def api_models():
    """列出可用模型及其状态名、以及相对当前数据的可映射性。

    前端据此决定下拉里哪些模型可以直接拟合；对不可直接映射的模型给出**候选**
    state_mapping（由调用方核对语义后使用），避免"选了模型却永远 400"。

    候选列的选取必须排除**零方差列**：按字母序取前 N 个 ``state_`` 列会选中
    Household 专属的常量列（例如 state_cultural_level），把模型拟到常数列上会得到
    R²=0.0 却 converged=True，是比"静默猜列"更糟的误导（实测 logistic 命中）。
    因此这里只提供"有变化"的列，并且当候选不足以覆盖状态数时明确标记
    ``needs_manual_mapping``，不给出看似可用的建议。

    对"默认映射恰好命中常量列"的模型（例如某些数据下 happiness/stress 为常量），
    ``directly_fittable`` 也必须判为 False —— 否则用户点一下就会得到
    R²≈0 却 converged=True 的误导结果。
    """
    usable, constant, unverifiable = _column_variance_report(_sim_df)
    flat_columns = set(constant) | set(unverifiable)

    models = []
    for name, state_names in MODEL_STATE_NAMES.items():
        expected = {s: f'state_{s}' for s in state_names}
        # 默认映射命中，且该列确实有变化，才算"可直接拟合"
        default_ok = all(col in usable for col in expected.values())
        # 不可验证/为常量的默认映射列，作为"存在但不可用"单独列出
        unusable_defaults = {s: col for s, col in expected.items() if col in flat_columns}
        missing = [] if default_ok else [s for s in state_names if expected[s] not in usable]

        if default_ok:
            suggested = expected
        else:
            alternative = [c for c in usable if c not in expected.values()]
            suggested = ({s: alternative[i] for i, s in enumerate(state_names)}
                         if len(alternative) >= len(state_names) else None)
        needs_manual = bool(missing) and suggested is None

        models.append({
            'name': name,
            'state_names': state_names,
            'expected_columns': expected,
            'unusable_default_columns': unusable_defaults,
            'missing_states': missing,
            'directly_fittable': default_ok,
            'needs_manual_mapping': needs_manual,
            'suggested_mapping': suggested,
        })
    return JSONResponse({
        'models': models,
        'available_state_columns': usable + constant + unverifiable,
        'usable_state_columns': usable,
        'constant_state_columns': constant,
        'unverifiable_state_columns': unverifiable,
    })


@app.post('/api/fit')
async def api_fit(req: FitRequest):
    global _sim_df, _last_fitter
    if _sim_df is None:
        return JSONResponse({'error': 'No simulation data. POST /api/run first.'}, 400)

    result = None
    prediction_error: Exception | None = None
    try:
        # 不再自动猜列：默认只用「模型状态名 -> state_<状态名>」这一条显式约定，
        # 抽象模型必须由请求显式提供 state_mapping。
        # 历史上静默映射会把模型拟到无关列（甚至方差为 0 的列）上并返回看似
        # 合理的 R²=0.878。
        fitter = make_fitter(req.model_name, state_mapping=req.state_mapping)

        # 只给拟合阶段包 try/except：这样"多起点全失败"(RuntimeError) 与
        # 拟合之后的 predict() 失败能被区分开。
        # 历史问题：把整个 try 都 catch RuntimeError，会把 predict() 的
        # RuntimeError 误诊成 all_starts_failed 并丢掉 summary。
        try:
            if req.robust:
                result = fitter.fit_robust(_sim_df, agent_id=req.agent_id)
            else:
                result = fitter.fit_from_dataframe(_sim_df, agent_id=req.agent_id)
        except RuntimeError as e:
            return JSONResponse({
                'error': f'{e}（多起点拟合全部失败；请检查状态列选择与参数边界，或减少起点数重试）',
                'status': 'all_starts_failed',
            }, 400)

        _last_fitter = fitter

        # 优化器自身失败（超过迭代上限等）属于"模型/边界不适用"，返回 400 并带诊断。
        if result is None or not bool(getattr(result, 'success', False)):
            return JSONResponse({
                'error': (
                    f'模型 {req.model_name} 的优化未能收敛（optimizer success=False）。'
                    '常见原因：该模型结构与当前数据量纲不匹配，或参数边界不合适。'
                    '可尝试放宽 bounds、改选状态列，或改用差分进化全局搜索。'
                ),
                'status': 'optimizer_failed',
                'summary': fitter.summary_json(),
            }, 400)

        # Build prediction trace
        if fitter._t is not None and fitter._y0 is not None:
            try:
                t_pred = np.linspace(fitter._t[0], fitter._t[-1], 200)
                _, y_pred = fitter.predict(t_pred, fitter._y0)
                predict_trace = [
                    {'t': list(t_pred.astype(float)), 'y': [float(v) for v in y_pred[i]]}
                    for i in range(fitter.n_states)
                ]
            except Exception as exc:  # 预测失败不是输入问题：交回 500 以便暴露真实 bug
                prediction_error = exc
                predict_trace = []
        else:
            predict_trace = []
    except ValueError as e:
        # 状态列无法解析 / 数据不足等可预期的输入问题
        return JSONResponse({'error': str(e)}, 400)
    except KeyError as e:
        # 未知 model_name（make_fitter 抛 KeyError）：同样是调用方输入问题
        return JSONResponse({
            'error': f'未知模型名 {e}。可用模型：{list(MODEL_REGISTRY)}',
            'status': 'unknown_model',
        }, 400)
    except Exception as e:
        return JSONResponse({'error': f'{type(e).__name__}: {e}'}, 500)

    if prediction_error is not None:
        return JSONResponse({
            'error': f'拟合成功但预测轨迹生成失败：{type(prediction_error).__name__}: {prediction_error}',
            'status': 'prediction_failed',
        }, 500)

    summary = fitter.summary_json()
    # 命中失败哨兵时**不**返回 400：解虽不可用，但诊断信息（summary）必须能到达界面，
    # 而前端的告警条只在 HTTP 200 路径上渲染。返回 200 + 显式状态，
    # 由前端展示"该解未成功积分、R² 无意义"的告警。
    # （历史问题：这里曾直接 400，导致 dashboard.js 的哨兵告警分支成为死代码。）
    return JSONResponse({
        'status': 'model_not_applicable' if summary['hit_sentinel'] else 'ok',
        'model': req.model_name,
        'state_columns': fitter._resolved_columns,
        'summary': summary,
        'predict_trace': predict_trace,
        'warning': (
            f'模型 {req.model_name} 在给定数据与参数边界下未能积分出可用解（优化停留在失败哨兵）；'
            'R² 与参数估计无意义。可尝试放宽 bounds、改选状态列，或改用差分进化全局搜索。'
        ) if summary['hit_sentinel'] else None,
    })


@app.get('/api/niche')
async def api_niche():
    global _sim_env, _sim_df
    if _sim_env is None or _sim_df is None:
        return JSONResponse({'error': 'No simulation data. POST /api/run first.'}, 400)

    niches = []
    for agent in _sim_env.get_agents():
        if isinstance(agent, FamilyMember):
            n = MicroNiche(niche_id=agent.id)
            sub = _sim_df[_sim_df['agent_id'] == agent.id]
            if not sub.empty:
                last = sub.iloc[-1]
                agent_state = {
                    'income': last.get('state_income', 0),
                    'education': last.get('state_education', 0.5),
                    'social_capital': last.get('state_social_capital', 0.5),
                    'happiness': last.get('state_happiness', 0.5),
                }
                n.update_from_agent_state(agent_state)
            niches.append({
                'id': agent.id,
                'name': agent.get_attribute('name'),
                'role': agent.get_attribute('role'),
                'position': n.position,
            })
    return JSONResponse({'niches': niches})


@app.get('/api/network')
async def api_network():
    global _sim_env
    if _sim_env is None:
        return JSONResponse({'error': 'No simulation data. POST /api/run first.'}, 400)

    networks = []
    for agent in _sim_env.get_agents():
        if isinstance(agent, Household):
            nodes = []
            for mid, m in agent.members.items():
                nodes.append({
                    'id': mid,
                    'name': m.get_attribute('name') or mid[:8],
                    'role': m.get_attribute('role'),
                })
            edges = []
            for (a, b), rel in agent.relationships.items():
                if a < b:
                    edges.append({
                        'source': a, 'target': b,
                        'weight': round(rel.affection, 3),
                        'conflict': round(rel.conflict, 3),
                        'trust': round(rel.trust, 3),
                    })
            networks.append({
                'name': agent.get_attribute('name'),
                'nodes': nodes,
                'edges': edges,
            })
    return JSONResponse({'networks': networks})
