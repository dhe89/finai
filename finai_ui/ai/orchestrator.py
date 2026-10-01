"""Compatibility entry point for the FinAI v18 Financial Intelligence Agent."""
from .intelligence_agent import answer
from .openrouter import DEFAULT_MODEL


def run_financial_analysis(question, selected_period=None, model=DEFAULT_MODEL):
    """Called by app.py; keep the existing public interface stable."""
    return answer(question, selected_period=selected_period, model=model)
