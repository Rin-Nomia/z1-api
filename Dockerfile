FROM python:3.11-slim

WORKDIR /app

# 複製所有檔案
COPY . .

# 安裝依賴
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 7860

# 設定環境變數
ENV PORT=7860

# 啟動指令
CMD ["python", "app.py"]
