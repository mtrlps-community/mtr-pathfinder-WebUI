from flask import Flask, render_template, request, jsonify, session
import os
import json
import hashlib
import pickle
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

@app.route('/timetable')
def timetable():
    return render_template('timetable.html')

@app.route('/timetable/station/<station_short_id>', methods=['GET'])
def station_directions(station_short_id=None):
    """获取车站方向信息"""
    if not station_short_id:
        return jsonify({'error': '请输入车站短代码'})
    
    try:
        station_short_id = int(station_short_id)
    except ValueError:
        return jsonify({'error': '车站短代码格式错误'})
    
    if not os.path.exists(config['LOCAL_FILE_PATH']):
        return jsonify({'error': '车站数据不存在'}), 400
    
    with open(config['LOCAL_FILE_PATH'], encoding='utf-8') as f:
        data_v4 = json.load(f)
    
    # 从样本代码中导入函数
    from mtr_timetable import station_short_id_to_id, main_get_sta_directions
    
    sta_id = station_short_id_to_id(data_v4, station_short_id)
    if sta_id is None:
        return jsonify({'error': '车站短代码错误'})
    
    all_stations = data_v4['stations']
    station_name = all_stations[sta_id]['name']
    
    # 使用样本目录中的模板文件
    template_path = os.path.join('templates', 'directions_template.htm')
    if not os.path.exists(template_path):
        return jsonify({'error': '模板文件不存在'}), 500
    
    html = main_get_sta_directions(
        config['LOCAL_FILE_PATH'],
        station_name,
        template_path
    )
    
    if html is None or html is False:
        return jsonify({'error': '未找到该车站信息'})
    
    return html[0]

@app.route('/timetable/station/<station_short_id>/<direction>', methods=['GET'])
def station_timetable(station_short_id=None, direction=None):
    """获取车站时刻表"""
    if not station_short_id or not direction:
        return jsonify({'error': '请输入车站短代码和方向'})
    
    try:
        station_short_id = int(station_short_id)
        direction = int(direction)
    except ValueError:
        return jsonify({'error': '车站短代码或方向格式错误'})
    
    if not os.path.exists(config['LOCAL_FILE_PATH']):
        return jsonify({'error': '车站数据不存在'}), 400
    
    with open(config['LOCAL_FILE_PATH'], encoding='utf-8') as f:
        data_v4 = json.load(f)
    
    # 从样本代码中导入函数
    from mtr_timetable import station_short_id_to_id, main_get_sta_directions, main_sta_timetable
    
    sta_id = station_short_id_to_id(data_v4, station_short_id)
    if sta_id is None:
        return jsonify({'error': '车站短代码错误'})
    
    all_stations = data_v4['stations']
    station_name = all_stations[sta_id]['name']
    
    # 使用样本目录中的模板文件
    directions_template = os.path.join('templates', 'directions_template.htm')
    station_template = os.path.join('templates', 'station_template.htm')
    
    if not os.path.exists(directions_template) or not os.path.exists(station_template):
        return jsonify({'error': '模板文件不存在'}), 500
    
    # 获取车站方向信息
    directions_html = main_get_sta_directions(
        config['LOCAL_FILE_PATH'],
        station_name,
        directions_template
    )
    
    if directions_html is None:
        return jsonify({'error': '未找到该车站方向信息'})
    
    try:
        route_names = directions_html[2][direction]
    except (Exception, KeyError):
        return jsonify({'error': '路线编号错误'})
    
    # 获取车站时刻表
    html = main_sta_timetable(
        config['LOCAL_FILE_PATH'],
        config['LOCAL_FILE_PATH'],
        station_template,
        '',
        station_name, route_names
    )
    
    if html is None or html is False:
        return jsonify({'error': '未找到该车站时刻表信息'})
    
    return html[0]

@app.route('/timetable/train/<station_short_id>/<train_id>', methods=['GET'])
def train_timetable(station_short_id=None, train_id=None):
    """获取列车时刻表"""
    if not station_short_id or not train_id:
        return jsonify({'error': '请输入车站短代码和列车ID'})
    
    try:
        station_short_id = int(station_short_id)
        train_id = int(train_id)
    except ValueError:
        return jsonify({'error': '车站短代码或列车ID格式错误'})
    
    if not os.path.exists(config['LOCAL_FILE_PATH']):
        return jsonify({'error': '车站数据不存在'}), 400
    
    with open(config['LOCAL_FILE_PATH'], encoding='utf-8') as f:
        data_v4 = json.load(f)
    
    # 从样本代码中导入函数
    from mtr_timetable import station_short_id_to_id, main_train
    
    sta_id = station_short_id_to_id(data_v4, station_short_id)
    if sta_id is None:
        return jsonify({'error': '车站短代码错误'})
    
    all_stations = data_v4['stations']
    station_name = all_stations[sta_id]['name']
    
    # 使用样本目录中的模板文件
    timetable_template = os.path.join('templates', 'timetable_template.htm')
    
    if not os.path.exists(timetable_template):
        return jsonify({'error': '模板文件不存在'}), 500
    
    # 获取列车时刻表
    html = main_train(
        config['LOCAL_FILE_PATH'], '', '',
        timetable_template,
        station_name, train_id
    )
    
    if html is None or html is False:
        return jsonify({'error': '未找到该列车信息'})
    
    return html[0]

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

def gen_departure_data(data, DEP_PATH, IGNORED_LINES,  # 路线全名
                       filename1='station_timetable_data.dat',
                       filename2='train_timetable_data.dat'):
    with open(DEP_PATH, 'r', encoding='utf-8') as f:
        dep_data: dict[str, list[int]] = json.load(f)

    station_route_dep: dict[str, dict[str, list[int]]] = {}
    all_route_dep: dict[str, dict[str, list[int]]] = {}
    trains: dict[str, list] = {}
    station_train_id = {}
    for route_id, departures in dep_data.items():
        if route_id not in data['routes']:
            continue

        route = data['routes'][route_id]
        n: str = route['name']
        if n in IGNORED_LINES:
            continue

        try:
            eng_name = n.split('|')[1].split('|')[0]
            if eng_name == '':
                eng_name = n.split('|')[0]
        except IndexError:
            eng_name = n.split('|')[0]

        durations = route['durations']
        if durations == []:
            continue

        if route_id not in trains:
            trains[route_id] = []

        station_ids = [data['stations'][x['id']]['station']
                       for x in route['stations']]
        if len(station_ids) - 1 < len(durations):
            durations = durations[:len(station_ids) - 1]

        if len(station_ids) - 1 > len(durations):
            continue

        departures_new = []
        for x in departures:
            if x < 0:
                x += 86400
            elif x >= 86400:
                x -= 86400
            departures_new.append(x)

        real_ids = [x['id'] for x in route['stations']]
        dwells = [x['dwellTime'] for x in route['stations']]
        if len(dwells) > 0:
            dep = -round(dwells[-1] / 1000)
        else:
            dep = 0

        timetable = []
        for i in range(len(station_ids) - 1, 0, -1):
            station1 = station_ids[i - 1]
            station2 = station_ids[i]
            _station1 = real_ids[i - 1]
            _station2 = real_ids[i]
            dur = round(durations[i - 1] / 1000)
            arr_time = dep
            dep_time = dep - dur
            dwell = round(dwells[i - 1] / 1000)
            dep -= dur
            dep -= dwell
            if station1 == station2:
                continue

            timetable.insert(0, arr_time)
            timetable.insert(0, dep_time)

            if _station1 not in station_train_id:
                station_train_id[_station1] = 1

            if _station1 not in station_route_dep:
                station_route_dep[_station1] = {}

            if eng_name not in station_route_dep[_station1]:
                station_route_dep[_station1][eng_name] = []

            if _station1 not in all_route_dep:
                all_route_dep[_station1] = {}

            for i, x in enumerate(departures_new):
                new_dep = (dep_time + x + 8 * 60 * 60) % 86400
                train_id = station_train_id[_station1]
                station_route_dep[_station1][eng_name].append(
                    (route_id, new_dep, (i, train_id)))
                all_route_dep[_station1][train_id] = \
                    (route_id, i, new_dep)
                station_train_id[_station1] += 1

            station_route_dep[_station1][eng_name].sort()

        if timetable == []:
            continue

        for x in departures_new:
            new_timetable = [y + x + 8 * 60 * 60 for y in timetable]
            trains[route_id].append(new_timetable)

    if filename1 is not None:
        with open(filename1, 'wb') as f:
            pickle.dump(all_route_dep, f)

    if filename2 is not None:
        with open(filename2, 'wb') as f:
            pickle.dump(trains, f)

    return station_route_dep, trains, all_route_dep


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
        
        # 生成时刻表所需的.dat文件
        try:
            # 读取车站数据
            with open(config['LOCAL_FILE_PATH'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 确保数据格式正确
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            
            # 调用生成.dat文件的函数
            gen_departure_data(
                data,
                config['DEP_PATH'],
                config['ORIGINAL_IGNORED_LINES'],
                'station_timetable_data.dat',
                'train_timetable_data.dat'
            )
        except Exception as e:
            # 如果生成.dat文件失败，记录错误但不影响主流程
            print(f"生成.dat文件失败: {str(e)}")
        
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
        # 统一处理所有版本的数据格式
        # 确保station_data是字典格式，与get_text_timetable和get_train函数兼容
        if isinstance(station_data, list) and len(station_data) > 0:
            # 如果是列表格式，提取第一个元素
            station_data = station_data[0]
        elif not isinstance(station_data, dict):
            # 其他情况，返回错误
            return jsonify({'error': '无效的数据格式'}), 400
        
        # 加载时刻表数据文件
        station_tt = {}
        train_tt = {}
        
        try:
            if os.path.exists('station_timetable_data.dat'):
                with open('station_timetable_data.dat', 'rb') as f:
                    station_tt = pickle.load(f)
            
            if os.path.exists('train_timetable_data.dat'):
                with open('train_timetable_data.dat', 'rb') as f:
                    train_tt = pickle.load(f)
        except Exception as e:
            print(f"加载.dat文件失败: {str(e)}")
        
        if data['type'] == 'station':
            # 按车站获取时刻表
            timetable = get_text_timetable(
                station_data,
                data['station'],
                int(datetime.now().timestamp()),
                station_tt  # 传入加载的station_tt数据
            )
            return jsonify({'timetable': timetable})
        elif data['type'] == 'train':
            # 按列车获取时刻表
            timetable = get_train(
                station_data,
                data['station'],
                data['train_id'],
                station_tt,  # 传入加载的station_tt数据
                train_tt     # 传入加载的train_tt数据
            )
            return jsonify({'timetable': timetable})
        else:
            return jsonify({'error': '无效的时刻表类型'}), 400
    except Exception as e:
        import traceback
        print(f"获取时刻表错误: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
