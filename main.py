from flask import Flask, render_template, request, jsonify, session
import os
import json
import hashlib
from datetime import datetime

# 从包装模块导入，避免opencc初始化错误
from mtr_pathfinder_wrapper import (
    fetch_data_v3,
    create_graph,
    find_shortest_route,
    RouteType,
    fetch_data_v4,
    gen_departure,
    gen_route_interval,
    gen_timetable,
    load_tt,
    CSA,
    process_path,
    RouteTypeV4,
    get_text_timetable,
    get_train,
    main_sta_timetable,
    main_get_sta_directions,
    TIMETABLE_AVAILABLE
)

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# 配置文件路径
CONFIG_PATH = 'config.json'

# 默认配置
default_config = {
    'LINK': 'https://letsplay.minecrafttransitrailway.com/system-map',
    'MTR_VER': 4,
    'MAX_WILD_BLOCKS': 1500,
    'TRANSFER_ADDITION': {},
    'WILD_ADDITION': {},
    'STATION_TABLE': {},
    'ORIGINAL_IGNORED_LINES': [],
    'LOCAL_FILE_PATH': '',
    'DEP_PATH': '',
    'INTERVAL_PATH': '',
    'BASE_PATH': 'mtr_pathfinder_data',
    'PNG_PATH': 'mtr_pathfinder_data'
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

# 更新配置中的文件路径
def update_file_paths():
    if config['LINK']:
        link_hash = hashlib.md5(config['LINK'].encode('utf-8')).hexdigest()
        config['LOCAL_FILE_PATH'] = f'mtr-station-data-{link_hash}-{config["MTR_VER"]}.json'
        config['DEP_PATH'] = f'mtr-departure-data-{link_hash}-{config["MTR_VER"]}.json'
        config['INTERVAL_PATH'] = f'mtr-route-data-{link_hash}-{config["MTR_VER"]}.json'
    save_config(config)

# 确保数据目录存在
def ensure_data_dir():
    if not os.path.exists(config['BASE_PATH']):
        os.makedirs(config['BASE_PATH'])
    if not os.path.exists(config['PNG_PATH']):
        os.makedirs(config['PNG_PATH'])

ensure_data_dir()
update_file_paths()

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
            if config['MTR_VER'] == 3:
                stations_data = list(data[0]['stations'].values())
            else:
                stations_data = list(data['stations'].values())
    return render_template('stations.html', stations=stations_data)

@app.route('/routes')
def routes():
    # 读取线路数据
    routes_data = []
    if os.path.exists(config['LOCAL_FILE_PATH']):
        with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
            data = json.load(f)
            if config['MTR_VER'] == 3:
                routes_data = data[0]['routes']
            else:
                routes_data = list(data['routes'].values())
    return render_template('routes.html', routes=routes_data)

@app.route('/timetable')
def timetable():
    return render_template('timetable.html')

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
            # 使用mtr_pathfinder.py的NetworkX算法
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
            
            return jsonify({'result': result})
        elif algorithm == 'real_v4':
            # 使用mtr_pathfinder_v4.py的CSA算法
            # 这里需要实现完整的CSA算法调用逻辑
            return jsonify({'error': '实时[v4]算法暂未实现'}), 500
        else:
            return jsonify({'error': '无效的算法选择'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search_stations', methods=['GET'])
def api_search_stations():
    # 车站模糊搜索
    query = request.args.get('q', '').lower()
    
    if not os.path.exists(config['LOCAL_FILE_PATH']):
        return jsonify([])
    
    with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    stations = []
    if config['MTR_VER'] == 3:
        stations = data[0]['stations'].values()
    else:
        stations = data['stations'].values()
    
    results = []
    for station in stations:
        if query in station['name'].lower():
            results.append(station['name'])
    
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
        
        # 保存原始stdin
        original_stdin = sys.stdin
        # 创建模拟输入流，自动返回'y'
        mock_stdin = StringIO('y\n' * 10)  # 提供足够的'y'响应
        sys.stdin = mock_stdin
        
        try:
            if config['MTR_VER'] == 3:
                fetch_data_v3(
                    config['LINK'],
                    config['LOCAL_FILE_PATH'],
                    config['MTR_VER']
                )
            else:
                fetch_data_v4(
                    config['LINK'],
                    config['LOCAL_FILE_PATH'],
                    config['MAX_WILD_BLOCKS']
                )
            
            # 生成间隔数据文件
            gen_route_interval(
                config['LOCAL_FILE_PATH'],
                config['INTERVAL_PATH'],
                config['LINK'],
                config['MTR_VER']
            )
            
            gen_departure(
                config['LINK'],
                config['DEP_PATH']
            )
        finally:
            # 恢复原始stdin
            sys.stdin = original_stdin
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_timetable', methods=['POST'])
def api_get_timetable():
    # 获取时刻表
    data = request.json
    
    if not os.path.exists(config['LOCAL_FILE_PATH']):
        return jsonify({'error': '车站数据不存在'}), 400
    
    with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
        station_data = json.load(f)
    
    try:
        if data['type'] == 'station':
            # 按车站获取时刻表
            timetable = get_text_timetable(
                station_data,
                data['station'],
                int(datetime.now().timestamp()),
                {}  # 这里需要传入station_tt参数
            )
            return jsonify({'timetable': timetable})
        elif data['type'] == 'train':
            # 按列车获取时刻表
            timetable = get_train(
                station_data,
                data['station'],
                data['train_id'],
                {},  # station_tt
                {}   # train_tt
            )
            return jsonify({'timetable': timetable})
        else:
            return jsonify({'error': '无效的时刻表类型'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
