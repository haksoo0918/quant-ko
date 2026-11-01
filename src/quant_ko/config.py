"""quant-ko 설정 로더 모듈.

TOML 형식의 운영 및 전략 설정 파일(config.toml)을 안전하게 로드하고,
누락된 설정 항목은 DEFAULT_CONFIG와 딥 머지(deep merge)하여 기본값을 보장합니다.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 대비
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger("quant_ko.config")

# 기본 전략 및 브로커 운영 설정
DEFAULT_CONFIG: dict[str, Any] = {
    "strategy": {
        "mode": "seasonality",
        "target_count": 20,
        "cash_buffer_ratio": 0.015,
    },
    "broker": {
        "default_env": "real",
        "order_type": "01",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """기본 딕셔너리와 오버라이드 딕셔너리를 재귀적으로 병합합니다.

    Args:
        base: 기본 딕셔너리.
        override: 오버라이드할 값을 가진 딕셔너리.

    Returns:
        dict[str, Any]: 재귀적으로 병합된 새로운 딕셔너리.
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: str = "config.toml") -> dict[str, Any]:
    """TOML 설정 파일을 안전하게 읽어들여 딕셔너리로 반환합니다.

    설정 파일이 존재하지 않거나 구문 분석 오류(parse error)가 발생하는 경우,
    경고 로그를 남기고 DEFAULT_CONFIG 기본 설정을 반환합니다.
    일부 키만 존재하는 경우 DEFAULT_CONFIG와 딥 머지하여 기본값을 유지합니다.

    Args:
        path: 설정 파일의 경로 (기본값: 'config.toml').

    Returns:
        dict[str, Any]: 병합 완료된 최종 설정 딕셔너리.
    """
    config_path = Path(path)
    if not config_path.is_file():
        logger.debug("설정 파일(%s)을 찾을 수 없어 기본 설정을 적용합니다.", path)
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with config_path.open("rb") as f:
            user_config = tomllib.load(f)
        return _deep_merge(DEFAULT_CONFIG, user_config)
    except Exception as e:
        logger.warning(
            "설정 파일(%s)을 파싱하는 중 오류가 발생하여 기본 설정을 적용합니다: %s",
            path,
            e,
        )
        return copy.deepcopy(DEFAULT_CONFIG)
