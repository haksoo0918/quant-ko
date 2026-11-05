"""테스트 전역 fixture 및 격리 설정 모듈."""

import pytest

from quant_ko.broker.kis import KisClient


@pytest.fixture(autouse=True)
def reset_kis_shared_token_cache():
    """모든 단위 테스트 실행 전후에 KisClient의 인메모리 프로세스 공유 캐시를 초기화하여 테스트 간 격리를 보장합니다."""
    KisClient._shared_token_cache.clear()
    yield
    KisClient._shared_token_cache.clear()
