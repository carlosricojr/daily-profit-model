# ---------------------------------------------------------------------------
# Base image
# ---------------------------------------------------------------------------
FROM apache/airflow:3.0.2-python3.12

# ---------------------------------------------------------------------------
# Install project dependencies as *root* (default user)                      
# ---------------------------------------------------------------------------

# Install UV (solver + installer)
RUN pip install --no-cache-dir uv

# Generate a fully locked wheel set from pyproject.toml at build time
COPY pyproject.toml /tmp/pyproject.toml
RUN uv pip compile --output-file /tmp/requirements.txt /tmp/pyproject.toml

# Install all runtime dependencies (use pip to avoid permission edge-cases)
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Copy project source & switch to non-root airflow user for runtime
# ---------------------------------------------------------------------------

COPY src /opt/airflow/src

# Change to airflow user for safety when the container runs
USER airflow