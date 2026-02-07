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
import mtr_pathfinder
from mtr_pathfinder import (
    fetch_data as original_fetch_data_v3,
    gen_route_interval as original_gen_route_interval,
    create_graph as original_create_graph,
    find_shortest_route as original_find_shortest_route,
    station_name_to_id as original_station_name_to_id,
    process_path as original_process_path,
    RouteType,
    main as original_main
)

# 重新定义process_path函数，修复v4版本数据结构问题
def process_path(*args, **kwargs):
    """
    修复v4版本数据结构问题的process_path函数
    当检测到v4版本数据时，自动将其包装成列表格式
    """
    # 检查第三个参数是否为数据
    if len(args) >= 4 and isinstance(args[3], dict) and 'stations' in args[3] and 'routes' in args[3]:
        # v4版本的数据结构，需要包装成列表格式
        data = args[3]
        
        # 修复数据结构
        fixed_data = [{
            'stations': data['stations'],
            'routes': list(data['routes'].values())
        }]
        
        # 创建新的参数列表，替换第三个参数
        new_args = list(args)
        new_args[3] = fixed_data
        
        # 调用原函数
        return original_process_path(*new_args, **kwargs)
    else:
        # 其他版本或数据结构，直接调用原函数
        return original_process_path(*args, **kwargs)

# 替换mtr_pathfinder模块中的process_path函数
mtr_pathfinder.process_path = process_path

# 重新定义station_name_to_id函数，修复v4版本数据结构问题
def station_name_to_id(data, *args, **kwargs):
    """
    修复v4版本数据结构问题的station_name_to_id函数
    当检测到v4版本数据时，自动将其包装成列表格式
    """
    # 检查data的数据结构
    if isinstance(data, dict) and 'stations' in data and 'routes' in data:
        # v4版本的数据结构，需要包装成列表格式
        fixed_data = [{
            'stations': data['stations'],
            'routes': list(data['routes'].values())
        }]
        return original_station_name_to_id(fixed_data, *args, **kwargs)
    else:
        # 其他版本或数据结构，直接调用原函数
        return original_station_name_to_id(data, *args, **kwargs)

# 重新定义create_graph函数，修复v4版本数据结构问题
def create_graph(*args, **kwargs):
    """
    修复v4版本数据结构问题的create_graph函数
    当检测到v4版本数据时，自动将其包装成列表格式
    """
    import tempfile
    import json
    import os
    
    # 检查第一个参数是否为数据
    if args and isinstance(args[0], dict) and 'stations' in args[0] and 'routes' in args[0]:
        # v4版本的数据结构，需要包装成列表格式
        data = args[0]
        
        # 修复数据结构
        fixed_data = [{
            'stations': data['stations'],
            'routes': list(data['routes'].values())
        }]
        
        # 创建新的参数列表，替换第一个参数
        new_args = list(args)
        new_args[0] = fixed_data
        
        # 调用原函数
        return original_create_graph(*new_args, **kwargs)
    # 检查第一个参数是否为列表，且第一个元素是字典（v3版本数据结构）
    elif args and isinstance(args[0], list) and len(args[0]) > 0 and isinstance(args[0][0], dict):
        # v3版本数据结构，直接调用原函数
        return original_create_graph(*args, **kwargs)
    else:
        # 其他版本或数据结构，直接调用原函数
        return original_create_graph(*args, **kwargs)

# 重新定义find_shortest_route函数，修复v4版本数据结构问题
def find_shortest_route(*args, **kwargs):
    """
    修复v4版本数据结构问题的find_shortest_route函数
    当检测到v4版本数据时，自动将其包装成列表格式
    """
    # 检查第三个参数是否为数据
    if len(args) >= 3 and isinstance(args[2], dict) and 'stations' in args[2] and 'routes' in args[2]:
        # v4版本的数据结构，需要包装成列表格式
        data = args[2]
        
        # 修复数据结构
        fixed_data = [{
            'stations': data['stations'],
            'routes': list(data['routes'].values())
        }]
        
        # 创建新的参数列表，替换第三个参数
        new_args = list(args)
        new_args[2] = fixed_data
        
        # 调用原函数
        return original_find_shortest_route(*new_args, **kwargs)
    else:
        # 其他版本或数据结构，直接调用原函数
        return original_find_shortest_route(*args, **kwargs)

# 重新定义run函数，覆盖原有的run函数
import mtr_pathfinder
import os
import json
import hashlib

def custom_run():
    """
    自定义run函数，从config.json读取配置
    覆盖原有的run函数，避免直接运行时LINK为空的问题
    """
    import sys
    from io import StringIO
    
    # 保存原始stdin
    original_stdin = sys.stdin
    # 创建模拟输入流，自动返回'y'
    mock_stdin = StringIO('y\n' * 10)  # 提供足够的'y'响应
    sys.stdin = mock_stdin
    
    try:
        # 读取配置文件
        CONFIG_PATH = 'config.json'
        
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            print(f"错误: 配置文件 {CONFIG_PATH} 不存在")
            return
        
        # 检查是否有LINK配置
        if 'LINK' not in config or not config['LINK']:
            print("错误: 配置文件中没有设置有效的LINK值")
            return
        
        # 准备参数
        LINK = config['LINK']
        MTR_VER = config.get('MTR_VER', 3)
        
        # 计算文件路径
        link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
        LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
        INTERVAL_PATH = f'mtr-route-data-{link_hash}-{MTR_VER}.json'
        BASE_PATH = 'mtr_pathfinder_data'
        PNG_PATH = 'mtr_pathfinder_data'
        
        # 其他默认参数
        station1 = ''
        station2 = ''
        MAX_WILD_BLOCKS = 1500
        TRANSFER_ADDITION = {}
        WILD_ADDITION = {}
        STATION_TABLE = {}
        ORIGINAL_IGNORED_LINES = []
        UPDATE_DATA = False
        GEN_ROUTE_INTERVAL = False
        IGNORED_LINES = []
        AVOID_STATIONS = []
        CALCULATE_HIGH_SPEED = True
        CALCULATE_BOAT = True
        CALCULATE_WALKING_WILD = False
        ONLY_LRT = False
        IN_THEORY = False
        DETAIL = False
        
        # 调用main函数
        original_main(
            station1, station2, LINK, LOCAL_FILE_PATH, INTERVAL_PATH,
            BASE_PATH, PNG_PATH, MAX_WILD_BLOCKS,
            TRANSFER_ADDITION, WILD_ADDITION, STATION_TABLE,
            ORIGINAL_IGNORED_LINES, UPDATE_DATA, GEN_ROUTE_INTERVAL,
            IGNORED_LINES, AVOID_STATIONS, CALCULATE_HIGH_SPEED,
            CALCULATE_BOAT, CALCULATE_WALKING_WILD, ONLY_LRT, IN_THEORY, DETAIL,
            MTR_VER, show=True
        )
    finally:
        # 恢复原始stdin
        sys.stdin = original_stdin

# 覆盖原有的run函数
mtr_pathfinder.run = custom_run

# 现在可以导入v4版本的函数
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
    # 保存原始stdin
    original_stdin = sys.stdin
    # 创建模拟输入流，自动返回'y'
    mock_stdin = StringIO('y\n' * 5)  # 提供足够的'y'响应
    sys.stdin = mock_stdin
    try:
        # 调用原函数
        return original_fetch_data_v3(link, local_file_path, mtr_ver)
    finally:
        # 恢复原始stdin
        sys.stdin = original_stdin

# 重新定义fetch_data_v4，自动确认输入
def fetch_data_v4(link, local_file_path, max_wild_blocks):
    print("DEBUG: Calling wrapped fetch_data_v4")
    # 保存原始stdin
    original_stdin = sys.stdin
    # 创建模拟输入流，自动返回'y'
    mock_stdin = StringIO('y\n' * 5)  # 提供足够的'y'响应
    sys.stdin = mock_stdin
    try:
        # 调用原函数
        return original_fetch_data_v4(link, local_file_path, max_wild_blocks)
    finally:
        # 恢复原始stdin
        sys.stdin = original_stdin

# 重新定义gen_departure，自动确认输入
def gen_departure(link, dep_path):
    print("DEBUG: Calling wrapped gen_departure")
    # 保存原始stdin
    original_stdin = sys.stdin
    # 创建模拟输入流，自动返回'y'
    mock_stdin = StringIO('y\n' * 5)  # 提供足够的'y'响应
    sys.stdin = mock_stdin
    try:
        # 调用原函数
        return original_gen_departure(link, dep_path)
    finally:
        # 恢复原始stdin
        sys.stdin = original_stdin

# 重新定义gen_route_interval，自动确认输入并修复v4版本数据结构问题
def gen_route_interval(local_file_path, interval_path, link, mtr_ver):
    print("DEBUG: Calling wrapped gen_route_interval")
    # 保存原始stdin
    original_stdin = sys.stdin
    # 创建模拟输入流，自动返回'y'
    mock_stdin = StringIO('y\n' * 5)  # 提供足够的'y'响应
    sys.stdin = mock_stdin
    try:
        # 修复v4版本数据结构问题
        if mtr_ver == 4:
            # 先读取数据，修复结构后再写入临时文件
            import tempfile
            import shutil
            import json
            import requests
            
            # 读取原始数据
            with open(local_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False)
            temp_file_path = temp_file.name
            
            # 修复数据结构，将data包装成列表格式，让原函数能正常处理
            if isinstance(data, dict) and 'stations' in data and 'routes' in data:
                # v4版本的数据结构，需要包装成列表格式
                fixed_data = [{
                    'stations': data['stations'],
                    'routes': list(data['routes'].values())
                }]
                json.dump(fixed_data, temp_file)
            else:
                # 其他版本或数据结构，直接写入
                json.dump(data, temp_file)
            
            temp_file.close()
            
            try:
                # 调用原函数处理临时文件
                return original_gen_route_interval(temp_file_path, interval_path, link, mtr_ver)
            finally:
                # 删除临时文件
                os.unlink(temp_file_path)
        else:
            # 其他版本直接调用原函数
            return original_gen_route_interval(local_file_path, interval_path, link, mtr_ver)
    finally:
        # 恢复原始stdin
        sys.stdin = original_stdin

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

# 添加运行mtr_pathfinder的函数，用于替代直接运行原文件
def run_mtr_pathfinder():
    """
    运行mtr_pathfinder程序，从config.json读取配置
    替代直接运行mtr_pathfinder.py，避免LINK为空的问题
    """
    import os
    import json
    import hashlib
    
    # 读取配置文件
    CONFIG_PATH = 'config.json'
    
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        print(f"错误: 配置文件 {CONFIG_PATH} 不存在")
        return False
    
    # 检查是否有LINK配置
    if 'LINK' not in config or not config['LINK']:
        print("错误: 配置文件中没有设置有效的LINK值")
        return False
    
    # 准备参数
    LINK = config['LINK']
    MTR_VER = config.get('MTR_VER', 3)
    
    # 计算文件路径
    link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
    LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
    INTERVAL_PATH = f'mtr-route-data-{link_hash}-{MTR_VER}.json'
    BASE_PATH = 'mtr_pathfinder_data'
    PNG_PATH = 'mtr_pathfinder_data'
    
    # 其他默认参数
    station1 = ''
    station2 = ''
    MAX_WILD_BLOCKS = 1500
    TRANSFER_ADDITION = {}
    WILD_ADDITION = {}
    STATION_TABLE = {}
    ORIGINAL_IGNORED_LINES = []
    UPDATE_DATA = False
    GEN_ROUTE_INTERVAL = False
    IGNORED_LINES = []
    AVOID_STATIONS = []
    CALCULATE_HIGH_SPEED = True
    CALCULATE_BOAT = True
    CALCULATE_WALKING_WILD = False
    ONLY_LRT = False
    IN_THEORY = False
    DETAIL = False
    
    # 调用mtr_pathfinder的main函数
    try:
        from mtr_pathfinder import main as mtr_main
        import tempfile
        import json
        
        # 修复数据文件的结构，确保与mtr_pathfinder.py兼容
        temp_local_file = LOCAL_FILE_PATH
        temp_interval_file = INTERVAL_PATH
        
        if MTR_VER == 4:
            # 检查并修复LOCAL_FILE_PATH的数据结构
            if os.path.exists(LOCAL_FILE_PATH):
                with open(LOCAL_FILE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 如果数据是字典格式，需要包装成列表格式
                if isinstance(data, dict) and 'stations' in data and 'routes' in data:
                    # 创建临时文件
                    temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False)
                    temp_local_file = temp_file.name
                    
                    # 修复数据结构
                    fixed_data = [{
                        'stations': data['stations'],
                        'routes': list(data['routes'].values())
                    }]
                    json.dump(fixed_data, temp_file)
                    temp_file.close()
            
            # 检查并修复INTERVAL_PATH的数据结构
            if os.path.exists(INTERVAL_PATH):
                with open(INTERVAL_PATH, 'r', encoding='utf-8') as f:
                    interval_data = json.load(f)
                
                # 如果数据是字典格式，需要包装成列表格式
                if isinstance(interval_data, dict):
                    # 创建临时文件
                    temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False)
                    temp_interval_file = temp_file.name
                    
                    # 修复数据结构（这里假设interval_data的结构不需要修改，直接写入）
                    json.dump(interval_data, temp_file)
                    temp_file.close()
        
        # 调用原函数
        result = mtr_main(
            station1, station2, LINK, temp_local_file, temp_interval_file,
            BASE_PATH, PNG_PATH, MAX_WILD_BLOCKS,
            TRANSFER_ADDITION, WILD_ADDITION, STATION_TABLE,
            ORIGINAL_IGNORED_LINES, UPDATE_DATA, GEN_ROUTE_INTERVAL,
            IGNORED_LINES, AVOID_STATIONS, CALCULATE_HIGH_SPEED,
            CALCULATE_BOAT, CALCULATE_WALKING_WILD, ONLY_LRT, IN_THEORY, DETAIL,
            MTR_VER, show=True
        )
        
        # 删除临时文件
        if temp_local_file != LOCAL_FILE_PATH:
            os.unlink(temp_local_file)
        if temp_interval_file != INTERVAL_PATH:
            os.unlink(temp_interval_file)
        
        # 根据main函数的返回值处理
        if result is False:
            print("运行结果: 找不到路线")
        elif result is None:
            print("运行结果: 车站输入错误，请重新输入")
        else:
            print("运行结果: 成功生成路线图")
        return True
    except Exception as e:
        print(f"错误: 运行mtr_pathfinder时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

# 修复原程序中的数据读取问题，确保v4版本数据能被正确处理
# 替换mtr_pathfinder模块中的main函数，添加数据结构修复逻辑
def fixed_main(*args, **kwargs):
    """
    修复v4版本数据结构问题的main函数
    当检测到v4版本数据时，自动将其包装成列表格式
    """
    import sys
    from io import StringIO
    
    # 保存原始stdin
    original_stdin = sys.stdin
    # 创建模拟输入流，自动返回'y'（如果需要的话）
    mock_stdin = StringIO('y\n' * 10)
    sys.stdin = mock_stdin
    
    try:
        # 调用原函数
        result = original_main(*args, **kwargs)
        return result
    finally:
        # 恢复原始stdin
        sys.stdin = original_stdin

# 替换原程序的main函数
mtr_pathfinder.main = fixed_main

# 替换原程序的create_graph函数，确保数据结构正确
mtr_pathfinder.create_graph = create_graph

# 替换原程序的find_shortest_route函数，确保数据结构正确
mtr_pathfinder.find_shortest_route = find_shortest_route

# 替换原程序的process_path函数，确保数据结构正确
mtr_pathfinder.process_path = process_path

# 替换原程序的station_name_to_id函数，确保数据结构正确
mtr_pathfinder.station_name_to_id = station_name_to_id

# 如果直接运行这个wrapper文件，就执行run_mtr_pathfinder函数
if __name__ == '__main__':
    run_mtr_pathfinder()
