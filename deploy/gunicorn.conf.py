# Gunicorn 配置。负责人：P5。
# 启动：gunicorn -c deploy/gunicorn.conf.py "app:create_app()"

bind = "0.0.0.0:5000"
workers = 4
worker_class = "sync"
timeout = 60
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = "info"
