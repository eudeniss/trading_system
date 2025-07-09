#core/factories/init.py
"""Factories para criação de componentes."""
from .services import ServiceFactory
from .infrastructure import InfrastructureFactory

__all__ = ['ServiceFactory', 'InfrastructureFactory']