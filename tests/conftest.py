"""pytest 共享配置：把仓库根加入 sys.path，使测试无需先安装即可导入 family_abm。"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
