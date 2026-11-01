"""전략 및 브로커 설정 로더(quant_ko.config) 및 CLI 연동 테스트."""

import sys
from pathlib import Path

import pytest

from quant_ko.config import DEFAULT_CONFIG, load_config


def test_load_config_missing_file_returns_default(tmp_path: Path):
    """존재하지 않는 파일 경로가 주어졌을 때 DEFAULT_CONFIG 기본값을 반환하는지 검증합니다."""
    non_existent = tmp_path / "non_existent.toml"
    cfg = load_config(str(non_existent))

    assert cfg == DEFAULT_CONFIG
    # Deep copy 보장 검증: 반환된 딕셔너리를 수정해도 원본 DEFAULT_CONFIG에 영향이 없어야 함
    cfg["strategy"]["mode"] = "modified"
    assert DEFAULT_CONFIG["strategy"]["mode"] == "seasonality"


def test_load_config_custom_file(tmp_path: Path):
    """사용자 정의 TOML 파일을 정상 로드하여 설정값을 반환하는지 검증합니다."""
    toml_file = tmp_path / "custom_config.toml"
    toml_file.write_text(
        """
[strategy]
mode = "standard"
target_count = 10
cash_buffer_ratio = 0.02

[broker]
default_env = "mock"
order_type = "00"
""",
        encoding="utf-8",
    )

    cfg = load_config(str(toml_file))
    assert cfg["strategy"]["mode"] == "standard"
    assert cfg["strategy"]["target_count"] == 10
    assert cfg["strategy"]["cash_buffer_ratio"] == 0.02
    assert cfg["broker"]["default_env"] == "mock"
    assert cfg["broker"]["order_type"] == "00"


def test_load_config_partial_override(tmp_path: Path):
    """일부 항목만 정의된 TOML 로드 시 나머지 항목은 DEFAULT_CONFIG 값이 유지(Deep Merge)되는지 검증합니다."""
    toml_file = tmp_path / "partial_config.toml"
    toml_file.write_text(
        """
[strategy]
mode = "standard"
""",
        encoding="utf-8",
    )

    cfg = load_config(str(toml_file))
    assert cfg["strategy"]["mode"] == "standard"
    # 정의되지 않은 항목은 기본값 유지
    assert cfg["strategy"]["target_count"] == 20
    assert cfg["strategy"]["cash_buffer_ratio"] == 0.015
    assert cfg["broker"]["default_env"] == "real"
    assert cfg["broker"]["order_type"] == "01"


def test_load_config_invalid_toml_fallback(tmp_path: Path):
    """문법 오류가 있는 잘못된 TOML 파일 로드 시 예외 없이 DEFAULT_CONFIG로 안전하게 폴백되는지 검증합니다."""
    bad_toml = tmp_path / "broken.toml"
    bad_toml.write_text("invalid_toml = [broken", encoding="utf-8")

    cfg = load_config(str(bad_toml))
    assert cfg == DEFAULT_CONFIG


def test_workspace_root_config_toml():
    """프로젝트 루트의 config.toml 파일이 정상 로드되고 필수 키들이 올바르게 포함되어 있는지 검증합니다."""
    root_config_path = Path("config.toml")
    assert root_config_path.exists(), "프로젝트 루트에 config.toml 파일이 존재해야 합니다."

    cfg = load_config(str(root_config_path))
    assert cfg["strategy"]["mode"] in ["seasonality", "standard"]
    assert isinstance(cfg["strategy"]["target_count"], int)
    assert isinstance(cfg["strategy"]["cash_buffer_ratio"], float)
    assert cfg["broker"]["default_env"] in ["real", "mock"]
    assert cfg["broker"]["order_type"] in ["01", "00"]


def test_cli_argument_defaults_from_config(monkeypatch, tmp_path: Path):
    """main.py CLI 인자 파싱 시 기본값이 config.toml 설정값과 일치하는지 검증합니다."""
    import argparse

    from quant_ko.main import main

    custom_cfg = {
        "strategy": {"mode": "standard", "target_count": 15, "cash_buffer_ratio": 0.02},
        "broker": {"default_env": "mock", "order_type": "00"},
    }

    # quant_ko.main 내부의 load_config 모킹
    monkeypatch.setattr("quant_ko.main.load_config", lambda *args, **kwargs: custom_cfg)

    # status 모드로 실행하여 인자 기본값 확인 (DB나 KisClient 호출 전 parser.parse_args() 검증)
    captured_args = {}

    orig_parse_args = argparse.ArgumentParser.parse_args

    def mock_parse_args(self, args=None, namespace=None):
        res = orig_parse_args(self, args=args, namespace=namespace)
        captured_args["strategy"] = res.strategy
        captured_args["env"] = res.env
        captured_args["order_type"] = res.order_type
        # 빠른 종료를 위해 SystemExit 발생
        raise SystemExit(99)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", mock_parse_args)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 99
    assert captured_args["strategy"] == "standard"
    assert captured_args["env"] == "mock"
    assert captured_args["order_type"] == "00"
