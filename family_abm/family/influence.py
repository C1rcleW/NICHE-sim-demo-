"""代际影响的机制模块。

本模块只负责一件事：**把"年长成员对年轻成员的影响力随其发展阶段衰减"
这件事写成可测试的纯函数**，不掺入智能体状态管理（那些在 family_member.py）。

理论依据
--------
- Friedkin–Johnsen 的影响力模型把"影响"拆成两个独立的量：施力方的**影响力**
  与受力方的**易感性**。本模块实现后者的时间结构。
- 易感性的时间结构借用埃里克森心理社会发展阶段：每个阶段中个体对养育者的
  可塑性不同，影响的主要来源也从养育者转向同伴、再转向伴侣。因此父母的影响
  并非线性下降，而是在阶段边界附近出现较快的衰减。

建模选择（有意为之）
------------------
1. **易感性的取值是理论解读，不是实证标定**。阶段划分与相对高低取自阶段理论
   的含义；绝对数值属模型参数，需通过敏感性分析界定其影响。
2. **阶段边界做线性过渡**，不用硬切换。硬切换会让影响量在某一时刻跳变，
   使动力学出现人为的间断，也会让拟合残差集中在边界处（掩盖真实结构）。
3. 影响是**有限记忆的累积存量**，不是无限累加，否则数值会随仿真步数线性增长。
"""
from __future__ import annotations

from typing import Any

# ── 埃里克森阶段定义 ────────────────────────────────────────────────────────
#
# (起始年龄, 结束年龄, 易感性, 影响的主要来源, 阶段名)
# 易感性 = 该阶段个体对家庭内影响的开放程度（1 = 完全开放，0 = 完全封闭）

ERIKSON_STAGES: list[tuple[float, float, float, str, str]] = [
    (0.0, 1.0, 0.95, "caregiver", "婴儿期"),
    (1.0, 3.0, 0.85, "caregiver", "幼儿期"),
    (3.0, 6.0, 0.75, "caregiver", "学前期"),
    (6.0, 12.0, 0.50, "peer", "学龄期"),
    (12.0, 18.0, 0.28, "peer", "青春期"),
    (18.0, 40.0, 0.15, "partner", "成年早期"),
    (40.0, 999.0, 0.10, "self", "成年中期后"),
]

# 阶段边界过渡带的半宽（年）。1.0 表示在边界前后各一年内线性过渡。
TRANSITION_HALF_WIDTH = 1.0

# 影响存量的记忆系数：每步保留的比例。0.9 对应约 10 步的时间常数。
INFLUENCE_MEMORY = 0.90

# 成年成员"持续养育投入"的存量衰减率（每步）。这是"年长成员的影响能力随
# 时间消耗"的机制：投入本身有代价，不应与 strength 相乘——否则 strength 稍大
# 就会让衰减因子变成负数（曾经的实际 bug）。
INFLUENCE_DECAY = 0.01

# 成年阈值：跨过之后影响方向由"受影响"转为"施加影响"
ADULTHOOD_AGE = 18.0

# 成年成员的初始养育能力存量
INITIAL_INFLUENCE = 0.80

# 参与代际影响的人际关系类型
INFLUENCE_RELATION_TYPES = ("member", "generic")


def stage_for_age(age: float) -> tuple[float, float, float, str, str]:
    """返回年龄所在的埃里克森阶段定义。"""
    for stage in ERIKSON_STAGES:
        _start, end, *_rest = stage
        if age < end:
            return stage
    return ERIKSON_STAGES[-1]


def life_stage_of(age: float) -> str:
    """返回年龄所属阶段名，供分段拟合与分组统计使用。"""
    return stage_for_age(age)[4]


def susceptibility(
    age: float,
    half_width: float = TRANSITION_HALF_WIDTH,
    scale: float = 1.0,
    shift: float = 0.0,
) -> float:
    """年龄 ``age`` 处的易感性，阶段边界处线性过渡。

    易感性随年龄单调不增；`half_width=0` 时退化为硬切换（不推荐，会让影响量跳变）。

    Parameters
    ----------
    scale : float
        整体缩放因子。用于敏感性分析：把整条曲线按比例抬高/压低，
        同时保持阶段形状。结果钳位在 ``[0, 1]``（易感性是比例量，不应越界）。
    shift : float
        阶段边界整体平移（年）。正值表示阶段**推迟**到来：
        即按 ``age - shift`` 查表。用于敏感性分析——阶段年龄边界是模型参数，
        埃里克森本人并未给出精确年龄，因此必须检验结论对它的依赖。
    """
    lookup_age = age - shift
    if lookup_age <= 0:
        return min(1.0, max(0.0, ERIKSON_STAGES[0][2] * scale))

    # 以第一阶段为起点，逐个叠加阶段之间的过渡量。
    # 注意必须从 index=1 开始：index=0 对应"进入第一阶段"的过渡，
    # 对所有正年龄都已完全生效，把它计入会额外扣除第一段的易感性。
    value = ERIKSON_STAGES[0][2]
    for index in range(1, len(ERIKSON_STAGES)):
        boundary = ERIKSON_STAGES[index][0]
        previous = ERIKSON_STAGES[index - 1][2]
        current = ERIKSON_STAGES[index][2]
        weight = _smooth_step(lookup_age, boundary, half_width)
        value += (current - previous) * weight
    return min(1.0, max(0.0, value * scale))


def _smooth_step(age: float, boundary: float, half_width: float) -> float:
    """过渡权重：age 远小于 boundary 时为 0，远大于时为 1，之间线性。"""
    if half_width <= 0:
        return 1.0 if age >= boundary else 0.0
    raw = (age - (boundary - half_width)) / (2.0 * half_width)
    return min(1.0, max(0.0, raw))


def is_influencing(age: float, role_switch: bool = True) -> bool:
    """该成员当前是"施加影响"一方还是"接受影响"一方。

    ``role_switch=False`` 时始终接受影响（用于消融实验 C2）；
    开启后，成年成员转为施加影响（子代成年后反过来影响父母）。
    """
    return bool(role_switch) and age >= ADULTHOOD_AGE


def select_sources(member: Any, household: Any, role_switch: bool = True) -> list[Any]:
    """挑出该成员的影响来源：家庭中年龄更大、且已成年（或年长于自己）的成员。

    只用年龄做筛选，不额外引入配置项：家庭里天然是"年长者影响年幼者"。
    ``role_switch=False`` 时只要求来源年长（不做成年判定），用于消融对照。
    """
    sources = []
    my_age = member.get_attribute("age")
    for other in household.members.values():
        if other is member:
            continue
        other_age = other.get_attribute("age")
        if other_age <= my_age:
            continue
        if role_switch and other_age < ADULTHOOD_AGE:
            continue
        sources.append(other)
    return sources


def source_weight(member: Any, source: Any, household: Any) -> float:
    """来源的相对权重：关系越亲密、越受信任，影响越强。

    复用 `Relationship.influence_weight()` —— 该方法此前从未被任何仿真逻辑调用，
    这里第一次把它接进动力学。
    """
    relationship = household.get_relationship(source.id, member.id)
    if relationship is None:
        return 0.0
    if getattr(relationship, "relation_type", "") not in INFLUENCE_RELATION_TYPES:
        return 0.0
    base = relationship.influence_weight(source.id)
    # 关系中的冲突削弱影响
    return max(0.0, base * (1.0 - relationship.conflict))


def initial_influence_stock(age: float) -> float:
    """成年成员的初始影响存量（养育能力），未成年为 0（尚无影响力）。"""
    return 0.80 if age >= ADULTHOOD_AGE else 0.0


def apply_influence(
    member: Any,
    household: Any | None,
    params: dict[str, float],
    *,
    rng: Any,
    noise: float,
) -> float:
    """对 ``member`` 施加来自家庭的影响，返回本步接受的影响量。

    机制（Friedkin–Johnsen 式）：
        影响量 = 强度 × 易感性 × Σ(关系权重 × 来源养育能力 × 来源健康)
                 × (加权平均来源幸福感 − 自己幸福感)

      - **易感性**由年龄决定（见 :func:`susceptibility`），随阶段下降
      - **来源养育能力** = 来源的 influence 存量（成年人初始 0.80，随持续投入衰减）
      - **来源健康**作为能量约束：身体越差，施加影响的能力越弱
      - 方向是把受力者拉向来源的状态

    参数
    ----
    ``use_life_stage_susceptibility``
        1 = 易感性随埃里克森阶段变化；0 = 恒定 0.50（消融对照）。
    ``role_switch``
        1 = 跨过成年阈值后由"接受影响"转为"施加影响"；0 = 关闭（消融对照）。

    本函数只写 ``member`` 自身状态，不修改其它智能体。
    """
    strength = float(params.get("influence_strength", 0.0) or 0.0)
    role_switch = float(params.get("role_switch", 1.0) or 0.0) >= 0.5
    age = member.get_attribute("age")
    adult_side = is_influencing(age, role_switch)

    if household is None or strength <= 0.0 or adult_side:
        # 无家庭、影响被关闭、或本人处于"施加影响"一方：不接收影响
        if household is not None:
            _decay_own_stock(member)
        return 0.0

    use_stages = float(params.get("use_life_stage_susceptibility", 1.0) or 0.0) >= 0.5
    openness = (
        susceptibility(
            age,
            scale=float(params.get("susceptibility_scale", 1.0) or 1.0),
            shift=float(params.get("stage_shift_years", 0.0) or 0.0),
        )
        if use_stages
        else 0.50
    )
    member.set_state_value("susceptibility", openness)

    sources = select_sources(member, household, role_switch)
    if not sources:
        _decay_own_stock(member)
        return 0.0

    total_weight = 0.0
    weighted_target = 0.0
    for source in sources:
        weight = source_weight(member, source, household)
        if weight <= 0.0:
            continue
        capacity = float(source.get_state_value("influence", 0.0) or 0.0)
        energy = max(0.0, min(1.0, float(source.get_state_value("health", 1.0) or 1.0)))
        effective = weight * capacity * energy
        total_weight += effective
        weighted_target += effective * float(source.get_state_value("happiness", 0.0) or 0.0)

    if total_weight <= 0.0:
        _decay_own_stock(member)
        return 0.0

    # 每个养育者的影响由受其影响的未成年成员分摊（兄弟多不会让影响变强）
    recipients = sum(
        1 for other in household.members.values()
        if not is_influencing(other.get_attribute("age"), role_switch)
    )
    share = 1.0 / max(1, recipients)

    target = weighted_target / total_weight
    gap = target - float(member.get_state_value("happiness", 0.0) or 0.0)
    received = strength * openness * share * gap
    # 仅在确有噪声时抽取：sigma=0 的 gauss 也会推进一步随机数状态，
    # 而预计算每步对每个成员都会调用本函数——无效消耗会让同一条随机流
    # 在别处（例如关系的随机游走）错位，表现为"同一 seed 结果不可复现"。
    if noise > 0.0:
        received += rng.gauss(0, noise * 0.1)
    return received


def _decay_own_stock(member: Any) -> None:
    """施加影响一方的存量演化。

    两条规则：
    1. **刚跨过成年阈值**时获得初始养育能力（构造时未成年，存量为 0）。
       没有这一步，子代成年后永远是"零影响力"，角色切换形同虚设。
    2. 之后随"持续养育投入"缓慢衰减——投入有代价，这正是"年长成员的影响能力
       随时间被消耗"的机制之一。

    衰减率是独立常量、**不乘以 strength**：strength 衡量影响传导的强弱，
    不是存量的消耗速度；混在一起会让 strength 较大时衰减因子越界（曾经的实际 bug）。

    注意：这里按**年龄**判断是否成年，不使用 ``role_switch``。后者控制的是
    "成年人是否仍会被影响"这一方向性设定；若把它也用在这里，关闭角色切换时
    成年人的养育存量会被清零，导致没有任何影响来源（消融实验会退化成全零）。
    """
    if member.get_attribute("age") < ADULTHOOD_AGE:
        member.set_state_value("influence", 0.0)
        return
    stock = float(member.get_state_value("influence", 0.0) or 0.0)
    if stock <= 0.0:
        stock = initial_influence_stock(member.get_attribute("age"))
    stock *= (1.0 - INFLUENCE_DECAY)
    member.set_state_value("influence", max(0.0, min(1.0, stock)))


def prepare_received_influence(
    household: Any,
    params: dict[str, float],
    *,
    rng: Any,
) -> dict[str, float]:
    """在每个时间步开始前，为家庭中每个成员预计算本步接受的影响量。

    为什么需要这一步：若改为在成员各自的 ``step()`` 里边算边用，
    后更新的成员会读到同一步内已被更新的兄弟状态，使结果依赖调度顺序
    （也就是"边更新边读"）。预计算把影响量固定为**步初状态**的函数，
    使机制与调度顺序解耦。

    Returns
    -------
    dict[str, float]
        ``agent_id -> 本步接受的影响量``
    """
    params = dict(params or {})
    received: dict[str, float] = {}
    for member in household.members.values():
        received[member.id] = apply_influence(
            member, household, params, rng=rng, noise=0.0
        )
    return received
