import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
timeout = 120
graceful_timeout = 30
workers = 1
worker_class = "sync"
keepalive = 5
