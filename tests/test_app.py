"""示例测试：验证 CI 流水线能正常运行 pytest。"""

from app import add


def test_add_positive() -> None:
    """正数相加。"""
    assert add(1, 2) == 3


def test_add_negative() -> None:
    """负数相加。"""
    assert add(-1, 1) == 0
