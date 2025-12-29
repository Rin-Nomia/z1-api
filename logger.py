"""
Z1 Data Logger - 資料記錄 + GitHub 備份（完整版）
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
    """Z1 資料記錄器 - 完整版"""
    
    def __init__(self, log_dir='logs'):
        self.log_dir = log_dir
        
        # 建立資料夾
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 反饋資料夾
        self.feedback_dir = os.path.join(log_dir, 'feedback')
        if not os.path.exists(self.feedback_dir):
            os.makedirs(self.feedback_dir)
    
    def log(
        self,
        input_text: str,
        output_result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """記錄一次分析 - 完整版（包含 confidence 三階段 + rhythm details + patterns）"""
        
        timestamp = datetime.now().isoformat()
        
        # 從 pipeline 結果中提取所有數據
        entry = {
            'timestamp': timestamp,
            
            # ===== 輸入數據 =====
            'input': {
                'text': input_text,
                'original': output_result.get('original', input_text),
                'normalized': output_result.get('normalized', input_text),
                'length': len(input_text),
                'char_count': len(input_text),
                'word_count': len(input_text.split()),
                'language': output_result.get('language', self._detect_language(input_text))
            },
            
            # ===== 核心輸出 =====
            'output': {
                'freq_type': output_result.get('freq_type', 'Unknown'),
                
                # ✅ 完整的 confidence 三階段
                'confidence': self._extract_confidence(output_result),
                
                # 場景和修復
                'scenario': output_result.get('output', {}).get('scenario', 'unknown'),
                'scenario_confidence': output_result.get('output', {}).get('scenario_confidence', 0),
                'mode': output_result.get('output', {}).get('mode', 'unknown'),
                'repaired_text': output_result.get('output', {}).get('repaired_text', ''),
                'repair_strategy': output_result.get('output', {}).get('repair_strategy', {})
            },
            
            # ===== 節奏分析（完整） =====
            'rhythm': self._extract_rhythm(output_result),
            
            # ===== 模式識別 =====
            'patterns': self._extract_patterns(output_result),
            
            # ===== 除錯資訊 =====
            'debug': output_result.get('confidence', {}).get('debug', {}),
            
            # ===== Metadata =====
            'metadata': metadata or {},
            
            # ===== 截斷標記 =====
            'truncated': output_result.get('truncated', False)
        }
        
        # 寫入檔案（JSONL 格式：每行一筆）
        date_str = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(self.log_dir, f'analysis_{date_str}.jsonl')
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            logger.info(f"✅ Logged analysis to {log_file}")
        except Exception as e:
            logger.error(f"❌ Failed to log analysis: {e}")
        
        # 回傳簡化版本給 API 回傳給用戶
        return {
            'timestamp': timestamp,
            'log_id': timestamp,
            'freq_type': entry['output']['freq_type'],
            'confidence_final': entry['output']['confidence'].get('final', 0),
            'scenario': entry['output']['scenario'],
            'mode': entry['output']['mode'],
            'repaired_text': entry['output']['repaired_text']
        }
    
    def _extract_confidence(self, output_result: Dict[str, Any]) -> Dict[str, float]:
        """提取完整的 confidence 三階段"""
        conf_data = output_result.get('confidence', {})
        debug_info = conf_data.get('debug', {})
        
        return {
            'initial': debug_info.get('base_confidence', conf_data.get('base_confidence', 0)),
            'adjusted': debug_info.get('final_confidence', conf_data.get('final_confidence', 0)),
            'final': conf_data.get('final_confidence', conf_data.get('final', 0))
        }
    
    def _extract_rhythm(self, output_result: Dict[str, Any]) -> Dict[str, Any]:
        """提取完整的節奏分析"""
        rhythm = output_result.get('rhythm', {})
        
        # 計算 fast/medium/slow 詳細
        details = self._categorize_rhythm(rhythm.get('speed_index', 0.5))
        
        return {
            'total': rhythm.get('total', 0),
            'speed_index': rhythm.get('speed_index', 0),
            'emotion_rate': rhythm.get('emotion_rate', 0),
            'pause_density': rhythm.get('pause_density', 0),
            'details': details
        }
    
    def _categorize_rhythm(self, speed_index: float) -> Dict[str, int]:
        """將 speed_index 分類為 fast/medium/slow"""
        # 簡單分類：
        # 0.0 - 0.33: slow
        # 0.33 - 0.67: medium
        # 0.67 - 1.0: fast
        
        if speed_index < 0.33:
            return {'fast': 0, 'medium': 0, 'slow': 100}
        elif speed_index < 0.67:
            return {'fast': 0, 'medium': 100, 'slow': 0}
        else:
            return {'fast': 100, 'medium': 0, 'slow': 0}
    
    def _extract_patterns(self, output_result: Dict[str, Any]) -> Dict[str, Any]:
        """提取識別出的模式"""
        freq_type = output_result.get('freq_type', 'Unknown')
        normalized_text = output_result.get('normalized', '')
        
        patterns = {
            'detected_tone': freq_type,
            'tone_markers': self._extract_tone_markers(freq_type, normalized_text),
            'intensity_words': self._extract_intensity_words(normalized_text),
            'linguistic_features': self._extract_linguistic_features(normalized_text)
        }
        
        return patterns
    
    def _extract_tone_markers(self, tone: str, text: str) -> list:
        """提取語氣標記詞"""
        markers_map = {
            'Sharp': ['快點', '馬上', '立刻', '趕快', 'hurry', 'immediately', 'asap'],
            'Cold': ['嗯', '好', '隨便', 'ok', 'whatever', 'fine'],
            'Blur': ['可能', '大概', '應該', 'maybe', 'probably', 'sort of'],
            'Pushy': ['一定要', '必須', '得', 'must', 'have to'],
            'Anxious': ['怎麼辦', '不知道', '害怕', 'help', 'worried', 'confused']
        }
        
        detected = []
        for marker in markers_map.get(tone, []):
            if marker.lower() in text.lower():
                detected.append(marker)
        
        return detected
    
    def _extract_intensity_words(self, text: str) -> list:
        """提取強度詞"""
        intensity_words = [
            '非常', '真的', '太', '好想', '受不了', '絕望',
            'very', 'really', 'so', 'extremely', 'absolutely'
        ]
        
        detected = []
        for word in intensity_words:
            if word.lower() in text.lower():
                detected.append(word)
        
        return detected
    
    def _extract_linguistic_features(self, text: str) -> Dict[str, int]:
        """提取語言特徵"""
        return {
            'exclamations': text.count('!') + text.count('！'),
            'questions': text.count('?') + text.count('？'),
            'ellipsis': text.count('...') + text.count('…'),
            'commas': text.count(',') + text.count('，'),
            'periods': text.count('.') + text.count('。'),
            'all_caps_words': len([w for w in text.split() if w.isupper() and len(w) > 1])
        }
    
    def _detect_language(self, text: str) -> str:
        """自動語言偵測"""
        if any('\u4e00' <= char <= '\u9fff' for char in text):
            return 'zh'
        if any('\u3040' <= char <= '\u30ff' for char in text):
            return 'ja'
        if any('\uac00' <= char <= '\ud7af' for char in text):
            return 'ko'
        return 'en'
    
    def log_feedback(
        self,
        log_id: str,
        accuracy: int,
        helpful: int,
        accepted: bool
    ):
        """記錄用戶反饋"""
        feedback_entry = {
            'timestamp': datetime.now().isoformat(),
            'log_id': log_id,
            'accuracy': accuracy,  # 1-5
            'helpful': helpful,    # 1-5
            'accepted': accepted   # true/false
        }
        
        date_str = datetime.now().strftime('%Y-%m-%d')
        feedback_file = os.path.join(
            self.feedback_dir,
            f'feedback_{date_str}.jsonl'
        )
        
        try:
            with open(feedback_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(feedback_entry, ensure_ascii=False) + '\n')
            logger.info(f"✅ Feedback logged: accuracy={accuracy}, helpful={helpful}, accepted={accepted}")
        except Exception as e:
            logger.error(f"❌ Failed to log feedback: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊"""
        total_analyses = 0
        tones = []
        scenarios = []
        languages = []
        modes = []
        
        confidences_initial = []
        confidences_adjusted = []
        confidences_final = []
        
        # 讀取分析記錄
        for log_file in os.listdir(self.log_dir):
            if log_file.endswith('.jsonl') and log_file.startswith('analysis_'):
                filepath = os.path.join(self.log_dir, log_file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                                total_analyses += 1
                                
                                tones.append(data['output']['freq_type'])
                                scenarios.append(data['output'].get('scenario', 'unknown'))
                                languages.append(data['input']['language'])
                                modes.append(data['output'].get('mode', 'unknown'))
                                
                                # 三階段 confidence
                                conf = data['output'].get('confidence', {})
                                if conf.get('initial') is not None:
                                    confidences_initial.append(conf['initial'])
                                if conf.get('adjusted') is not None:
                                    confidences_adjusted.append(conf['adjusted'])
                                if conf.get('final') is not None:
                                    confidences_final.append(conf['final'])
                            except:
                                continue
                except:
                    continue
        
        # 讀取反饋記錄
        total_feedback = 0
        accuracy_ratings = []
        helpful_ratings = []
        acceptance_count = 0
        
        if os.path.exists(self.feedback_dir):
            for feedback_file in os.listdir(self.feedback_dir):
                if feedback_file.endswith('.jsonl'):
                    filepath = os.path.join(self.feedback_dir, feedback_file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            for line in f:
                                try:
                                    data = json.loads(line)
                                    total_feedback += 1
                                    accuracy_ratings.append(data['accuracy'])
                                    helpful_ratings.append(data['helpful'])
                                    if data['accepted']:
                                        acceptance_count += 1
                                except:
                                    continue
                    except:
                        continue
        
        return {
            'analyses': {
                'total': total_analyses,
                'tone_distribution': dict(Counter(tones)),
                'scenario_distribution': dict(Counter(scenarios)),
                'language_distribution': dict(Counter(languages)),
                'mode_distribution': dict(Counter(modes)),
                'confidence': {
                    'avg_initial': (
                        sum(confidences_initial) / len(confidences_initial)
                        if confidences_initial else 0
                    ),
                    'avg_adjusted': (
                        sum(confidences_adjusted) / len(confidences_adjusted)
                        if confidences_adjusted else 0
                    ),
                    'avg_final': (
                        sum(confidences_final) / len(confidences_final)
                        if confidences_final else 0
                    )
                }
            },
            'feedback': {
                'total': total_feedback,
                'avg_accuracy': (
                    sum(accuracy_ratings) / len(accuracy_ratings)
                    if accuracy_ratings else 0
                ),
                'avg_helpful': (
                    sum(helpful_ratings) / len(helpful_ratings)
                    if helpful_ratings else 0
                ),
                'acceptance_rate': (
                    acceptance_count / total_feedback
                    if total_feedback > 0 else 0
                )
            }
        }


class GitHubBackup:
    """GitHub 備份管理"""
    
    def __init__(self, log_dir='logs'):
        self.log_dir = log_dir
        self.gh_token = os.environ.get('GH_TOKEN')
        self.gh_repo = os.environ.get('GH_REPO')  # 格式: username/repo
        
        if not self.gh_token or not self.gh_repo:
            logger.warning("⚠️ GH_TOKEN or GH_REPO not set, backup disabled")
    
    def restore(self):
        """從 GitHub 恢復之前的 logs（啟動時執行）"""
        if not self.gh_token or not self.gh_repo:
            logger.info("ℹ️ GitHub backup not configured, skipping restore")
            return
        
        try:
            # 如果 logs/ 已經存在且是 git repo，就 pull
            if os.path.exists(os.path.join(self.log_dir, '.git')):
                logger.info("📥 Pulling latest logs from GitHub...")
                result = subprocess.run(
                    ['git', 'pull'],
                    cwd=self.log_dir,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    logger.info("✅ Pulled previous logs")
                else:
                    logger.warning(f"⚠️ Pull failed: {result.stderr}")
            else:
                # 否則 clone
                logger.info(f"📥 Cloning logs from {self.gh_repo}...")
                result = subprocess.run([
                    'git', 'clone',
                    f'https://{self.gh_token}@github.com/{self.gh_repo}.git',
                    self.log_dir
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info("✅ Cloned logs from GitHub")
                else:
                    logger.warning(f"⚠️ Clone failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"⚠️ Restore failed: {e}")
    
    def backup(self):
        """備份 logs 到 GitHub（每小時自動執行）"""
        if not self.gh_token or not self.gh_repo:
            logger.info("ℹ️ GitHub backup not configured, skipping backup")
            return
        
        try:
            # 初始化 git（如果還沒）
            if not os.path.exists(os.path.join(self.log_dir, '.git')):
                logger.info("🔧 Initializing git repository...")
                subprocess.run(['git', 'init', '-b', 'main'], cwd=self.log_dir)
                subprocess.run(['git', 'config', 'user.name', 'Z1 API'], cwd=self.log_dir)
                subprocess.run(['git', 'config', 'user.email', 'api@z1.dev'], cwd=self.log_dir)
                subprocess.run([
                    'git', 'remote', 'add', 'origin',
                    f'https://{self.gh_token}@github.com/{self.gh_repo}.git'
                ], cwd=self.log_dir)
            
            # 提交
            logger.info("📝 Committing changes...")
            subprocess.run(['git', 'add', '.'], cwd=self.log_dir)
            result = subprocess.run([
                'git', 'commit', '-m',
                f'Auto backup {datetime.now().isoformat()}'
            ], cwd=self.log_dir, capture_output=True, text=True)
            
            # 推送
            logger.info("📤 Pushing to GitHub...")
            result = subprocess.run(
                ['git', 'push', '-u', 'origin', 'main', '--force'],
                cwd=self.log_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("✅ Backup successful")
            else:
                logger.error(f"❌ Push failed: {result.stderr}")
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
