from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
import os
import json
import hashlib
from datetime import datetime

from mtr_pathfinder_lib.mtr_pathfinder import (
    fetch_data as fetch_data_v3,
    gen_route_interval as gen_route_interval_v3,
    create_graph as create_graph_v3,
    find_shortest_route as find_shortest_route_v3,
    RouteType as RouteTypeV3,
)

from mtr_pathfinder_lib.mtr_pathfinder_v4 import (
    main as mtr_main_v4,
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/stations')
def stations():
    # 读取车站数据
    stations_data = []
    # 优先使用v3版本的数据文件，因为它包含更多信息
    data_file_path = config['LOCAL_FILE_PATH_V3']
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 统一处理，无论MTR_VER版本，都使用列表格式
            if isinstance(data, list) and len(data) > 0:
                stations_data = list(data[0]['stations'].values())
            elif isinstance(data, dict):
                # 如果是字典格式，将其转换为列表格式
                stations_data = list(data['stations'].values())
    
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
                    # 将线路名称中的竖杠替换为空格
                    if 'name' in route:
                        route['name'] = route['name'].replace('|', ' ')
                    
                    # 处理站点列表，添加站点名称和运行时间
                    processed_stations = []
                    durations = route.get('durations', [])
                    
                    for i, route_station in enumerate(route['stations']):
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
                            
                            # 添加运行时间信息：durations[i]是从当前站点到下一个站点的运行时间
                            if i < len(durations):
                                # 将秒转换为mm:ss格式
                                seconds = durations[i]
                                minutes = seconds // 60
                                remaining_seconds = seconds % 60
                                processed_station['travel_time'] = f"{minutes:02d}:{remaining_seconds:02d}"
                            
                            processed_stations.append(processed_station)
                    # 更新线路的站点列表
                    route['stations'] = processed_stations
                    
                    station_routes.append(route)
                    break
    
    return render_template('station_detail.html', station=station_data, routes=station_routes, station_id=station_id)

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
    
    # 将线路名称中的竖杠替换为空格
    for route in routes_data:
        if isinstance(route, dict) and 'name' in route:
            route['name'] = route['name'].replace('|', ' ')
    
    return render_template('routes.html', routes=routes_data)



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
                                   error='密码错误')
    
    # GET请求，检查是否已登录
    if not session.get('admin_logged_in'):
        return render_template('admin.html', error=None)
    
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
                           interval_version=interval_version)

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
            
            # 调用v4版程序的main函数，获取路线详情
            result = mtr_main_v4(
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
                AVOID_STATIONS=data.get('avoid_stations', []),
                CALCULATE_HIGH_SPEED=not data.get('disable_high_speed', False),
                CALCULATE_BOAT=not data.get('disable_boat', False),
                CALCULATE_WALKING_WILD=data.get('enable_wild', False),
                ONLY_LRT=data.get('only_lrt', False),
                DETAIL=False,
                MAX_HOUR=config['MAX_HOUR'],
                gen_image=False,
                show=False
            )
            
            # 更新进度
            search_progress.update({
                'percentage': 75,
                'stage': '(4/4)结果处理',
                'message': '寻路计算完成，正在处理结果...'
            })
            
            # 检查寻路结果
            if result == []:
                # 找不到路线
                return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
            elif result is False:
                # 找不到路线
                return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
            elif result is None:
                # 车站名称不正确
                return jsonify({'error': '车站名称不正确，请检查输入'}), 400
            
            # 处理v4版程序的返回结果
            # v4版返回的是路线详情列表，需要转换为前端期望的格式
            
            # 构建车站列表
            station_names = []
            for leg in result:
                if len(leg) >= 2:
                    # leg格式：(起点站, 终点站, 颜色, 路线名, 终点站信息, 发车时间, 到站时间, 交通类型)
                    start_station, end_station = leg[0], leg[1]
                    route_name = leg[3]
                    
                    if not station_names:
                        station_names.append(start_station)
                    station_names.append(route_name)
                    station_names.append(end_station)
            
            # 计算总用时、乘车时间和等车时间
            # v4版返回的是实际的发车和到站时间，需要计算差值
            if result:
                total_time = result[-1][6] - result[0][5]  # 总用时 = 最后一站到站时间 - 第一站发车时间
                riding_time = sum(leg[6] - leg[5] for leg in result)  # 乘车时间 = 各段乘车时间之和
                waiting_time = total_time - riding_time  # 等车时间 = 总用时 - 乘车时间
            else:
                total_time = 0
                riding_time = 0
                waiting_time = 0
            
            # 构建符合前端期望的结果数组
            formatted_result = [
                total_time,  # 总用时 (元素0)
                station_names,  # 车站列表 (元素1)
                result,  # 路线详情 (元素2)
                riding_time,  # 乘车时间 (元素3)
                waiting_time  # 等车时间 (元素4)
            ]
        else:
            # 使用v3版程序的寻路功能
            
            # 更新进度
            search_progress.update({
                'percentage': 20,
                'stage': '(1/5)数据加载',
                'message': '正在加载车站数据...'
            })
            
            # 读取数据文件
            with open(config['LOCAL_FILE_PATH'], encoding='utf-8') as f:
                data_file = json.load(f)
            
            # 更新进度
            search_progress.update({
                'percentage': 40,
                'stage': '(2/5)参数准备',
                'message': '正在准备寻路参数...'
            })
            
            IN_THEORY = algorithm == 'theory'
            
            # 合并忽略线路
            ignored_lines = data.get('ignored_lines', []) + config['ORIGINAL_IGNORED_LINES']
            
            # 转换车站表格式
            station_table = {x.lower(): y.lower() for x, y in config['STATION_TABLE'].items()}
            
            # 更新进度
            search_progress.update({
                'percentage': 60,
                'stage': '(3/5)图构建',
                'message': '正在构建站点连接图...'
            })
            
            # 创建图
            G, used_cache = create_graph_v3(
                data_file,
                ignored_lines,
                not data.get('disable_high_speed', False),
                not data.get('disable_boat', False),
                data.get('enable_wild', False),
                data.get('only_lrt', False),
                data.get('avoid_stations', []),
                RouteTypeV3.IN_THEORY if IN_THEORY else RouteTypeV3.WAITING,
                config['ORIGINAL_IGNORED_LINES'],
                config['INTERVAL_PATH'],
                '', '',
                config['LOCAL_FILE_PATH'],
                station_table,
                config['WILD_ADDITION'],
                config['TRANSFER_ADDITION'],
                config['MAX_WILD_BLOCKS'],
                config['MTR_VER'],
                True
            )
            
            # 更新进度
            search_progress.update({
                'percentage': 80,
                'stage': '(4/5)寻路计算',
                'message': '正在使用最短路径算法计算最优路线...'
            })
            
            # 调用寻路函数获取完整结果
            result = find_shortest_route_v3(
                G, data['start'], data['end'],
                data_file, station_table,
                config['MTR_VER']
            )
            
            # 更新进度
            search_progress.update({
                'percentage': 90,
                'stage': '(5/5)结果处理',
                'message': '寻路计算完成，正在处理结果...'
            })
            
            # 检查寻路结果
            station_str, shortest_distance, waiting_time, riding_time, every_route_time = result
            
            if all(item is None for item in result):
                # 所有结果都是None，说明车站名称不正确
                return jsonify({'error': '车站名称不正确，请检查输入'}), 400
            elif station_str is False:
                # 找不到路线
                return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
            else:
                # 将车站字符串转换为车站列表
                # 原始格式："车站1 -> 路线1 -> 车站2 -> 路线2 -> 车站3"
                # 需要转换为：["车站1", "路线1", "车站2", "路线2", "车站3"]
                station_names = station_str.split(' ->\n')
                
                # 构建符合前端期望的结果数组
                formatted_result = [
                    shortest_distance,  # 总用时 (元素0)
                    station_names,  # 车站列表 (元素1)
                    every_route_time,  # 路线详情 (元素2)
                    riding_time,  # 乘车时间 (元素3)
                    waiting_time  # 等车时间 (元素4)
                ]
        
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
        used_cache = locals().get('used_cache', False)
        
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
            }
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

@app.route('/api/generate_image', methods=['POST'])
def api_generate_image():
    """生成结果图片"""
    global latest_image_path
    try:
        # 获取请求数据
        data = request.json
        
        # 准备参数
        algorithm = data.get('algorithm', 'default')
        
        # 确保输出目录存在
        import os
        output_dir = 'generated_images'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 生成唯一的图片文件名
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_path = os.path.join(output_dir, f'path_result_{timestamp}.png')
        
        # 根据算法选择不同的寻路实现
        if algorithm == 'real':
            # 使用v4版程序生成图片
            result = mtr_main_v4(
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
                AVOID_STATIONS=data.get('avoid_stations', []),
                CALCULATE_HIGH_SPEED=not data.get('disable_high_speed', False),
                CALCULATE_BOAT=not data.get('disable_boat', False),
                CALCULATE_WALKING_WILD=data.get('enable_wild', False),
                ONLY_LRT=data.get('only_lrt', False),
                DETAIL=True,
                MAX_HOUR=config['MAX_HOUR'],
                gen_image=True,
                show=False
            )
        else:
            # 使用v3版程序生成图片
            # 检查数据文件是否存在
            import os
            if not os.path.exists(config['LOCAL_FILE_PATH']) or not os.path.exists(config['INTERVAL_PATH']):
                return jsonify({'error': '数据文件不存在，请先更新数据'}), 400
            
            # 直接调用v3版的相关函数生成图片
            from mtr_pathfinder_lib.mtr_pathfinder import (
                create_graph as create_graph_v3,
                find_shortest_route as find_shortest_route_v3,
                save_image,
                RouteType
            )
            
            # 读取数据文件
            with open(config['LOCAL_FILE_PATH'], encoding='utf-8') as f:
                data_file = json.load(f)
            
            IN_THEORY = algorithm == 'theory'
            route_type = RouteType.IN_THEORY if IN_THEORY else RouteType.WAITING
            
            # 合并忽略线路
            ignored_lines = data.get('ignored_lines', []) + config['ORIGINAL_IGNORED_LINES']
            
            # 转换车站表格式
            station_table = {x.lower(): y.lower() for x, y in config['STATION_TABLE'].items()}
            
            # 创建图
            G, used_cache = create_graph_v3(
                data_file,
                ignored_lines,
                not data.get('disable_high_speed', False),
                not data.get('disable_boat', False),
                data.get('enable_wild', False),
                data.get('only_lrt', False),
                data.get('avoid_stations', []),
                route_type,
                config['ORIGINAL_IGNORED_LINES'],
                config['INTERVAL_PATH'],
                '', '',  # version1, version2
                config['LOCAL_FILE_PATH'],
                station_table,
                config['WILD_ADDITION'],
                config['TRANSFER_ADDITION'],
                config['MAX_WILD_BLOCKS'],
                config['MTR_VER'],
                True
            )
            
            # 查找最短路径
            shortest_path, shortest_distance, waiting_time, riding_time, ert = find_shortest_route_v3(
                G, data['start'], data['end'],
                data_file, station_table, config['MTR_VER']
            )
            
            # 检查寻路结果
            if shortest_path in [False, None]:
                with open('debug_log.txt', 'a') as f:
                    f.write(f"[{datetime.now()}] DEBUG: 寻路失败，shortest_path: {shortest_path}\n")
                return jsonify({'error': '生成图片失败，可能是找不到路线或车站名称错误'}), 400
            
            # 获取数据版本信息
            import os
            from datetime import datetime
            
            station_version = ""
            interval_version = ""
            
            if os.path.exists(config['LOCAL_FILE_PATH_V3']):
                station_version = datetime.fromtimestamp(
                    os.path.getmtime(config['LOCAL_FILE_PATH_V3'])
                ).strftime('%Y%m%d-%H%M')
            if os.path.exists(config['INTERVAL_PATH_V3']):
                interval_version = datetime.fromtimestamp(
                    os.path.getmtime(config['INTERVAL_PATH_V3'])
                ).strftime('%Y%m%d-%H%M')
            
            # 生成图片
            result = save_image(
                route_type,
                ert,
                shortest_distance,
                riding_time,
                waiting_time,
                BASE_PATH,
                station_version,
                interval_version,
                True,  # DETAIL
                PNG_PATH,
                False  # show
            )
        
        # 检查结果
        if result in [False, None]:
            return jsonify({'error': '生成图片失败，可能是找不到路线或车站名称错误'}), 400
        
        # 保存图片到文件系统
        try:
            image, base64_str = result
        except Exception as e:
            return jsonify({'error': f'解析图片结果失败: {str(e)}'}), 500
        image.save(image_path)
        
        # 更新最新图片路径
        latest_image_path = image_path
        
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        print(f"生成图片错误: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_image', methods=['GET'])
def api_get_image():
    """获取生成的结果图片"""
    try:
        import os
        
        # 检查是否有最新生成的图片
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
        
        # 返回最新生成的图片
        return send_from_directory(os.path.dirname(latest_image_path), os.path.basename(latest_image_path))
    except Exception as e:
        import traceback
        print(f"获取图片错误: {traceback.format_exc()}")
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



if __name__ == '__main__':
    app.run(debug=True, port=5000)
