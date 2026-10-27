FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
WORKDIR /app
COPY --chown=1000:1000 app.py respawn.py schedule.py defaults.json live.html control.html ./
COPY --chown=1000:1000 screens ./screens
RUN mkdir /data && chown 1000:1000 /data
ENV APEX_BIND=0.0.0.0 PORT=8080 APEX_STATE_FILE=/data/state.json
USER 1000:1000
EXPOSE 8080
CMD ["python", "app.py"]
