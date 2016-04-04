FROM python:3-onbuild
ENV SERVER_URL https://logme.link
ENV REDIS_HOST redis
ENV KEY_TTL 300
CMD python ./server.py
