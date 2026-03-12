FROM python:3.12-slim

WORKDIR /app

# System deps for git operations
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Configure git globally for agent commits
RUN git config --global user.email "bismuth-agent@localhost" && \
    git config --global user.name "Bismuth Agent"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 5000

CMD ["python", "src/main.py"]
