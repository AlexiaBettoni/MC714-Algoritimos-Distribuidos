FROM python:3.12-slim
WORKDIR /app
COPY src/node.py .
CMD ["python", "-u", "node.py"]
