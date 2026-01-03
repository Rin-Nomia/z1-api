"""
Continuum Data Logger - 資料記錄 + GitHub 備份（真・完整版）
RIN Protocol — Continuum Module
記錄所有 Pipeline 輸出、LLM 原始回應、完整修復內容
"""

import json
from datetime import datetime
import os
from collections import Counter
from typing import Dict, Any, Optional
import subprocess
import logging

logger = logging.getLogger(__name__)


class DataLogger:
    """Continuum 資料記錄器 - 真・完整版"""
    
    # ... (其他部分保持不變)


class GitHubBackup:
    """GitHub 備份管理"""
    
    def __init__(self, log_dir='logs'):
        self.log_dir = log_dir
        self.gh_token = os.environ.get('GH_TOKEN')
        self.gh_repo = os.environ.get('GH_REPO')
        
        if not self.gh_token or not self.gh_repo:
            logger.warning("⚠️ GH_TOKEN or GH_REPO not set, backup disabled")
    
    def restore(self):
        """從 GitHub 恢復 logs"""
        if not self.gh_token or not self.gh_repo:
            return
        
        try:
            if os.path.exists(os.path.join(self.log_dir, '.git')):
                subprocess.run(['git', 'pull'], cwd=self.log_dir, capture_output=True)
                logger.info("✅ Pulled previous logs")
            else:
                subprocess.run([
                    'git', 'clone',
                    f'https://{self.gh_token}@github.com/{self.gh_repo}.git',
                    self.log_dir
                ], capture_output=True)
                logger.info("✅ Cloned logs from GitHub")
        except Exception as e:
            logger.warning(f"⚠️ Restore failed: {e}")
    
    def backup(self):
        """備份到 GitHub"""
        if not self.gh_token or not self.gh_repo:
            return
        
        try:
            if not os.path.exists(os.path.join(self.log_dir, '.git')):
                subprocess.run(['git', 'init', '-b', 'main'], cwd=self.log_dir)
                subprocess.run(['git', 'config', 'user.name', 'Continuum API'], cwd=self.log_dir)
                subprocess.run(['git', 'config', 'user.email', 'api@continuum.dev'], cwd=self.log_dir)
                subprocess.run([
                    'git', 'remote', 'add', 'origin',
                    f'https://{self.gh_token}@github.com/{self.gh_repo}.git'
                ], cwd=self.log_dir)
            
            subprocess.run(['git', 'add', '.'], cwd=self.log_dir)
            subprocess.run([
                'git', 'commit', '-m',
                f'Auto backup {datetime.now().isoformat()}'
            ], cwd=self.log_dir, capture_output=True)
            
            subprocess.run(
                ['git', 'push', '-u', 'origin', 'main', '--force'],
                cwd=self.log_dir,
                capture_output=True
            )
            
            logger.info("✅ Backup successful")
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
