"""Validator / Critic Agent package.

Public surface — import only these symbols outside this package:

    from agents.validator import ValidatorAgent

All other symbols are internal implementation details.
"""
from agents.validator.validator_agent import ValidatorAgent

__all__ = ["ValidatorAgent"]
