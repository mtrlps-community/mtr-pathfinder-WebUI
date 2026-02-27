from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect
import os
import json
import hashlib
import re
import time
from datetime import datetime

from mtr_pathfinder_lib.mtr_pathfinder import (
    main as mtr_main_v3,
    save_image as save_image_v3,
    fetch_data as fetch_data_v3,
    gen_route_interval as gen_route_interval_v3,
    RouteType as RouteTypeV3
)

from mtr_pathfinder_lib.mtr_pathfinder_v4 import (
    main as mtr_main_v4,
    save_image as save_image_v4,
    fetch_data as fetch_data_v4,
    gen_departure as gen_departure_v4
)

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# 全局进度跟踪变量
search_progress = {
    'percentage': 0,
    'stage': '初始化',
    'message': '传入寻路参数...'
}

# 数据更新进度跟踪变量
data_update_progress = {
    'percentage': 0,
    'stage': '准备中...',
    'message': '正在准备数据更新...'
}

# 寻路次数统计
route_search_count = 0

# 数据检查标志位，确保只运行一次
data_checked = False

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
        config['LOCAL_FILE_PATH_V3'] = f'mtr-original-data-{link_hash}-mtr{config["MTR_VER"]}-v3.json'
        config['LOCAL_FILE_PATH_V4'] = f'mtr-original-data-{link_hash}-mtr4-v4.json'
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

# 专门处理favicon.ico请求
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('.', 'favicon.ico', mimetype='image/x-icon')

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
    
    # 数据字段过滤：只返回前端页面需要的字段
    filtered_stations = []
    for station in stations_data:
        if isinstance(station, dict):
            filtered_station = {
                'id': station.get('id', 'N/A'),
                'name': station.get('name', 'N/A'),
                'line_count': station.get('line_count', 0),
                'branch_count': station.get('branch_count', 0)
            }
            filtered_stations.append(filtered_station)
    
    return render_template('stations.html', stations=filtered_stations)

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
    
    # 数据字段过滤：只返回前端页面需要的字段
    filtered_routes = []
    for route in routes_data:
        if isinstance(route, dict):
            # 只计算车站数量，不传递完整的车站列表
            stations = route.get('stations', [])
            station_count = len(stations)
            
            filtered_route = {
                'id': route.get('id', 'N/A'),
                'name': route.get('name', 'N/A'),
                'route_number': route.get('route_number', ''),
                'number': route.get('number', ''),
                'station_count': station_count
            }
            filtered_routes.append(filtered_route)
    
    return render_template('routes.html', routes=filtered_routes, interval_data=interval_data, line_count=line_count, branch_count=branch_count)

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
        'stage': '初始化',
        'message': '传入寻路参数...'
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
    
    # 初始化变量来存储实际使用的出发时间
    actual_departure_time = None
    
    # 更新进度
    search_progress.update({
        'percentage': 5,
        'stage': '数据验证',
        'message': '检查数据文件是否存在...'
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
        'percentage': 10,
        'stage': '算法判定',
        'message': '根据传入参数选择相应的寻路算法...'
    })
    
    try:
        # 根据算法选择不同的寻路实现
        if algorithm == 'real':
            # 使用v4版程序的寻路功能
            
            # 更新进度
            search_progress.update({
                'percentage': 20,
                'stage': '(1/8)寻路计算-V4',
                'message': '处理出发时间...'
            })
            
            # 处理出发时间参数
            dep_time_seconds = data.get('dep_time')
            client_time = data.get('client_time')
            
            # 如果dep_time_seconds为None且提供了客户端时间，使用客户端时间+10秒作为出发时间
            if dep_time_seconds is None and client_time is not None:
                dep_time_seconds = (client_time + 10) % 86400
            
            # 保存实际使用的出发时间
            actual_departure_time = dep_time_seconds
            
            search_progress.update({
                'percentage': 25,
                'stage': '(2/8)寻路计算-V4',
                'message': '调用寻路算法...'
            })

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

            search_progress.update({
                'percentage': 45,
                'stage': '(3/8)寻路计算-V4',
                'message': '检查寻路结果...'
            })

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
            
            search_progress.update({
                'percentage': 55,
                'stage': '(4/8)寻路计算-V4',
                'message': '提取路线详情列表...'
            })

            # 提取路线详情列表
            every_route_time = result_gen_image_false
            
            search_progress.update({
                'percentage': 60,
                'stage': '(5/8)寻路计算-V4',
                'message': '构建车站列表...'
            })

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
            
            search_progress.update({
                'percentage': 70,
                'stage': '(6/8)寻路计算-V4',
                'message': '计算总用时、乘车时间和等车时间...'
            })

            # 计算总用时、乘车时间和等车时间
            if every_route_time:
                total_time = every_route_time[-1][6] - every_route_time[0][5]  # 总用时 = 最后一站到站时间 - 第一站发车时间
                riding_time = sum(leg[6] - leg[5] for leg in every_route_time)  # 乘车时间 = 各段乘车时间之和
                waiting_time = total_time - riding_time  # 等车时间 = 总用时 - 乘车时间
            else:
                total_time = 0
                riding_time = 0
                waiting_time = 0
            
            search_progress.update({
                'percentage': 80,
                'stage': '(7/8)寻路计算-V4',
                'message': '构建用于前端展示的结果数组...'
            })

            # 构建用于前端展示的结果数组
            formatted_result = [
                total_time,  # 总用时 (元素0)
                station_names,  # 车站列表 (元素1)
                every_route_time,  # 路线详情 (元素2) - 使用正确的路线详情列表
                riding_time,  # 乘车时间 (元素3)
                waiting_time  # 等车时间 (元素4)
            ]
            
            search_progress.update({
                'percentage': 90,
                'stage': '(8/8)寻路计算-V4',
                'message': '准备图片生成所需数据...'
            })
            
            # 3. 将寻路结果和生成图片所需数据存储在缓存中，供后续图片生成使用
            # 生成唯一标识符
            import uuid
            image_id = str(uuid.uuid4())
            
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
            
            # 存储寻路结果和生成图片所需数据
            image_cache[image_id] = {
                'status': 'ready',
                'algorithm': algorithm,
                'data': {
                    'every_route_time': every_route_time,
                    'version1': version1,
                    'version2': version2,
                    'dep_time_seconds': dep_time_seconds
                },
                'image_path': None,
                'image_base64': None
            }
            
            # 初始化缓存使用状态
            used_cache = False
            
        else:
            # 使用v3版程序的寻路功能，直接调用main函数
            
            # 更新进度
            search_progress.update({
                'percentage': 15,
                'stage': '寻路计算-V3',
                'message': '准备所需参数...'
            })
            
            # 构建调用main函数所需的参数
            LINK = config['LINK']
            LOCAL_FILE_PATH = config['LOCAL_FILE_PATH_V3']
            INTERVAL_PATH = config['INTERVAL_PATH_V3']
            MTR_VER = config['MTR_VER']
            IN_THEORY = algorithm == 'theory'
            DETAIL = data.get('detail', True)
            
            # 加载数据文件，用于处理ert数据和获取版本信息
            if os.path.exists(LOCAL_FILE_PATH):
                with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
                    data_file = json.load(f)
            else:
                return jsonify({'error': '车站数据不存在，请先更新数据'}), 400
            
            # 获取版本信息
            version1 = ''
            version2 = ''
            if os.path.exists(LOCAL_FILE_PATH):
                version1 = time.strftime('%Y%m%d-%H%M',
                                        time.gmtime(os.path.getmtime(LOCAL_FILE_PATH)))
            if os.path.exists(INTERVAL_PATH):
                version2 = time.strftime('%Y%m%d-%H%M',
                                        time.gmtime(os.path.getmtime(INTERVAL_PATH)))
            
            # 设置寻路类型
            route_type = RouteTypeV3.IN_THEORY if IN_THEORY else RouteTypeV3.WAITING
            
            # 生成与 create_graph 函数完全一致的缓存文件名
            import hashlib
            m = hashlib.md5()
            # 注意：缓存文件名必须考虑原始禁路线，因为原始禁路线不同，生成的图也不同
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
            
            # 在调用寻路函数之前，检查缓存文件是否已经存在
            cache_file_existed_before = os.path.exists(filename)
            
            search_progress.update({
                'percentage': 20,
                'stage': '寻路计算-V3',
                'message': '调用寻路算法...'
            })

            # 调用mtr_pathfinder.py的main函数，gen_image=False
            result_gen_image_false = mtr_main_v3(
                station1=data['start'],
                station2=data['end'],
                LINK=LINK,
                LOCAL_FILE_PATH=LOCAL_FILE_PATH,
                INTERVAL_PATH=INTERVAL_PATH,
                BASE_PATH=BASE_PATH,
                PNG_PATH=PNG_PATH,
                MAX_WILD_BLOCKS=config['MAX_WILD_BLOCKS'],
                TRANSFER_ADDITION=config['TRANSFER_ADDITION'],
                WILD_ADDITION=config['WILD_ADDITION'],
                STATION_TABLE=config['STATION_TABLE'],
                ORIGINAL_IGNORED_LINES=config['ORIGINAL_IGNORED_LINES'],
                UPDATE_DATA=False,
                GEN_ROUTE_INTERVAL=False,
                IGNORED_LINES=data.get('ignored_lines', []),
                ONLY_LINES=data.get('only_lines', []),
                AVOID_STATIONS=data.get('avoid_stations', []),
                CALCULATE_HIGH_SPEED=not data.get('disable_high_speed', False),
                CALCULATE_BOAT=not data.get('disable_boat', False),
                CALCULATE_WALKING_WILD=data.get('enable_wild', False),
                ONLY_LRT=data.get('only_lrt', False),
                IN_THEORY=IN_THEORY,
                DETAIL=DETAIL,
                MTR_VER=MTR_VER,
                gen_image=False
            )
            
            search_progress.update({
                'percentage': 30,
                'stage': '寻路计算-V3',
                'message': '检查寻路结果...'
            })

            # 检查寻路结果
            if result_gen_image_false in [False, None]:
                if result_gen_image_false is False:
                    return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
                else:
                    return jsonify({'error': '车站名称不正确，请检查输入'}), 400
            
            search_progress.update({
                'percentage': 35,
                'stage': '寻路计算-V3',
                'message': '提取寻路结果...'
            })

            # 提取main函数返回的数据
            ert, shortest_distance = result_gen_image_false
            
            search_progress.update({
                'percentage': 40,
                'stage': '寻路计算-V3',
                'message': '检查寻路结果是否有效...'
            })

            # 检查寻路结果是否有效
            if ert in [False, None]:
                if ert is False:
                    return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
                else:
                    return jsonify({'error': '车站名称不正确，请检查输入'}), 400
            
            search_progress.update({
                'percentage': 55,
                'stage': '寻路计算-V3',
                'message': '设置寻路类型...'
            })
            
            search_progress.update({
                'percentage': 60,
                'stage': '寻路计算-V3',
                'message': '检查缓存使用状态...'
            })
            
            # 检查是否使用了缓存
            # 只检查用户是否额外添加了禁路线，不考虑全局禁路线
            user_ignored_lines = data.get('ignored_lines', [])
            global_ignored_lines = config['ORIGINAL_IGNORED_LINES']
            
            # 计算用户真正额外添加的禁路线：用户传入的禁路线减去全局禁路线
            extra_ignored_lines = [line for line in user_ignored_lines if line not in global_ignored_lines]
            
            # 只有当用户没有额外添加禁路线时，才满足缓存条件
            ignored_lines_ok = len(extra_ignored_lines) == 0
            disable_boat_ok = not data.get('disable_boat', False)
            only_lrt_ok = not data.get('only_lrt', False)
            only_lines_ok = len(data.get('only_lines', [])) == 0
            avoid_stations_ok = len(data.get('avoid_stations', [])) == 0
            route_type_ok = route_type == RouteTypeV3.WAITING
            
            cache_conditions_met = (ignored_lines_ok and \
                                  disable_boat_ok and \
                                  only_lrt_ok and \
                                  only_lines_ok and \
                                  avoid_stations_ok and \
                                  route_type_ok)
               
            # 正确的缓存逻辑：
            # 1. 只有当缓存条件满足，并且
            # 2. 调用寻路函数之前缓存文件已经存在，并且
            # 3. 调用寻路函数之后缓存文件仍然存在
            # 才认为使用了缓存
            # 这确保了只有当程序真正从缓存中读取数据时，才会被判定为使用缓存
            used_cache = cache_conditions_met and cache_file_existed_before
            
            # 更新进度
            search_progress.update({
                'percentage': 70,
                'stage': '寻路计算-V3',
                'message': '处理寻路结果...'
            })
            
            # 重新获取完整的寻路结果，包括shortest_path、waiting_time和riding_time
            # 这里需要重新调用find_shortest_route，因为main函数(gen_image=False)没有返回这些信息
            # 但我们可以从ert中提取一些信息
            
            # 处理ert数据，将route_id转换为线路名称，以便前端使用禁路线功能
            processed_ert = []
            for route_segment in ert:
                # 复制原始路线段数据
                processed_segment = route_segment.copy()
                
                # 获取route_id和线路名称
                route_info = route_segment[10]  # route_info是第11个元素(索引10)
                route_id = route_info[0] if route_info else None  # route_id是列表中的第一个元素
                route_name = route_segment[3]  # 当前的线路名称
                
                # 如果有route_id，尝试获取更完整的线路名称
                if route_id and data_file:
                    for route in data_file[0]['routes']:
                        if route['id'] == route_id:
                            # 找到匹配的线路，使用完整的线路名称
                            original_route_name = route['name']
                            # 处理线路名称：移除交路编号(||后的内容)，将|替换为空格
                            # 与原程序保持一致：添加线路编号 + 处理后的线路名称
                            route_name_part = original_route_name.split('||')[0].strip()
                            full_route_name = (route.get('number', '') + ' ' + route_name_part).strip()
                            full_route_name = full_route_name.replace('|', ' ')
                            # 更新路线段中的线路名称
                            processed_segment[3] = full_route_name
                            break
                
                processed_ert.append(processed_segment)
            
            # 处理"或"路线：将出发站和到达站相同的线路分组
            route_groups = []
            if processed_ert:
                current_group = [processed_ert[0]]
                current_start = processed_ert[0][0]
                current_end = processed_ert[0][1]
                
                for segment in processed_ert[1:]:
                    if segment[0] == current_start and segment[1] == current_end:
                        # 同一组"或"路线
                        current_group.append(segment)
                    else:
                        # 新的路线段
                        route_groups.append(current_group)
                        current_group = [segment]
                        current_start = segment[0]
                        current_end = segment[1]
                # 添加最后一组
                route_groups.append(current_group)
            
            # 计算riding_time和waiting_time
            # 注意：ert中的时间字段是：
            # segment[5]: duration (乘车时间)
            # segment[6]: waiting (等待时间)
            # 对于"或"路线，我们只计算一次等待时间
            
            # 从每个路线组中选择第一个线路来计算等待时间
            unique_segments = []
            for group in route_groups:
                unique_segments.append(group[0])
            
            # 计算总等待时间：只计算每个路线组的等待时间（避免重复计算"或"路线的等待时间）
            waiting_time = sum(segment[6] for segment in unique_segments) if unique_segments else 0
            
            # 计算总乘车时间：总用时 - 等车时间（符合用户期望的计算方式）
            riding_time = shortest_distance - waiting_time if shortest_distance >= waiting_time else 0
            
            # 总用时 = 最短路线的总时间（已经在shortest_distance中返回）
            
            # 构建车站列表
            # 对于"或"路线，我们只显示一次
            station_names = []
            if processed_ert:
                # 添加起点站
                station_names.append(processed_ert[0][0])
                # 添加线路和站点
                for group in route_groups:
                    # 只显示每组"或"路线的第一个线路
                    segment = group[0]
                    station_names.append(segment[3])  # 线路名称
                    station_names.append(segment[1])  # 终点站

            search_progress.update({
                'percentage': 80,
                'stage': '寻路计算-V3',
                'message': '构建用于前端展示的结果数组...'
            })            

            # 构建用于前端展示的结果数组
            formatted_result = [
                shortest_distance,  # 总用时 (元素0) - 来自main函数返回的shortest_distance
                station_names,  # 车站列表 (元素1) - 只显示每组"或"路线的第一个线路
                processed_ert,  # 处理后的路线详情 (元素2) - 包含所有"或"路线
                riding_time,  # 乘车时间 (元素3) - 所有线路的乘车时间之和
                waiting_time  # 等车时间 (元素4) - 每个路线组的等待时间之和
            ]

            # 更新进度
            search_progress.update({
                'percentage': 90,
                'stage': '寻路计算-V3',
                'message': '准备图片生成所需数据...'
            })

            # 3. 将寻路结果和生成图片所需数据存储在缓存中，供后续图片生成使用
            # 生成唯一标识符
            import uuid
            image_id = str(uuid.uuid4())
            
            # 存储寻路结果和生成图片所需数据
            # 注意：图片生成需要所有线路信息，所以使用processed_ert
            image_cache[image_id] = {
                'status': 'ready',
                'algorithm': algorithm,
                'data': {
                    'every_route_time': processed_ert,
                    'version1': version1,
                    'version2': version2,
                    'route_type': route_type,
                    'shortest_distance': shortest_distance,
                    'riding_time': riding_time,
                    'waiting_time': waiting_time,
                    'DETAIL': DETAIL
                },
                'image_path': None,
                'image_base64': None
            }
        
        # 更新进度为100%
        search_progress.update({
            'percentage': 100,
            'stage': '完成',
            'message': '路径计算完成'
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
        
        # 图片将由/api/generate_image路由生成，这里只需要将状态设置为ready
        image_cache[image_id]['status'] = 'ready'
        
        # 构建响应数据
        response_data = {
            'result': formatted_result, 
            'algorithm': algorithm,
            'calc_time': calc_time,
            'used_cache': used_cache if algorithm != 'real' else False,  # 只有实时寻路模式下重置为False
            'data_versions': {
                'station_version': station_version,
                'station_version_v4': station_version_v4,
                'route_version_v4': route_version_v4,
                'interval_version': interval_version
            },
            'image_id': image_id  # 返回图片的唯一标识符
        }
        
        # 仅实时模式返回实际使用的出发时间
        if algorithm == 'real' and actual_departure_time is not None:
            response_data['departure_time'] = actual_departure_time
        
        # 返回调整后的结果，包含寻路模式、计算用时、数据版本和缓存标志
        return jsonify(response_data)
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

@app.route('/api/generate_image', methods=['POST'])
def api_generate_image():
    """生成结果图片"""
    global latest_image_path
    try:
        # 获取请求数据
        data = request.json
        image_id = data.get('image_id')
        
        # 验证必要参数
        if not image_id:
            return jsonify({'error': '缺少必要参数image_id'}), 400
        
        # 检查缓存中是否有该图片的数据
        if image_id not in image_cache:
            return jsonify({'error': '找不到图片数据'}), 404
        
        # 从缓存中获取图片数据
        image_info = image_cache[image_id]
        
        # 如果图片已经生成完成，直接返回成功
        if image_info['status'] in ['success', 'failed']:
            return jsonify({'status': image_info['status'], 'image_id': image_id})
        
        # 确保输出目录存在
        import os
        output_dir = 'generated_images'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 生成唯一的图片文件名
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_path = os.path.join(output_dir, f'path_result_{timestamp}.png')
        
        # 标记图片为生成中
        image_cache[image_id]['status'] = 'generating'
        
        # 根据算法选择不同的图片生成实现
        algorithm = image_info['algorithm']
        image_data = image_info['data']
        generated_image_base64 = None
        
        if algorithm == 'real':
            # 使用v4版程序生成图片
            from mtr_pathfinder_lib.mtr_pathfinder_v4 import RouteType as RouteTypeV4
            image_result = save_image_v4(
                route_type=RouteTypeV4.REAL_TIME,
                every_route_time=image_data['every_route_time'],
                BASE_PATH=BASE_PATH,
                version1=image_data['version1'],
                version2=image_data['version2'],
                PNG_PATH=PNG_PATH,
                departure_time=image_data['dep_time_seconds'],
                show=False
            )
        else:
            # 使用v3版程序生成图片
            image_result = save_image_v3(
                route_type=image_data['route_type'],
                every_route_time=image_data['every_route_time'],
                shortest_distance=image_data['shortest_distance'],
                riding_time=image_data['riding_time'],
                waiting_time=image_data['waiting_time'],
                BASE_PATH=BASE_PATH,
                version1=image_data['version1'],
                version2=image_data['version2'],
                DETAIL=image_data['DETAIL'],
                PNG_PATH=PNG_PATH,
                show=False
            )
        
        # 处理图片生成结果
        if image_result and image_result not in [False, None]:
            if isinstance(image_result, tuple) and len(image_result) == 2:
                # v3版和v4版save_image函数返回的图片格式：(image object, base64 str)
                image, generated_image_base64 = image_result
                image.save(image_path)
                
                # 更新最新图片路径
                latest_image_path = image_path
                
                # 更新缓存中的图片信息
                image_cache[image_id]['status'] = 'success'
                image_cache[image_id]['image_path'] = image_path
                image_cache[image_id]['image_base64'] = generated_image_base64
                
                return jsonify({'status': 'success', 'image_id': image_id})
            else:
                # 图片生成失败
                image_cache[image_id]['status'] = 'failed'
                image_cache[image_id]['error'] = '图片生成失败，格式不正确'
                return jsonify({'status': 'failed', 'error': '图片生成失败，格式不正确', 'image_id': image_id}), 500
        else:
            # 图片生成失败
            image_cache[image_id]['status'] = 'failed'
            image_cache[image_id]['error'] = '图片生成失败'
            return jsonify({'status': 'failed', 'error': '图片生成失败', 'image_id': image_id}), 500
    except Exception as e:
        import traceback
        print(f"生成图片错误: {traceback.format_exc()}")
        # 更新缓存中的图片信息
        if image_id in image_cache:
            image_cache[image_id]['status'] = 'failed'
            image_cache[image_id]['error'] = f'图片生成失败: {str(e)}'
        return jsonify({'error': str(e)}), 500

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
            elif image_info['image_base64']:
                # 如果图片生成成功，返回图片数据
                image_base64 = image_info['image_base64']
                
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
    
    if 'max_hour' in data:
        config['MAX_HOUR'] = int(data['max_hour'])
    
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

def _update_data():
    """内部函数：执行数据更新逻辑，被api_update_data和check_and_update_data调用"""
    import sys
    from io import StringIO
    
    # 保存原始stdin
    original_stdin = sys.stdin
    # 创建模拟输入流，自动返回'y'
    mock_stdin = StringIO('y\n' * 20)  # 提供足够的'y'响应
    sys.stdin = mock_stdin
    
    try:
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
        # 调用内部数据更新函数
        success = _update_data()
        
        if success:
            # 数据更新完成
            data_update_progress.update({
                'percentage': 100,
                'stage': '完成',
                'message': '数据更新完成！'
            })
            return jsonify({'success': True})
        else:
            # 更新失败时设置错误状态
            data_update_progress.update({
                'percentage': 0,
                'stage': '错误',
                'message': '数据更新失败'
            })
            return jsonify({'error': '数据更新失败'}), 500
    except Exception as e:
        # 更新失败时设置错误状态
        data_update_progress.update({
            'percentage': 0,
            'stage': '错误',
            'message': f'更新失败: {str(e)}'
        })
        return jsonify({'error': str(e)}), 500

@app.before_request
def check_and_update_data():
    """检查数据文件是否存在，如果不存在则自动更新数据，确保只运行一次"""
    global data_checked
    
    # 如果已经检查过数据，直接返回
    if data_checked:
        return
    
    # 设置标志位为True，确保只运行一次
    data_checked = True
    
    import os
    
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
        return
    
    print("检测到缺失的数据文件，正在自动更新...")
    
    # 调用内部数据更新函数
    _update_data()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
