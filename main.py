from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
import os
import json
import hashlib
import re
from datetime import datetime

from mtr_pathfinder_lib.mtr_pathfinder import (
    fetch_data as fetch_data_v3,
    gen_route_interval as gen_route_interval_v3,
    create_graph as create_graph_v3,
    find_shortest_route as find_shortest_route_v3,
    save_image as save_image_v3,
    main as mtr_main_v3,
    RouteType as RouteTypeV3,
)

from mtr_pathfinder_lib.mtr_pathfinder_v4 import (
    main as mtr_main_v4,
    save_image as save_image_v4,
    gen_departure as gen_departure_v4
)

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# 全局进度跟踪变量
search_progress = {
    'percentage': 0,
    'stage': '准备中...',
    'message': '正在初始化寻路参数...'
}

# 数据更新进度跟踪变量
data_update_progress = {
    'percentage': 0,
    'stage': '准备中...',
    'message': '正在准备数据更新...'
}

# 寻路次数统计
route_search_count = 0

# 配置文件路径
CONFIG_PATH = 'config.json'

# 默认配置
default_config = {
    'LINK': 'https://letsplay.minecrafttransitrailway.com/system-map',
    'MTR_VER': 4,
    'MAX_HOUR': 3,
    'MAX_WILD_BLOCKS': 1500,
    'TRANSFER_ADDITION': {},
    'WILD_ADDITION': {},
    'STATION_TABLE': {},
    'ORIGINAL_IGNORED_LINES': [],
    'CONSOLE_PASSWORD': 'admin',
    'UMAMI_SCRIPT_URL': '',
    'UMAMI_WEBSITE_ID': ''
}

# 加载配置
def load_config():
    # 先加载默认配置
    config = default_config.copy()
    
    # 如果配置文件存在，使用配置文件的内容更新默认配置
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config_file = json.load(f)
            # 使用配置文件的内容更新默认配置，确保所有默认字段都存在
            config.update(config_file)
    
    # 从环境变量加载配置，优先级最高
    for key, default_value in default_config.items():
        # 直接使用配置项名称作为环境变量名，不添加前缀
        env_key = key
        env_value = os.environ.get(env_key)
        
        if env_value is not None:
            # 根据默认值类型进行类型转换
            if isinstance(default_value, bool):
                # 布尔值处理
                config[key] = env_value.lower() in ('true', '1', 'yes', 'y')
            elif isinstance(default_value, int):
                # 整数处理
                try:
                    config[key] = int(env_value)
                except ValueError:
                    print(f"Warning: Environment variable {env_key} is not a valid integer, using default value")
            elif isinstance(default_value, float):
                # 浮点数处理
                try:
                    config[key] = float(env_value)
                except ValueError:
                    print(f"Warning: Environment variable {env_key} is not a valid float, using default value")
            elif isinstance(default_value, list):
                # 数组处理，支持JSON数组格式或逗号分隔格式
                try:
                    # 尝试解析为JSON数组
                    config[key] = json.loads(env_value)
                    if not isinstance(config[key], list):
                        raise ValueError("Not a list")
                except (ValueError, json.JSONDecodeError):
                    # 尝试按逗号分隔处理
                    config[key] = [item.strip() for item in env_value.split(',')]
            elif isinstance(default_value, dict):
                # 对象处理，需要JSON格式
                try:
                    config[key] = json.loads(env_value)
                    if not isinstance(config[key], dict):
                        raise ValueError("Not a dictionary")
                except (ValueError, json.JSONDecodeError):
                    print(f"Warning: Environment variable {env_key} is not a valid JSON object, using default value")
            else:
                # 字符串处理，直接使用
                config[key] = env_value
    
    return config

# 保存配置
def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# 初始化配置
config = load_config()

# 根据配置中的文件路径配置变量
def update_file_paths():
    if config['LINK']:
        link_hash = hashlib.md5(config['LINK'].encode('utf-8')).hexdigest()
        # 为v3和v4版本分别生成不同的文件路径
        config['LOCAL_FILE_PATH_V3'] = f'mtr-station-data-{link_hash}-mtr{config["MTR_VER"]}-v3.json'
        config['LOCAL_FILE_PATH_V4'] = f'mtr-station-data-{link_hash}-mtr4-v4.json'
        config['DEP_PATH_V3'] = f'mtr-departure-data-{link_hash}-mtr{config["MTR_VER"]}-v3.json'
        config['DEP_PATH_V4'] = f'mtr-route-departure-data-{link_hash}-mtr4-v4.json'
        config['INTERVAL_PATH_V3'] = f'mtr-route-interval-data-{link_hash}-mtr{config["MTR_VER"]}-v3.json'
        # 兼容现有代码，保持旧的键名
        config['LOCAL_FILE_PATH'] = config['LOCAL_FILE_PATH_V3']
        config['DEP_PATH'] = config['DEP_PATH_V3']
        config['INTERVAL_PATH'] = config['INTERVAL_PATH_V3']
    save_config(config)

update_file_paths()
BASE_PATH = 'mtr_pathfinder_data'
PNG_PATH = 'mtr_pathfinder_data'

@app.context_processor
def inject_config():
    return dict(config=config, request=request)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/stations')
def stations():
    # 读取车站数据和线路数据
    stations_data = []
    routes_data = []
    # 优先使用v3版本的数据文件，因为它包含更多信息
    data_file_path = config['LOCAL_FILE_PATH_V3']
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 统一处理，无论MTR_VER版本，都使用列表格式
            if isinstance(data, list) and len(data) > 0:
                stations_data = list(data[0]['stations'].values())
                routes_data = data[0]['routes']
            elif isinstance(data, dict):
                # 如果是字典格式，将其转换为列表格式
                stations_data = list(data['stations'].values())
                routes_data = data['routes']
    
    # 创建车站ID到车站对象的映射
    station_id_map = {}
    for station in stations_data:
        if isinstance(station, dict) and 'id' in station:
            station_id_map[station['id']] = station
            # 初始化routes属性为空列表
            station['routes'] = []
    
    # 计算每个车站被多少条线路经过
    for route in routes_data:
        if isinstance(route, dict) and 'stations' in route:
            for station in route['stations']:
                if isinstance(station, dict) and 'id' in station:
                    station_id = station['id']
                    if station_id in station_id_map:
                        # 将线路添加到车站的routes列表中
                        station_id_map[station_id]['routes'].append(route)
    
    # 计算每个车站的线路数量（去重）和交路数量
    for station in stations_data:
        if isinstance(station, dict) and 'routes' in station:
            # 交路数量 = routes列表长度
            station['branch_count'] = len(station['routes'])
            
            # 线路数量 = 不同线路名称的数量
            line_names = set()
            for route in station['routes']:
                if isinstance(route, dict) and 'name' in route:
                    # 提取线路主名称（去除交路编号）
                    route_name = route['name']
                    if '||' in route_name:
                        main_name = route_name.split('||')[0].strip()
                    else:
                        main_name = route_name.strip()
                    line_names.add(main_name)
            station['line_count'] = len(line_names)
    
    # 将车站名称中的竖杠替换为空格
    for station in stations_data:
        if isinstance(station, dict) and 'name' in station:
            station['name'] = station['name'].replace('|', ' ')
    
    return render_template('stations.html', stations=stations_data)

@app.route('/stations/<station_id>')
def station_detail(station_id):
    # 读取车站数据
    station_data = None
    routes_data = []
    # 优先使用v3版本的数据文件，因为它包含更多信息
    data_file_path = config['LOCAL_FILE_PATH_V3']
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 统一处理，无论MTR_VER版本，都使用列表格式
            if isinstance(data, list) and len(data) > 0:
                # 获取车站数据
                stations = data[0]['stations']
                if station_id in stations:
                    station_data = stations[station_id]
                # 获取线路数据
                routes_data = data[0]['routes']
            elif isinstance(data, dict):
                # 兼容旧格式
                if 'stations' in data and station_id in data['stations']:
                    station_data = data['stations'][station_id]
                if 'routes' in data:
                    routes_data = data['routes']
    
    # 不再使用v4版本数据文件
    
    # 如果仍然没有找到车站数据，返回404
    if not station_data:
        return render_template('error.html', message='车站不存在'), 404
    
    # 将车站名称中的竖杠替换为空格
    if isinstance(station_data, dict) and 'name' in station_data:
        station_data['name'] = station_data['name'].replace('|', ' ')
    
    # 获取所有车站数据
    all_stations = {}
    if isinstance(data, list) and len(data) > 0 and 'stations' in data[0]:
        all_stations = data[0]['stations']
    elif isinstance(data, dict) and 'stations' in data:
        all_stations = data['stations']
    
    # 查找该车站所在的线路
    station_routes = []
    for route in routes_data:
        if isinstance(route, dict) and 'stations' in route:
            for station in route['stations']:
                if isinstance(station, dict) and station.get('id') == station_id:
                    # 处理线路名称，将名称和交路编号分开
                    if 'name' in route:
                        route_name = route['name']
                        # 检查是否包含双竖杠分隔符
                        if '||' in route_name:
                            # 分割线路名称和交路编号
                            name_parts = route_name.split('||')
                            # 将名称中的单个竖杠替换为空格
                            route['name'] = name_parts[0].strip().replace('|', ' ')
                            # 处理交路编号
                            if len(name_parts) > 1:
                                route_number = name_parts[1].strip()
                                # 移除JSON调试信息（大括号包裹的内容）
                                route_number = re.sub(r'\{.*?\}', '', route_number)
                                # 将单个竖杠替换为空格
                                route_number = route_number.replace('|', ' ')
                                # 去除多余空格
                                route_number = ' '.join(route_number.split())
                                route['route_number'] = route_number
                            else:
                                route['route_number'] = ''
                        else:
                            # 没有交路编号，只保留名称
                            route['name'] = route_name.strip().replace('|', ' ')
                            route['route_number'] = ''
                    
                    # 处理站点列表，添加站点名称和运行时间
                    processed_stations = []
                    durations = route.get('durations', [])
                    
                    # 查找当前车站在该线路中的站台编号
                    current_platform = 'N/A'
                    for route_station in route['stations']:
                        if isinstance(route_station, dict) and route_station.get('id') == station_id:
                            # 使用原始站点数据中的name字段作为站台编号
                            current_platform = route_station.get('name', 'N/A')
                            break
                    
                    for i, route_station in enumerate(route['stations']):
                        if isinstance(route_station, dict):
                            # 深拷贝，避免修改原始数据
                            processed_station = route_station.copy()
                            # 获取站点ID
                            route_station_id = processed_station.get('id')
                            # 如果能找到对应的车站数据，替换为车站名称
                            if route_station_id in all_stations:
                                # 使用临时变量存储线路站点数据，避免覆盖原始车站数据
                                route_station_data = all_stations[route_station_id]
                                # 将车站名称中的竖杠替换为空格
                                if 'name' in route_station_data:
                                    processed_station['name'] = route_station_data['name'].replace('|', ' ')
                            
                            # 添加运行时间信息：durations[i]是从当前站点到下一个站点的运行时间
                            if i < len(durations):
                                # 将秒转换为适当的格式：超过一小时显示为h:mm:ss，否则为mm:ss
                                seconds = durations[i]
                                # 转换为整数，避免浮点数格式化错误
                                hours = int(seconds // 3600)
                                minutes = int((seconds % 3600) // 60)
                                remaining_seconds = int(seconds % 60)
                                
                                if hours > 0:
                                    processed_station['travel_time'] = f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
                                else:
                                    processed_station['travel_time'] = f"{minutes:02d}:{remaining_seconds:02d}"
                            
                            processed_stations.append(processed_station)
                    
                    # 将当前车站的站台编号添加到线路数据中
                    route['current_platform'] = current_platform
                    # 更新线路的站点列表
                    route['stations'] = processed_stations
                    
                    station_routes.append(route)
                    break
    
    # 将线路按主名称分组
    grouped_routes = {}
    for route in station_routes:
        route_name = route.get('name', 'N/A')
        if route_name not in grouped_routes:
            grouped_routes[route_name] = {
                'main_route': route,  # 使用第一条线路作为主线路信息
                'routes': []
            }
        grouped_routes[route_name]['routes'].append(route)
    
    # 转换为列表格式便于模板处理
    grouped_routes_list = list(grouped_routes.values())
    
    # 处理连接车站信息
    connected_stations = []
    if 'connections' in station_data and station_data['connections']:
        for connection_id in station_data['connections']:
            if connection_id in all_stations:
                connected_station = all_stations[connection_id].copy()
                # 将车站名称中的竖杠替换为空格
                if 'name' in connected_station:
                    connected_station['name'] = connected_station['name'].replace('|', ' ')
                connected_stations.append(connected_station)
    
    return render_template('station_detail.html', station=station_data, grouped_routes=grouped_routes_list, station_id=station_id, connected_stations=connected_stations)

@app.route('/routes')
def routes():
    # 读取线路数据
    routes_data = []
    # 优先使用v3版本的数据文件，因为它包含更多信息
    data_file_path = config['LOCAL_FILE_PATH_V3']
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 统一处理，无论MTR_VER版本，都使用列表格式
            if isinstance(data, list) and len(data) > 0:
                # 检查data[0]['routes']是否为字典，如果是则转换为列表
                if isinstance(data[0]['routes'], dict):
                    routes_data = list(data[0]['routes'].values())
                else:
                    routes_data = data[0]['routes']
            elif isinstance(data, dict):
                # 如果是字典格式，将其转换为列表格式
                routes_data = list(data['routes'].values())
    
    # 读取interval数据文件，用于搜索功能
    interval_data = {}
    interval_file_path = config['INTERVAL_PATH_V3']
    if os.path.exists(interval_file_path):
        with open(interval_file_path, 'r', encoding='utf-8') as f:
            interval_data = json.load(f)
    
    # 处理线路名称，将名称和交路编号分开
    import re
    for route in routes_data:
        if isinstance(route, dict) and 'name' in route:
            route_name = route['name']
            # 检查是否包含双竖杠分隔符
            if '||' in route_name:
                # 分割线路名称和交路编号
                name_parts = route_name.split('||')
                # 将名称中的单个竖杠替换为空格
                route['name'] = name_parts[0].strip().replace('|', ' ')
                # 处理交路编号
                if len(name_parts) > 1:
                    route_number = name_parts[1].strip()
                    # 移除JSON调试信息（大括号包裹的内容）
                    route_number = re.sub(r'\{.*?\}', '', route_number)
                    # 将单个竖杠替换为空格
                    route_number = route_number.replace('|', ' ')
                    # 去除多余空格
                    route_number = ' '.join(route_number.split())
                    route['route_number'] = route_number
                else:
                    route['route_number'] = ''
            else:
                # 没有交路编号，只保留名称
                route['name'] = route_name.strip().replace('|', ' ')
                route['route_number'] = ''
    
    # 计算线路总数和交路总数，模仿车站详情页的统计逻辑
    # 交路总数 = 所有线路的数量
    branch_count = len(routes_data)
    
    # 线路总数 = 不同线路主名称的数量（去除交路编号）
    line_names = set()
    for route in routes_data:
        if isinstance(route, dict) and 'name' in route:
            # 提取线路主名称（这里已经处理过，直接使用name字段）
            line_names.add(route['name'])
    line_count = len(line_names)
    
    return render_template('routes.html', routes=routes_data, interval_data=interval_data, line_count=line_count, branch_count=branch_count)

@app.route('/routes/<route_id>')
def route_detail(route_id):
    # 读取线路数据
    route_data = None
    all_stations = {}
    all_routes_data = []
    same_name_routes = []  # 初始化same_name_routes，避免UnboundLocalError
    # 优先使用v3版本的数据文件，因为它包含更多信息
    data_file_path = config['LOCAL_FILE_PATH_V3']
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 统一处理，无论MTR_VER版本，都使用列表格式
            if isinstance(data, list) and len(data) > 0:
                # 获取车站数据
                all_stations = data[0]['stations']
                # 获取线路数据
                routes_data = data[0]['routes']
                # 转换为列表格式便于处理
                if isinstance(routes_data, dict):
                    all_routes_data = list(routes_data.values())
                else:
                    all_routes_data = routes_data
                # 查找指定线路
                for route in all_routes_data:
                    if isinstance(route, dict) and route.get('id') == route_id:
                        route_data = route
                        break
            elif isinstance(data, dict):
                # 兼容旧格式
                all_stations = data.get('stations', {})
                routes_data = data.get('routes', {})
                # 转换为列表格式便于处理
                if isinstance(routes_data, dict):
                    all_routes_data = list(routes_data.values())
                else:
                    all_routes_data = routes_data
                # 查找指定线路
                for route in all_routes_data:
                    if isinstance(route, dict) and route.get('id') == route_id:
                        route_data = route
                        break
    
    # 如果没有找到线路数据，返回404
    if not route_data:
        return render_template('error.html', message='线路不存在'), 404
    
    import re
    # 处理线路名称，分割主线路名称和交路编号
    if isinstance(route_data, dict) and 'name' in route_data:
        original_name = route_data['name']
        # 分割主线路名称和交路编号
        if '||' in original_name:
            main_name = original_name.split('||')[0].strip()
            route_data['main_name'] = main_name.replace('|', ' ')
        else:
            route_data['main_name'] = original_name.replace('|', ' ')
        
        # 处理交路编号
        route_number = ''
        if '||' in original_name:
            route_number = original_name.split('||')[1].strip()
            # 移除JSON调试信息（大括号包裹的内容）
            route_number = re.sub(r'\{.*?\}', '', route_number)
            # 将单个竖杠替换为空格
            route_number = route_number.replace('|', ' ')
            # 去除多余空格
            route_number = ' '.join(route_number.split())
        route_data['route_number'] = route_number
    
    # 处理站点列表，添加站点名称和运行时间
    processed_stations = []
    durations = route_data.get('durations', [])
    if isinstance(route_data, dict) and 'stations' in route_data:
        total_seconds = 0  # 累计运行时长（秒）
        for i, route_station in enumerate(route_data['stations']):
            if isinstance(route_station, dict):
                # 深拷贝，避免修改原始数据
                processed_station = route_station.copy()
                # 获取站点ID
                route_station_id = processed_station.get('id')
                # 如果能找到对应的车站数据，替换为车站名称
                if route_station_id in all_stations:
                    station_data = all_stations[route_station_id]
                    # 将车站名称中的竖杠替换为空格
                    if 'name' in station_data:
                        processed_station['name'] = station_data['name'].replace('|', ' ')
                
                # 处理停靠站台：使用原始站点数据中的name字段作为站台编号
                processed_station['platform'] = route_station.get('name', 'N/A')
                
                # 处理停站时长：将毫秒转换为秒格式
                dwell_time_ms = processed_station.get('dwellTime', 0)
                dwell_seconds = int(dwell_time_ms / 1000)
                processed_station['dwell_time'] = f"{dwell_seconds}秒"
                
                # 处理累计运行时长：转换为适当的格式：超过一小时显示为h:mm:ss，否则为mm:ss
                total_hours = int(total_seconds // 3600)
                total_minutes = int((total_seconds % 3600) // 60)
                total_remaining_seconds = int(total_seconds % 60)
                
                if total_hours > 0:
                    processed_station['total_time'] = f"{total_hours}:{total_minutes:02d}:{total_remaining_seconds:02d}"
                else:
                    processed_station['total_time'] = f"{total_minutes:02d}:{total_remaining_seconds:02d}"
                
                # 添加运行时间信息：durations[i]是从当前站点到下一个站点的运行时间
                if i < len(durations):
                    # 将秒转换为适当的格式：超过一小时显示为h:mm:ss，否则为mm:ss
                    seconds = durations[i]
                    # 转换为整数，避免浮点数格式化错误
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    remaining_seconds = int(seconds % 60)
                    
                    if hours > 0:
                        processed_station['travel_time'] = f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
                    else:
                        processed_station['travel_time'] = f"{minutes:02d}:{remaining_seconds:02d}"
                    
                    # 计算累计运行时长（不包括当前站点的停站时间）
                    # 将当前站点到下一站的运行时间加到累计时间中
                    total_seconds += seconds
                
                processed_stations.append(processed_station)
        # 更新线路的站点列表
        route_data['stations'] = processed_stations
    
    # 计算总运行时间
    if durations:
        total_runtime_seconds = sum(durations)
        total_runtime_hours = int(total_runtime_seconds // 3600)
        total_runtime_minutes = int((total_runtime_seconds % 3600) // 60)
        total_runtime_remaining_seconds = int(total_runtime_seconds % 60)
        
        if total_runtime_hours > 0:
            route_data['total_runtime'] = f"{total_runtime_hours}:{total_runtime_minutes:02d}:{total_runtime_remaining_seconds:02d}"
        else:
            route_data['total_runtime'] = f"{total_runtime_minutes:02d}:{total_runtime_remaining_seconds:02d}"
    else:
        route_data['total_runtime'] = "00:00"
    
    # 读取interval数据文件，获取发车间隔
    interval_data = {}
    interval_file_path = config['INTERVAL_PATH_V3']
    if os.path.exists(interval_file_path):
        with open(interval_file_path, 'r', encoding='utf-8') as f:
            interval_data = json.load(f)
    
    # 提取车厂信息（如果线路数据中包含）
    if 'depots' in route_data and isinstance(route_data['depots'], list) and route_data['depots']:
        # 车厂信息是一个数组，取第一个元素
        route_data['depot'] = route_data['depots'][0]
    else:
        route_data['depot'] = '未知'
    
    # 查找当前线路的发车间隔，使用线路完整名称作为键
    route_full_name = route_data.get('name', '')
    route_data['interval'] = interval_data.get(route_full_name, '未知')
    
    # 如果找到的是数字，转换为可读格式（秒 -> mm:ss 或 h:mm:ss）
    if isinstance(route_data['interval'], int):
        total_seconds = route_data['interval']
        hours = int(total_seconds // 3600)
        remaining_seconds = int(total_seconds % 3600)
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        
        if hours > 0:
            # 超过一小时，格式为 h:mm:ss
            route_data['interval'] = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            # 不足一小时，格式为 mm:ss
            route_data['interval'] = f"{minutes:02d}:{seconds:02d}"
    
    # 查找所有同名线路的交路
    same_name_routes = []
    for route in all_routes_data:
        if isinstance(route, dict) and 'name' in route:
            # 提取主线路名称
            route_name = route['name']
            if '||' in route_name:
                route_main_name = route_name.split('||')[0].strip()
            else:
                route_main_name = route_name.strip()
            
            # 比较主线路名称
            if route_main_name == (original_name.split('||')[0].strip() if '||' in original_name else original_name.strip()):
                # 处理交路信息
                route_info = {
                    'id': route.get('id', ''),
                    'name': route_name.replace('|', ' '),
                    'number': route.get('number', '')  # 添加线路编号
                }
                # 添加交路编号
                if '||' in route_name:
                    route_number = route_name.split('||')[1].strip()
                    # 移除JSON调试信息
                    route_number = re.sub(r'\{.*?\}', '', route_number)
                    # 清理交路编号
                    route_number = route_number.replace('|', ' ')
                    route_number = ' '.join(route_number.split())
                    route_info['route_number'] = route_number
                same_name_routes.append(route_info)
    
    return render_template('route_detail.html', route=route_data, same_name_routes=same_name_routes)



@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        # 处理登录请求
        password = request.form.get('password')
        if password == config['CONSOLE_PASSWORD']:
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            # 获取文件版本信息
            station_version = ""
            station_version_v4 = ""
            route_version_v4 = ""
            interval_version = ""
            
            if os.path.exists(config['LOCAL_FILE_PATH_V3']):
                station_version = datetime.fromtimestamp(
                    os.path.getmtime(config['LOCAL_FILE_PATH_V3'])
                ).strftime('%Y%m%d-%H%M')
            if os.path.exists(config['LOCAL_FILE_PATH_V4']):
                station_version_v4 = datetime.fromtimestamp(
                    os.path.getmtime(config['LOCAL_FILE_PATH_V4'])
                ).strftime('%Y%m%d-%H%M')
            if os.path.exists(config['DEP_PATH_V4']):
                route_version_v4 = datetime.fromtimestamp(
                    os.path.getmtime(config['DEP_PATH_V4'])
                ).strftime('%Y%m%d-%H%M')
            if os.path.exists(config['INTERVAL_PATH_V3']):
                interval_version = datetime.fromtimestamp(
                    os.path.getmtime(config['INTERVAL_PATH_V3'])
                ).strftime('%Y%m%d-%H%M')
            
            return render_template('admin.html', 
                           config=config, 
                           station_version=station_version,
                           station_version_v4=station_version_v4,
                           route_version_v4=route_version_v4,
                           interval_version=interval_version,
                           route_search_count=route_search_count,
                           error='密码错误')
    
    # GET请求，检查是否已登录
    if not session.get('admin_logged_in'):
        return render_template('admin.html', error=None, route_search_count=route_search_count)
    
    # 已登录，显示控制台内容
    # 获取文件版本信息
    station_version = ""
    station_version_v4 = ""
    route_version_v4 = ""
    interval_version = ""
    
    if os.path.exists(config['LOCAL_FILE_PATH_V3']):
        station_version = datetime.fromtimestamp(
            os.path.getmtime(config['LOCAL_FILE_PATH_V3'])
        ).strftime('%Y%m%d-%H%M')
    if os.path.exists(config['LOCAL_FILE_PATH_V4']):
        station_version_v4 = datetime.fromtimestamp(
            os.path.getmtime(config['LOCAL_FILE_PATH_V4'])
        ).strftime('%Y%m%d-%H%M')
    if os.path.exists(config['DEP_PATH_V4']):
        route_version_v4 = datetime.fromtimestamp(
            os.path.getmtime(config['DEP_PATH_V4'])
        ).strftime('%Y%m%d-%H%M')
    if os.path.exists(config['INTERVAL_PATH_V3']):
        interval_version = datetime.fromtimestamp(
            os.path.getmtime(config['INTERVAL_PATH_V3'])
        ).strftime('%Y%m%d-%H%M')
    
    return render_template('admin.html', 
                           config=config, 
                           station_version=station_version,
                           station_version_v4=station_version_v4,
                           route_version_v4=route_version_v4,
                           interval_version=interval_version,
                           route_search_count=route_search_count)

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin')

@app.route('/api/find_route', methods=['POST'])
def api_find_route():
    # 开始计时
    start_time = datetime.now()
    
    # 重置进度
    global search_progress
    search_progress = {
        'percentage': 0,
        'stage': '准备中...',
        'message': '正在初始化寻路参数...'
    }
    
    # 声明全局变量
    global latest_image_path
    
    # 增加寻路次数统计
    global route_search_count
    route_search_count += 1
    
    # 处理寻路请求
    data = request.json
    
    # 验证必要参数
    if not all(key in data for key in ['start', 'end']):
        return jsonify({'error': '缺少必要参数'}), 400
    
    # 准备参数
    algorithm = data.get('algorithm', 'default')
    
    # 更新进度
    search_progress.update({
        'percentage': 25,
        'stage': '(1/4)验证参数',
        'message': '正在验证输入参数...'
    })
    
    # 检查数据文件是否存在
    if algorithm == 'real':
        # 对于实时寻路，检查v4版本的数据文件
        if not os.path.exists(config['LOCAL_FILE_PATH_V4']):
            return jsonify({'error': '车站数据不存在，请先更新数据'}), 400
        if not os.path.exists(config['DEP_PATH_V4']):
            return jsonify({'error': '发车数据不存在，请先更新数据'}), 400
    else:
        # 对于默认/理论寻路，检查v3版本的数据文件
        if not os.path.exists(config['LOCAL_FILE_PATH_V3']):
            return jsonify({'error': '车站数据不存在，请先更新数据'}), 400
        if not os.path.exists(config['INTERVAL_PATH_V3']):
            return jsonify({'error': '间隔数据不存在，请先更新数据'}), 400
    
    # 更新进度
    search_progress.update({
        'percentage': 50,
        'stage': '(2/4)数据验证',
        'message': '数据文件验证通过，准备开始寻路...'
    })
    
    try:
        # 根据算法选择不同的寻路实现
        if algorithm == 'real':
            # 使用v4版程序的寻路功能
            
            # 更新进度
            search_progress.update({
                'percentage': 75,
                'stage': '(3/4)寻路计算',
                'message': '正在使用实时算法计算路径...'
            })
            
            # 处理出发时间参数
            dep_time_seconds = data.get('dep_time')
            client_time = data.get('client_time')
            
            # 如果dep_time_seconds为None且提供了客户端时间，使用客户端时间+10秒作为出发时间
            if dep_time_seconds is None and client_time is not None:
                dep_time_seconds = (client_time + 10) % 86400
            
            # 1. 生成gen_image=False条件下的数组结果
            result_gen_image_false = mtr_main_v4(
                station1=data['start'],
                station2=data['end'],
                LINK=config['LINK'],
                LOCAL_FILE_PATH=config['LOCAL_FILE_PATH_V4'],
                DEP_PATH=config['DEP_PATH_V4'],
                BASE_PATH=BASE_PATH,
                PNG_PATH=PNG_PATH,
                MAX_WILD_BLOCKS=config['MAX_WILD_BLOCKS'],
                TRANSFER_ADDITION=config['TRANSFER_ADDITION'],
                WILD_ADDITION=config['WILD_ADDITION'],
                STATION_TABLE=config['STATION_TABLE'],
                ORIGINAL_IGNORED_LINES=config['ORIGINAL_IGNORED_LINES'],
                UPDATE_DATA=False,
                GEN_DEPARTURE=False,
                IGNORED_LINES=data.get('ignored_lines', []),
                ONLY_LINES=data.get('only_lines', []),
                AVOID_STATIONS=data.get('avoid_stations', []),
                CALCULATE_HIGH_SPEED=not data.get('disable_high_speed', False),
                CALCULATE_BOAT=not data.get('disable_boat', False),
                CALCULATE_WALKING_WILD=data.get('enable_wild', False),
                ONLY_LRT=data.get('only_lrt', False),
                DETAIL=False,
                MAX_HOUR=config['MAX_HOUR'],
                gen_image=False,
                show=False,
                departure_time=dep_time_seconds
            )
            
            # 检查寻路结果
            if result_gen_image_false == []:
                # 找不到路线
                return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
            elif result_gen_image_false is False:
                # 找不到路线
                return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
            elif result_gen_image_false is None:
                # 车站名称不正确
                return jsonify({'error': '车站名称不正确，请检查输入'}), 400
            
            # 提取路线详情列表
            every_route_time = result_gen_image_false
            
            # 构建车站列表
            station_names = []
            for leg in every_route_time:
                if len(leg) >= 2:
                    # leg格式：(起点站, 终点站, 颜色, 路线名, 终点站信息, 发车时间, 到站时间, 交通类型, 站台编号, 原始路线名)
                    start_station, end_station = leg[0], leg[1]
                    route_name = leg[3]
                    
                    if not station_names:
                        station_names.append(start_station)
                    station_names.append(route_name)
                    station_names.append(end_station)
            
            # 计算总用时、乘车时间和等车时间
            if every_route_time:
                total_time = every_route_time[-1][6] - every_route_time[0][5]  # 总用时 = 最后一站到站时间 - 第一站发车时间
                riding_time = sum(leg[6] - leg[5] for leg in every_route_time)  # 乘车时间 = 各段乘车时间之和
                waiting_time = total_time - riding_time  # 等车时间 = 总用时 - 乘车时间
            else:
                total_time = 0
                riding_time = 0
                waiting_time = 0
            
            # 构建符合前端期望的结果数组
            formatted_result = [
                total_time,  # 总用时 (元素0)
                station_names,  # 车站列表 (元素1)
                every_route_time,  # 路线详情 (元素2) - 使用正确的路线详情列表
                riding_time,  # 乘车时间 (元素3)
                waiting_time  # 等车时间 (元素4)
            ]
            
            # 2. 继续处理图片生成的相关逻辑
            # 生成图片，直接调用save_image函数，避免重复寻路计算
            search_progress.update({
                'percentage': 85,
                'stage': '(4/4)生成图片',
                'message': '寻路计算完成，正在生成路线图片...'
            })
            
            # 获取数据版本信息
            version1 = ''
            version2 = ''
            if os.path.exists(config['LOCAL_FILE_PATH_V4']):
                version1 = datetime.fromtimestamp(
                    os.path.getmtime(config['LOCAL_FILE_PATH_V4'])
                ).strftime('%Y%m%d-%H%M')
            if os.path.exists(config['DEP_PATH_V4']):
                version2 = datetime.fromtimestamp(
                    os.path.getmtime(config['DEP_PATH_V4'])
                ).strftime('%Y%m%d-%H%M')
            
            # 直接调用save_image_v4函数生成图片，使用已经生成的every_route_time
            from mtr_pathfinder_lib.mtr_pathfinder_v4 import RouteType as RouteTypeV4
            image_result = save_image_v4(
                route_type=RouteTypeV4.REAL_TIME,
                every_route_time=every_route_time,
                BASE_PATH=BASE_PATH,
                version1=version1,
                version2=version2,
                PNG_PATH=PNG_PATH,
                departure_time=dep_time_seconds,
                show=False
            )
            
            # 3. 保存图片到文件系统
            image_base64 = None
            if image_result and image_result not in [False, None]:
                if isinstance(image_result, tuple) and len(image_result) == 2:
                    # v4版save_image_v4函数返回的图片格式：(image object, base64 str)
                    image, image_base64 = image_result
                    
                    # 保存图片到文件系统，方便前端获取
                    output_dir = 'generated_images'
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    image_path = os.path.join(output_dir, f'path_result_{timestamp}.png')
                    image.save(image_path)
                    
                    # 更新最新图片路径
                    latest_image_path = image_path
        else:
            # 使用v3版程序的寻路功能，完全集成mtr_pathfinder.py的main函数逻辑
            
            # 更新进度
            search_progress.update({
                'percentage': 75,
                'stage': '(3/4)寻路计算',
                'message': '正在使用最短路径算法计算最优路线...'
            })
            
            # 提取参数
            LINK = config['LINK']
            LOCAL_FILE_PATH = config['LOCAL_FILE_PATH_V3']
            INTERVAL_PATH = config['INTERVAL_PATH_V3']
            MTR_VER = config['MTR_VER']
            IN_THEORY = algorithm == 'theory'
            DETAIL = data.get('detail', True)
            
            # 原封不动地集成mtr_pathfinder.py的main函数逻辑
            if MTR_VER not in [3, 4]:
                return jsonify({'error': 'MTR_VER should be 3 or 4'}), 500

            # 合并忽略线路
            IGNORED_LINES = data.get('ignored_lines', []) + config['ORIGINAL_IGNORED_LINES']
            
            # 转换车站表格式
            STATION_TABLE = {x.lower(): y.lower() for x, y in config['STATION_TABLE'].items()}
            
            # 处理LINK格式
            if LINK.endswith('/index.html'):
                LINK = LINK.rstrip('/index.html')

            # 检查并加载数据文件
            if not os.path.exists(LOCAL_FILE_PATH):
                return jsonify({'error': '车站数据不存在，请先更新数据'}), 400
            with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
                data_file = json.load(f)

            # 检查路线间隔文件
            if not os.path.exists(INTERVAL_PATH):
                return jsonify({'error': '间隔数据不存在，请先更新数据'}), 400

            # 获取版本信息
            version1 = ''
            version2 = ''
            if os.path.exists(LOCAL_FILE_PATH):
                version1 = datetime.fromtimestamp(
                    os.path.getmtime(LOCAL_FILE_PATH)
                ).strftime('%Y%m%d-%H%M')
            if os.path.exists(INTERVAL_PATH):
                version2 = datetime.fromtimestamp(
                    os.path.getmtime(INTERVAL_PATH)
                ).strftime('%Y%m%d-%H%M')

            # 设置路线类型
            route_type = RouteTypeV3.IN_THEORY if IN_THEORY else RouteTypeV3.WAITING

            # 检查是否使用了缓存
            used_cache = False
            cache_conditions_met = (True and \
                                  IGNORED_LINES == config['ORIGINAL_IGNORED_LINES'] and \
                                  not data.get('disable_boat', False) and \
                                  not data.get('only_lrt', False) and \
                                  not data.get('only_lines', []) and \
                                  not data.get('avoid_stations', []) and \
                                  route_type == RouteTypeV3.WAITING)
            
            if cache_conditions_met:
                # 生成与 create_graph 函数完全一致的缓存文件名
                import hashlib
                m = hashlib.md5()
                for s in config['ORIGINAL_IGNORED_LINES']:
                    m.update(s.encode('utf-8'))
                
                # 确定配置参数
                CALCULATE_HIGH_SPEED = not data.get('disable_high_speed', False)
                CALCULATE_WALKING_WILD = data.get('enable_wild', False)
                __version__ = '130'  # 与 mtr_pathfinder.py 中的版本号保持一致
                
                # 生成缓存文件名
                filename = f'mtr_pathfinder_temp{os.sep}' + \
                    f'3{int(CALCULATE_HIGH_SPEED)}{int(CALCULATE_WALKING_WILD)}' + \
                    f'-{version1}-{version2}-{m.hexdigest()}-{__version__}.dat'
                
                # 检查缓存文件是否实际存在
                used_cache = os.path.exists(filename)

            # 创建图
            G = create_graph_v3(
                data_file,
                IGNORED_LINES,
                data.get('only_lines', []),
                not data.get('disable_high_speed', False),
                not data.get('disable_boat', False),
                data.get('enable_wild', False),
                data.get('only_lrt', False),
                data.get('avoid_stations', []),
                route_type,
                config['ORIGINAL_IGNORED_LINES'],
                INTERVAL_PATH,
                version1, version2,
                LOCAL_FILE_PATH,
                STATION_TABLE,
                config['WILD_ADDITION'],
                config['TRANSFER_ADDITION'],
                config['MAX_WILD_BLOCKS'],
                MTR_VER,
                True
            )

            # 查找最短路径
            shortest_path, shortest_distance, waiting_time, riding_time, ert = find_shortest_route_v3(
                G, data['start'], data['end'],
                data_file, STATION_TABLE, MTR_VER
            )

            # 检查寻路结果
            if shortest_path in [False, None]:
                if shortest_path is False:
                    return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
                else:
                    return jsonify({'error': '车站名称不正确，请检查输入'}), 400

            # 1. 处理gen_image=False的结果，构建前端需要的格式
            # 将车站字符串转换为车站列表
            station_names = shortest_path.split(' ->\n')
            
            # 构建符合前端期望的结果数组
            formatted_result = [
                shortest_distance,  # 总用时 (元素0)
                station_names,  # 车站列表 (元素1)
                ert,  # 路线详情 (元素2)
                riding_time,  # 乘车时间 (元素3)
                waiting_time  # 等车时间 (元素4)
            ]
            
            # 2. 继续处理图片生成的相关逻辑
            # 生成图片，直接调用save_image函数，避免重复寻路计算
            search_progress.update({
                'percentage': 85,
                'stage': '(4/4)生成图片',
                'message': '寻路计算完成，正在生成路线图片...'
            })
            
            # 调用save_image函数生成图片
            image_result = save_image_v3(
                route_type=route_type,
                every_route_time=ert,
                shortest_distance=shortest_distance,
                riding_time=riding_time,
                waiting_time=waiting_time,
                BASE_PATH=BASE_PATH,
                version1=version1,
                version2=version2,
                DETAIL=DETAIL,
                PNG_PATH=PNG_PATH,
                show=False
            )
            
            # 3. 保存图片到文件系统
            image_base64 = None
            if image_result and image_result not in [False, None]:
                if isinstance(image_result, tuple) and len(image_result) == 2:
                    # v3版save_image函数返回的图片格式：(image object, base64 str)
                    image, image_base64 = image_result
                    
                    # 保存图片到文件系统，方便前端获取
                    output_dir = 'generated_images'
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    image_path = os.path.join(output_dir, f'path_result_{timestamp}.png')
                    image.save(image_path)
                    
                    # 更新最新图片路径
                    latest_image_path = image_path
        
        # 更新进度为100%
        search_progress.update({
            'percentage': 100,
            'stage': '完成',
            'message': '路径计算完成！'
        })
        
        # 计算寻路用时
        end_time = datetime.now()
        calc_time = (end_time - start_time).total_seconds()
        
        # 获取数据版本信息
        station_version = ""
        station_version_v4 = ""
        route_version_v4 = ""
        interval_version = ""
        
        if os.path.exists(config['LOCAL_FILE_PATH_V3']):
            station_version = datetime.fromtimestamp(
                os.path.getmtime(config['LOCAL_FILE_PATH_V3'])
            ).strftime('%Y%m%d-%H%M')
        if os.path.exists(config['LOCAL_FILE_PATH_V4']):
            station_version_v4 = datetime.fromtimestamp(
                os.path.getmtime(config['LOCAL_FILE_PATH_V4'])
            ).strftime('%Y%m%d-%H%M')
        if os.path.exists(config['DEP_PATH_V4']):
            route_version_v4 = datetime.fromtimestamp(
                os.path.getmtime(config['DEP_PATH_V4'])
            ).strftime('%Y%m%d-%H%M')
        if os.path.exists(config['INTERVAL_PATH_V3']):
            interval_version = datetime.fromtimestamp(
                os.path.getmtime(config['INTERVAL_PATH_V3'])
            ).strftime('%Y%m%d-%H%M')
        
        # 初始化used_cache变量，实时寻路模式下默认为False
        used_cache = False
        
        # 生成唯一标识符
        import uuid
        image_id = str(uuid.uuid4())
        
        # 直接将生成好的图片数据存储在缓存中
        if image_base64:
            image_cache[image_id] = {
                'status': 'success',
                'data': image_base64
            }
        else:
            image_cache[image_id] = {
                'status': 'failed',
                'error': '图片生成失败'
            }
        
        # 返回调整后的结果，包含寻路模式、计算用时、数据版本和缓存标志
        return jsonify({
            'result': formatted_result, 
            'algorithm': algorithm,
            'calc_time': calc_time,
            'used_cache': used_cache,
            'data_versions': {
                'station_version': station_version,
                'station_version_v4': station_version_v4,
                'route_version_v4': route_version_v4,
                'interval_version': interval_version
            },
            'image_id': image_id  # 返回图片的唯一标识符
        })
    except Exception as e:
        import traceback
        import logging
        logging.basicConfig(level=logging.ERROR)
        logger = logging.getLogger(__name__)
        
        error_detail = traceback.format_exc()
        logger.error(f"寻路错误: {error_detail}")
        
        # 出错时重置进度
        search_progress.update({
            'percentage': 0,
            'stage': '错误',
            'message': f'寻路计算出错: {str(e)}'
        })
        
        return jsonify({'error': str(e), 'detail': error_detail}), 500

@app.route('/api/progress', methods=['GET'])
def api_progress():
    """返回当前寻路进度"""
    global search_progress
    return jsonify(search_progress)



@app.route('/api/update_progress', methods=['GET'])
def api_update_progress():
    """返回当前数据更新进度"""
    global data_update_progress
    return jsonify(data_update_progress)


@app.route('/api/search_stations', methods=['GET'])
def api_search_stations():
    # 车站模糊搜索
    query = request.args.get('q', '').lower()
    
    # 优先使用v3版本的数据文件，因为它包含更多信息
    data_file_path = config['LOCAL_FILE_PATH_V3']
    if not os.path.exists(data_file_path):
        return jsonify([])
    
    with open(data_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    stations = []
    # 统一处理，无论MTR_VER版本，数据都是列表格式
    if isinstance(data, list) and len(data) > 0:
        stations = data[0]['stations'].values()
    elif isinstance(data, dict):
        # 兼容旧格式，直接访问
        stations = data['stations'].values()
    else:
        # 无效格式，返回空列表
        return jsonify([])
    
    results = []
    for station in stations:
        if query in station['name'].lower():
            # 将车站名称中的竖线替换为空格
            formatted_name = station['name'].replace('|', ' ')
            results.append(formatted_name)
    
    return jsonify(results[:10])  # 限制返回10个结果

# 全局变量，用于存储最新生成的图片文件路径
latest_image_path = ''

# 图片缓存，用于存储生成的图片数据
image_cache = {}

@app.route('/api/get_image', methods=['GET'])
def api_get_image():
    """获取生成的结果图片"""
    try:
        import os
        from flask import Response
        
        # 获取image_id参数
        image_id = request.args.get('image_id')
        
        if image_id and image_id in image_cache:
            # 从缓存中获取图片数据
            image_info = image_cache[image_id]
            
            if image_info['status'] == 'generating':
                # 如果图片还在生成中，返回生成中的状态
                return jsonify({'status': 'generating'}), 202
            elif image_info['status'] == 'failed':
                # 如果图片生成失败，返回错误信息
                return jsonify({'status': 'failed', 'error': image_info.get('error', '图片生成失败')}), 500
            elif image_info['data']:
                # 如果图片生成成功，返回图片数据
                image_base64 = image_info['data']
                
                # 解析base64数据
                import base64
                if image_base64.startswith('data:image/png;base64,'):
                    image_base64 = image_base64.split(',')[1]
                
                # 转换为二进制数据
                image_data = base64.b64decode(image_base64)
                
                # 返回图片响应
                return Response(image_data, mimetype='image/png')
        
        # 检查是否有最新生成的图片文件
        if not latest_image_path or not os.path.exists(latest_image_path):
            # 如果没有，查找generated_images目录下的最新PNG文件
            output_dir = 'generated_images'
            if not os.path.exists(output_dir):
                return jsonify({'error': '没有找到图片文件'}), 404
            
            import glob
            png_files = glob.glob(os.path.join(output_dir, '*.png'))
            if not png_files:
                return jsonify({'error': '没有找到图片文件'}), 404
            
            # 按修改时间排序，获取最新的图片
            latest_png = max(png_files, key=os.path.getmtime)
            return send_from_directory(os.path.dirname(latest_png), os.path.basename(latest_png))
        
        # 返回最新生成的图片文件
        return send_from_directory(os.path.dirname(latest_image_path), os.path.basename(latest_image_path))
    except Exception as e:
        import traceback
        print(f"获取图片错误: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear_cache', methods=['POST'])
def api_clear_cache():
    """清除寻路缓存"""
    try:
        import os
        import shutil
        
        # 清除mtr_pathfinder_temp文件夹中的所有内容
        temp_dir = 'mtr_pathfinder_temp'
        deleted_files = []
        
        if os.path.exists(temp_dir):
            # 遍历文件夹中的所有文件和子文件夹
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    deleted_files.append(file_path)
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    shutil.rmtree(dir_path)
                    deleted_files.append(dir_path)
        
        return jsonify({'success': True, 'deleted_files': deleted_files})
    except Exception as e:
        import traceback
        print(f"清除寻路缓存错误: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear_images', methods=['POST'])
def api_clear_images():
    """清除寻路结果图片"""
    try:
        import os
        import glob
        
        # 清除generated_images目录下的所有PNG文件
        output_dir = 'generated_images'
        if os.path.exists(output_dir):
            png_files = glob.glob(os.path.join(output_dir, '*.png'))
            for png_file in png_files:
                if os.path.exists(png_file):
                    os.remove(png_file)
        
        # 重置最新图片路径
        global latest_image_path
        latest_image_path = ''
        
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        print(f"清除结果图片错误: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_config', methods=['POST'])
def api_update_config():
    # 更新配置
    global config
    data = request.json
    
    if 'link' in data:
        config['LINK'] = data['link']
        update_file_paths()
    
    if 'mtr_ver' in data:
        config['MTR_VER'] = int(data['mtr_ver'])
    
    if 'max_wild_blocks' in data:
        config['MAX_WILD_BLOCKS'] = int(data['max_wild_blocks'])
    
    if 'transfer_addition' in data:
        config['TRANSFER_ADDITION'] = data['transfer_addition']
    
    if 'wild_addition' in data:
        config['WILD_ADDITION'] = data['wild_addition']
    
    if 'station_table' in data:
        config['STATION_TABLE'] = data['station_table']
    
    if 'original_ignored_lines' in data:
        config['ORIGINAL_IGNORED_LINES'] = data['original_ignored_lines']
    
    if 'umami_script_url' in data:
        config['UMAMI_SCRIPT_URL'] = data['umami_script_url']
    
    if 'umami_website_id' in data:
        config['UMAMI_WEBSITE_ID'] = data['umami_website_id']

    save_config(config)
    return jsonify({'success': True})

@app.route('/api/update_data', methods=['POST'])
def api_update_data():
    # 更新数据
    if not config['LINK']:
        return jsonify({'error': '未设置地图链接'}), 400
    
    # 重置数据更新进度
    global data_update_progress
    data_update_progress = {
        'percentage': 0,
        'stage': '准备中...',
        'message': '正在准备数据更新...'
    }
    
    try:
        import sys
        from io import StringIO
        
        # 保存原始stdin
        original_stdin = sys.stdin
        # 创建模拟输入流，自动返回'y'
        mock_stdin = StringIO('y\n' * 20)  # 提供足够的'y'响应
        sys.stdin = mock_stdin
        
        try:
            # 1. 生成v3版程序所需的数据 - 阶段1
            data_update_progress.update({
                'percentage': 0,
                'stage': '生成V3车站数据',
                'message': '正在生成V3版车站数据...'
            })
            
            # 调用v3版的fetch_data函数
            fetch_data_v3(
                config['LINK'],
                config['LOCAL_FILE_PATH_V3'],
                config['MTR_VER']
            )
            
            # 阶段1完成，进入阶段2
            data_update_progress.update({
                'percentage': 25,
                'stage': '生成V3间隔数据',
                'message': '正在生成V3版间隔数据...'
            })
            
            # 生成v3版的间隔数据文件
            gen_route_interval_v3(
                config['LOCAL_FILE_PATH_V3'],
                config['INTERVAL_PATH_V3'],
                config['LINK'],
                config['MTR_VER']
            )
            
            # 阶段2完成，进入阶段3
            data_update_progress.update({
                'percentage': 50,
                'stage': '生成V4车站数据',
                'message': '正在生成V4版车站数据...'
            })
            
            # 2. 生成v4版程序所需的数据
            # 调用v4版的fetch_data函数
            from mtr_pathfinder_lib.mtr_pathfinder_v4 import fetch_data as fetch_data_v4
            fetch_data_v4(
                config['LINK'],
                config['LOCAL_FILE_PATH_V4'],
                config['MAX_WILD_BLOCKS']
            )
            
            # 阶段3完成，进入阶段4
            data_update_progress.update({
                'percentage': 75,
                'stage': '生成V4发车数据',
                'message': '正在生成V4版发车数据...'
            })
            
            # 生成v4版的发车数据
            gen_departure_v4(
                config['LINK'],
                config['DEP_PATH_V4']
            )
            
            # 数据更新完成
            data_update_progress.update({
                'percentage': 100,
                'stage': '完成',
                'message': '数据更新完成！'
            })
        finally:
            # 恢复原始stdin
            sys.stdin = original_stdin
        
        return jsonify({'success': True})
    except Exception as e:
        # 更新失败时设置错误状态
        data_update_progress.update({
            'percentage': 0,
            'stage': '错误',
            'message': f'更新失败: {str(e)}'
        })
        return jsonify({'error': str(e)}), 500
def check_and_update_data():
    """检查数据文件是否存在，如果不存在则自动更新数据"""
    import os
    import sys
    from io import StringIO
    
    print("检查数据文件是否存在...")
    
    # 检查必要的数据文件是否存在
    required_files = [
        config['LOCAL_FILE_PATH_V3'],
        config['INTERVAL_PATH_V3'],
        config['LOCAL_FILE_PATH_V4'],
        config['DEP_PATH_V4']
    ]
    
    # 检查是否有任何文件不存在
    files_exist = all(os.path.exists(file_path) for file_path in required_files)
    
    if files_exist:
        print("所有数据文件已存在，无需更新")
        return True
    
    print("检测到缺失的数据文件，正在自动更新...")
    
    try:
        # 保存原始stdin
        original_stdin = sys.stdin
        # 创建模拟输入流，自动返回'y'
        mock_stdin = StringIO('y\n' * 20)  # 提供足够的'y'响应
        sys.stdin = mock_stdin
        
        # 1. 生成v3版程序所需的数据
        print("正在生成V3版车站数据...")
        fetch_data_v3(
            config['LINK'],
            config['LOCAL_FILE_PATH_V3'],
            config['MTR_VER']
        )
        
        print("正在生成V3版间隔数据...")
        gen_route_interval_v3(
            config['LOCAL_FILE_PATH_V3'],
            config['INTERVAL_PATH_V3'],
            config['LINK'],
            config['MTR_VER']
        )
        
        # 2. 生成v4版程序所需的数据
        print("正在生成V4版车站数据...")
        from mtr_pathfinder_lib.mtr_pathfinder_v4 import fetch_data as fetch_data_v4
        fetch_data_v4(
            config['LINK'],
            config['LOCAL_FILE_PATH_V4'],
            config['MAX_WILD_BLOCKS']
        )
        
        print("正在生成V4版发车数据...")
        gen_departure_v4(
            config['LINK'],
            config['DEP_PATH_V4']
        )
        
        print("数据更新完成！")
        return True
    except Exception as e:
        print(f"数据更新失败: {str(e)}")
        return False
    finally:
        # 恢复原始stdin
        sys.stdin = original_stdin


if __name__ == '__main__':
    # 检查并更新数据文件
    check_and_update_data()
    
    app.run(debug=True, port=5000)
