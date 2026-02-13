from flask import Flask, render_template, request, jsonify
import os
import json
import hashlib
from datetime import datetime
from opencc import OpenCC

# 直接导入mtr_pathfinder模块
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

# 导入v4版本的函数
from mtr_pathfinder_v4 import (
    fetch_data as original_fetch_data_v4
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
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default_config.copy()

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
        config['LOCAL_FILE_PATH'] = f'mtr-station-data-{link_hash}-mtr{config["MTR_VER"]}-v3.json'
        config['DEP_PATH'] = f'mtr-departure-data-{link_hash}-mtr{config["MTR_VER"]}-v3.json'
        config['INTERVAL_PATH'] = f'mtr-route-interval-data-{link_hash}-mtr{config["MTR_VER"]}-v3.json'
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
    if os.path.exists(config['LOCAL_FILE_PATH']):
        with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
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
    if os.path.exists(config['LOCAL_FILE_PATH']):
        with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
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
    route_version = ""
    interval_version = ""
    
    if os.path.exists(config['LOCAL_FILE_PATH']):
        station_version = datetime.fromtimestamp(
            os.path.getmtime(config['LOCAL_FILE_PATH'])
        ).strftime('%Y%m%d-%H%M')
    if os.path.exists(config['DEP_PATH']):
        route_version = datetime.fromtimestamp(
            os.path.getmtime(config['DEP_PATH'])
        ).strftime('%Y%m%d-%H%M')
    if os.path.exists(config['INTERVAL_PATH']):
        interval_version = datetime.fromtimestamp(
            os.path.getmtime(config['INTERVAL_PATH'])
        ).strftime('%Y%m%d-%H%M')
    
    return render_template('admin.html', 
                           config=config, 
                           station_version=station_version,
                           route_version=route_version,
                           interval_version=interval_version)

@app.route('/api/find_route', methods=['POST'])
def api_find_route():
    # 处理寻路请求
    data = request.json
    
    # 验证必要参数
    if not all(key in data for key in ['start', 'end']):
        return jsonify({'error': '缺少必要参数'}), 400
    
    # 读取车站数据
    if not os.path.exists(config['LOCAL_FILE_PATH']):
        return jsonify({'error': '车站数据不存在，请先更新数据'}), 400
    
    with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
        station_data = json.load(f)
    
    # 选择寻路算法
    algorithm = data.get('algorithm', 'default')
    
    try:
        if algorithm in ['default', 'theory', 'real']:
            # 统一处理所有版本的数据格式
            # 确保station_data是列表格式，与源程序兼容
            if isinstance(station_data, dict):
                # 如果是字典格式，包装成列表格式
                fixed_data = [{
                    'stations': station_data['stations'],
                    'routes': list(station_data['routes'].values())
                }]
                station_data = fixed_data
            elif not isinstance(station_data, list):
                # 其他情况，返回错误
                return jsonify({'error': '无效的数据格式'}), 400
            
            # 根据MTR_VER选择对应的寻路逻辑
            G = create_graph(
                station_data,
                data.get('ignored_lines', []),
                not data.get('disable_high_speed', False),
                not data.get('disable_boat', False),
                data.get('enable_wild', False),
                data.get('only_lrt', False),
                data.get('avoid_stations', []),
                RouteType.WAITING if algorithm == 'default' else RouteType.IN_THEORY,
                config['ORIGINAL_IGNORED_LINES'],
                config['INTERVAL_PATH'],
                '', '',
                config['LOCAL_FILE_PATH'],
                config['STATION_TABLE'],
                config['WILD_ADDITION'],
                config['TRANSFER_ADDITION'],
                config['MAX_WILD_BLOCKS'],
                config['MTR_VER'],
                True
            )
            
            result = find_shortest_route(
                G, data['start'], data['end'],
                station_data, config['STATION_TABLE'],
                config['MTR_VER']
            )
            
            # 检查寻路结果
            if all(item is None for item in result):
                # 所有结果都是None，说明车站名称不正确
                return jsonify({'error': '车站名称不正确，请检查输入'}), 400
            elif result[0] is False:
                # 找不到路线
                return jsonify({'error': '找不到路线，请尝试调整选项'}), 400
            else:
                # 修复结果格式，使其与前端期望的格式匹配
                # 前端期望的格式：[0: ?, 1: ?, 2: ?, 3: 总用时, 4: 车站列表, 5: ?, 6: 路线详情, 7: 乘车时间, 8: 等车时间]
                
                # 解析原始结果
                # result = (station_str, shortest_distance, waiting_time, riding_time, every_route_time)
                station_str, shortest_distance, waiting_time, riding_time, every_route_time = result
                
                # 将车站字符串转换为车站列表
                # 原始格式："车站1 -> 路线1 -> 车站2 -> 路线2 -> 车站3"
                # 需要转换为：["车站1", "路线1", "车站2", "路线2", "车站3"]
                station_names = station_str.split(' ->\n')
                
                # 构建符合前端期望的结果数组
                formatted_result = [
                    None,  # 占位符0
                    None,  # 占位符1
                    None,  # 占位符2
                    shortest_distance,  # 总用时 (元素3)
                    station_names,  # 车站列表 (元素4)
                    None,  # 占位符5
                    every_route_time,  # 路线详情 (元素6)
                    riding_time,  # 乘车时间 (元素7)
                    waiting_time  # 等车时间 (元素8)
                ]
                
                # 返回调整后的结果
                return jsonify({'result': formatted_result})
        elif algorithm == 'real_v4':
            # 使用mtr_pathfinder_v4.py的CSA算法
            # 这里需要实现完整的CSA算法调用逻辑
            return jsonify({'error': '实时[v4]算法暂未实现'}), 500
        else:
            return jsonify({'error': '无效的算法选择'}), 400
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
    
    if not os.path.exists(config['LOCAL_FILE_PATH']):
        return jsonify([])
    
    with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
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
        
        # 直接从源程序导入函数，确保数据格式一致
        from mtr_pathfinder import fetch_data as original_fetch_data
        from mtr_pathfinder import gen_route_interval as original_gen_route_interval
        
        # 保存原始stdin
        original_stdin = sys.stdin
        # 创建模拟输入流，自动返回'y'
        mock_stdin = StringIO('y\n' * 10)  # 提供足够的'y'响应
        sys.stdin = mock_stdin
        
        try:
            # 对于所有版本，统一使用mtr_pathfinder.py中的fetch_data函数
            # 这确保生成的数据格式与源程序完全相同
            original_fetch_data(
                config['LINK'],
                config['LOCAL_FILE_PATH'],
                config['MTR_VER']
            )
            
            # 生成间隔数据文件，使用源程序的函数
            original_gen_route_interval(
                config['LOCAL_FILE_PATH'],
                config['INTERVAL_PATH'],
                config['LINK'],
                config['MTR_VER']
            )
            
            # 生成发车数据
            if config['MTR_VER'] == 4:
                from mtr_pathfinder_v4 import gen_departure as original_gen_departure
                original_gen_departure(
                    config['LINK'],
                    config['DEP_PATH']
                )
        finally:
            # 恢复原始stdin
            sys.stdin = original_stdin
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True, port=5000)
