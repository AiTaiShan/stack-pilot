import pytest
from app.services.scanner.rules.base_rule import BaseRule


def test_base_rule_abstract():
    with pytest.raises(TypeError):
        BaseRule()


def test_concrete_subclass():
    class IncompleteRule(BaseRule):
        @classmethod
        def language_id(cls): return "test"
    with pytest.raises(TypeError):
        IncompleteRule()
