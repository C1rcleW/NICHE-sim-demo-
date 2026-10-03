"""兼容层：所有包元数据与依赖均声明在 pyproject.toml（单一真源）。

保留本文件是为了兼容仍执行 `python setup.py ...` 的旧工具链；
请勿在此重新声明 install_requires / packages，否则会与 pyproject.toml 产生分歧。
"""
from setuptools import setup

setup()
