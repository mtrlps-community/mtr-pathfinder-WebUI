from flask import Flask, render_template, request, jsonify
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



@app.route('/admin')
def admin():
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

@app.route('/api/find_route', methods=['POST'])
def api_find_route():
    # 处理寻路请求
    data = request.json
    
    # 验证必要参数
    if not all(key in data for key in ['start', 'end']):
        return jsonify({'error': '缺少必要参数'}), 400
    
    # 准备参数
    algorithm = data.get('algorithm', 'default')
    
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
    
    try:
        # 根据算法选择不同的寻路实现
        if algorithm == 'real':
            # 使用v4版程序的寻路功能
            
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
            
            # 读取数据文件
            with open(config['LOCAL_FILE_PATH'], encoding='utf-8') as f:
                data_file = json.load(f)
            
            IN_THEORY = algorithm == 'theory'
            
            # 合并忽略线路
            ignored_lines = data.get('ignored_lines', []) + config['ORIGINAL_IGNORED_LINES']
            
            # 转换车站表格式
            station_table = {x.lower(): y.lower() for x, y in config['STATION_TABLE'].items()}
            
            # 创建图
            G = create_graph_v3(
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
            
            # 调用寻路函数获取完整结果
            result = find_shortest_route_v3(
                G, data['start'], data['end'],
                data_file, station_table,
                config['MTR_VER']
            )
            
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
        
        # 返回调整后的结果，包含寻路模式
        return jsonify({'result': formatted_result, 'algorithm': algorithm})
    except Exception as e:
        import traceback
        import logging
        logging.basicConfig(level=logging.ERROR)
        logger = logging.getLogger(__name__)
        
        error_detail = traceback.format_exc()
        logger.error(f"寻路错误: {error_detail}")
        return jsonify({'error': str(e), 'detail': error_detail}), 500

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
    
    save_config(config)
    return jsonify({'success': True})

@app.route('/api/update_data', methods=['POST'])
def api_update_data():
    # 更新数据
    if not config['LINK']:
        return jsonify({'error': '未设置地图链接'}), 400
    
    try:
        import sys
        from io import StringIO
        import json
        import os
        
        # 保存原始stdin
        original_stdin = sys.stdin
        # 创建模拟输入流，自动返回'y'
        mock_stdin = StringIO('y\n' * 20)  # 提供足够的'y'响应
        sys.stdin = mock_stdin
        
        try:
            # 1. 生成v3版程序所需的数据
            # 调用v3版的fetch_data函数
            fetch_data_v3(
                config['LINK'],
                config['LOCAL_FILE_PATH_V3'],
                config['MTR_VER']
            )
            
            # 生成v3版的间隔数据文件
            gen_route_interval_v3(
                config['LOCAL_FILE_PATH_V3'],
                config['INTERVAL_PATH_V3'],
                config['LINK'],
                config['MTR_VER']
            )
            
            # 2. 生成v4版程序所需的数据
            # 调用v4版的fetch_data函数
            from mtr_pathfinder_lib.mtr_pathfinder_v4 import fetch_data as fetch_data_v4
            fetch_data_v4(
                config['LINK'],
                config['LOCAL_FILE_PATH_V4'],
                config['MAX_WILD_BLOCKS']
            )
            
            # 生成v4版的发车数据
            gen_departure_v4(
                config['LINK'],
                config['DEP_PATH_V4']
            )
        finally:
            # 恢复原始stdin
            sys.stdin = original_stdin
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True, port=5000)
