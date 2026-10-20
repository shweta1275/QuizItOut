FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir requests
WORKDIR /srv
COPY loadgen.py .
RUN useradd -m loadgen
USER loadgen
CMD ["python", "loadgen.py"]
