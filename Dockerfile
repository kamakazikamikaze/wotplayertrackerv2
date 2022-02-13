FROM kamakazikamikaze/wotplayertrackerv2-base:latest

ENV BASE=/app

ENV AGGRESIVE_RECOVER=0

ENV TRACE_MEMORY=0

WORKDIR $BASE

COPY . .

RUN chmod +x $BASE/docker-entrypoint.sh && mkdir files && chmod 777 files && dos2unix $BASE/docker-entrypoint.sh

ENTRYPOINT ["sh", "-c", "$BASE/docker-entrypoint.sh"]
