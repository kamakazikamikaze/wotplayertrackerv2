FROM python:alpine

ENV BASE=/app

ENV AGGRESIVE_RECOVER=0

ENV TRACE_MEMORY=0

WORKDIR $BASE

COPY . .

RUN apk add --no-cache build-base && \
	apk add --no-cache libffi-dev && \
	pip install -r server-requirements.txt && \
	pip install -r client-requirements.txt && \
	apk del build-base && \
	apk del libffi-dev && \
	chmod +x $BASE/docker-entrypoint.sh

ENTRYPOINT ["sh", "-c", "$BASE/docker-entrypoint.sh"]
