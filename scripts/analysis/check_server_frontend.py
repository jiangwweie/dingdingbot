#!/usr/bin/env python3
"""
Check server frontend code for time formatting
"""
import re

with open('/tmp/server-frontend.js', 'r') as f:
    content = f.read()

# 查找包含 kline_timestamp 的代码段
matches = re.findall(r'.{0,50}kline_timestamp.{0,200}', content)
print("=== kline_timestamp usage ===")
for m in matches[:5]:
    print(m[:300])
    print("---")

# 查找时间格式化相关函数
time_funcs = re.findall(r'.{0,30}(formatTime|formatDate|formatTimestamp|formatBeijingTime).{0,100}', content)
print("\n=== Time formatting functions ===")
for f in time_funcs[:10]:
    print(f)
