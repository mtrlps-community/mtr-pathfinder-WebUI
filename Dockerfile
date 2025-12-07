FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip3 install -U fontTools opencc pillow networkx requests flask

EXPOSE 5000

CMD ["python3", "main.py"]