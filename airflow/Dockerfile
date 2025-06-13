FROM apache/airflow:3.0.2-python3.12

USER root

# Install any system dependencies if needed
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Copy requirements file if you have custom Python dependencies
# COPY requirements-airflow.txt /requirements-airflow.txt

# Install custom Python packages
RUN pip install --no-cache-dir \
    pandas==2.1.4 \
    sqlalchemy==2.0.23 \
    psycopg2-binary==2.9.9 \
    python-dotenv==1.0.0 \
    requests==2.31.0

# If you have a requirements file, uncomment:
# RUN pip install --no-cache-dir -r /requirements-airflow.txt