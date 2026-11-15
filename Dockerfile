FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# The expenses are kept here. docker-compose.yml mounts a volume on /data.
ENV EXPENSE_TRACKER_FILE=/data/expenses.json

ENTRYPOINT ["python", "-m", "expense_tracker"]
CMD ["--help"]
