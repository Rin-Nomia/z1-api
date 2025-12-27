# 在你的 z1-api 專案裡
# 新增一個檔案：logger.py

import json
from datetime import datetime
import os

class DataLogger:
    def __init__(self, log_dir='logs'):
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
    
    def log(self, input_text, output_result, metadata=None):
        """
        記錄一次分析
        
        Args:
            input_text: 用戶輸入的文字
            output_result: Z1 分析的結果
            metadata: 其他資訊（可選）
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'input': {
                'text': input_text,
                'length': len(input_text),
                'language': self._detect_language(input_text)
            },
            'output': {
                'original': output_result.get('original'),
                'freq_type': output_result.get('freq_type'),
                'confidence': output_result.get('confidence'),
                'scenario': output_result.get('scenario'),
                'repaired_text': output_result.get('repaired_text')
            }
        }
        
        if metadata:
            entry['metadata'] = metadata
        
        # 寫入檔案
        date_str = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(self.log_dir, f'analysis_{date_str}.jsonl')
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        
        return entry
    
    def _detect_language(self, text):
        """簡單判斷語言"""
        # 如果有中文字符
        if any('\u4e00' <= char <= '\u9fff' for char in text):
            return 'zh'
        return 'en'
    
    def get_stats(self):
        """取得統計資訊"""
        total = 0
        tones = []
        
        for log_file in os.listdir(self.log_dir):
            if log_file.endswith('.jsonl'):
                filepath = os.path.join(self.log_dir, log_file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        data = json.loads(line)
                        total += 1
                        tones.append(data['output']['freq_type'])
        
        from collections import Counter
        return {
            'total_analyses': total,
            'tone_distribution': dict(Counter(tones))
        }

# 使用範例
logger = DataLogger()

# 在你的 API endpoint 裡
@app.post("/api/v1/analyze")
async def analyze(request: AnalyzeRequest):
    # 你原本的分析邏輯
    result = {
        'original': request.text,
        'freq_type': 'Anxious',
        'confidence': 0.85,
        'scenario': 'customer_service',
        'repaired_text': 'I\'m seeking guidance on next steps...'
    }
    
    # 記錄 ← 就加這一行
    logger.log(request.text, result)
    
    return result

# 查看統計
@app.get("/api/v1/stats")
async def get_stats():
    return logger.get_stats()
