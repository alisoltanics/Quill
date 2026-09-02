FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
RUN chmod +x start.sh wait-for-db.sh
CMD ["sh", "./wait-for-db.sh"]
