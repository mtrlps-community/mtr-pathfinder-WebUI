# 包装模块，处理opencc初始化问题
import sys
import os
import json
import hashlib
from datetime import datetime
from io import StringIO

# 直接在sys.modules中添加模拟的opencc模块
class MockOpenCC:
    def __init__(self, config):
        self.config = config
    def convert(self, text):
        return text

# 创建模拟模块
mock_opencc_module = type('module', (), {})
mock_opencc_module.OpenCC = MockOpenCC

# 将模拟模块添加到sys.modules
sys.modules['opencc'] = mock_opencc_module

# 现在可以安全地导入原程序
from mtr_pathfinder import (
    fetch_data as original_fetch_data_v3,
    gen_route_interval as original_gen_route_interval,
    create_graph,
    find_shortest_route,
    RouteType
)
from mtr_pathfinder_v4 import (
    fetch_data as original_fetch_data_v4,
    gen_departure as original_gen_departure,
    gen_timetable,
    load_tt,
    CSA,
    process_path,
    RouteType as RouteTypeV4
)

# 重新定义fetch_data_v3，自动确认输入

def fetch_data_v3(link, local_file_path, mtr_ver):
    print("DEBUG: Calling wrapped fetch_data_v3")
    # 保存原始input函数
    original_input = __builtins__['input']
    
    # 定义自动返回'y'的mock input函数
    def mock_input(prompt):
        print(f"DEBUG: Mocking input for prompt: {prompt}")
        return 'y'
    
    try:
        # 替换内置input函数
        __builtins__['input'] = mock_input
        # 调用原函数
        return original_fetch_data_v3(link, local_file_path, mtr_ver)
    finally:
        # 恢复原始input函数
        __builtins__['input'] = original_input

# 重新定义fetch_data_v4，自动确认输入
def fetch_data_v4(link, local_file_path, max_wild_blocks):
    print("DEBUG: Calling wrapped fetch_data_v4")
    # 保存原始input函数
    original_input = __builtins__['input']
    
    # 定义自动返回'y'的mock input函数
    def mock_input(prompt):
        print(f"DEBUG: Mocking input for prompt: {prompt}")
        return 'y'
    
    try:
        # 替换内置input函数
        __builtins__['input'] = mock_input
        # 调用原函数
        return original_fetch_data_v4(link, local_file_path, max_wild_blocks)
    finally:
        # 恢复原始input函数
        __builtins__['input'] = original_input

# 重新定义gen_departure，自动确认输入
def gen_departure(link, dep_path):
    print("DEBUG: Calling wrapped gen_departure")
    # 保存原始input函数
    original_input = __builtins__['input']
    
    # 定义自动返回'y'的mock input函数
    def mock_input(prompt):
        print(f"DEBUG: Mocking input for prompt: {prompt}")
        return 'y'
    
    try:
        # 替换内置input函数
        __builtins__['input'] = mock_input
        # 调用原函数
        return original_gen_departure(link, dep_path)
    finally:
        # 恢复原始input函数
        __builtins__['input'] = original_input

# 重新定义gen_route_interval，自动确认输入
def gen_route_interval(local_file_path, interval_path, link, mtr_ver):
    print("DEBUG: Calling wrapped gen_route_interval")
    # 保存原始input函数
    original_input = __builtins__['input']
    
    # 定义自动返回'y'的mock input函数
    def mock_input(prompt):
        print(f"DEBUG: Mocking input for prompt: {prompt}")
        return 'y'
    
    try:
        # 替换内置input函数
        __builtins__['input'] = mock_input
        # 调用原函数
        return original_gen_route_interval(local_file_path, interval_path, link, mtr_ver)
    finally:
        # 恢复原始input函数
        __builtins__['input'] = original_input

# 尝试导入timetable模块，如果失败则跳过
try:
    from mtr_timetable_github import (
        get_text_timetable,
        get_train,
        main_sta_timetable,
        main_get_sta_directions
    )
    TIMETABLE_AVAILABLE = True
except Exception as e:
    print(f"警告: 导入timetable模块失败: {e}")
    TIMETABLE_AVAILABLE = False
    get_text_timetable = None
    get_train = None
    main_sta_timetable = None
    main_get_sta_directions = None
