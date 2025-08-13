#!/usr/bin/env python3

"""Custom exceptions for Jora components."""


class ConfigException(Exception):
    """Exception raised by Config class operations."""

    pass


class JiraAPIException(Exception):
    """Exception raised by JiraAPI class operations."""

    pass


class PRManagerException(Exception):
    """Exception raised by PRManager class operations."""

    pass


class GitOperationsException(Exception):
    """Exception raised by GitOperations class operations."""

    pass
