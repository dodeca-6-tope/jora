#!/usr/bin/env python3

"""
Client modules for external integrations.

This package contains all the client classes for integrating with external services:
- JiraAPI: Jira integration client
- GitOperations: Git operations client  
- PRManager: GitHub PR management client
"""

from .git import GitOperations
from .github import PRManager
from .jira import JiraAPI

__all__ = ['JiraAPI', 'GitOperations', 'PRManager']