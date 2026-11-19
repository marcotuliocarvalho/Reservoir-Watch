FROM apache/airflow:3.1.3-python3.12

# Writable by group 0, so any AIRFLOW_UID (user "<uid>:0") can use the
# named volume mounted here (SQLite DB + logs).
USER root
RUN mkdir -p /opt/airflow/state && chown airflow:0 /opt/airflow/state && chmod 2775 /opt/airflow/state
USER airflow

# Pin apache-airflow in the same install so pip never upgrades/downgrades it.
COPY requirements-airflow.txt /requirements-airflow.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements-airflow.txt
