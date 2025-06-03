FROM python:3.13-alpine

WORKDIR /app

# Copy từ root project vào Docker context
COPY ../alembic.ini .
COPY ../alembic/ ./alembic/
COPY ../requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY ../app ./app
COPY ../entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
CMD ["/entrypoint.sh"]
