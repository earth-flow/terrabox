# This package provides a lightweight platform backend for the
# Terralink SDK.  It exposes a set of REST APIs for tool discovery,
# account connections and tool execution.  The SDK communicates with
# this service to retrieve tool schemas, establish OAuth connections
# and execute actions on behalf of users.  See the README for
# usage details.

def create_app(*args, **kwargs):
    from .main import create_app as _create_app

    return _create_app(*args, **kwargs)
