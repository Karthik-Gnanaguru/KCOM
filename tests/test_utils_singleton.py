"""Tests for kcom/utils/singleton.py — SingletonMeta."""
from __future__ import annotations

import pytest
from kcom.utils.singleton import SingletonMeta


class TestSingletonMeta:
    def setup_method(self):
        # Clear instance cache before each test so classes are fresh
        SingletonMeta._instances.clear()

    def test_same_instance_returned(self):
        class MyClass(metaclass=SingletonMeta):
            pass
        a = MyClass()
        b = MyClass()
        assert a is b

    def test_different_classes_independent(self):
        class ClassA(metaclass=SingletonMeta):
            pass
        class ClassB(metaclass=SingletonMeta):
            pass
        a = ClassA()
        b = ClassB()
        assert a is not b

    def test_init_called_once(self):
        calls = []
        class Tracked(metaclass=SingletonMeta):
            def __init__(self):
                calls.append(1)
        Tracked()
        Tracked()
        Tracked()
        assert len(calls) == 1

    def test_args_used_only_first_time(self):
        class Configurable(metaclass=SingletonMeta):
            def __init__(self, value=0):
                self.value = value
        a = Configurable(42)
        b = Configurable(99)  # args ignored on second call
        assert a.value == 42
        assert b.value == 42
        assert a is b
