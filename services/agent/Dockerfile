FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY src/ src/

EXPOSE 9091

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "9091"]
