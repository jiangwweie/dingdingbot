#!/usr/bin/env python3
"""Generate docs/INDEX.json from active/ and constraints/ directories."""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DOCS_DIR = PROJECT_ROOT / "docs"
ACTIVE_DIR = DOCS_DIR / "active"
CONSTRAINTS_DIR = DOCS_DIR / "constraints"
INDEX_FILE = DOCS_DIR / "INDEX.json"

TOPIC_KEYWORDS = {
    'websocket': ['websocket', 'ws', 'ccxt.pro', 'ccxtpro'],
    'backtest': ['backtest', '回测', 'backtester'],
    'config': ['config', '配置', 'yaml', 'settings'],
    'order': ['order', '订单', 'order_gateway', 'order_lifecycle'],
    'risk': ['risk', '风控', 'position_size', 'stop_loss', 'leverage'],
    'signal': ['signal', '信号', 'signal_pipeline'],
    'kline': ['kline', 'k 线', 'ohlcv', 'candle'],
    'database': ['database', '数据库', 'sqlite', 'wal', 'db'],
    'api': ['api', 'rest', 'fastapi', 'endpoint', '路由'],
    'frontend': ['frontend', '前端', 'react', 'typescript', 'vue'],
    'testing': ['test', '测试', 'e2e', 'pytest'],
    'architecture': ['architecture', '架构', 'adr', 'design', '设计'],
    'strategy': ['strategy', '策略', 'pinbar', 'engulfing'],
    'notification': ['notification', '通知', 'feishu', 'telegram', 'notifier'],
    'exchange': ['exchange', '交易所', 'binance', 'bybit', 'okx'],
    'connection': ['connection', '连接', 'pool', 'pooling'],
}


def extract_topics(content: str) -> list[str]:
    """Extract topics from document content."""
    topics = []
    content_lower = content.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in content_lower for kw in keywords):
            topics.append(topic)
    return topics


def extract_refs(content: str) -> list[str]:
    """Extract src/ path references."""
    return list(set(re.findall(r'(?:src/[a-zA-Z0-9_/\-]+\.py)', content)))


def read_file(path: Path) -> str:
    """Read file content safely, limited to first 50 lines."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= 50:
                    break
                lines.append(line)
            return ''.join(lines)
    except Exception:
        return ''


def scan_dir(dir_path: Path, category: str) -> list[dict]:
    """Scan a directory and return file metadata."""
    results = []
    if not dir_path.exists():
        return results

    for md_file in sorted(dir_path.glob('*.md')):
        content = read_file(md_file)
        stat = md_file.stat()

        entry = {
            'path': str(md_file.relative_to(DOCS_DIR)),
            'name': md_file.name,
            'category': category,
            'size_kb': round(stat.st_size / 1024, 1),
            'topics': extract_topics(content),
            'refs': extract_refs(content),
            'headings': re.findall(r'^#{1,3}\s+(.+)$', content, re.MULTILINE)[:5],
            'mtime': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
        results.append(entry)

    return results


def build_search_index(files: list[dict]) -> dict:
    """Build search indexes by topic and file reference."""
    by_topic = defaultdict(list)
    by_file = defaultdict(list)

    for f in files:
        for topic in f['topics']:
            by_topic[topic].append(f['path'])
        for ref in f['refs']:
            by_file[ref].append(f['path'])

    return {
        'by_topic': dict(by_topic),
        'by_file': dict(by_file),
    }


def main():
    print("Generating INDEX.json ...")

    active_files = scan_dir(ACTIVE_DIR, 'active')
    constraint_files = scan_dir(CONSTRAINTS_DIR, 'constraints')
    all_files = active_files + constraint_files

    search_index = build_search_index(all_files)

    index = {
        'generated_at': datetime.now(tz=timezone.utc).isoformat(),
        'total_files': len(all_files),
        'active': active_files,
        'constraints': constraint_files,
        'search_index': search_index,
    }

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"INDEX.json generated: {len(active_files)} active + {len(constraint_files)} constraints = {len(all_files)} total")
    print(f"Topics indexed: {len(search_index['by_topic'])}")
    print(f"File refs indexed: {len(search_index['by_file'])}")
    print(f"Path → {INDEX_FILE}")


if __name__ == '__main__':
    main()
