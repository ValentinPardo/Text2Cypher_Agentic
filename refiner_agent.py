"""Compatibility shim: re-export refiner agent from `agents` package."""

from agents.refiner_agent import refine_query

__all__ = ["refine_query"]

