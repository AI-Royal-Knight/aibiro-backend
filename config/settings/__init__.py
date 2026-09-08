import os
import environ

env = environ.Env()
current_env = env('ENVIRONMENT', default='dev')

if current_env == 'prod':
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403
