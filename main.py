'''
Find paths between two stations for Minecraft Transit Railway. 
'''

# 导入各种必要的库
from difflib import SequenceMatcher  # 用于字符串相似度比较
from enum import Enum  # 枚举类型
from math import gcd, sqrt  # 数学函数：最大公约数、平方根
from operator import itemgetter  # 用于排序
from statistics import median_low  # 统计学中位数计算
from threading import Thread, BoundedSemaphore  # 多线程和信号量
from time import gmtime, strftime, time  # 时间处理
from typing import Optional, Dict, Literal, Tuple, List, Union  # 类型提示
from queue import Queue  # 队列
import base64  # Base64编码
import hashlib  # 哈希算法
import json  # JSON处理
import os  # 操作系统接口
import pickle  # 对象序列化
import re  # 正则表达式

# 第三方库导入
from opencc import OpenCC  # 简繁中文转换
import networkx as nx  # 图论和网络分析
import requests  # HTTP请求

# 添加Flask相关导入
from flask import Flask, render_template_string, request, jsonify

# 创建Flask应用
app = Flask(__name__)

SERVER_TICK: int = 20

DEFAULT_AVERAGE_SPEED: dict = {
    'train_normal': 14,
    'train_light_rail': 11,
    'train_high_speed': 40,
    'boat_normal': 10,
    'boat_light_rail': 10,
    'boat_high_speed': 13,
    'cable_car_normal': 8,
    'airplane_normal': 70
}
RUNNING_SPEED: int = 5.612
TRANSFER_SPEED: int = 4.317
WILD_WALKING_SPEED: int = 2.25

ROUTE_INTERVAL_DATA = Queue()
semaphore = BoundedSemaphore(25)
original = {}
tmp_names = {}
opencc1 = OpenCC('s2t')
opencc2 = OpenCC('t2jp')
opencc3 = OpenCC('t2s')
opencc4 = OpenCC('jp2t')

# HTML模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTR路径查找器</title>
    <style>
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        . container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            text-align: center;
            color: #333;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input, select, button {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        button {
            background-color: #4CAF50;
            color: white;
            border: none;
            cursor: pointer;
            font-size: 16px;
            padding: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        . result {
            margin-top: 20px;
            padding: 15px;
            border-radius: 4px;
            background-color: #f9f9f9;
            display: none;
        }
        .route-step {
            margin: 10px 0;
            padding: 10px;
            border-left: 4px solid #4CAF50;
            background-color: #f1f1f1;
        }
        .station {
            font-weight: bold;
            color: #333;
        }
        .route-info {
            margin-left: 20px;
            color: #666;
        }
        .time-info {
            margin-top: 15px;
            padding: 10px;
            background-color: #e7f3ff;
            border-radius: 4px;
        }
        .loading {
            text-align: center;
            display: none;
        }
        .error {
            color: #d32f2f;
            background-color: #ffebee;
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>MTR路径查找器</h1>
        <form id="routeForm">
            <div class="form-group">
                <label for="startStation">起点站:</label>
                <input type="text" id="startStation" name="startStation" required>
            </div>
            <div class="form-group">
                <label for="endStation">终点站:</label>
                <input type="text" id="endStation" name="endStation" required>
            </div>
            <div class="form-group">
                <label for="mtrVersion">MTR版本:</label>
                <select id="mtrVersion" name="mtrVersion">
                    <option value="3">3</option>
                    <option value="4">4</option>
                </select>
            </div>
            <div class="form-group">
                <label for="routeType">路线类型:</label>
                <select id="routeType" name="routeType">
                    <option value="WAITING">实际路线（考虑等车时间）</option>
                    <option value="IN_THEORY">理论路线（不考虑等车时间）</option>
                </select>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="calculateHighSpeed" name="calculateHighSpeed" checked>
                    允许高铁
                </label>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="calculateBoat" name="calculateBoat" checked>
                    允许船只
                </label>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="calculateWalkingWild" name="calculateWalkingWild">
                    允许野外步行
                </label>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="onlyLRT" name="onlyLRT">
                    仅轻轨
                </label>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="detail" name="detail">
                    显示详细信息
                </label>
            </div>
            <button type="submit">查找路径</button>
        </form>
        
        <div class="loading" id="loading">
            正在计算路径，请稍候...
        </div>
        
        <div class="result" id="result">
            <!-- 结果将在这里动态显示 -->
        </div>
    </div>

    <script>
        document.getElementById('routeForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const data = {
                startStation: formData. get('startStation'),
                endStation: formData.get('endStation'),
                mtrVersion: parseInt(formData.get('mtrVersion')),
                routeType: formData.get('routeType'),
                calculateHighSpeed: formData.get('calculateHighSpeed') === 'on',
                calculateBoat: formData.get('calculateBoat') === 'on',
                calculateWalkingWild: formData.get('calculateWalkingWild') === 'on',
                onlyLRT: formData.get('onlyLRT') === 'on',
                detail: formData.get('detail') === 'on'
            };
            
            // 显示加载中
            document.getElementById('loading'). style.display = 'block';
            document.getElementById('result').style.display = 'none';
            
            fetch('/find-route', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            })
            . then(response => response.json())
            .then(data => {
                document.getElementById('loading').style.display = 'none';
                const resultDiv = document.getElementById('result');
                resultDiv.style.display = 'block';
                
                if (data.success) {
                    resultDiv.innerHTML = data.html;
                } else {
                    resultDiv. innerHTML = `<div class="error">${data.error}</div>`;
                }
            })
            .catch(error => {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('result').innerHTML = `<div class="error">请求失败: ${error}</div>`;
                document.getElementById('result').style.display = 'block';
            });
        });
    </script>
</body>
</html>
'''

# 常量定义
SERVER_TICK: int = 20  # Minecraft服务器刻数

# 各种交通工具的平均速度（单位：方块/秒）
DEFAULT_AVERAGE_SPEED: dict = {
    'train_normal': 14,
    'train_light_rail': 11,
    'train_high_speed': 40,
    'boat_normal': 10,
    'boat_light_rail': 10,
    'boat_high_speed': 13,
    'cable_car_normal': 8,
    'airplane_normal': 70
}

RUNNING_SPEED: int = 5.612          # 站内换乘速度
TRANSFER_SPEED: int = 4.317         # 出站换乘速度
WILD_WALKING_SPEED: int = 2.25      # 非出站换乘（越野）速度

# 全局变量
ROUTE_INTERVAL_DATA = Queue()  # 存储路线间隔数据的队列
semaphore = BoundedSemaphore(25)  # 限制并发数的信号量
original = {}  # 存储原始数据
tmp_names = {}  # 临时名称存储

# 中文简繁转换器初始化
opencc1 = OpenCC('s2t')  # 简体转繁体
opencc2 = OpenCC('t2jp')  # 繁体转日文
opencc3 = OpenCC('t2s')  # 繁体转简体
opencc4 = OpenCC('jp2t')  # 日文转繁体


def get_close_matches(words, possibilities, cutoff=0.2):
    '''
    使用序列匹配器找到最相似的字符串
    '''
    result = [(-1, None)]  # 初始化结果
    s = SequenceMatcher()  # 创建序列匹配器
    for word in words:
        s.set_seq2(word)  # 设置目标序列
        for x, y in possibilities:
            s.set_seq1(x)  # 设置源序列
            # 快速匹配检查
            if s.real_quick_ratio() >= cutoff and \
                    s.quick_ratio() >= cutoff:
                ratio = s.ratio()  # 计算相似度
                if ratio >= cutoff:
                    result.append((ratio, y))  # 添加到结果

    return max(result)[1]  # 返回相似度最高的结果


class RouteType(Enum):
    '''
    定义路线类型的枚举类
    '''
    IN_THEORY = 0  # 理论路线（不考虑等车时间）
    WAITING = 1    # 实际路线（考虑等车时间）


def round_ten(n: float) -> int:
    '''
    将数字四舍五入到最近的十位数
    '''
    ans = round(n / 10) * 10  # 四舍五入到十位
    return ans if ans > 0 else 10  # 确保结果为正


def atoi(text: str) -> Union[str, int]:
    '''
    将字符串转换为数字（如果可以）
    '''
    return int(text) if text.isdigit() else text  # 如果是数字则转换


def natural_keys(text: str) -> list:
    '''
    自然排序键（数字顺序）
    '''
    return [atoi(c) for c in re.split(r'(\d+)', text)]  # 分割数字和非数字部分


def lcm(a: int, b: int) -> int:
    '''
    计算两个整数的最小公倍数
    '''
    return a * b // gcd(a, b)  # 使用公式 LCM = (a*b)/GCD


def fetch_interval_data(station_id: str, LINK) -> None:
    '''
    获取车站的间隔数据
    '''
    global ROUTE_INTERVAL_DATA
    with semaphore:  # 使用信号量限制并发
        link = LINK + f'/arrivals? worldIndex=0&stationId={station_id}'  # 构建API链接
        try:
            data = requests.get(link).json()  # 发送请求获取数据
        except Exception:
            pass  # 忽略异常
        else:
            ROUTE_INTERVAL_DATA.put([station_id, [time(), data]])  # 将数据放入队列


def gen_route_interval(LOCAL_FILE_PATH, INTERVAL_PATH, LINK, MTR_VER) -> None:
    '''
    生成所有路线间隔数据
    '''
    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)  # 加载本地数据

    if MTR_VER == 3:  # MTR版本3的处理
        threads: list[Thread] = []
        for station_id in data[0]['stations']:  # 为每个车站创建线程
            t = Thread(target=fetch_interval_data, args=(station_id, LINK))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()  # 等待所有线程完成

        interval_data_list = []
        while not ROUTE_INTERVAL_DATA.empty():
            interval_data_list.append(ROUTE_INTERVAL_DATA.get())  # 从队列获取数据

        arrivals = dict(interval_data_list)
        dep_dict_per_route: dict[str, list] = {}
        dep_dict_per_route_: dict[str, list] = {}
        for t, arrivals in arrivals.values():
            dep_dict_per_station: dict[str, list] = {}
            for arrival in arrivals[:-1]:
                name = arrival['name']
                if name in dep_dict_per_station:
                    dep_dict_per_station[name] += [arrival['arrival']]  # 添加到达时间
                else:
                    dep_dict_per_station[name] = [arrival['arrival']]

            for x, item in dep_dict_per_station.items():
                dep_s_list = []
                if len(item) == 1:  # 如果只有一个数据点
                    if x not in dep_dict_per_route_:
                        dep_dict_per_route_[x] = [(item[0] / 1000 - t) * 1.25]
                else:  # 多个数据点
                    for y in range(len(item) - 1):
                        dep_s_list.append((item[y + 1] - item[y]) / 1000)  # 计算间隔
                    if x in dep_dict_per_route:
                        dep_dict_per_route[x] += [sum(dep_s_list) / len(dep_s_list)]
                    else:
                        dep_dict_per_route[x] = [sum(dep_s_list) / len(dep_s_list)]

        for x in dep_dict_per_route_:
            if x not in dep_dict_per_route:
                dep_dict_per_route[x] = dep_dict_per_route_[x]  # 合并数据

        freq_dict: dict[str, list] = {}
        for route, arrivals in dep_dict_per_route.items():
            if len(arrivals) == 1:
                freq_dict[route] = round_ten(arrivals[0])  # 单数据点直接取整
            else:
                freq_dict[route] = round_ten(sum(arrivals) / len(arrivals))  # 多数据点取平均

    elif MTR_VER == 4:  # MTR版本4的处理
        link = LINK. rstrip('/') + '/mtr/api/map/departures? dimension=0'
        departures = requests.get(link). json()['data']['departures']  # 获取发车数据
        dep_dict: dict[str, list[int]] = {}
        for x in departures:
            dep_list = set()
            for y in x['departures']:
                for z in y['departures']:
                    dep = round(z / 1000)  # 转换为秒
                    while dep < 0:
                        dep += 86400  # 处理负值（跨天）

                    dep_list.add(dep)

            dep_list = list(sorted(dep_list))  # 排序
            dep_dict[x['id']] = dep_list

        freq_dict: dict[str, list] = {}
        for route_id, stats in dep_dict.items():
            if len(stats) == 0:
                continue

            for route_stats in data[0]['routes']:  # 查找路线信息
                if route_stats['id'] == route_id:
                    break
            else:
                print(f'Route {route_id} not found')
                continue

            route_name = route_stats['name']
            freq_list = []
            for i1 in range(len(stats)):  # 计算频率
                i2 = i1 + 1
                if i2 == len(stats):
                    i2 = 0
                    dep_2 = stats[i2] + 86400  # 处理跨天
                else:
                    dep_2 = stats[i2]

                dep_1 = stats[i1]
                freq = dep_2 - dep_1  # 计算间隔
                freq_list.append(freq)

            median_freq = median_low(freq_list)  # 取中位数
            freq_dict[route_name] = round_ten(median_freq)  # 四舍五入

    else:
        return

    y = input(f'是否替换{INTERVAL_PATH}文件?  (Y/N) ').lower()
    if y == 'y':
        with open(INTERVAL_PATH, 'w', encoding='utf-8') as f:
            json. dump(freq_dict, f)  # 保存间隔数据


def fetch_data(link: str, LOCAL_FILE_PATH, MTR_VER) -> str:
    '''
    获取所有路线数据和车站数据
    '''
    if MTR_VER == 3:  # MTR版本3
        link = link. rstrip('/') + '/data'
        data = requests.get(link).json()  # 获取数据
    else:  # MTR版本4
        link = link.rstrip('/') + '/mtr/api/map/stations-and-routes? dimension=0'
        data = requests.get(link).json()['data']  # 获取数据

        data_new = {'routes': [], 'stations': {}}
        i = 0
        for d in data['stations']:  # 处理车站数据
            d['station'] = hex(i)[2:]  # 生成十六进制ID
            data_new['stations'][d['id']] = d
            i += 1

        x_dict = {x['id']: [] for x in data['stations']}
        z_dict = {x['id']: [] for x in data['stations']}
        for route in data['routes']:  # 处理路线数据
            # if route['hidden'] is True:
            #     continue

            # 处理环形路线状态
            if route['circularState'] == 'CLOCKWISE':
                route['circular'] = 'cw'  # 顺时针
            elif route['circularState'] == 'ANTICLOCKWISE':
                route['circular'] = 'ccw'  # 逆时针
            else:
                route['circular'] = ''

            route['durations'] = [round(x / 1000) for x in route['durations']]  # 转换为秒
            for station in route['stations']:  # 收集坐标数据
                x_dict[station['id']] += [station['x']]
                z_dict[station['id']] += [station['z']]

            data_new['routes'].append(route)

        for station in data['stations']:  # 计算平均坐标
            x_list = x_dict[station['id']]
            z_list = z_dict[station['id']]
            if len(x_list) == 0:
                continue

            data_new['stations'][station['id']]['x'] = sum(x_list) / len(x_list)
            data_new['stations'][station['id']]['z'] = sum(z_list) / len(z_list)

        data = [data_new]  # 包装数据

    y = input(f'是否替换{LOCAL_FILE_PATH}文件? (Y/N) ').lower()
    if y == 'y':
        with open(LOCAL_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f)  # 保存数据

    return data


def get_distance(a_dict: dict, b_dict: dict, square: bool = False) -> float:
    '''
    获取两个车站之间的距离
    '''
    dist_square = (a_dict['x'] - b_dict['x']) ** 2 + \
        (a_dict['z'] - b_dict['z']) ** 2  # 计算平方距离
    if square is True:
        return dist_square
    return sqrt(dist_square)  # 返回实际距离


def station_name_to_id(data: list, sta: str, STATION_TABLE,
                       fuzzy_compare=True) -> str:
    '''
    将车站名称转换为其ID
    '''
    sta = sta.lower()  # 转换为小写
    if sta in STATION_TABLE:  # 检查车站表
        sta = STATION_TABLE[sta]

    if sta in tmp_names:  # 检查临时名称
        return tmp_names[sta]

    # 尝试多种中文变体
    tra1 = opencc1.convert(sta)
    sta_try = [sta, tra1, opencc2.convert(tra1)]

    all_names = []
    stations = data[0]['stations']
    output = None
    has_station = False
    for station_id, station_dict in stations.items():
        s_1 = station_dict['name']
        if 'x' in station_dict and 'z' in station_dict:  # 检查是否有坐标
            all_names.append((s_1, station_id))

        s_split = station_dict['name'].split('|')
        s_2_2 = s_split[-1]
        s_2 = s_2_2.split('/')[-1]
        s_3 = s_split[0]
        for st in sta_try:  # 尝试匹配各种名称变体
            if st in (s_1. lower(), s_2.lower(), s_2_2.lower(), s_3.lower()):
                has_station = True
                output = station_id
                break

    if has_station is False and fuzzy_compare is True:  # 模糊匹配
        output = get_close_matches(sta_try, all_names)

    if output is not None:
        tmp_names[sta] = output  # 缓存结果

    return output


def get_route_station_index(route: dict, station_1_id: str, station_2_id: str,
                            MTR_VER=3) -> tuple:
    '''
    获取两个车站在同一路线中的索引
    '''
    if MTR_VER == 3:
        st = [x. split('_')[0] for x in route['stations']]  # 提取车站ID
    else:
        st = [x['id'] for x in route['stations']]

    check_station_2 = False
    for i, station in enumerate(st):
        if station == station_1_id:  # 找到第一个车站
            index1 = i
            check_station_2 = True
        if check_station_2 and station == station_2_id:  # 找到第二个车站
            index2 = i
            break
    else:
        index1 = index2 = None  # 未找到

    return index1, index2


def get_approximated_time(route: dict, station_1_id: str, station_2_id: str,
                          data: list, tick: bool = False, MTR_VER=3) -> float:
    '''
    获取两个车站在同一路线中的近似时间
    '''
    if MTR_VER == 4:  # MTR版本4使用专用函数
        return get_app_time_v4(route, station_1_id, station_2_id)

    index1, index2 = get_route_station_index(route, station_1_id, station_2_id)
    if index2 is None:  # 车站不在同一路线
        return None

    station_1_position = {}
    station_2_position = {}
    t = 0
    stations = route['stations'][index1:index2 + 1]  # 获取车站区间
    for i, station_1 in enumerate(stations):
        try:
            station_2 = stations[i + 1]  # 下一站
        except IndexError:
            break

        station_1_check = False
        station_2_check = False
        for k, position_dict in data[0]['positions'].items():  # 查找坐标
            if k == station_1:
                station_1_position['x'] = position_dict['x']
                station_1_position['z'] = position_dict['y']
                station_1_check = True
            elif k == station_2:
                station_2_position['x'] = position_dict['x']
                station_2_position['z'] = position_dict['y']
                station_2_check = True
            if station_1_check and station_2_check:  # 找到两个车站坐标
                t += get_distance(station_1_position, station_2_position) \
                    / DEFAULT_AVERAGE_SPEED[route['type']]  # 计算时间
                break

    if tick is True:
        t *= 20  # 转换为游戏刻

    return t


def get_app_time_v4(route: dict, station_1_id: str, station_2_id: str) -> float:
    '''
    MTR版本4：获取两个车站在同一路线中的近似时间
    '''
    index1, index2 = get_route_station_index(route, station_1_id, station_2_id, 4)
    if index2 is None:
        return None

    t = 0
    stations = route['stations'][index1:index2 + 1]
    for i, station_1 in enumerate(stations):
        try:
            station_2 = stations[i + 1]
        except IndexError:
            break

        t += get_distance(station_1, station_2) / \
            DEFAULT_AVERAGE_SPEED[route['type']]  # 使用默认速度计算时间

    return t


def create_graph(data: list, IGNORED_LINES: bool,
                 CALCULATE_HIGH_SPEED: bool, CALCULATE_BOAT: bool,
                 CALCULATE_WALKING_WILD: bool, ONLY_LRT: bool,
                 AVOID_STATIONS: list, route_type: RouteType,
                 original_ignored_lines: list,
                 INTERVAL_PATH: str,
                 version1: str, version2: str,
                 LOCAL_FILE_PATH, STATION_TABLE,
                 WILD_ADDITION, TRANSFER_ADDITION,
                 MAX_WILD_BLOCKS, MTR_VER, cache) -> nx.MultiDiGraph:
    '''
    创建所有路线的图
    '''
    global original, intervals
    with open(INTERVAL_PATH, 'r', encoding='utf-8') as f:
        intervals = json.load(f)  # 加载间隔数据

    if not os.path.exists('mtr_pathfinder_temp'):
        os.makedirs('mtr_pathfinder_temp')  # 创建临时目录

    filename = ''
    # 检查是否可以使用缓存
    if cache is True and IGNORED_LINES == original_ignored_lines and \
            CALCULATE_BOAT is True and ONLY_LRT is False and \
            AVOID_STATIONS == [] and route_type == RouteType.WAITING:
        filename = f'mtr_pathfinder_temp{os.sep}' + \
            f'{int(CALCULATE_HIGH_SPEED)}{int(CALCULATE_WALKING_WILD)}' + \
            f'-{version1}-{version2}.dat'
        if os.path.exists(filename):  # 缓存文件存在
            with open(filename, 'rb') as f:
                tup = pickle.load(f)  # 加载缓存
                G = tup[0]
                original = tup[1]

            return G

    routes = data[0]['routes']
    new_durations = {}
    # 计算缺失的持续时间
    for it0, route in enumerate(routes):
        name_lower = route['name'].lower()
        if 'placeholder' in name_lower or 'dummy' in name_lower:  # 跳过占位路线
            continue

        old_durations = route['durations']
        if 0 in old_durations or old_durations == []:  # 需要计算持续时间
            stations = route['stations']
            new_dur = []
            for it1 in range(len(route['stations']) - 1):
                if old_durations != [] and old_durations[it1] != 0:  # 已有数据
                    new_dur. append(old_durations[it1])
                    continue

                it2 = it1 + 1
                if MTR_VER == 3:
                    station_1 = stations[it1]. split('_')[0]
                    station_2 = stations[it2].split('_')[0]
                else:
                    station_1 = stations[it1]['id']
                    station_2 = stations[it2]['id']

                app_time = get_approximated_time(route, station_1, station_2,
                                                 data, True, MTR_VER)  # 计算近似时间
                if app_time == 0:
                    app_time = 0.01  # 避免零值
                new_dur.append(app_time)

            if sum(new_dur) == 0:  # 无效路线
                continue

            new_durations[str(it0)] = new_dur  # 存储新计算的持续时间

    # 更新数据文件
    if len(new_durations) > 0:
        for route_id, new_duration in new_durations.items():
            route_id = int(route_id)
            old_route_data = data[0]['routes'][route_id]
            old_route_data['durations'] = new_duration  # 更新持续时间
            data[0]['routes'][route_id] = old_route_data

        with open(LOCAL_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f)  # 保存更新后的数据

    # 转换避开的车站名称为ID
    avoid_ids = [station_name_to_id(data, x, STATION_TABLE)
                 for x in AVOID_STATIONS]

    all_stations = data[0]['stations']
    G = nx.MultiDiGraph()  # 创建有向多重图
    edges_dict = {}
    edges_attr_dict = {}
    original = {}
    waiting_walking_dict = {}

    # 添加出站换乘边
    for station, station_dict in all_stations.items():
        if 'x' not in station_dict or 'z' not in station_dict:  # 跳过无坐标车站
            continue

        if station in avoid_ids:  # 跳过避开的车站
            continue

        for transfer in station_dict['connections']:  # 处理连接车站
            if transfer not in all_stations:
                continue

            if transfer in avoid_ids:
                continue

            transfer_dict = all_stations[transfer]
            if 'x' not in transfer_dict or 'z' not in transfer_dict:
                continue

            dist = get_distance(station_dict, transfer_dict)  # 计算距离
            duration = dist / TRANSFER_SPEED  # 计算时间

            # 添加出站换乘边
            if (station, transfer) in edges_attr_dict:
                edges_attr_dict[(station, transfer)]. append(
                    (f'出站换乘步行 Walk {round(dist, 2)}m', duration, 0))
            else:
                edges_attr_dict[(station, transfer)] = [
                    (f'出站换乘步行 Walk {round(dist, 2)}m', duration, 0)]
            waiting_walking_dict[(station, transfer)] = \
                (duration, f'出站换乘步行 Walk {round(dist, 2)}m')

        # 处理额外的换乘连接
        additions1 = set()
        if station_dict['name'] in TRANSFER_ADDITION:
            for x in TRANSFER_ADDITION[station_dict['name']]:
                additions1.add(x)

        for x in additions1:
            for station2, station2_dict in all_stations.items():
                if station2 in avoid_ids:
                    continue

                if station2_dict['name'] == x:
                    if station2 not in station_dict['connections']:  # 新连接
                        try:
                            dist = get_distance(station_dict, station2_dict)
                            duration = dist / TRANSFER_SPEED
                            if (station, station2) not in edges_attr_dict:
                                edges_attr_dict[(station, station2)] = []
                            edges_attr_dict[(station, station2)].append(
                                (f'出站换乘步行 Walk {round(dist, 2)}m',
                                 duration, 0))
                            waiting_walking_dict[(station, station2)] = \
                                (duration, f'出站换乘步行 Walk {round(dist, 2)}m')
                        except KeyError:
                            pass

                        break

        # 处理野外步行连接
        additions2 = set()
        if station_dict['name'] in WILD_ADDITION and \
                CALCULATE_WALKING_WILD is True:
            for x in WILD_ADDITION[station_dict['name']]:
                additions2. add(x)

        for x in additions2:
            for station2, station2_dict in all_stations.items():
                if station2 in avoid_ids:
                    continue

                if station2_dict['name'] == x:
                    if station2 not in station_dict['connections']:  # 新连接
                        try:
                            dist = get_distance(station_dict, station2_dict)
                            duration = dist / WILD_WALKING_SPEED
                            if (station, station2) not in edges_attr_dict:
                                edges_attr_dict[(station, station2)] = []

                            edges_attr_dict[(station, station2)].append(
                                (f'步行 Walk {round(dist, 2)}m', duration, 0))
                            waiting_walking_dict[(station, station2)] = \
                                (duration, f'步行 Walk {round(dist, 2)}m')
                        except KeyError:
                            pass

                        break

    # 处理忽略的路线
    TEMP_IGNORED_LINES = [x. lower(). strip() for x in IGNORED_LINES if x != '']
    # 添加普通路线边
    for route in data[0]['routes']:
        n: str = route['name']
        number: str = route['number']
        route_names = [n, n.split('|')[0]]  # 各种名称变体
        if ('||' in n and n.count('|') > 2) or \
                ('||' not in n and n.count('|') > 0):
            eng_name = n.split('|')[1]. split('|')[0]
            if eng_name != '':
                route_names. append(eng_name)

        if number not in ['', ' ']:  # 添加带编号的名称
            for tmp_name in route_names[1:]:
                route_names.append(tmp_name + ' ' + number)

        cont = False
        for x in route_names:  # 检查是否在忽略列表中
            x = x.lower().strip()
            if x in TEMP_IGNORED_LINES:
                cont = True
                break

            if x. isascii():  # 英文名称
                continue

            simp1 = opencc3.convert(x)  # 简体中文
            if simp1 in TEMP_IGNORED_LINES:
                cont = True
                break

            simp2 = opencc3.convert(opencc4.convert(x))  # 日文转简体
            if simp2 in TEMP_IGNORED_LINES:
                cont = True
                break

        if cont is True:  # 跳过忽略的路线
            continue

        # 根据设置过滤路线类型
        if (not CALCULATE_HIGH_SPEED) and route['type'] == 'train_high_speed':
            continue

        if (not CALCULATE_BOAT) and 'boat' in route['type']:
            continue

        if ONLY_LRT and route['type'] != 'train_light_rail':
            continue

        # 处理等待时间
        if route_type == RouteType.WAITING:
            if route['type'] == 'cable_car_normal':  # 缆车特殊处理
                intervals[n] = 2

            if n not in intervals:  # 无间隔数据
                continue

        stations = route['stations']
        durations = route['durations']
        if len(stations) < 2:  # 无效路线
            continue

        if len(stations) - 1 < len(durations):  # 调整持续时间长度
            durations = durations[:len(stations) - 1]

        if len(stations) - 1 > len(durations):  # 数据不匹配
            continue

        # 添加路线边
        for i in range(len(durations)):
            for i2 in range(len(durations[i:])):
                i2 += i + 1
                if MTR_VER == 3:
                    station_1 = stations[i]. split('_')[0]
                    station_2 = stations[i2].split('_')[0]
                    dur_list = durations[i:i2]
                    station_list = stations[i:i2 + 1]
                    c = False
                    for sta in station_list:  # 检查是否包含避开车站
                        if sta.split('_')[0] in avoid_ids:
                            c = True
                    if c is True:
                        continue

                    if 0 in dur_list:  # 需要计算时间
                        t = get_approximated_time(route, station_1, station_2,
                                                  data, MTR_VER)
                        if t is None:
                            continue
                        dur = t
                    else:
                        dur = sum(durations[i:i2]) / SERVER_TICK  # 使用已有数据

                else:  # MTR版本4
                    station_1 = stations[i]
                    station_2 = stations[i2]
                    dur_list = durations[i:i2]
                    station_list = stations[i:i2 + 1]
                    dwell = sum([x['dwellTime'] / 1000  # 计算停站时间
                                 for x in station_list][1:-1])
                    c = False
                    for sta in station_list:
                        if sta['id'] in avoid_ids:
                            c = True
                    if c is True:
                        continue

                    if 0 in dur_list:  # 需要计算时间
                        t = get_app_time_v4(route, station_1, station_2,
                                            data, MTR_VER)
                        if t is None:
                            continue
                        dur = round(t + dwell)
                    else:
                        dur = round(sum(durations[i:i2]) + dwell)  # 使用已有数据

                    station_1 = station_1['id']
                    station_2 = station_2['id']

                # 根据路线类型处理
                if route_type == RouteType.WAITING:
                    wait = float(intervals[n])  # 获取等待时间
                    if (station_1, station_2) not in edges_dict:
                        edges_dict[(station_1, station_2)] = [
                            (dur, wait, route['name'])]
                    else:
                        edges_dict[(station_1, station_2)].append(
                            (dur, wait, route['name']))
                    original[(station_1, station_2, route['name'])] = dur  # 存储原始数据
                else:  # 理论路线
                    if (station_1, station_2) in edges_attr_dict:
                        edges_attr_dict[(station_1, station_2)].append(
                            (route['name'], dur, 0))
                    else:
                        edges_attr_dict[(station_1, station_2)] = [
                            (route['name'], dur, 0)]

    # 处理等待时间路线
    if route_type == RouteType. WAITING:
        for tup, dur_tup in edges_dict.items():
            dur = [x[0] for x in dur_tup]  # 提取持续时间
            wait = [x[1] for x in dur_tup]  # 提取等待时间
            routes = [x[2] for x in dur_tup]  # 提取路线名称
            final_wait = []
            final_routes = []
            min_dur = min(dur)  # 最小持续时间
            # 筛选相近的路线
            for i, x in enumerate(dur):
                if abs(x - min_dur) <= 60:  # 时间相近
                    final_wait.append(wait[i])
                    final_routes.append(routes[i])

            s1 = tup[0]
            s2 = tup[1]
            lcm_sum = 1
            sum_interval = 0
            # 计算最小公倍数
            for x in final_wait:
                if x != 0:
                    lcm_sum = lcm(lcm_sum, round(x))
            for x in final_wait:
                if x != 0:
                    sum_interval += (lcm_sum / round(x))

            if sum_interval == 0:
                sum_int = 0
            else:
                sum_int = lcm_sum / sum_interval / 2  # 计算平均间隔

            # 添加步行选项
            if (s1, s2) in waiting_walking_dict:
                t = waiting_walking_dict[(s1, s2)][0]
                if abs(t - min_dur) <= 60:  # 时间相近
                    route_name = waiting_walking_dict[(s1, s2)][1]
                    dur = waiting_walking_dict[(s1, s2)][0]
                    final_routes.append(route_name)
                    original[(s1, s2, route_name)] = dur

            edges_attr_dict[(s1, s2)] = [(final_routes, min_dur, sum_int)]  # 存储最终边

    # 将边添加到图中
    for edge in edges_attr_dict.items():
        u, v = edge[0]
        min_time = min(e[1] + e[2] for e in edge[1])  # 计算最小时间
        for r in edge[1]:
            route_name = r[0]
            duration = r[1]
            waiting_time = r[2]
            weight = duration + waiting_time  # 计算权重
            if abs(weight - min_time) <= 60 and weight > 0:  # 时间相近且有效
                G.add_edge(u, v, weight=weight, name=route_name,
                           waiting=waiting_time)  # 添加边

    # 添加野外行走边（无铁路连接）
    if CALCULATE_WALKING_WILD is True:
        edges_attr_dict = {}
        for station, station_dict in all_stations. items():
            if station in avoid_ids:
                continue

            if 'x' not in station_dict or 'z' not in station_dict:
                continue

            for station2, station2_dict in all_stations.items():
                if station2 in avoid_ids:
                    continue

                if 'x' not in station2_dict or 'z' not in station2_dict:
                    continue

                if station == station2:  # 相同车站
                    continue

                if (station, station2) in waiting_walking_dict:  # 已有连接
                    continue

                dist = get_distance(station_dict, station2_dict, True)  # 平方距离
                if dist <= (MAX_WILD_BLOCKS ** 2):  # 在最大距离内
                    dist = sqrt(dist)
                    duration = dist / WILD_WALKING_SPEED  # 计算时间
                    # 如果已有边且时间更长，跳过
                    if G.has_edge(station, station2) and \
                            duration - G[station][station2][0]['weight'] > 60:
                        continue

                    edges_attr_dict[(station, station2)] = [
                        (f'步行 Walk {round(dist, 2)}m', duration, 0)]
                    # 如果步行更快，移除原有边
                    if G.has_edge(station, station2) and \
                            duration + 120 < \
                            G[station][station2][0]['weight']:
                        G.remove_edge(station, station2)

        # 添加野外行走边
        for edge in edges_attr_dict.items():
            u, v = edge[0]
            for r in edge[1]:
                route_name = r[0]
                duration = r[1]
                waiting_time = r[2]
                G.add_edge(u, v, weight=duration, name=route_name,
                           waiting=waiting_time)

    # 保存缓存
    if filename != '':
        if not os.path.exists(filename):
            with open(filename, 'wb') as f:
                pickle. dump((G, original), f)  # 序列化图和数据

    return G


def find_shortest_route(G: nx.MultiDiGraph, start: str, end: str,
                        data: list, STATION_TABLE,
                        MTR_VER) -> list[str, int, int, int, list]:
    '''
    查找两个车站之间的最短路线
    '''
    # 转换车站名称为ID
    start_station = station_name_to_id(data, start, STATION_TABLE)
    end_station = station_name_to_id(data, end, STATION_TABLE)
    if not (start_station and end_station):  # 车站不存在
        return None, None, None, None, None

    if start_station == end_station:  # 相同车站
        return None, None, None, None, None

    shortest_path = []
    shortest_distance = -1
    try:
        # 查找所有最短路径
        shortest_path = nx. all_shortest_paths(G, start_station,
                                              end_station, weight='weight')
        shortest_path = list(sorted(shortest_path, key=lambda x: len(x)))[0]  # 取最短
        shortest_distance = nx.shortest_path_length(G, start_station,
                                                    end_station,
                                                    weight='weight')  # 计算距离
    except nx.exception.NetworkXNoPath:  # 无路径
        return False, False, False, False, False
    except nx.exception.NodeNotFound:  # 节点不存在
        return False, False, False, False, False

    return process_path(G, shortest_path, shortest_distance, data, MTR_VER)  # 处理路径


def process_path(G: nx. MultiDiGraph, path: list, shortest_distance: int,
                 data: list, MTR_VER) -> list[str, int, int, int, list]:
    '''
    处理路径，将其转换为人类可读的形式
    '''
    stations = data[0]['stations']
    routes = data[0]['routes']
    station_names = [stations[path[0]]['name']]  # 起始站
    every_route_time = []
    each_route_time = []
    waiting_time = 0
    # 处理路径中的每一段
    for i in range(len(path) - 1):
        station_1 = path[i]
        station_2 = path[i + 1]
        edge = G[station_1][station_2]  # 获取边数据
        duration_list = []
        waiting_list = []
        route_name_list = []
        # 提取边信息
        for v in edge.values():
            duration = v['weight']
            route_name = v['name']
            waiting = v['waiting']
            duration_list.append((route_name, duration))
            waiting_list.append((route_name, waiting))
            if isinstance(route_name, list):
                route_name_list.extend(route_name)
            elif isinstance(route_name, str):
                route_name_list.append(route_name)
            waiting_time += waiting  # 累计等待时间

        # 格式化路线名称
        if len(route_name_list) == 1:
            route_name = route_name_list[0]
        else:
            route_name = '(' + ' / '.join(route_name_list) + ')'

        station_names.append(route_name)  # 添加路线名称
        station_names.append(stations[path[i + 1]]['name'])  # 添加车站名称

        sta1_name = stations[station_1]['name']. replace('|', ' ')
        sta2_name = stations[station_2]['name']. replace('|', ' ')
        sta1_id = stations[station_1]['id']
        # 处理每个路线
        for route_name in route_name_list:
            # 查找持续时间
            for x in duration_list:
                if route_name == x[0]:
                    duration = x[1]
                    break
            else:  # 从原始数据查找
                for x in duration_list:
                    for y in x[0]:
                        if route_name == y:
                            duration = original[(station_1, station_2,
                                                 route_name)]
                            break

            # 查找等待时间
            for x in waiting_list:
                if route_name == x[0]:
                    waiting = x[1]
                    break
            else:  # 从原始数据查找
                for x in waiting_list:
                    for y in x[0]:
                        if route_name == y:
                            waiting = x[1]
                            break

            # 查找路线详细信息
            for z in routes:
                if z['name'] == route_name:
                    route = (z['number'] + ' ' +
                             route_name. split('||')[0]). strip()
                    route = route.replace('|', ' ')
                    next_id = None
                    # 查找下一站ID
                    if MTR_VER == 3:
                        sta_id = z['stations'][-1]. split('_')[0]  # 终点站
                        for q, x in enumerate(z['stations']):
                            if x. split('_')[0] == sta1_id and \
                                    q != len(z['stations']) - 1:  # 不是最后一站
                                next_id = z['stations'][q + 1]. split('_')[0]
                                break
                    else:
                        sta_id = z['stations'][-1]['id']
                        for q, x in enumerate(z['stations']):
                            if x['id'] == sta1_id and \
                                    q != len(z['stations']) - 1:
                                next_id = z['stations'][q + 1]['id']
                                break

                    # 处理环形路线
                    if z['circular'] in ['cw', 'ccw']:
                        sta_id = next_id  # 使用下一站作为方向

                    terminus_name: str = stations[sta_id]['name']
                    if terminus_name. count('|') == 0:  # 无分隔符
                        t1_name = t2_name = terminus_name
                    else:
                        t1_name = terminus_name. split('|')[0]  # 中文名
                        t2_name = terminus_name.split('|')[1]. replace('|',
                                                                      ' ')  # 英文名

                    # 处理方向显示
                    if z['circular'] == 'cw':  # 顺时针
                        if next_id is None:
                            t1_name = '(顺时针) ' + t1_name
                            t2_name += ' (Clockwise)'
                            terminus = (t1_name, t2_name)
                        else:
                            name1 = '(顺时针) 经由' + t1_name
                            name2 = f'(Clockwise) Via {t2_name}'
                            terminus = (True, name1, name2)
                    elif z['circular'] == 'ccw':  # 逆时针
                        if next_id is None:
                            t1_name = '(逆时针) ' + t1_name
                            t2_name += ' (Counterclockwise)'
                            terminus = (t1_name, t2_name)
                        else:
                            name1 = '(逆时针) 经由' + t1_name
                            name2 = f'(Counterclockwise) Via {t2_name}'
                            terminus = (True, name1, name2)
                    else:  # 非环形
                        terminus = (t1_name, t2_name)

                    color = hex(z['color']).lstrip('0x'). rjust(6, '0')  # 颜色代码
                    train_type = z['type']  # 列车类型
                    break
            else:  # 步行路线
                color = '000000'
                route = route_name
                terminus = (route_name. split('，用时')[0], 'Walk')  # 提取步行描述
                train_type = None

            color = '#' + color  # 颜色格式

            sep_waiting = None
            if route_name in intervals:  # 有间隔数据
                sep_waiting = int(intervals[route_name])

            # 创建路线数据元组
            r = (sta1_name, sta2_name, color, route, terminus, duration,
                 waiting, sep_waiting, train_type)

            # 避免重复添加相同路线段
            if len(each_route_time) > 0:
                old_r = each_route_time[-1]
                if old_r[:5] != r[:5] or \
                        round(old_r[5]) != round(r[5]):  # 不同路线或时间
                    each_route_time.append(r)

            if len(each_route_time) == 0:  # 第一条路线
                each_route_time.append(r)

        # 排序路线时间
        each_route_time.sort(key=lambda x: natural_keys(x[3]))  # 自然排序
        each_route_time. sort(key=itemgetter(5))  # 按时间排序
        every_route_time.extend(each_route_time)  # 添加到总列表

        each_route_time = []
        duration = 0
        waiting = 0

    end_ = stations[station_2]['name']
    if station_names[-1] != end_:
        station_names += end_  # 确保包含终点站

    # 返回格式化结果
    return ' ->\n'.join(station_names), shortest_distance, \
        waiting_time, shortest_distance - waiting_time, every_route_time


def generate_html(route_type: RouteType, every_route_time: list,
                 shortest_distance, riding_time, waiting_time,
                 version1, version2, DETAIL) -> str:
    '''
    生成HTML格式的路线显示
    '''
    # 格式化时间
    gm_full = gmtime(shortest_distance)
    gm_waiting = gmtime(waiting_time)
    gm_travelling = gmtime(riding_time)
    full_time = str(strftime('%H:%M:%S', gm_full))
    waiting_time_str = str(strftime('%H:%M:%S', gm_waiting))
    travelling_time = str(strftime('%H:%M:%S', gm_travelling))
    
    # 去除前导零
    if int(full_time.split(':', maxsplit=1)[0]) == 0:
        full_time = ''.join(full_time.split(':', maxsplit=1)[1:])
    if int(waiting_time_str.split(':', maxsplit=1)[0]) == 0:
        waiting_time_str = ''.join(waiting_time_str.split(':', maxsplit=1)[1:])
    if int(travelling_time.split(':', maxsplit=1)[0]) == 0:
        travelling_time = ''.join(travelling_time.split(':', maxsplit=1)[1:])
    
    html_parts = []
    
    # 添加时间信息
    html_parts.append('<div class="time-info">')
    if route_type == RouteType.IN_THEORY:
        html_parts.append(f'<p><strong>总用时 Total Time:</strong> {full_time}</p>')
    else:
        html_parts.append(f'<p><strong>总用时 Total Time:</strong> {full_time}</p>')
        html_parts.append(f'<p><strong>其中乘车时间 Travelling Time:</strong> {travelling_time}</p>')
        html_parts.append(f'<p><strong>其中等车时间 Waiting Time:</strong> {waiting_time_str}</p>')
    html_parts.append('</div>')
    
    # 添加路线步骤
    last_station = None
    for i, route_data in enumerate(every_route_time):
        station_from, station_to, color, route_name, terminus, duration, waiting, sep_waiting, train_type = route_data
        
        # 处理终点站显示
        if isinstance(terminus, tuple) and len(terminus) > 0:
            if terminus[0] is True:  # 环形路线
                terminus_display = ' '.join(terminus[1:])
            else:
                terminus_display = f"{terminus[0]} 方向 To {terminus[1]}"
        else:
            terminus_display = str(terminus)
        
        # 格式化时间
        duration_str = str(strftime('%M:%S', gmtime(duration)))
        waiting_str = str(strftime('%M:%S', gmtime(waiting)))
        
        # 如果是新起点站，显示车站
        if station_from != last_station:
            html_parts.append(f'<div class="route-step">')
            html_parts.append(f'<div class="station">🚉 {station_from}</div>')
            last_station = station_from
        else:
            html_parts.append(f'<div class="route-step" style="margin-left: 20px;">')
            html_parts.append(f'<div style="margin-bottom: 5px;">或</div>')
        
        # 路线信息
        html_parts.append(f'<div class="route-info">')
        html_parts.append(f'<div><strong>路线:</strong> {route_name}</div>')
        
        if train_type is not None:  # 不是步行
            html_parts.append(f'<div><strong>方向:</strong> {terminus_display}</div>')
            html_parts.append(f'<div><strong>乘车时间:</strong> {duration_str}</div>')
            
            if DETAIL and route_type == RouteType.WAITING and sep_waiting is not None:
                interval_str = str(strftime('%M:%S', gmtime(sep_waiting)))
                html_parts.append(f'<div><strong>等车时间:</strong> {waiting_str}</div>')
                html_parts.append(f'<div><strong>发车间隔:</strong> {interval_str}</div>')
            elif DETAIL and route_type == RouteType.WAITING:
                html_parts.append(f'<div><strong>等车时间:</strong> {waiting_str}</div>')
        else:  # 步行
            html_parts.append(f'<div><strong>步行时间:</strong> {duration_str}</div>')
        
        html_parts.append('</div>')  # 结束route-info
        html_parts.append('</div>')  # 结束route-step
    
    # 添加终点站
    if every_route_time:
        last_route = every_route_time[-1]
        html_parts.append(f'<div class="route-step">')
        html_parts.append(f'<div class="station">🚉 {last_route[1]}</div>')
        html_parts.append('</div>')
    
    # 添加版本信息
    html_parts.append('<div style="margin-top: 20px; font-size: 12px; color: #666;">')
    html_parts.append(f'<p>车站数据版本 Station data version: {version1}</p>')
    html_parts.append(f'<p>路线数据版本 Route data version: {version2}</p>')
    html_parts.append('</div>')
    
    return ''.join(html_parts)




def main(station1: str, station2: str, LINK: str,
         LOCAL_FILE_PATH, INTERVAL_PATH, BASE_PATH, PNG_PATH,
         MAX_WILD_BLOCKS: int = 1500,
         TRANSFER_ADDITION: dict[str, list[str]] = {},
         WILD_ADDITION: dict[str, list[str]] = {},
         STATION_TABLE: dict[str, str] = {},
         ORIGINAL_IGNORED_LINES: list = [], UPDATE_DATA: bool = False,
         GEN_ROUTE_INTERVAL: bool = False, IGNORED_LINES: list = [],
         AVOID_STATIONS: list = [], CALCULATE_HIGH_SPEED: bool = True,
         CALCULATE_BOAT: bool = True, CALCULATE_WALKING_WILD: bool = False,
         ONLY_LRT: bool = False, IN_THEORY: bool = False, DETAIL: bool = False,
         MTR_VER: int = 3, G=None, gen_image=True, show=False,
         cache=True) -> Union[str, bool, None]:
    '''
    主函数。可以在自己的代码中调用。
    输出：
    False -- 找不到路线
    None -- 车站名称错误，请重新输入
    其他 -- 元组 (图片对象, 生成图片的base64字符串)
    '''
    if MTR_VER not in [3, 4]:  # 检查MTR版本
        raise NotImplementedError('MTR_VER should be 3 or 4')

    # 初始化设置
    IGNORED_LINES += ORIGINAL_IGNORED_LINES  # 合并忽略的路线
    STATION_TABLE = {x.lower(): y.lower() for x, y in STATION_TABLE.items()}  # 标准化车站表
    if LINK.endswith('/index.html'):
        LINK = LINK.rstrip('/index.html')  # 清理链接

    # 获取或更新数据
    if UPDATE_DATA is True or (not os.path.exists(LOCAL_FILE_PATH)):
        if LINK == '':
            raise ValueError('Railway System Map link is empty')

        data = fetch_data(LINK, LOCAL_FILE_PATH, MTR_VER)  # 获取数据
    else:
        with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
            data = json.load(f)  # 加载本地数据

    # 生成路线间隔数据
    if GEN_ROUTE_INTERVAL is True or (not os.path.exists(INTERVAL_PATH)):
        if LINK == '':
            raise ValueError('Railway System Map link is empty')

        gen_route_interval(LOCAL_FILE_PATH, INTERVAL_PATH, LINK, MTR_VER)  # 生成间隔数据

    # 获取版本信息
    version1 = strftime('%Y%m%d-%H%M',
                        gmtime(os.path.getmtime(LOCAL_FILE_PATH)))  # 车站数据版本
    version2 = strftime('%Y%m%d-%H%M',
                        gmtime(os.path.getmtime(INTERVAL_PATH)))  # 路线数据版本

    # 确定路线类型
    if IN_THEORY is True:
        route_type = RouteType.IN_THEORY  # 理论路线
    else:
        route_type = RouteType.WAITING  # 实际路线

    # 创建图
    if G is None:
        G = create_graph(data, IGNORED_LINES, CALCULATE_HIGH_SPEED,
                         CALCULATE_BOAT, CALCULATE_WALKING_WILD, ONLY_LRT,
                         AVOID_STATIONS, route_type, ORIGINAL_IGNORED_LINES,
                         INTERVAL_PATH, version1, version2, LOCAL_FILE_PATH,
                         STATION_TABLE, WILD_ADDITION, TRANSFER_ADDITION,
                         MAX_WILD_BLOCKS, MTR_VER, cache)  # 创建图

    # 查找最短路线
    shortest_path, shortest_distance, waiting_time, riding_time, ert = \
        find_shortest_route(G, station1, station2,
                            data, STATION_TABLE, MTR_VER)

    if gen_image is False:  # 不生成图像
        return ert, shortest_distance

    if shortest_path in [False, None]:  # 无路径或错误
        return shortest_path

    # 使用新的HTML生成函数替代原来的图像生成
    return generate_html(route_type, ert, shortest_distance, riding_time,
                         waiting_time, version1, version2, DETAIL)

# 添加Flask路由
@app.route('/')
def index():
    '''显示主页面'''
    return render_template_string(HTML_TEMPLATE)

@app.route('/find-route', methods=['POST'])
def find_route():
    '''处理路径查找请求'''
    try:
        data = request.json
        station1 = data.get('startStation')
        station2 = data.get('endStation')
        MTR_VER = data.get('mtrVersion', 3)
        route_type_str = data.get('routeType', 'WAITING')
        CALCULATE_HIGH_SPEED = data.get('calculateHighSpeed', True)
        CALCULATE_BOAT = data.get('calculateBoat', True)
        CALCULATE_WALKING_WILD = data.get('calculateWalkingWild', False)
        ONLY_LRT = data.get('onlyLRT', False)
        DETAIL = data.get('detail', False)
        
        # 转换路线类型
        IN_THEORY = (route_type_str == 'IN_THEORY')
        
        # 这里需要设置你的实际文件路径和其他参数
        LINK = 'https://letsplay.minecrafttransitrailway.com/system-map'  # 设置为你的MTR地图链接
        link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
        LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
        INTERVAL_PATH = f'mtr-route-data-{link_hash}-{MTR_VER}.json'
        BASE_PATH = 'mtr_pathfinder_data'
        PNG_PATH = 'mtr_pathfinder_data'
        
        # 调用主函数
        result = main(
            station1=station1,
            station2=station2,
            LINK=LINK,
            LOCAL_FILE_PATH=LOCAL_FILE_PATH,
            INTERVAL_PATH=INTERVAL_PATH,
            BASE_PATH=BASE_PATH,
            PNG_PATH=PNG_PATH,
            MAX_WILD_BLOCKS=1500,
            TRANSFER_ADDITION={},
            WILD_ADDITION={},
            STATION_TABLE={},
            ORIGINAL_IGNORED_LINES=[],
            UPDATE_DATA=False,
            GEN_ROUTE_INTERVAL=False,
            IGNORED_LINES=[],
            AVOID_STATIONS=[],
            CALCULATE_HIGH_SPEED=CALCULATE_HIGH_SPEED,
            CALCULATE_BOAT=CALCULATE_BOAT,
            CALCULATE_WALKING_WILD=CALCULATE_WALKING_WILD,
            ONLY_LRT=ONLY_LRT,
            IN_THEORY=IN_THEORY,
            DETAIL=DETAIL,
            MTR_VER=MTR_VER,
            gen_image=True,
            show=False,
            cache=True
        )
        
        if result is False:
            return jsonify({'success': False, 'error': '找不到路线'})
        elif result is None:
            return jsonify({'success': False, 'error': '车站名称错误，请重新输入'})
        else:
            return jsonify({'success': True, 'html': result})
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'发生错误: {str(e)}'})





def run():
    '''运行Flask应用'''
    print("启动MTR路径查找器Web服务...")
    print("访问 http://localhost:5000 使用路径查找功能")
    app.run(debug=True, host='0.0.0.0', port=5000)


if __name__ == '__main__':
    run()  # 程序入口点
