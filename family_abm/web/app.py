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
from ..fitting.fitter import make_fitter, compare_models
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
            df[c] = df[c].round(4).fillna(0)
    df = df.fillna(0)

    return JSONResponse({
        'agents': agents,
        'columns': list(df.columns),
        'data': df.to_dict(orient='records'),
        'steps': int(df['time'].max()) if 'time' in df.columns else 0,
    })


@app.post('/api/fit')
async def api_fit(req: FitRequest):
    global _sim_df, _last_fitter
    if _sim_df is None:
        return JSONResponse({'error': 'No simulation data. POST /api/run first.'}, 400)

    try:
        # 不再自动猜列：只使用「模型状态名 -> state_<状态名>」这一条显式约定。
        # 抽象模型（square_law 的 R1/R2、influence 的 O1/O2 等）与 ABM 状态列之间
        # 没有默认语义对应关系，历史上静默映射会把模型拟到无关列（甚至方差为 0 的列）
        # 上并返回看似合理的 R²=0.878。无法解析时明确报错，由调用方给 state_mapping。
        fitter = make_fitter(req.model_name)
        if req.robust:
            fitter.fit_robust(_sim_df, agent_id=req.agent_id)
        else:
            fitter.fit_from_dataframe(_sim_df, agent_id=req.agent_id)
        _last_fitter = fitter

        # Build prediction trace
        if fitter._t is not None and fitter._y0 is not None:
            t_pred = np.linspace(fitter._t[0], fitter._t[-1], 200)
            _, y_pred = fitter.predict(t_pred, fitter._y0)
            predict_trace = [
                {'t': list(t_pred.astype(float)), 'y': [float(v) for v in y_pred[i]]}
                for i in range(fitter.n_states)
            ]
        else:
            predict_trace = []

        return JSONResponse({
            'status': 'ok',
            'model': req.model_name,
            'state_columns': fitter.resolve_state_columns(_sim_df) if hasattr(fitter, 'resolve_state_columns') else {},
            'summary': fitter.summary_json(),
            'predict_trace': predict_trace,
        })
    except ValueError as e:
        # 状态列无法解析 / 数据不足等可预期的输入问题
        return JSONResponse({'error': str(e)}, 400)
    except Exception as e:
        return JSONResponse({'error': f'{type(e).__name__}: {e}'}, 500)


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
