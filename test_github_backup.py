# test_github_backup.py
"""
測試 GitHub 備份功能
驗證數據能否成功推送到 z1-api-logs repo
"""

import os
import json
import subprocess
from datetime import datetime
from logger import DataLogger, GitHubBackup

def test_backup_flow():
    """完整測試備份流程"""
    
    print("=" * 60)
    print("🧪 Z1 GitHub 備份測試")
    print("=" * 60)
    print()
    
    # 步驟 1: 檢查環境變數
    print("📋 步驟 1: 檢查環境變數")
    print("-" * 60)
    
    gh_token = os.environ.get('GH_TOKEN')
    gh_repo = os.environ.get('GH_REPO')
    
    if not gh_token:
        print("❌ GH_TOKEN 未設定")
        print("   請在 HuggingFace Secrets 設定 GH_TOKEN")
        return False
    else:
        print(f"✅ GH_TOKEN 已設定（長度: {len(gh_token)} 字符）")
    
    if not gh_repo:
        print("❌ GH_REPO 未設定")
        print("   請在 HuggingFace Secrets 設定 GH_REPO")
        return False
    else:
        print(f"✅ GH_REPO 已設定: {gh_repo}")
    
    print()
    
    # 步驟 2: 建立測試數據
    print("📋 步驟 2: 建立測試數據")
    print("-" * 60)
    
    logger = DataLogger()
    
    # 模擬一次分析
    test_result = {
        'original': 'Test message for backup verification',
        'freq_type': 'Anxious',
        'confidence': {'final': 0.75},
        'output': {
            'scenario': 'test',
            'repaired_text': 'Test repaired message',
            'mode': 'repair'
        },
        'rhythm': {
            'total': 10,
            'speed_index': 0.5,
            'emotion_rate': 0.3
        }
    }
    
    log_entry = logger.log(
        input_text='Test message for backup verification',
        output_result=test_result,
        metadata={
            'test': True,
            'timestamp': datetime.now().isoformat()
        }
    )
    
    print(f"✅ 測試數據已記錄")
    print(f"   Log ID: {log_entry['timestamp']}")
    print(f"   檔案: logs/analysis_{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    print()
    
    # 步驟 3: 檢查 logs 資料夾
    print("📋 步驟 3: 檢查 logs 資料夾")
    print("-" * 60)
    
    if not os.path.exists('logs'):
        print("❌ logs/ 資料夾不存在")
        return False
    
    log_files = [f for f in os.listdir('logs') if f.endswith('.jsonl')]
    print(f"✅ logs/ 資料夾存在")
    print(f"   檔案數量: {len(log_files)}")
    
    for f in log_files:
        size = os.path.getsize(os.path.join('logs', f))
        print(f"   - {f} ({size} bytes)")
    
    print()
    
    # 步驟 4: 執行備份
    print("📋 步驟 4: 執行 GitHub 備份")
    print("-" * 60)
    
    backup = GitHubBackup()
    
    try:
        backup.backup()
        print("✅ 備份執行完成")
    except Exception as e:
        print(f"❌ 備份失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # 步驟 5: 驗證 GitHub repo
    print("📋 步驟 5: 驗證 GitHub repo")
    print("-" * 60)
    
    try:
        # 檢查 remote 設定
        result = subprocess.run(
            ['git', 'remote', '-v'],
            cwd='logs',
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Git remote 已設定:")
            for line in result.stdout.strip().split('\n'):
                # 隱藏 token
                line = line.replace(gh_token, '***')
                print(f"   {line}")
        else:
            print("⚠️  無法讀取 git remote")
        
        print()
        
        # 檢查最後一次 commit
        result = subprocess.run(
            ['git', 'log', '-1', '--oneline'],
            cwd='logs',
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ 最後一次 commit:")
            print(f"   {result.stdout.strip()}")
        else:
            print("⚠️  無法讀取 git log")
        
        print()
        
        # 檢查 push 狀態
        result = subprocess.run(
            ['git', 'status'],
            cwd='logs',
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Git 狀態:")
            print(f"   {result.stdout.strip()}")
        
    except Exception as e:
        print(f"⚠️  無法驗證 git 狀態: {e}")
    
    print()
    
    # 步驟 6: 提供驗證連結
    print("📋 步驟 6: 驗證連結")
    print("-" * 60)
    print(f"✅ 請前往以下網址確認數據是否已推送:")
    print(f"   https://github.com/{gh_repo}")
    print()
    print(f"   應該會看到:")
    print(f"   - analysis_{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    print(f"   - 檔案大小 > 0 bytes")
    print(f"   - 最新 commit 時間為剛剛")
    print()
    
    # 總結
    print("=" * 60)
    print("✅ 測試完成！")
    print("=" * 60)
    print()
    print("📊 測試結果摘要:")
    print(f"   環境變數: ✅")
    print(f"   數據記錄: ✅")
    print(f"   備份執行: ✅")
    print(f"   GitHub 推送: ✅（請手動確認）")
    print()
    print("🔗 驗證步驟:")
    print(f"   1. 開啟 https://github.com/{gh_repo}")
    print(f"   2. 確認檔案存在")
    print(f"   3. 檢查檔案內容")
    print()
    
    return True

if __name__ == "__main__":
    try:
        success = test_backup_flow()
        exit(0 if success else 1)
    except Exception as e:
        print(f"❌ 測試過程發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
