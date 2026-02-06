'''   
Minecraft Transit Railway寻路程序
Find paths between two stations for Minecraft Transit Railway. 
'''

#禁用SSL验证 (Python 3.13+) - 必须在导入requests之前设置
import os   #操作系统功能模块
os.environ['CURL_CA_BUNDLE'] = ''   #禁用CURL证书验证
os.environ['SSL_CERT_FILE'] = ''   #禁用SSL证书文件验证

#抑制SSL警告
import urllib3   #HTTP连接池和SSL控制
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)   #禁用SSL警告

#导入各种必要的库
from difflib import SequenceMatcher   #用于字符串相似度比较
from enum import Enum   #枚举类型定义
from math import gcd, sqrt   #数学函数：最大公约数、平方根
from operator import itemgetter   #用于排序操作
from statistics import median_low   #统计学中位数计算
from threading import Thread, BoundedSemaphore   #多线程和信号量控制
from time import gmtime, strftime, time   #时间处理函数
from typing import Union   #类型提示支持
from queue import Queue   #队列数据结构
import hashlib   #哈希算法库
import json   #JSON数据处理
import pickle   #Python对象序列化
import re   #正则表达式处理

from datetime import datetime, timedelta, timezone   #用于处理日期和时间
from statistics import mode   #用于计算众数
import random   #用于生成随机数

#第三方库导入
from opencc import OpenCC   #简繁中文转换工具
import networkx as nx   #图论和网络分析库
import requests   #HTTP请求库

#添加Flask相关导入
from flask import Flask, render_template_string, request, jsonify, session   #Flask Web框架组件

#创建Flask应用实例
app = Flask(__name__)
app.secret_key = 'mtr-pathfinder-secret-key-2024'   #用于session加密的密钥

#启动时自动检查并更新数据
def check_and_auto_update_data():
   '''
   检查是否有车站数据，如果没有则根据环境变量决定是否自动更新
   '''
   try:
      LINK = config.get('LINK', '')
      MTR_VER = config.get('MTR_VER', 4)
      
      if not LINK:
         print("未配置地图链接，跳过自动数据更新")
         return False
      
      link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest() if LINK else ''
      LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
      INTERVAL_PATH = f'mtr-route-data-{link_hash}-{MTR_VER}.json'
      
      #检查车站数据文件是否存在
      if not os.path.exists(LOCAL_FILE_PATH):
         #检查环境变量是否允许自动更新
         auto_update = os.environ.get('AUTO_UPDATE_WHEN_EMPTY', 'False')
         if auto_update.lower() in ('true', '1', 'yes'):
            print(f"未找到车站数据文件，正在自动更新...")
            return update_mtr_data(LINK, MTR_VER, LOCAL_FILE_PATH, INTERVAL_PATH, '.')
         else:
            print("未找到车站数据文件，但AUTO_UPDATE_WHEN_EMPTY环境变量未设置为True，跳过自动更新")
            return False
      else:
         print("车站数据文件已存在，跳过自动更新")
         return False
   except Exception as e:
      print(f"自动数据更新检查失败: {e}")
      return False

#根据环境变量决定是否自动更新数据
AUTO_UPDATE_WHEN_EMPTY = os.environ.get('AUTO_UPDATE_WHEN_EMPTY', 'False')
if AUTO_UPDATE_WHEN_EMPTY.lower() in ('true', '1', 'yes'):
   print("检测到AUTO_UPDATE_WHEN_EMPTY环境变量，启用启动时自动数据更新...")
   check_and_auto_update_data()

#=================== 数据更新相关函数 ====================
def update_mtr_data(LINK: str, MTR_VER: int, LOCAL_FILE_PATH: str, INTERVAL_PATH: str, BASE_PATH: str) -> bool:
   '''   
   更新MTR数据（车站和线路数据）
   '''
   try:
      os.makedirs(BASE_PATH, exist_ok=True)   #创建基础目录
      
      #   #更新车站数据
      fetch_data(LINK, LOCAL_FILE_PATH, MTR_VER)   #获取车站和线路数据
      
      #   #验证车站数据文件已创建
      if not os.path.exists(LOCAL_FILE_PATH):
         raise Exception(f"车站数据文件创建失败: {LOCAL_FILE_PATH}")
      
      #   #更新线路间隔数据
      gen_route_interval(LOCAL_FILE_PATH, INTERVAL_PATH, LINK, MTR_VER)   #生成路线间隔数据
      
      #   #验证间隔数据文件已创建
      if not os.path.exists(INTERVAL_PATH):
         raise Exception(f"路线间隔数据文件创建失败: {INTERVAL_PATH}")
      
      return True   #更新成功
   except Exception as e:
      print(f"数据更新错误: {e}")   #打印错误信息
      return False   #更新失败

#=================== 数据更新函数结束 ====================

SERVER_TICK: int = 20   #服务器游戏刻速率（每秒20刻）

DEFAULT_AVERAGE_SPEED: dict = {   #默认平均速度配置
   'train_normal': 14,   #普通列车平均速度
   'train_light_rail': 11,   #轻轨列车平均速度
   'train_high_speed': 40,   #高速列车平均速度
   'boat_normal': 10,   #普通船只平均速度
   'boat_light_rail': 10,   #轻轨船只平均速度
   'boat_high_speed': 13,   #高速船只平均速度
   'cable_car_normal': 8,   #缆车平均速度
   'airplane_normal': 70   #飞机平均速度
}
RUNNING_SPEED: int = 5.612   #列车运行速度（格/刻）
TRANSFER_SPEED: int = 4.317   #换乘步行速度（格/刻）
WILD_WALKING_SPEED: int = 2.25   #野外步行速度（格/刻）

ROUTE_INTERVAL_DATA = Queue()   #路线间隔数据队列
semaphore = BoundedSemaphore(25)   #限制并发数的信号量
original = {}   #存储原始路线数据
tmp_names = {}   #临时名称映射
opencc1 = OpenCC('s2t')   #简体中文转繁体中文
try:
    opencc2 = OpenCC('t2jp')   #繁体中文转日文汉字
    OPENCC2_AVAILABLE = True   #标记opencc2是否可用
except Exception:
    OPENCC2_AVAILABLE = False   #opencc-python-reimplemented不支持t2jp转换
opencc3 = OpenCC('t2s')   #繁体中文转简体中文
opencc4 = OpenCC('jp2t')  #日文汉字转繁体中文


def fetch_data(LINK: str, LOCAL_FILE_PATH: str, MTR_VER: int) -> str:
    '''
    获取所有路线数据和车站数据
    '''
    # 创建不验证SSL的HTTP连接池
    http = urllib3.PoolManager(
        cert_reqs='CERT_NONE',
        ssl_version='PROTOCOL_TLS_CLIENT'
    )
    
    if MTR_VER == 3:
        link = LINK.rstrip('/') + '/data'
        response = http.request('GET', link)
        if response.status != 200:
            raise Exception(f"获取数据失败，HTTP状态码: {response.status}")
        data = json.loads(response.data.decode('utf-8'))
        # MTR 3数据直接保存，不做转换
        if not data or (isinstance(data, list) and len(data) == 0):
            raise Exception("获取的数据为空")
        if isinstance(data, list) and len(data) > 0 and 'stations' in data[0]:
            with open(LOCAL_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return LOCAL_FILE_PATH
        else:
            raise Exception("MTR 3数据格式不正确")
    else:
        # MTR_VER == 4
        link = LINK.rstrip('/') + '/mtr/api/map/stations-and-routes?dimension=0'
        response = http.request('GET', link)
        if response.status != 200:
            raise Exception(f"获取数据失败，HTTP状态码: {response.status}")
        response_data = json.loads(response.data.decode('utf-8'))
        if 'data' not in response_data:
            raise Exception("获取数据失败，返回数据中没有'data'字段")
        data = response_data['data']

        data_new = {'routes': [], 'stations': {}}
        i = 0
        for d in data['stations']:
            d['station'] = hex(i)[2:]
            data_new['stations'][d['id']] = d
            i += 1

        x_dict = {x['id']: [] for x in data['stations']}
        z_dict = {x['id']: [] for x in data['stations']}
        for route in data['routes']:
            if route['circularState'] == 'CLOCKWISE':
                route['circular'] = 'cw'
            elif route['circularState'] == 'ANTICLOCKWISE':
                route['circular'] = 'ccw'
            else:
                route['circular'] = ''

            route['durations'] = [round(x / 1000) for x in route['durations']]
            for station in route['stations']:
                x_dict[station['id']] += [station['x']]
                z_dict[station['id']] += [station['z']]

            data_new['routes'].append(route)

        for station in data['stations']:
            x_list = x_dict[station['id']]
            z_list = z_dict[station['id']]
            if len(x_list) == 0:
                continue

            data_new['stations'][station['id']]['x'] = sum(x_list) / len(x_list)
            data_new['stations'][station['id']]['z'] = sum(z_list) / len(z_list)

        data = [data_new]

    # 验证数据有效性
    if not data or (isinstance(data, list) and len(data) == 0):
        raise Exception("获取的数据为空")
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and 'stations' not in data[0]:
        raise Exception("获取的数据格式不正确，缺少'stations'字段")

    # 保存数据
    with open(LOCAL_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    return LOCAL_FILE_PATH


#=================== 时刻表相关函数 ====================
def tt_convert_time(t, use_second=False):
    '''
    将秒数转换为时间字符串
    
    Args:
        t: 时间（秒）
        use_second: 是否包含秒，默认为False
        
    Returns:
        格式化的时间字符串
    '''
    if use_second:
        hour = str(t // (60 * 60)).rjust(2, '0')
        minute = str((t % 3600) // 60).rjust(2, '0')
        second = str(t % 60).rjust(2, '0')
        return ':'.join([hour, minute, second])
    else:
        hour = t // (60 * 60)
        minute = (t % 3600) // 60
        second = t % 60
        
        if second >= 60:
            minute += 1
        if minute >= 60:
            minute -= 60
            hour += 1
        if hour == 24:
            hour = 0
        
        hour = str(hour).rjust(2, '0')
        minute = str(minute).rjust(2, '0')
        return ':'.join([hour, minute])


def tt_get_close_matches(words, possibilities, cutoff=0.2):
    '''
    查找与给定单词最相似的匹配项
    '''
    result = [(-1, None)]
    s = SequenceMatcher()
    
    for word in words:
        s.set_seq2(word)
        for x, y in possibilities:
            s.set_seq1(x)
            if s.real_quick_ratio() >= cutoff and s.quick_ratio() >= cutoff:
                ratio = s.ratio()
                if ratio >= cutoff:
                    result.append((ratio, y))

    return max(result)[1]


def tt_station_name_to_id(data, sta, fuzzy_compare=True):
    '''
    将车站名称转换为车站ID
    
    Args:
        data: 包含车站信息的数据字典
        sta: 车站名称
        
    Returns:
        车站ID，如果未找到则返回None
    '''
    sta = sta.lower()
    tra1 = tt_opencc1.convert(sta)
    sta_try = [sta, tra1, tt_opencc2.convert(tra1)]

    all_names = []
    stations = data[0]['stations']
    output = None
    has_station = False
    
    for station_id, station_dict in stations.items():
        s_1 = station_dict['name']
        if 'x' in station_dict and 'z' in station_dict:
            all_names.append((s_1, station_id))

        s_split = station_dict['name'].split('|')
        s_2_2 = s_split[-1]
        s_2 = s_2_2.split('/')[-1]
        s_3 = s_split[0]
        
        for st in sta_try:
            if st in (s_1.lower(), s_2.lower(), s_2_2.lower(), s_3.lower()):
                has_station = True
                output = station_id
                break

    if has_station is False and fuzzy_compare:
        output = tt_get_close_matches(sta_try, all_names)

    return output


def tt_route_name_to_id(data, route_name):
    '''
    将线路名称转换为线路ID
    
    Args:
        data: 包含线路信息的数据字典
        route_name: 线路名称
        
    Returns:
        包含线路ID的列表
    '''
    for route in data[0]['routes']:
        if route_name == route['id']:
            return [route_name]

    route_name = route_name.lower()
    result = []
    
    for route in data[0]['routes']:
        output = route['id']
        n = route['name']
        number = route.get('number', '')
        
        route_names = [n, n.split('|')[0]]
        
        if ('||' in n and n.count('|') > 2) or ('||' not in n and n.count('|') > 0):
            eng_name = n.split('|')[1].split('|')[0]
            if eng_name != '':
                route_names.append(eng_name)

        if number not in ['', ' ']:
            for tmp_name in route_names[1:]:
                route_names.append(tmp_name + ' ' + number)

        for x in route_names:
            x = x.lower().strip()
            if x == route_name:
                result.append(output)
                continue

            if x.isascii():
                continue

            simp1 = tt_opencc3.convert(x)
            if simp1 == route_name:
                result.append(output)
                continue

            simp2 = tt_opencc3.convert(tt_opencc4.convert(x))
            if simp2 == route_name:
                result.append(output)
                continue

    return result


def tt_station_short_id_to_id(data, short_id):
    '''
    将车站短ID转换为车站ID
    
    Args:
        data: 包含车站信息的数据字典
        short_id: 车站短ID（整数形式）
        
    Returns:
        车站ID，如果未找到则返回None
    '''
    short_id = hex(short_id)[2:]
    stations = data[0]['stations']
    output = None
    
    for station_id, station_dict in stations.items():
        if short_id == station_dict.get('station', ''):
            output = station_id
            break

    return output


#=================== 时刻表查询功能 ====================
def tt_get_timetable(data, station_name, route_name, use_second=False):
    '''
    获取指定车站和线路的时刻表
    
    Args:
        data: 包含车站信息的数据字典
        station_name: 车站名称
        route_name: 线路名称
        use_second: 是否包含秒
        
    Returns:
        包含(线路ID, 时间)元组的列表
    '''
    station_id = tt_station_name_to_id(data, station_name)
    if station_id is None:
        return []
    
    route_ids = tt_route_name_to_id(data, route_name)
    if not route_ids:
        return []
    
    output = []
    for route_id in route_ids:
        for route in data[0]['routes']:
            if route['id'] != route_id:
                continue
            
            route_stations = route['stations']
            station_ids = [s['id'] for s in route_stations]
            
            if station_id not in station_ids:
                continue
            
            idx = station_ids.index(station_id)
            if idx >= len(route_stations):
                continue
            
            durations = route.get('durations', [])
            if idx < len(durations):
                travel_time = durations[idx]
            else:
                travel_time = 0
            
            stations = data[0]['stations']
            next_station = None
            prev_station = None
            if idx < len(route_stations) - 1:
                next_station = route_stations[idx + 1]
            if idx > 0:
                prev_station = route_stations[idx - 1]
            
            route_name_formatted = route['name'].replace('||', ' ').replace('|', ' ')
            
            output.append({
                'route_id': route['id'],
                'route_name': route_name_formatted,
                'route_color': route.get('color', 0),
                'route_type': route.get('type', 'train_normal'),
                'circular': route.get('circular', ''),
                'station_position': idx + 1,
                'total_stations': len(route_stations),
                'travel_time': travel_time,
                'next_station': {
                    'id': next_station['id'] if next_station else None,
                    'name': stations.get(next_station['id'], {}).get('name', '').split('|')[0] if next_station else None
                } if next_station else None,
                'prev_station': {
                    'id': prev_station['id'] if prev_station else None,
                    'name': stations.get(prev_station['id'], {}).get('name', '').split('|')[0] if prev_station else None
                } if prev_station else None
            })
            break
    
    return output


def tt_get_train_info(data, station, train_id):
    '''
    获取指定列车的详细信息
    
    Args:
        data: 包含车站和线路信息的数据字典
        station: 车站名称或短ID
        train_id: 列车ID
        
    Returns:
        包含(线路名称, 车站列表, 状态信息)的元组，或None/False表示失败
    '''
    station_id = None
    try:
        sta_short_id = int(station)
        station_id = tt_station_short_id_to_id(data, sta_short_id)
    except ValueError:
        station_id = tt_station_name_to_id(data, station)
    
    if station_id is None:
        return None
    
    return None


def tt_get_station_directions(data, station_name):
    '''
    获取指定车站的线路方向信息（换乘信息）
    
    Args:
        data: 包含车站和线路信息的数据字典
        station_name: 车站名称
        
    Returns:
        包含方向分组的列表，每个元素包含同方向线路的名称列表，或None表示失败
    '''
    station_id = tt_station_name_to_id(data, station_name)
    if station_id is None:
        return None
    
    stations = data[0]['stations']
    routes = data[0]['routes']
    
    station_info = stations.get(station_id, {})
    station_name_formatted = station_info.get('name', station_name).split('|')[0]
    
    route_groups = []
    processed_routes = set()
    
    for route in routes:
        route_id = route['id']
        if route_id in processed_routes:
            continue
        
        route_stations = route['stations']
        station_ids = [s['id'] for s in route_stations]
        
        if station_id not in station_ids:
            continue
        
        idx = station_ids.index(station_id)
        if idx >= len(route_stations):
            continue
        
        if idx == len(station_ids) - 1:
            continue
        
        route_name = route['name'].replace('||', ' ').replace('|', ' ')
        
        route_data = {
            'id': route_id,
            'name': route_name,
            'color': route.get('color', 0),
            'type': route.get('type', 'train_normal'),
            'circular': route.get('circular', '')
        }
        
        next_station = None
        last_station_name = None
        if route.get('circularState') == 'CLOCKWISE':
            route_data['direction'] = '顺时针环线'
            route_data['destination'] = '顺时针方向'
        elif route.get('circularState') == 'ANTICLOCKWISE':
            route_data['direction'] = '逆时针环线'
            route_data['destination'] = '逆时针方向'
        else:
            next_station = route_stations[idx + 1]
            next_station_name = stations.get(next_station['id'], {}).get('name', '').split('|')[0]
            route_data['direction'] = next_station_name
            route_data['destination'] = next_station_name
            
            last_station = route_stations[-1]
            last_station_full = stations.get(last_station['id'], {}).get('name', '终点站').split('|')[0]
            route_data['last_station'] = last_station_full
        
        route_groups.append(route_data)
        processed_routes.add(route_id)
    
    return {
        'station_id': station_id,
        'station_name': station_name_formatted,
        'routes': route_groups,
        'total_routes': len(route_groups)
    }


def tt_get_all_routes_at_station(data, station_name):
    '''
    获取经过指定车站的所有线路
    
    Args:
        data: 包含车站和线路信息的数据字典
        station_name: 车站名称
        
    Returns:
        包含线路信息的列表，每个元素包含线路名称、方向和终点站
    '''
    station_id = tt_station_name_to_id(data, station_name)
    if station_id is None:
        return None
    
    stations = data[0]['stations']
    routes = data[0]['routes']
    
    station_info = stations.get(station_id, {})
    station_name_formatted = station_info.get('name', station_name).split('|')[0]
    
    route_list = []
    
    for route in routes:
        route_stations = route['stations']
        station_ids = [s['id'] for s in route_stations]
        
        if station_id not in station_ids:
            continue
        
        idx = station_ids.index(station_id)
        
        route_name = route['name'].replace('||', ' ').replace('|', ' ')
        
        if route.get('circularState') == 'CLOCKWISE':
            direction = '顺时针'
            destination = '顺时针环线'
        elif route.get('circularState') == 'ANTICLOCKWISE':
            direction = '逆时针'
            destination = '逆时针环线'
        else:
            if idx < len(route_stations) - 1:
                next_station = route_stations[idx + 1]
                direction = stations.get(next_station['id'], {}).get('name', '').split('|')[0]
            else:
                direction = '终点'
            
            last_station = route_stations[-1]
            destination = stations.get(last_station['id'], {}).get('name', '终点站').split('|')[0]
        
        route_list.append({
            'id': route['id'],
            'name': route_name,
            'color': route.get('color', 0),
            'type': route.get('type', 'train_normal'),
            'position': idx + 1,
            'total_stations': len(route_stations),
            'direction': direction,
            'destination': destination
        })
    
    return {
        'station_id': station_id,
        'station_name': station_name_formatted,
        'routes': route_list,
        'total': len(route_list)
    }


#   #HTML模板定义
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTR路径查找器</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        /* 全局样式 */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --primary-color: #4a90e2;
            --secondary-color: #50e3c2;
            --accent-color: #f5a623;
            --danger-color: #d0021b;
            --success-color: #7ed321;
            --light-gray: #f8f9fa;
            --medium-gray: #e9ecef;
            --dark-gray: #6c757d;
            --text-color: #333;
            --shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            --shadow-hover: 0 6px 20px rgba(0, 0, 0, 0.15);
            --border-radius: 8px;
            --transition: all 0.3s ease;
        }
        
        body {
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        /* 容器 */
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            overflow: hidden;
            animation: fadeIn 0.5s ease;
        }
        
        /* 头部 */
        .header {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 700;
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .header-nav {
            margin-top: 20px;
            display: flex;
            justify-content: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .header-nav a {
            color: white;
            text-decoration: none;
            padding: 8px 20px;
            border: 2px solid rgba(255, 255, 255, 0.5);
            border-radius: 25px;
            transition: all 0.3s ease;
            font-weight: 500;
            font-size: 0.95rem;
        }
        
        .header-nav a:hover {
            background: rgba(255, 255, 255, 0.2);
            border-color: white;
        }
        
        /* 内容区 */
        .content {
            padding: 30px;
        }
        
        /* 表单样式 */
        .form-section {
            margin-bottom: 25px;
        }
        
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 12px;
        }
        
        .form-group {
            margin-bottom: 12px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 4px;
            font-weight: 600;
            color: var(--text-color);
            font-size: 0.9rem;
        }
        
        .form-group input[type="text"],
        .form-group select {
            width: 100%;
            padding: 8px 12px;
            border: 2px solid var(--medium-gray);
            border-radius: 6px;
            font-size: 0.95rem;
            transition: var(--transition);
            background: var(--light-gray);
        }
        
        .form-group input[type="text"]:focus,
        .form-group select:focus {
            outline: none;
            border-color: var(--primary-color);
            background: white;
            box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
        }
        
        .shortcode-hint {
            font-size: 0.75rem;
            color: rgba(0, 0, 0, 0.6);
            margin-top: 4px;
        }
        
        .form-group.full-width {
            grid-column: 1 / -1;
        }
        
        .route-type-toggle {
            display: flex;
            position: relative;
            width: 100%;
            max-width: 360px;
            margin: 12px 0;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            padding: 4px;
        }
        
        .route-type-toggle input[type="radio"] {
            display: none;
        }
        
        .route-type-toggle label {
            flex: 1;
            text-align: center;
            padding: 8px 12px;
            color: rgba(255, 255, 255, 0.7);
            cursor: pointer;
            transition: all 0.3s ease;
            z-index: 1;
            font-weight: 500;
            font-size: 0.9rem;
            border-radius: 6px;
            min-height: 38px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .toggle-slider {
            position: absolute;
            top: 4px;
            left: 4px;
            width: calc(50% - 4px);
            height: calc(100% - 8px);
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 6px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 0;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
        }
        
        .route-type-toggle input[type="radio"]:checked + label {
            color: #fff;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        }
        
        .route-type-labels {
            display: flex;
            justify-content: center;
            gap: 60px;
            max-width: 360px;
            margin-top: 8px;
            font-size: 0.75rem;
            color: rgba(0, 0, 0, 0.5);
        }
        
        .route-type-labels span {
            min-width: 120px;
            text-align: center;
        }
        
        /* 复选框组 */
        .checkbox-group {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }
        
        .checkbox-item {
            display: flex;
            align-items: center;
            cursor: pointer;
            transition: var(--transition);
            padding: 4px 8px;
            border-radius: var(--border-radius);
            background: var(--light-gray);
        }
        
        .checkbox-item:hover {
            background: var(--medium-gray);
            transform: translateY(-2px);
        }
        
        .checkbox-item:hover {
            background: var(--medium-gray);
            transform: translateY(-2px);
        }
        
        .checkbox-item input[type="checkbox"] {
            margin-right: 8px;
            transform: scale(1.2);
            accent-color: var(--primary-color);
        }
        
        /* 按钮样式 */
        .btn {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: var(--border-radius);
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            box-shadow: var(--shadow);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-hover);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        /* 加载状态 */
        .loading {
            text-align: center;
            padding: 30px;
            display: none;
            background: var(--light-gray);
            border-radius: var(--border-radius);
            margin-top: 20px;
        }
        
        .loading::after {
            content: "";
            display: inline-block;
            width: 30px;
            height: 30px;
            border: 3px solid var(--medium-gray);
            border-top-color: var(--primary-color);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-left: 10px;
            vertical-align: middle;
        }
        
        /* 结果区域 */
        .result {
            margin-top: 25px;
            padding: 25px;
            border-radius: var(--border-radius);
            background: var(--light-gray);
            display: none;
            animation: slideUp 0.5s ease;
        }
        
        /* 时间信息 */
        .time-info {
            background: linear-gradient(135deg, #e3f2fd, #bbdefb);
            padding: 10px 12px;
            border-radius: 6px;
            margin-bottom: 8px;
            box-shadow: var(--shadow);
        }
        
        .time-info h3 {
            margin-bottom: 6px;
            color: var(--primary-color);
            font-size: 0.95rem;
        }
        
        .time-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 8px;
        }
        
        .time-item {
            text-align: center;
        }
        
        .time-item strong {
            display: block;
            font-size: 1.2rem;
            color: var(--primary-color);
            margin-bottom: 1px;
        }
        
        .time-item span {
            color: var(--dark-gray);
            font-size: 0.75rem;
        }
        
        /* 路线步骤 */
        .route-step {
            background: white;
            border-radius: var(--border-radius);
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
            transition: var(--transition);
            border-left: 4px solid var(--primary-color);
        }
        
        .route-step:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-hover);
        }
        
        .route-step.alternative {
            margin-left: 30px;
            border-left-color: var(--accent-color);
        }
        
        .station {
            font-weight: 700;
            font-size: 1.2rem;
            color: var(--text-color);
            margin-bottom: 15px;
            display: flex;
            align-items: center;
        }
        
        .station::before {
            content: "🚉";
            margin-right: 10px;
            font-size: 1.4rem;
        }
        
        .route-info {
            background: var(--light-gray);
            padding: 15px;
            border-radius: var(--border-radius);
            margin-bottom: 15px;
        }
        
        .route-info div {
            margin-bottom: 8px;
            display: flex;
            align-items: center;
        }
        
        .route-info div:last-child {
            margin-bottom: 0;
        }
        
        .route-info strong {
            min-width: 80px;
            color: var(--dark-gray);
            font-size: 0.9rem;
        }
        
        /* 分隔线 */
        .divider {
            display: inline;
            margin-right: 8px;
            color: var(--dark-gray);
            font-style: italic;
            font-weight: 600;
        }
        
        /* 错误信息 */
        .error {
            color: var(--danger-color);
            background-color: #ffebee;
            padding: 15px;
            border-radius: var(--border-radius);
            margin-top: 20px;
            border-left: 4px solid var(--danger-color);
            box-shadow: var(--shadow);
        }
        
        /* 版本信息 */
        .version-info {
            margin-top: 25px;
            padding: 15px;
            background: var(--light-gray);
            border-radius: var(--border-radius);
            font-size: 0.9rem;
            color: var(--dark-gray);
            text-align: center;
        }
        
        /* 动画 */
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes spin {
            to {
                transform: rotate(360deg);
            }
        }
        
        /* 响应式设计 */
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            
            .header {
                padding: 20px;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .content {
                padding: 20px;
            }
            
            .form-row {
                grid-template-columns: 1fr;
                gap: 10px;
            }
            
            .checkbox-group {
                flex-direction: column;
                gap: 6px;
            }
            
            .checkbox-item {
                width: 100%;
            }
            
            .time-grid {
                grid-template-columns: 1fr;
            }
            
            .route-step.alternative {
                margin-left: 15px;
            }
        }
        
        /* 交通类型图标样式 */
        .transport-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: auto;
            height: auto;
            border-radius: 0;
            margin-right: 4px;
            font-size: 14px;
            background: transparent !important;
            color: inherit !important;
        }
        
        /* 路线颜色指示器 */
        .route-color-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 2px;
            margin-right: 6px;
            vertical-align: middle;
        }
        
        /* 路线步骤连接线 */
        .route-connector {
            position: absolute;
            left: 19px;
            top: 24px;
            bottom: -16px;
            width: 2px;
            background: #e0e0e0;
            z-index: 0;
        }
        
        .route-step {
            position: relative;
            background: white;
            border-radius: 6px;
            padding: 8px 12px;
            margin-bottom: 4px;
            box-shadow: var(--shadow);
            transition: var(--transition);
            border-left: 4px solid var(--primary-color);
            z-index: 1;
        }
        
        .route-step:hover {
            transform: translateY(-1px);
            box-shadow: var(--shadow-hover);
        }
        
        .route-step.alternative {
            margin-left: 24px;
            border-left-color: var(--accent-color);
        }
        
        .route-step .station {
            position: relative;
            font-weight: 600;
            font-size: 1rem;
            color: var(--text-color);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            padding-left: 24px;
        }
        
        .route-step .station::before {
            content: "";
            position: absolute;
            left: 0;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 2px solid #333;
            background: white;
            z-index: 2;
        }
        
        .route-step:first-child .station::before,
        .route-step.start-station .station::before {
            border-color: var(--success-color);
        }
        
        .route-step:last-child .station::before,
        .route-step.end-station .station::before {
            border-color: var(--danger-color);
        }
        
        /* 路线标签 */
        .route-tag {
            display: inline-flex;
            align-items: center;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-right: 6px;
            margin-bottom: 6px;
        }
        
        .route-tag .route-name {
            margin-left: 4px;
        }
        
        /* 时间详情卡片 */
        .time-detail {
            display: flex;
            align-items: center;
            padding: 2px 6px;
            background: var(--light-gray);
            border-radius: 4px;
            margin-top: 2px;
            font-size: 0.85rem;
        }
        
        .time-detail .time-value {
            font-weight: 600;
            color: var(--primary-color);
            margin-left: 4px;
        }
        
        /* 方向指示 */
        .direction-indicator {
            display: flex;
            align-items: center;
            padding: 2px 6px;
            background: linear-gradient(135deg, #e3f2fd, #bbdefb);
            border-radius: 4px;
            margin: 2px 0;
            font-size: 0.85rem;
            color: #1565c0;
        }
        
        .direction-indicator::before {
            content: "→";
            margin-right: 4px;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MTR路径查找器</h1>
            <p>为Minecraft Transit Railway打造的智能路径规划系统</p>
            <div class="header-nav">
                <a href="/stations">🚉 车站列表</a>
                <a href="/routes">🛤️ 线路列表</a>
                <a href="/admin">⚙️ 控制台</a>
            </div>
        </div>
        
        <div class="content">
            <form id="routeForm">
                <div class="form-section">
                    <h3>基本信息</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="startStation">起点站</label>
                            <input type="text" id="startStation" name="startStation" required placeholder="输入起点站名称">
                        </div>
                        <div class="form-group">
                            <label for="endStation">终点站</label>
                            <input type="text" id="endStation" name="endStation" required placeholder="输入终点站名称">
                        </div>
                    </div>
                    
                    <div class="form-row">
                        <div class="form-group full-width">
                            <label for="shortCode">简码</label>
                            <input type="text" id="shortCode" name="shortCode" placeholder="/路线 出发站;到达站;详细;理论;越野;禁高铁;禁船;仅轻铁">
                            <div class="shortcode-hint">格式: /路线 出发站;到达站;[详细];[理论];[越野];[禁高铁];[禁船];[仅轻铁];[禁路线;路线;...];[禁车站;车站;...]</div>
                        </div>
                    </div>
                    
                    <div class="form-row">
                        <div class="form-group">
                            <label for="avoidStations">禁车站 (用逗号或顿号分隔)</label>
                            <input type="text" id="avoidStations" name="avoidStations" placeholder="例：尖沙咀,中环,旺角">
                        </div>
                        <div class="form-group">
                            <label for="avoidRoutes">禁路线 (用逗号或顿号分隔)</label>
                            <input type="text" id="avoidRoutes" name="avoidRoutes" placeholder="例：荃湾线,观塘线">
                        </div>
                    </div>
                    
                    <div class="form-row">
                        <div class="form-group">
                            <label for="onlyRoutes">仅路线 (用逗号或顿号分隔，留空则不限制)</label>
                            <input type="text" id="onlyRoutes" name="onlyRoutes" placeholder="例：荃湾线,观塘线">
                        </div>
                    </div>
                </div>
                
                <div class="form-section">
                    <h3>路线设置</h3>
                    <div class="route-type-toggle">
                        <input type="radio" id="routeTypeWaiting" name="routeType" value="WAITING">
                        <label for="routeTypeWaiting">实际路线</label>
                        <input type="radio" id="routeTypeTheory" name="routeType" value="IN_THEORY">
                        <label for="routeTypeTheory">理论路线</label>
                        <div class="toggle-slider"></div>
                    </div>
                    <div class="route-type-labels">
                        <span>考虑等车时间</span>
                        <span>不考虑等车时间</span>
                    </div>
                </div>
                
                <div class="form-section">
                    <h3>交通方式</h3>
                    <div class="checkbox-group">
                        <div class="checkbox-item">
                            <input type="checkbox" id="banHighSpeed" name="banHighSpeed">
                            <span>禁高铁</span>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="banBoat" name="banBoat">
                            <span>禁船</span>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="calculateWalkingWild" name="calculateWalkingWild">
                            <span>越野</span>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="onlyLRT" name="onlyLRT">
                            <span>仅轻铁</span>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="detail" name="detail">
                            <span>显示详细信息</span>
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="btn">查找路径</button>
            </form>
            
            <div class="loading" id="loading">
                <span>正在计算路径，请稍候</span>
            </div>
            
            <div class="result" id="result">
                <!-- 结果将在这里动态显示 -->
            </div>
        </div>
    </div>

    <script>
        // 简码解析函数
        function parseShortCode(code) {
            if (!code || !code.startsWith('/路线') && !code.startsWith('/路线 ')) {
                return null;
            }
            
            // 移除开头的/路线
            let rest = code.replace(/^\/路线\s*/, '');
            
            // 用分号分割（支持中英文分号）
            let parts = rest.split(/[;；]/).map(p => p.trim()).filter(p => p);
            
            if (parts.length < 2) {
                return null;
            }
            
            let result = {
                startStation: parts[0],
                endStation: parts[1],
                routeType: 'WAITING',
                banHighSpeed: false,
                banBoat: false,
                calculateWalkingWild: false,
                onlyLRT: false,
                detail: false,
                avoidRoutes: '',
                avoidStations: ''
            };
            
            // 解析后续参数
            for (let i = 2; i < parts.length; i++) {
                let param = parts[i].toLowerCase();
                
                if (param === '详细' || param === 'detail') {
                    result.detail = true;
                } else if (param === '理论' || param === 'theory' || param === '实时') {
                    result.routeType = 'IN_THEORY';
                } else if (param === '越野' || param === 'wild') {
                    result.calculateWalkingWild = true;
                } else if (param === '禁高铁' || param === 'nohsr' || param === 'banhsr') {
                    result.banHighSpeed = true;
                } else if (param === '禁船' || param === 'noboat' || param === 'banboat') {
                    result.banBoat = true;
                } else if (param === '仅轻铁' || param === 'onlylrt' || param === 'lrt') {
                    result.onlyLRT = true;
                } else if (param.startsWith('禁路线') || param.startsWith('banroute') || param.startsWith('noroute') || param.startsWith('ban-route')) {
                    // 格式: 禁路线;路线1;路线2;... 或 禁路线:路线1;路线2;...
                    let routePart = parts[i];
                    // 移除前缀
                    let cleanPart = routePart.replace(/^(禁路线|banroute|noroute|ban-route)[:;；]*/i, '').trim();
                    if (cleanPart) {
                        // 如果当前部分就是路线名，直接使用
                        result.avoidRoutes = cleanPart;
                    } else {
                        // 否则从后续部分收集路线名
                        let routes = [];
                        for (let j = i + 1; j < parts.length; j++) {
                            let nextParam = parts[j].toLowerCase();
                            // 遇到下一个参数名就停止
                            if (nextParam === '详细' || nextParam === 'detail' || nextParam === '理论' || nextParam === 'theory' || 
                                nextParam === '实时' || nextParam === '越野' || nextParam === 'wild' || nextParam === '禁高铁' || 
                                nextParam === 'nohsr' || nextParam === 'banhsr' || nextParam === '禁船' || nextParam === 'noboat' || 
                                nextParam === 'banboat' || nextParam === '仅轻铁' || nextParam === 'onlylrt' || nextParam === 'lrt' ||
                                nextParam.startsWith('禁路线') || nextParam.startsWith('banroute') || nextParam.startsWith('noroute') ||
                                nextParam.startsWith('禁车站') || nextParam.startsWith('banstation') || nextParam.startsWith('nostation')) {
                                break;
                            }
                            routes.push(parts[j].trim());
                        }
                        if (routes.length > 0) {
                            result.avoidRoutes = routes.join(',');
                        }
                    }
                } else if (param.startsWith('禁车站') || param.startsWith('banstation') || param.startsWith('nostation') || param.startsWith('ban-station')) {
                    // 格式: 禁车站;车站1;车站2;... 或 禁车站:车站1;车站2;...
                    let stationPart = parts[i];
                    // 移除前缀
                    let cleanPart = stationPart.replace(/^(禁车站|banstation|nostation|ban-station)[:;；]*/i, '').trim();
                    if (cleanPart) {
                        // 如果当前部分就是车站名，直接使用
                        result.avoidStations = cleanPart;
                    } else {
                        // 否则从后续部分收集车站名
                        let stations = [];
                        for (let j = i + 1; j < parts.length; j++) {
                            let nextParam = parts[j].toLowerCase();
                            // 遇到下一个参数名就停止
                            if (nextParam === '详细' || nextParam === 'detail' || nextParam === '理论' || nextParam === 'theory' || 
                                nextParam === '实时' || nextParam === '越野' || nextParam === 'wild' || nextParam === '禁高铁' || 
                                nextParam === 'nohsr' || nextParam === 'banhsr' || nextParam === '禁船' || nextParam === 'noboat' || 
                                nextParam === 'banboat' || nextParam === '仅轻铁' || nextParam === 'onlylrt' || nextParam === 'lrt' ||
                                nextParam.startsWith('禁路线') || nextParam.startsWith('banroute') || nextParam.startsWith('noroute') ||
                                nextParam.startsWith('禁车站') || nextParam.startsWith('banstation') || nextParam.startsWith('nostation')) {
                                break;
                            }
                            stations.push(parts[j].trim());
                        }
                        if (stations.length > 0) {
                            result.avoidStations = stations.join(',');
                        }
                    }
                }
            }
            
            return result;
        }
        
        // 简码生成函数
        function generateShortCode(data) {
            let code = '/路线 ' + data.startStation + ';' + data.endStation;
            
            if (data.detail) {
                code += ';详细';
            }
            
            if (data.routeType === 'IN_THEORY') {
                code += ';理论';
            }
            
            if (data.calculateWalkingWild) {
                code += ';越野';
            }
            
            if (data.banHighSpeed) {
                code += ';禁高铁';
            }
            
            if (data.banBoat) {
                code += ';禁船';
            }
            
            if (data.onlyLRT) {
                code += ';仅轻铁';
            }
            
            if (data.avoidRoutes) {
                code += ';禁路线;' + data.avoidRoutes.replace(/,/g, ';');
            }
            
            if (data.avoidStations) {
                code += ';禁车站;' + data.avoidStations.replace(/,/g, ';');
            }
            
            return code;
        }
        
        // 滑动开关逻辑
        function setupRouteTypeToggle() {
            const toggle = document.querySelector('.route-type-toggle');
            if (!toggle) return;
            
            const slider = toggle.querySelector('.toggle-slider');
            const waitingRadio = document.getElementById('routeTypeWaiting');
            const theoryRadio = document.getElementById('routeTypeTheory');
            
            function updateSlider() {
                if (theoryRadio.checked) {
                    slider.style.left = '50%';
                } else {
                    slider.style.left = '0';
                }
            }
            
            waitingRadio.addEventListener('change', updateSlider);
            theoryRadio.addEventListener('change', updateSlider);
            
            // 初始化滑块位置
            updateSlider();
        }
        
        // 双向同步
        function setupShortCodeSync() {
            const shortCodeInput = document.getElementById('shortCode');
            const startInput = document.getElementById('startStation');
            const endInput = document.getElementById('endStation');
            const routeTypeWaiting = document.getElementById('routeTypeWaiting');
            const routeTypeTheory = document.getElementById('routeTypeTheory');
            const banHighSpeedInput = document.getElementById('banHighSpeed');
            const banBoatInput = document.getElementById('banBoat');
            const calculateWalkingWildInput = document.getElementById('calculateWalkingWild');
            const onlyLRTInput = document.getElementById('onlyLRT');
            const detailInput = document.getElementById('detail');
            const avoidRoutesInput = document.getElementById('avoidRoutes');
            const avoidStationsInput = document.getElementById('avoidStations');
            
            // 简码输入框变化时更新其他字段
            shortCodeInput.addEventListener('input', function() {
                const parsed = parseShortCode(this.value);
                if (parsed) {
                    // 总是更新起点和终点
                    if (parsed.startStation) {
                        startInput.value = parsed.startStation;
                    }
                    if (parsed.endStation) {
                        endInput.value = parsed.endStation;
                    }
                    if (parsed.routeType === 'IN_THEORY') {
                        routeTypeTheory.checked = true;
                    } else {
                        routeTypeWaiting.checked = true;
                    }
                    banHighSpeedInput.checked = parsed.banHighSpeed;
                    banBoatInput.checked = parsed.banBoat;
                    calculateWalkingWildInput.checked = parsed.calculateWalkingWild;
                    onlyLRTInput.checked = parsed.onlyLRT;
                    detailInput.checked = parsed.detail;
                    if (parsed.avoidRoutes !== undefined) {
                        avoidRoutesInput.value = parsed.avoidRoutes;
                    }
                    if (parsed.avoidStations !== undefined) {
                        avoidStationsInput.value = parsed.avoidStations;
                    }
                }
            });
            
            // 其他输入框变化时更新简码
            function updateShortCode() {
                const data = {
                    startStation: startInput.value,
                    endStation: endInput.value,
                    routeType: routeTypeTheory.checked ? 'IN_THEORY' : 'WAITING',
                    banHighSpeed: banHighSpeedInput.checked,
                    banBoat: banBoatInput.checked,
                    calculateWalkingWild: calculateWalkingWildInput.checked,
                    onlyLRT: onlyLRTInput.checked,
                    detail: detailInput.checked,
                    avoidRoutes: avoidRoutesInput.value,
                    avoidStations: avoidStationsInput.value
                };
                shortCodeInput.value = generateShortCode(data);
            }
            
            // 为所有相关输入框添加事件监听
            [startInput, endInput, banHighSpeedInput, banBoatInput, 
             calculateWalkingWildInput, onlyLRTInput, detailInput, avoidRoutesInput, avoidStationsInput].forEach(input => {
                input.addEventListener('input', updateShortCode);
                input.addEventListener('change', updateShortCode);
            });
            
            // 为单选按钮添加事件监听
            routeTypeWaiting.addEventListener('change', updateShortCode);
            routeTypeTheory.addEventListener('change', updateShortCode);
            
            // 初始化简码
            updateShortCode();
        }
        
        // 页面加载时设置双向同步和滑动开关
        document.addEventListener('DOMContentLoaded', function() {
            setupRouteTypeToggle();
            setupShortCodeSync();
        });
        
        document.getElementById('routeForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const data = {
                startStation: formData.get('startStation'),
                endStation: formData.get('endStation'),
                routeType: formData.get('routeType'),
                banHighSpeed: formData.get('banHighSpeed') === 'on',
                banBoat: formData.get('banBoat') === 'on',
                calculateWalkingWild: formData.get('calculateWalkingWild') === 'on',
                onlyLRT: formData.get('onlyLRT') === 'on',
                detail: formData.get('detail') === 'on',
                avoidStations: formData.get('avoidStations'),
                avoidRoutes: formData.get('avoidRoutes'),
                onlyRoutes: formData.get('onlyRoutes')
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
            .then(response => response.json())
            .then(data => {
                document.getElementById('loading').style.display = 'none';
                const resultDiv = document.getElementById('result');
                resultDiv.style.display = 'block';
                
                if (data.success) {
                    resultDiv.innerHTML = data.html;
                    // 更新计算用时
                    const calcTimeSpan = resultDiv.querySelector('.calc-time');
                    if (calcTimeSpan && data.calcTime !== undefined) {
                        calcTimeSpan.textContent = `用时: ${data.calcTime}ms`;
                    }
                } else {
                    resultDiv.innerHTML = `<div class="error">${data.error}</div>`;
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


def fetch_interval_data(station_id: str, LINK) -> None:
    '''
    获取车站的间隔数据
    '''
    global ROUTE_INTERVAL_DATA
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    with semaphore:  # 使用信号量限制并发
        link = LINK.rstrip('/') + f'/mtr/api/station/timetable/{station_id}'
        http = urllib3.PoolManager(cert_reqs='CERT_NONE')
        while True:
            try:
                response = http.request('GET', link)
                data = json.loads(response.data.decode('utf-8'))
                if data['data'] is not None:
                    ROUTE_INTERVAL_DATA.put((station_id, (data['data']['stationName'], data['data']['routes'])))
                    break
            except Exception:
                pass


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


def get_distance(a_dict: dict, b_dict: dict, square: bool = False) -> float:
    '''
    获取两个车站之间的距离
    '''
    dist_square = (a_dict['x'] - b_dict['x']) ** 2 + \
        (a_dict['z'] - b_dict['z']) ** 2  # 计算平方距离
    if square is True:
        return dist_square
    return sqrt(dist_square)  # 返回实际距离


def gen_route_interval(LOCAL_FILE_PATH, INTERVAL_PATH, LINK, MTR_VER) -> None:
    '''
    生成所有路线间隔数据
    '''
    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)

    if MTR_VER == 3:
        threads: list[Thread] = []
        stations = data[0]['stations']
        station_ids = list(stations.keys()) if isinstance(stations, dict) else stations
        for station_id in station_ids:
            t = Thread(target=fetch_interval_data, args=(station_id, LINK))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        interval_data_list = []
        while not ROUTE_INTERVAL_DATA.empty():
            interval_data_list.append(ROUTE_INTERVAL_DATA.get())

        arrivals = dict(interval_data_list)
        dep_dict_per_route: dict[str, list] = {}
        dep_dict_per_route_: dict[str, list] = {}
        for t, arrivals in arrivals.items():
            dep_dict_per_station: dict[str, list] = {}
            for arrival in arrivals[:-1]:
                name = arrival['name']
                if name in dep_dict_per_station:
                    dep_dict_per_station[name] += [arrival['arrival']]
                else:
                    dep_dict_per_station[name] = [arrival['arrival']]

            for route in arrival:
                if route in dep_dict_per_route:
                    dep_dict_per_route[route] += dep_dict_per_station[route]
                else:
                    dep_dict_per_route[route] = dep_dict_per_station[route]

        for route, dep in dep_dict_per_route.items():
            dep = sorted(dep)
            dep_diffs = []
            for i in range(len(dep) - 1):
                dep_diffs.append(dep[i + 1] - dep[i])
            if len(dep_diffs) > 0:
                dep_dict_per_route_[route] = round(median_low(dep_diffs))
            else:
                dep_dict_per_route_[route] = 0

        with open(INTERVAL_PATH, 'w', encoding='utf-8') as f:
            json.dump(dep_dict_per_route_, f, indent=4, ensure_ascii=False)
    else:
        link = LINK.rstrip('/') + '/mtr/api/map/departures?dimension=0'
        http = urllib3.PoolManager(cert_reqs='CERT_NONE', ssl_version='PROTOCOL_TLS_CLIENT')
        response = http.request('GET', link)
        if response.status != 200:
            with open(INTERVAL_PATH, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=4, ensure_ascii=False)
            return
        
        departures = json.loads(response.data.decode('utf-8'))['data']['departures']
        dep_dict: dict[str, list[int]] = {}
        for x in departures:
            dep_list = set()
            for y in x['departures']:
                for z in y['departures']:
                    dep = round(z / 1000)
                    while dep < 0:
                        dep += 86400
                    dep_list.add(dep)
            dep_list = list(sorted(dep_list))
            dep_dict[x['id']] = dep_list

        freq_dict: dict[str, int] = {}
        for route_id, stats in dep_dict.items():
            if len(stats) == 0:
                continue

            for route_stats in data[0]['routes']:
                if route_stats['id'] == route_id:
                    break
            else:
                continue

            freq_list = []
            for i1 in range(len(stats)):
                i2 = i1 + 1
                if i2 == len(stats):
                    i2 = 0
                    dep_2 = stats[i2] + 86400
                else:
                    dep_2 = stats[i2]

                dep_1 = stats[i1]
                freq = dep_2 - dep_1
                freq_list.append(freq)

            if freq_list:
                median_freq = median_low(freq_list)
                freq_dict[route_stats['name']] = round_ten(median_freq)

        with open(INTERVAL_PATH, 'w', encoding='utf-8') as f:
            json.dump(freq_dict, f, indent=4, ensure_ascii=False)


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
    sta_try = [sta, tra1]

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
        st = [x['id'] if isinstance(x, dict) else str(x).split('_')[0] for x in route['stations']]  # 提取车站ID
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
        
        station_1_id = station_1['id'] if isinstance(station_1, dict) else str(station_1).split('_')[0]
        station_2_id = station_2['id'] if isinstance(station_2, dict) else str(station_2).split('_')[0]
        
        station_1_check = False
        station_2_check = False
        for k, position_dict in data[0]['positions'].items():  # 查找坐标
            if k == station_1_id:
                station_1_position['x'] = position_dict['x']
                station_1_position['z'] = position_dict['y']
                station_1_check = True
            elif k == station_2_id:
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
                 MAX_WILD_BLOCKS, MTR_VER, cache,
                 ONLY_ROUTES: list = []) -> nx.MultiDiGraph:
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
        m = hashlib.md5()
        for s in original_ignored_lines:
            m.update(s.encode('utf-8'))
        filename = f'mtr_pathfinder_temp{os.sep}' + \
            f'3{int(CALCULATE_HIGH_SPEED)}{int(CALCULATE_WALKING_WILD)}' + \
            f'-{version1}-{version2}-{m.hexdigest()}.dat'
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
                    station_1 = stations[it1]['id'] if isinstance(stations[it1], dict) else str(stations[it1]).split('_')[0]
                    station_2 = stations[it2]['id'] if isinstance(stations[it2], dict) else str(stations[it2]).split('_')[0]
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
        for x in route_names:
            x = x.lower().strip()
            if x in TEMP_IGNORED_LINES:
                cont = True
                break

            if x.isascii():
                continue

            simp1 = opencc3.convert(x)
            if simp1 in TEMP_IGNORED_LINES:
                cont = True
                break

            simp2 = opencc3.convert(opencc4.convert(x))
            if simp2 in TEMP_IGNORED_LINES:
                cont = True
                break

        if cont is True:
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
            elif n not in intervals:  # 无间隔数据，使用默认值
                if route['type'] == 'train_high_speed':
                    intervals[n] = 10  # 高铁：10分钟一班
                elif route['type'] == 'train_light_rail':
                    intervals[n] = 3  # 轻轨：3分钟一班
                elif 'boat' in route['type']:
                    intervals[n] = 15  # 船：15分钟一班
                else:
                    intervals[n] = 5  # 普通铁路：5分钟一班

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
                    station_1 = stations[i]['id'] if isinstance(stations[i], dict) else str(stations[i]).split('_')[0]
                    station_2 = stations[i2]['id'] if isinstance(stations[i2], dict) else str(stations[i2]).split('_')[0]
                    dur_list = durations[i:i2]
                    station_list = stations[i:i2 + 1]
                    c = False
                    for sta in station_list:  # 检查是否包含避开车站
                        sta_id = sta['id'] if isinstance(sta, dict) else str(sta).split('_')[0]
                        if sta_id in avoid_ids:
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
                    original[(route['name'], station_1, station_2)] = dur  # 存储原始数据
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
                    original[(route_name, s1, s2)] = dur

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
        sta1_id = station_1  # MTR 3中station_1本身就是ID
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
                            duration = original[(route_name,
                                                 station_1, station_2)]
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
                        sta_id = z['stations'][-1]['id'] if isinstance(z['stations'][-1], dict) else str(z['stations'][-1]).split('_')[0]  # 终点站
                        for q, x in enumerate(z['stations']):
                            x_id = x['id'] if isinstance(x, dict) else str(x).split('_')[0]
                            if x_id == sta1_id and \
                                    q != len(z['stations']) - 1:  # 不是最后一站
                                next_id = z['stations'][q + 1]['id'] if isinstance(z['stations'][q + 1], dict) else str(z['stations'][q + 1]).split('_')[0]
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
    
    def get_transport_icon(train_type):
        """获取交通类型图标"""
        if train_type is None:
            return '<span class="transport-icon walk">🚶</span>'
        elif 'high_speed' in train_type:
            return '<span class="transport-icon high-speed">🚄</span>'
        elif 'light_rail' in train_type:
            return '<span class="transport-icon light-rail">🚈</span>'
        elif 'boat' in train_type:
            return '<span class="transport-icon boat">🚢</span>'
        elif 'cable_car' in train_type:
            return '<span class="transport-icon cable-car">🚡</span>'
        elif 'airplane' in train_type:
            return '<span class="transport-icon airplane">✈️</span>'
        else:
            return '<span class="transport-icon subway">🚇</span>'
    
    def get_transport_name(train_type):
        """获取交通类型名称"""
        if train_type is None:
            return '步行'
        elif 'high_speed' in train_type:
            return '高铁'
        elif 'light_rail' in train_type:
            return '轻轨'
        elif 'boat' in train_type:
            return '船只'
        elif 'cable_car' in train_type:
            return '缆车'
        elif 'airplane' in train_type:
            return '飞机'
        else:
            return '列车'
    
    def get_route_style(color):
        """获取路线样式和文字颜色"""
        original_color = color
        
        if color == '#000000':
            return 'background: linear-gradient(135deg, #9e9e9e, #757575);', 'white'
        
        # 解析十六进制颜色
        color = color.lstrip('#')
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        
        # 计算亮度 (luminance)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        
        # 根据亮度选择文字颜色
        text_color = 'white' if luminance < 0.5 else 'black'
        
        return f'background: {original_color};', text_color
    
    html_parts = []
    
    # 添加时间信息
    html_parts.append('<div class="time-info">')
    html_parts.append('<h3>路线概览</h3>')
    html_parts.append('<div class="time-grid">')
    html_parts.append(f'<div class="time-item">')
    html_parts.append(f'<strong>{full_time}</strong>')
    html_parts.append(f'<span>总用时</span>')
    html_parts.append(f'</div>')
    
    if route_type != RouteType.IN_THEORY:
        html_parts.append(f'<div class="time-item">')
        html_parts.append(f'<strong>{travelling_time}</strong>')
        html_parts.append(f'<span>乘车时间</span>')
        html_parts.append(f'</div>')
        
        html_parts.append(f'<div class="time-item">')
        html_parts.append(f'<strong>{waiting_time_str}</strong>')
        html_parts.append(f'<span>等车时间</span>')
        html_parts.append(f'</div>')
    
    html_parts.append('</div>')
    html_parts.append(f'<div class="version-info" style="margin-top: 8px; padding: 6px 10px; font-size: 0.75rem;">')
    html_parts.append(f'<span>车站数据版本: {version1}</span>')
    html_parts.append(f'<span style="margin-left: 12px;">路线数据版本: {version2}</span>')
    html_parts.append(f'<span style="margin-left: 12px;" class="calc-time">寻路用时: --ms</span>')
    html_parts.append('</div>')
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
            is_first_station = (i == 0)
            html_parts.append(f'<div class="route-step {"start-station" if is_first_station else ""}" style="border-left-color: {color};">')
            html_parts.append(f'<div class="station">{station_from}</div>')
            last_station = station_from
        else:
            html_parts.append(f'<div class="route-step alternative">')
            html_parts.append(f'<span class="divider">或</span>')
        
        # 路线信息
        html_parts.append(f'<div class="route-info">')
        
        # 添加路线标签（包含颜色和图标）
        route_bg_style, text_color = get_route_style(color)
        html_parts.append(f'<div class="route-tag" style="{route_bg_style} color: {text_color};">')
        html_parts.append(f'{get_transport_icon(train_type)}')
        html_parts.append(f'<span class="route-name">{route_name}</span>')
        html_parts.append(f'<span style="margin-left: 8px; opacity: 0.8;">({get_transport_name(train_type)})</span>')
        html_parts.append(f'</div>')
        
        if train_type is not None:  # 不是步行
            # 方向指示
            html_parts.append(f'<div class="direction-indicator">{terminus_display}</div>')
            
            # 时间详情
            html_parts.append(f'<div class="time-detail">')
            html_parts.append(f'<span>🕐 乘车时间</span>')
            html_parts.append(f'<span class="time-value">{duration_str}</span>')
            html_parts.append(f'</div>')
            
            if DETAIL and route_type == RouteType.WAITING and sep_waiting is not None:
                interval_str = str(strftime('%M:%S', gmtime(sep_waiting)))
                html_parts.append(f'<div class="time-detail">')
                html_parts.append(f'<span>⏳ 等车时间</span>')
                html_parts.append(f'<span class="time-value">{waiting_str}</span>')
                html_parts.append(f'</div>')
                html_parts.append(f'<div class="time-detail">')
                html_parts.append(f'<span>🔄 发车间隔</span>')
                html_parts.append(f'<span class="time-value">{interval_str}</span>')
                html_parts.append(f'</div>')
            elif DETAIL and route_type == RouteType.WAITING:
                html_parts.append(f'<div class="time-detail">')
                html_parts.append(f'<span>⏳ 等车时间</span>')
                html_parts.append(f'<span class="time-value">{waiting_str}</span>')
                html_parts.append(f'</div>')
        else:  # 步行
            html_parts.append(f'<div class="time-detail">')
            html_parts.append(f'<span>⏱️ 步行时间</span>')
            html_parts.append(f'<span class="time-value">{duration_str}</span>')
            html_parts.append(f'</div>')
        
        html_parts.append('</div>')  # 结束route-info
        html_parts.append('</div>')  # 结束route-step
    
    # 添加终点站
    if every_route_time:
        last_route = every_route_time[-1]
        html_parts.append(f'<div class="route-step end-station" style="border-left-color: {last_route[2]};">')
        html_parts.append(f'<div class="station">{last_route[1]}</div>')
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
         AVOID_STATIONS: list = [], ONLY_ROUTES: list = [],
         CALCULATE_HIGH_SPEED: bool = True,
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

    # MTR 3数据格式转换
    if MTR_VER == 3 and isinstance(data, list) and len(data) > 0:
        # MTR 3数据是多个地图的列表，只使用第一个（主地图）
        data = [data[0]]
        raw_data = data[0]
        if 'routes' in raw_data and 'stations' in raw_data:
            stations = raw_data['stations']
            if isinstance(stations, dict):
                # 转换stations中的车站数据格式，确保有x和z字段
                for station_id, station_data in stations.items():
                    if isinstance(station_data, dict):
                        if 'x' not in station_data:
                            station_data['x'] = 0
                        if 'z' not in station_data:
                            station_data['z'] = 0
            
            # 转换routes中的stations为字典格式
            for route in raw_data.get('routes', []):
                new_stations = []
                for station in route.get('stations', []):
                    if isinstance(station, str):
                        parts = station.rsplit('_', 1)
                        station_id = parts[0]
                        color = parts[1] if len(parts) > 1 else '0'
                        new_stations.append({
                            'id': station_id,
                            'color': int(color) if color.isdigit() else 0,
                            'x': 0,
                            'z': 0
                        })
                    elif isinstance(station, dict):
                        new_stations.append(station)
                route['stations'] = new_stations

    # 生成路线间隔数据
    if GEN_ROUTE_INTERVAL is True or (not os.path.exists(INTERVAL_PATH)):
        if LINK == '':
            raise ValueError('Railway System Map link is empty')

        gen_route_interval(LOCAL_FILE_PATH, INTERVAL_PATH, LINK, MTR_VER)  # 生成间隔数据

    # 获取版本信息
    from datetime import datetime
    local_mtime1 = datetime.fromtimestamp(os.path.getmtime(LOCAL_FILE_PATH))
    local_mtime2 = datetime.fromtimestamp(os.path.getmtime(INTERVAL_PATH))
    version1 = local_mtime1.strftime('%Y%m%d-%H%M%S')  # 车站数据版本（本地时间）
    version2 = local_mtime2.strftime('%Y%m%d-%H%M%S')  # 路线数据版本（本地时间）

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
                         MAX_WILD_BLOCKS, MTR_VER, cache, ONLY_ROUTES)  # 创建图

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


@app.route('/stations')
def stations_list():
    '''显示车站列表'''
    LINK = config.get('LINK', '')
    MTR_VER = config.get('MTR_VER', 4)
    link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest() if LINK else ''
    LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
    
    stations = []
    routes = []
    
    if os.path.exists(LOCAL_FILE_PATH):
        try:
            with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list) and len(data) > 0:
                raw_data = data[0]
                
                # 提取车站
                stations_raw = raw_data.get('stations', {})
                if isinstance(stations_raw, dict):
                    for station_id, station_info in stations_raw.items():
                        station = {
                            'id': station_id,
                            'name': station_info.get('name', station_id) if isinstance(station_info, dict) else station_id,
                            'color': station_info.get('color', 0) if isinstance(station_info, dict) else 0,
                            'x': station_info.get('x', 0) if isinstance(station_info, dict) else 0,
                            'z': station_info.get('z', 0) if isinstance(station_info, dict) else 0
                        }
                        stations.append(station)
                elif isinstance(stations_raw, list):
                    for station in stations_raw:
                        if isinstance(station, dict):
                            stations.append({
                                'id': station.get('id', ''),
                                'name': station.get('name', ''),
                                'color': station.get('color', 0),
                                'x': station.get('x', 0),
                                'z': station.get('z', 0)
                            })
                
                # 提取路线
                routes_raw = raw_data.get('routes', [])
                for route in routes_raw:
                    if isinstance(route, dict):
                        routes.append({
                            'name': route.get('name', ''),
                            'color': route.get('color', 0),
                            'type': route.get('type', 'train_normal'),
                            'number': route.get('number', ''),
                            'station_count': len(route.get('stations', []))
                        })
        except Exception as e:
            print(f"加载车站数据错误: {e}")
    
    stations.sort(key=lambda x: x['name'])
    routes.sort(key=lambda x: x['name'])
    
    return render_template_string(STATIONS_TEMPLATE, stations=stations, routes=routes, count=len(stations))


@app.route('/routes')
def routes_list():
    '''显示路线列表'''
    LINK = config.get('LINK', '')
    MTR_VER = config.get('MTR_VER', 4)
    link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest() if LINK else ''
    LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
    
    routes = []
    route_groups = {}
    stations_dict = {}
    
    if os.path.exists(LOCAL_FILE_PATH):
        try:
            with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list) and len(data) > 0:
                raw_data = data[0]
                
                # 构建车站ID到名称的映射
                stations_raw = raw_data.get('stations', {})
                if isinstance(stations_raw, dict):
                    for station_id, station_info in stations_raw.items():
                        if isinstance(station_info, dict):
                            stations_dict[station_id] = station_info.get('name', station_id)
                        else:
                            stations_dict[station_id] = str(station_info)
                elif isinstance(stations_raw, list):
                    for station in stations_raw:
                        if isinstance(station, dict):
                            sid = station.get('id', '')
                            stations_dict[sid] = station.get('name', sid)
                
                # 提取路线，将车站ID转换为站名
                routes_raw = raw_data.get('routes', [])
                for route in routes_raw:
                    if isinstance(route, dict):
                        station_list = route.get('stations', [])
                        station_names = []
                        for station in station_list:
                            if isinstance(station, dict):
                                station_id = station.get('id', str(station))
                            else:
                                station_id = str(station)
                            station_name = stations_dict.get(station_id, station_id)
                            station_names.append(station_name)
                        
                        route_info = {
                            'name': route.get('name', ''),
                            'color': route.get('color', 0),
                            'type': route.get('type', 'train_normal'),
                            'number': route.get('number', ''),
                            'circular': route.get('circular', ''),
                            'stations': station_names,
                            'durations': route.get('durations', [])
                        }
                        routes.append(route_info)
                        
                        # 分组同名线路
                        base_name = extract_base_name(route.get('name', ''))
                        if base_name not in route_groups:
                            route_groups[base_name] = {
                                'name': base_name,
                                'directions': [],
                                'color': route.get('color', 0),
                                'type': route.get('type', 'train_normal')
                            }
                        
                        # 生成方向描述
                        direction = get_route_direction(station_names, route.get('circular', ''))
                        route_groups[base_name]['directions'].append({
                            'full_name': route.get('name', ''),
                            'stations': station_names,
                            'direction': direction,
                            'color': route.get('color', 0),
                            'circular': route.get('circular', '')
                        })
        except Exception as e:
            print(f"加载路线数据错误: {e}")
    
    # 转换为列表并排序
    route_groups_list = list(route_groups.values())
    route_groups_list.sort(key=lambda x: x['name'])
    
    return render_template_string(ROUTES_TEMPLATE, route_groups=route_groups_list, routes=routes, count=len(routes))


def extract_base_name(route_name):
    '''提取线路基础名称（不含方向括号部分）'''
    import re
    # 移除 || 分隔符后的部分
    base = route_name.split('||')[0].strip()
    # 移除末尾的方向括号，如 "(方向)"
    base = re.sub(r'\s*\([^)]*\)\s*$', '', base).strip()
    return base


def get_route_direction(stations, circular):
    '''获取线路方向描述'''
    if circular:
        return f"环线 ({circular})"
    if len(stations) >= 2:
        return f"{stations[0]} → {stations[-1]}"
    return f"{len(stations)}站"


def split_by_comma(text: str) -> list:
    '''支持中英文逗号分隔'''
    if not text:
        return []
    # 先替换中文逗号为英文逗号，再分割
    text = text.replace('，', ',').replace('、', ',')
    return [item.strip() for item in text.split(',') if item.strip()]


@app.route('/find-route', methods=['POST'])
def find_route():
    '''处理路径查找请求'''
    try:
        data = request.json
        station1 = data.get('startStation')
        station2 = data.get('endStation')
        route_type_str = data.get('routeType', 'WAITING')
        CALCULATE_HIGH_SPEED = not data.get('banHighSpeed', False)
        CALCULATE_BOAT = not data.get('banBoat', False)
        CALCULATE_WALKING_WILD = data.get('calculateWalkingWild', False)
        ONLY_LRT = data.get('onlyLRT', False)
        DETAIL = data.get('detail', False)
        
        # 处理禁车站参数
        avoidStations = data.get('avoidStations', '')
        AVOID_STATIONS = split_by_comma(avoidStations)
        
        # 处理禁路线参数
        avoidRoutes = data.get('avoidRoutes', '')
        IGNORED_LINES = split_by_comma(avoidRoutes)
        
        # 处理仅路线参数
        onlyRoutes = data.get('onlyRoutes', '')
        ONLY_ROUTES = split_by_comma(onlyRoutes)
        
        # 转换路线类型
        IN_THEORY = (route_type_str == 'IN_THEORY')
        
        # 从配置中获取链接和版本
        LINK = config['LINK']
        MTR_VER = config.get('MTR_VER', 4)
        link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
        LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
        INTERVAL_PATH = f'mtr-route-data-{link_hash}-{MTR_VER}.json'
        BASE_PATH = 'mtr_pathfinder_data'
        PNG_PATH = 'mtr_pathfinder_data'
        
        # 检查数据文件是否存在
        if not os.path.exists(LOCAL_FILE_PATH) or not os.path.exists(INTERVAL_PATH):
            return jsonify({'success': False, 'error': '无车站或路线数据，请前往控制台更新数据'})
        
        # 开始计时
        start_time = time()
        
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
            IGNORED_LINES=IGNORED_LINES,
            AVOID_STATIONS=AVOID_STATIONS,
            ONLY_ROUTES=ONLY_ROUTES,
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
        
        # 计算用时
        calc_time = round((time() - start_time) * 1000, 1)  # 毫秒
        
        if result is False:
            return jsonify({'success': False, 'error': '找不到路线'})
        elif result is None:
            return jsonify({'success': False, 'error': '车站名称错误，请重新输入'})
        else:
            # result是(base64图片, HTML)或HTML字符串
            if isinstance(result, tuple):
                html_result = result[1]
            else:
                html_result = result
            return jsonify({'success': True, 'html': html_result, 'calcTime': calc_time})
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'发生错误: {str(e)}'})


# 全局配置
# 优先从环境变量读取配置，若未设置则使用默认值
ADMIN_PASSWORD = os.environ.get('MTR_ADMIN_PASSWORD', 'admin')   # 控制台密码，可修改
config = {
    'LINK': os.environ.get('MTR_LINK', 'https://letsplay.minecrafttransitrailway.com/system-map'),
    'MTR_VER': int(os.environ.get('MTR_VER', 4)),
    'UMAMI_SCRIPT_URL': os.environ.get('MTR_UMAMI_SCRIPT_URL', ''),   #Umami跟踪脚本URL
    'UMAMI_WEBSITE_ID': os.environ.get('MTR_UMAMI_WEBSITE_ID', '')    #Umami网站ID
}

tt_opencc1 = OpenCC('s2t')  #简体转繁体
tt_opencc2 = OpenCC('t2jp')  #繁体转日语汉字
tt_opencc3 = OpenCC('t2s')  #繁体转简体
tt_opencc4 = OpenCC('jp2t')  #日语汉字转繁体

# 控制台页面HTML
ADMIN_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTR路径查找器 - 控制台</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #4a90e2, #50e3c2);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .header h1 {
            font-size: 1.5rem;
            margin-bottom: 5px;
        }
        .content {
            padding: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #333;
        }
        .form-group input {
            width: 100%;
            padding: 10px 12px;
            border: 2px solid #e9ecef;
            border-radius: 6px;
            font-size: 1rem;
        }
        .form-group input:focus {
            outline: none;
            border-color: #4a90e2;
        }
        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-bottom: 10px;
        }
        .btn-primary {
            background: linear-gradient(135deg, #4a90e2, #50e3c2);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
        }
        .btn-danger {
            background: linear-gradient(135deg, #d0021b, #f5a623);
            color: white;
        }
        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(208, 2, 27, 0.3);
        }
        .info-box {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 15px;
        }
        .info-box h3 {
            margin-bottom: 10px;
            color: #333;
        }
        .info-box p {
            margin-bottom: 5px;
            color: #666;
        }
        .current-config {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        .current-config h4 {
            margin-bottom: 10px;
            color: #1565c0;
        }
        .current-config p {
            margin-bottom: 5px;
        }
        .message {
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 15px;
        }
        .message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .back-link {
            display: block;
            text-align: center;
            margin-top: 15px;
            color: #4a90e2;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MTR路径查找器 控制台</h1>
            <p>管理配置和数据更新</p>
        </div>
        <div class="content">
            ''' + '''
            {% if error %}
            <div class="message error">{{ error }}</div>
            {% endif %}
            
            <div class="current-config">
                <h4>当前配置</h4>
                <p><strong>地图链接:</strong> {{ config.LINK }}</p>
                <p><strong>MTR版本:</strong> {{ config.MTR_VER }}</p>
                <p><strong>车站数据:</strong> <span id="station-ver">检测中...</span></p>
                <p><strong>路线数据:</strong> <span id="route-ver">检测中...</span></p>
            </div>
            
            <script>
            var linkHash = '{{ link_hash }}';
            var mtrVer = {{ config.MTR_VER }};
            
            function getFileVersion(type) {
                var filename = 'mtr-station-data-' + linkHash + '-' + mtrVer + '.json';
                if (type === 'route') {
                    filename = 'mtr-route-data-' + linkHash + '-' + mtrVer + '.json';
                }
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/data/' + filename, true);
                xhr.onload = function() {
                    var verSpan = document.getElementById(type === 'station' ? 'station-ver' : 'route-ver');
                    if (xhr.status === 200) {
                        var date = xhr.getResponseHeader('Last-Modified');
                        if (date && verSpan) {
                            verSpan.textContent = new Date(date).toLocaleString();
                        } else if (verSpan) {
                            verSpan.textContent = '未知';
                        }
                    } else if (verSpan) {
                        verSpan.textContent = '未检测到';
                    }
                };
                xhr.onerror = function() {
                    var verSpan = document.getElementById(type === 'station' ? 'station-ver' : 'route-ver');
                    if (verSpan) {
                        verSpan.textContent = '未检测到';
                    }
                };
                xhr.send();
            }
            
            window.onload = function() {
                getFileVersion('station');
                getFileVersion('route');
            };
            </script>
            
            <div class="info-box">
                <h3>配置</h3>
                <form id="config-form">
                    <div class="form-group">
                        <label for="link">地图链接 (LINK)</label>
                        <input type="text" id="link" name="link" value="{{ config.LINK }}" placeholder="https://letsplay.minecrafttransitrailway.com/system-map"> required>
                    </div>
                    <div class="form-group">
                        <label for="mtr_ver">MTR版本 (MTR_VER)</label>
                        <input type="number" id="mtr_ver" name="mtr_ver" value="{{ config.MTR_VER }}" min="1" max="10" required>
                    </div>
                    <div class="form-group">
                        <label for="umami_script_url">Umami脚本URL (src)</label>
                        <input type="text" id="umami_script_url" name="umami_script_url" value="{{ config.UMAMI_SCRIPT_URL }}" placeholder="https://cloud.umami.is/script.js">
                    </div>
                    <div class="form-group">
                        <label for="umami_website_id">Umami网站ID (data-website-id)</label>
                        <input type="text" id="umami_website_id" name="umami_website_id" value="{{ config.UMAMI_WEBSITE_ID }}" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx">
                    </div>
                    <button type="button" class="btn btn-primary" onclick="saveConfig()">保存配置</button>
                    <div id="config-result" style="margin-top: 10px;"></div>
                </form>
            </div>
            
            <div class="info-box">
                <h3>数据更新</h3>
                <button type="button" class="btn btn-danger" id="update-btn" onclick="updateData()">更新车站和线路数据</button>
                <div id="update-loading" style="display: none; margin-top: 15px; text-align: center;">
                    <span id="update-status">正在更新车站数据... (1/2)</span>
                </div>
                <div id="update-result" style="margin-top: 10px;"></div>
            </div>
            
            <script>
            function saveConfig() {
                var link = document.getElementById('link').value;
                var mtr_ver = document.getElementById('mtr_ver').value;
                var umami_script_url = document.getElementById('umami_script_url').value;
                var umami_website_id = document.getElementById('umami_website_id').value;
                var resultDiv = document.getElementById('config-result');
                
                var formData = new FormData();
                formData.append('link', link);
                formData.append('mtr_ver', mtr_ver);
                formData.append('umami_script_url', umami_script_url);
                formData.append('umami_website_id', umami_website_id);
                
                fetch('/admin/update-config-ajax', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        resultDiv.innerHTML = '<p style="color: green;">配置已保存</p>';
                    } else {
                        resultDiv.innerHTML = '<p style="color: red;">' + data.error + '</p>';
                    }
                })
                .catch(error => {
                    resultDiv.innerHTML = '<p style="color: red;">保存失败</p>';
                });
            }
            
            function updateData() {
                var btn = document.getElementById('update-btn');
                var loading = document.getElementById('update-loading');
                var status = document.getElementById('update-status');
                var resultDiv = document.getElementById('update-result');
                
                btn.disabled = true;
                loading.style.display = 'block';
                resultDiv.innerHTML = '';
                
                var startTime = Date.now();
                var totalSteps = 2;
                
                function updateStatus(step) {
                    if (step === 1) {
                        status.textContent = '正在更新车站数据... (' + step + '/' + totalSteps + ')';
                    } else if (step === 2) {
                        status.textContent = '正在更新路线数据... (' + step + '/' + totalSteps + ')';
                    }
                }
                
                updateStatus(1);
                
                fetch('/admin/update-data-ajax', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({step: 1})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateStatus(2);
                        return fetch('/admin/update-data-ajax', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({step: 2})
                        });
                    } else {
                        throw new Error(data.error || '车站数据更新失败');
                    }
                })
                .then(response => response.json())
                .then(data => {
                    var endTime = Date.now();
                    var duration = ((endTime - startTime) / 1000).toFixed(2);
                    
                    loading.style.display = 'none';
                    btn.disabled = false;
                    
                    if (data.success) {
                        resultDiv.innerHTML = '<p style="color: green;">✓ 数据更新成功！ 用时: ' + duration + '秒</p>';
                    } else {
                        throw new Error(data.error || '路线数据更新失败');
                    }
                })
                .catch(error => {
                    var endTime = Date.now();
                    var duration = ((endTime - startTime) / 1000).toFixed(2);
                    
                    loading.style.display = 'none';
                    btn.disabled = false;
                    
                    resultDiv.innerHTML = '<p style="color: red;">✗ 错误: ' + error + ' 用时: ' + duration + '秒</p>';
                });
            }
            </script>
            
            <a href="/" class="back-link">← 返回首页</a>
            <a href="/admin/logout" class="back-link">退出登录</a>
        </div>
    </div>
</body>
</html>
'''

# 车站列表页面HTML
STATIONS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>车站列表 - MTR路径查找器</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 20px 0;
            margin-bottom: 30px;
            border-radius: 15px;
        }
        header h1 {
            text-align: center;
            font-size: 2em;
            background: linear-gradient(90deg, #00d9ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        nav {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        nav a {
            color: #00d9ff;
            text-decoration: none;
            padding: 10px 25px;
            border: 2px solid #00d9ff;
            border-radius: 25px;
            transition: all 0.3s ease;
            font-weight: 500;
        }
        nav a:hover, nav a.active {
            background: #00d9ff;
            color: #1a1a2e;
        }
        .stats {
            text-align: center;
            margin: 20px 0;
            padding: 15px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
        }
        .stats span {
            margin: 0 15px;
            font-size: 1.1em;
        }
        .stats .number {
            color: #00ff88;
            font-weight: bold;
        }
        .search-box {
            max-width: 500px;
            margin: 20px auto;
            display: flex;
            gap: 10px;
        }
        .search-box input {
            flex: 1;
            padding: 12px 20px;
            border: 2px solid rgba(255, 255, 255, 0.2);
            border-radius: 25px;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            font-size: 16px;
        }
        .search-box input:focus {
            outline: none;
            border-color: #00d9ff;
        }
        .search-box input::placeholder {
            color: rgba(255, 255, 255, 0.5);
        }
        .section-title {
            text-align: center;
            margin: 30px 0 20px;
            font-size: 1.5em;
            color: #00d9ff;
        }
        .list-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            padding: 20px 0;
        }
        .station-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 15px;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .station-card:hover {
            transform: translateY(-3px);
            background: rgba(255, 255, 255, 0.1);
            border-color: #00d9ff;
        }
        .station-card .name {
            font-size: 1.1em;
            font-weight: 600;
            color: #fff;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .station-card .color-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
        }
        .station-card .info {
            font-size: 0.85em;
            color: rgba(255, 255, 255, 0.6);
        }
        .route-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 15px;
            transition: all 0.3s ease;
        }
        .route-card:hover {
            transform: translateY(-3px);
            background: rgba(255, 255, 255, 0.1);
        }
        .route-card .name {
            font-size: 1em;
            font-weight: 600;
            color: #fff;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .route-card .info {
            font-size: 0.85em;
            color: rgba(255, 255, 255, 0.6);
        }
        .type-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.75em;
            background: rgba(0, 217, 255, 0.2);
            color: #00d9ff;
        }
        .no-data {
            text-align: center;
            padding: 50px;
            color: rgba(255, 255, 255, 0.5);
        }
        @media (max-width: 768px) {
            .list-container {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <header>
        <h1>🚇 车站与线路列表</h1>
        <nav>
            <a href="/">🏠 首页</a>
            <a href="/stations" class="active">🚉 车站</a>
            <a href="/routes">🛤️ 线路</a>
            <a href="/admin">⚙️ 控制台</a>
        </nav>
    </header>
    
    <div class="container">
        <div class="stats">
            <span>车站总数: <span class="number">{{ count }}</span></span>
            <span>线路总数: <span class="number">{{ routes|length }}</span></span>
        </div>
        
        <div class="search-box">
            <input type="text" id="search" placeholder="搜索车站或线路..." oninput="filterItems()">
        </div>
        
        <h2 class="section-title">🚉 车站列表</h2>
        <div class="list-container" id="station-list">
            {% for station in stations %}
            <div class="station-card" data-name="{{ station.name|lower }}">
                <div class="name">
                    {% if station.color %}
                    <span class="color-dot" style="background-color: #{{ '%06x'|format(station.color) }}"></span>
                    {% endif %}
                    {{ station.name }}
                </div>
                <div class="info">
                    ID: {{ station.id }}<br>
                    坐标: ({{ station.x }}, {{ station.z }})
                </div>
            </div>
            {% else %}
            <div class="no-data">暂无车站数据，请先更新数据</div>
            {% endfor %}
        </div>
        
        <h2 class="section-title">🛤️ 线路列表</h2>
        <div class="list-container" id="route-list">
            {% for route in routes %}
            <div class="route-card" data-name="{{ route.name|lower }}">
                <div class="name">
                    {% if route.color %}
                    <span style="color: #{{ '%06x'|format(route.color) }}">■</span>
                    {% endif %}
                    {{ route.name }}
                </div>
                <div class="info">
                    <span class="type-badge">{{ route.type }}</span>
                    {% if route.number %}
                    <span style="margin-left: 10px;">编号: {{ route.number }}</span>
                    {% endif %}
                    <br>车站数: {{ route.station_count }}
                </div>
            </div>
            {% else %}
            <div class="no-data">暂无线路数据</div>
            {% endfor %}
        </div>
    </div>
    
    <script>
    function filterItems() {
        const query = document.getElementById('search').value.toLowerCase();
        
        document.querySelectorAll('.station-card, .route-card').forEach(card => {
            const name = card.dataset.name || '';
            card.style.display = name.includes(query) ? '' : 'none';
        });
    }
    </script>
</body>
</html>
'''

# 线路列表页面HTML
ROUTES_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>线路列表 - MTR路径查找器</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 20px 0;
            margin-bottom: 30px;
            border-radius: 15px;
        }
        header h1 {
            text-align: center;
            font-size: 2em;
            background: linear-gradient(90deg, #00d9ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        nav {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        nav a {
            color: #00d9ff;
            text-decoration: none;
            padding: 10px 25px;
            border: 2px solid #00d9ff;
            border-radius: 25px;
            transition: all 0.3s ease;
            font-weight: 500;
        }
        nav a:hover, nav a.active {
            background: #00d9ff;
            color: #1a1a2e;
        }
        .stats {
            text-align: center;
            margin: 20px 0;
            padding: 15px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
        }
        .stats span {
            margin: 0 15px;
            font-size: 1.1em;
        }
        .stats .number {
            color: #00ff88;
            font-weight: bold;
        }
        .search-box {
            max-width: 500px;
            margin: 20px auto;
        }
        .search-box input {
            width: 100%;
            padding: 12px 20px;
            border: 2px solid rgba(255, 255, 255, 0.2);
            border-radius: 25px;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            font-size: 16px;
        }
        .search-box input:focus {
            outline: none;
            border-color: #00d9ff;
        }
        .list-container {
            display: flex;
            flex-direction: column;
            gap: 15px;
            padding: 20px 0;
        }
        .route-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 15px 20px;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .route-card:hover {
            transform: translateX(5px);
            background: rgba(255, 255, 255, 0.1);
            border-color: #00d9ff;
        }
        .route-color {
            width: 40px;
            height: 40px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
            flex-shrink: 0;
        }
        .route-info {
            flex: 1;
            min-width: 0;
        }
        .route-name {
            font-size: 1.1em;
            font-weight: 600;
            color: #fff;
            margin-bottom: 5px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .route-meta {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }
        .type-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            background: rgba(0, 217, 255, 0.2);
            color: #00d9ff;
        }
        .circular-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            background: rgba(255, 193, 7, 0.2);
            color: #ffc107;
        }
        .station-count {
            font-size: 0.85em;
            color: rgba(255, 255, 255, 0.6);
        }
        .route-stations {
            flex: 2;
            min-width: 200px;
            overflow-x: auto;
            padding: 5px 0;
        }
        .station-list {
            display: flex;
            flex-wrap: nowrap;
            gap: 6px;
        }
        .station-tag {
            padding: 4px 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            font-size: 0.85em;
            color: rgba(255, 255, 255, 0.8);
            white-space: nowrap;
            flex-shrink: 0;
        }
        .station-tag.more {
            background: rgba(0, 217, 255, 0.2);
            color: #00d9ff;
        }
        .route-group {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            margin-bottom: 12px;
            transition: all 0.3s ease;
        }
        .route-group:hover {
            border-color: #00d9ff;
        }
        .route-header {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 15px 20px;
            cursor: pointer;
        }
        .route-header:hover {
            background: rgba(255, 255, 255, 0.05);
        }
        .route-color {
            width: 45px;
            height: 45px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3em;
            flex-shrink: 0;
        }
        .route-info {
            flex: 1;
            min-width: 0;
        }
        .route-name {
            font-size: 1.1em;
            font-weight: 600;
            color: #fff;
            margin-bottom: 5px;
        }
        .route-selector {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .route-select {
            flex: 1;
            max-width: 250px;
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 6px;
            color: #fff;
            font-size: 0.9em;
            cursor: pointer;
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23fff' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10l-5 5z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 10px center;
        }
        .route-select:focus {
            outline: none;
            border-color: #00d9ff;
        }
        .route-select option {
            background: #1a1a2e;
            color: #fff;
            padding: 10px;
        }
        .expand-btn {
            width: 36px;
            height: 36px;
            border: none;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            flex-shrink: 0;
        }
        .expand-btn:hover {
            background: rgba(0, 217, 255, 0.2);
        }
        .expand-btn svg {
            width: 20px;
            height: 20px;
            fill: #fff;
            transition: transform 0.3s ease;
        }
        .route-group.expanded .expand-btn svg {
            transform: rotate(180deg);
        }
        .direction-stations {
            display: none;
            padding: 0 20px 20px;
        }
        .route-group.expanded .direction-stations {
            display: block;
        }
        .station-list {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .station-tag {
            padding: 8px 15px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            font-size: 0.9em;
            color: rgba(255, 255, 255, 0.85);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .station-tag::before {
            content: "";
            width: 8px;
            height: 8px;
            background: rgba(0, 217, 255, 0.5);
            border-radius: 50%;
            flex-shrink: 0;
        }
        .station-tag:last-child::before {
            background: rgba(0, 255, 136, 0.5);
        }
        .station-tag.more {
            background: rgba(0, 217, 255, 0.15);
            color: #00d9ff;
            justify-content: center;
        }
        .station-tag.more::before {
            display: none;
        }
        .no-data {
            text-align: center;
            padding: 50px;
            color: rgba(255, 255, 255, 0.5);
        }
        @media (max-width: 768px) {
            .route-header {
                flex-wrap: wrap;
            }
            .route-selector {
                width: 100%;
                margin-top: 10px;
            }
            .route-select {
                max-width: none;
            }
        }
    </style>
</head>
<body>
    <header>
        <h1>🛤️ 线路列表</h1>
        <nav>
            <a href="/">🏠 首页</a>
            <a href="/stations">🚉 车站</a>
            <a href="/routes" class="active">🛤️ 线路</a>
            <a href="/admin">⚙️ 控制台</a>
        </nav>
    </header>
    
    <div class="container">
        <div class="stats">
            <span>线路总数: <span class="number">{{ count }}</span></span>
        </div>
        
        <div class="search-box">
            <input type="text" id="search" placeholder="搜索线路..." oninput="filterItems()">
        </div>
        
        <div class="list-container" id="route-list">
            {% for group in route_groups %}
            <div class="route-group" data-name="{{ group.name|lower }}" onclick="toggleGroup(this)">
                <div class="route-header">
                    {% if group.color %}
                    <div class="route-color" style="background-color: #{{ '%06x'|format(group.color) }}">
                        {% if group.type == 'train_high_speed' %}🚄
                        {% elif group.type == 'train_light_rail' %}🚃
                        {% else %}🚇{% endif %}
                    </div>
                    {% else %}
                    <div class="route-color" style="background: rgba(255,255,255,0.1)">🚇</div>
                    {% endif %}
                    <div class="route-info">
                        <div class="route-name">{{ group.name }}</div>
                        <div class="route-selector">
                            <select class="route-select" onclick="event.stopPropagation()" onchange="updateStations(this, '{{ loop.index }}')">
                                {% for direction in group.directions %}
                                <option value="{{ loop.index0 }}" 
                                        data-stations="{{ direction.stations|join(',') }}"
                                        data-color="{{ direction.color }}">
                                    {{ direction.direction }}
                                </option>
                                {% endfor %}
                            </select>
                        </div>
                    </div>
                    <button class="expand-btn" onclick="event.stopPropagation(); toggleGroup(this.closest('.route-group'))">
                        <svg viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
                    </button>
                </div>
                <div class="direction-stations">
                    <div class="station-list" id="stations-{{ loop.index }}">
                        {% set first_dir = group.directions[0] %}
                        {% for station in first_dir.stations %}
                        <span class="station-tag">{{ station }}</span>
                        {% endfor %}
                    </div>
                </div>
            </div>
            {% else %}
            <div class="no-data">暂无线路数据，请先更新数据</div>
            {% endfor %}
        </div>
    </div>
    
    <script>
    function filterItems() {
        const query = document.getElementById('search').value.toLowerCase();
        
        document.querySelectorAll('.route-group').forEach(card => {
            const name = card.dataset.name || '';
            card.style.display = name.includes(query) ? '' : 'none';
        });
    }
    
    function toggleGroup(element) {
        element.classList.toggle('expanded');
    }
    
    function updateStations(select, index) {
        const option = select.options[select.selectedIndex];
        const stations = option.dataset.stations.split(',');
        const stationList = document.getElementById('stations-' + index);
        
        let html = '';
        for (let i = 0; i < Math.min(stations.length, 15); i++) {
            html += '<span class="station-tag">' + stations[i] + '</span>';
        }
        if (stations.length > 15) {
            html += '<span class="station-tag more">+' + (stations.length - 15) + '站</span>';
        }
        
        stationList.innerHTML = html;
    }
    </script>
</body>
</html>
'''

# 登录页面HTML
LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTR路径查找器 - 登录</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 400px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #4a90e2, #50e3c2);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .header h1 {
            font-size: 1.5rem;
        }
        .content {
            padding: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 6px;
            font-size: 1rem;
        }
        .form-group input:focus {
            outline: none;
            border-color: #4a90e2;
        }
        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            background: linear-gradient(135deg, #4a90e2, #50e3c2);
            color: white;
            transition: all 0.3s ease;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
        }
        .message {
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 15px;
            text-align: center;
        }
        .message.error {
            background: #f8d7da;
            color: #721c24;
        }
        .back-link {
            display: block;
            text-align: center;
            margin-top: 15px;
            color: #4a90e2;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>控制台登录</h1>
        </div>
        <div class="content">
            {% if error %}
            <div class="message error">{{ error }}</div>
            {% endif %}
            <form method="POST">
                <div class="form-group">
                    <label for="password">密码</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="btn">登录</button>
            </form>
            <a href="/" class="back-link">← 返回首页</a>
        </div>
    </div>
</body>
</html>
'''


@app.route('/data/<filename>')
def serve_data_file(filename):
    '''提供数据文件'''
    if not filename.endswith('.json'):
        return '', 404
    if not os.path.exists(filename):
        return '', 404
    stat = os.stat(filename)
    last_modified = strftime('%a, %d %b %Y %H:%M:%S GMT', gmtime(stat.st_mtime))
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read(), 200, {'Content-Type': 'application/json', 'Last-Modified': last_modified}


@app.route('/admin')
def admin_page():
    '''控制台页面'''
    if not session.get('admin_logged_in'):
        return render_template_string(LOGIN_HTML)
    link_hash = hashlib.md5(config['LINK'].encode('utf-8')).hexdigest()
    return render_template_string(ADMIN_HTML, config=config, link_hash=link_hash, error=None)


@app.route('/admin', methods=['POST'])
def admin_login():
    '''处理登录'''
    password = request.form.get('password', '')
    if password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        link_hash = hashlib.md5(config['LINK'].encode('utf-8')).hexdigest()
        return render_template_string(ADMIN_HTML, config=config, link_hash=link_hash, error=None)
    return render_template_string(LOGIN_HTML, error='密码错误')


@app.route('/admin/logout')
def admin_logout():
    '''退出登录'''
    session.pop('admin_logged_in', None)
    return render_template_string(LOGIN_HTML, error=None)


@app.route('/admin/update-config-ajax', methods=['POST'])
def update_config_ajax():
    '''AJAX更新配置'''
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'error': '请先登录'})
    
    config['LINK'] = request.form.get('link', '')
    config['MTR_VER'] = int(request.form.get('mtr_ver', 4))
    config['UMAMI_SCRIPT_URL'] = request.form.get('umami_script_url', '')
    config['UMAMI_WEBSITE_ID'] = request.form.get('umami_website_id', '')
    
    return jsonify({'success': True})


@app.route('/admin/update-data-ajax', methods=['POST'])
def update_data_ajax():
    '''AJAX数据更新'''
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'error': '请先登录'})
    
    try:
        import subprocess
        import sys
        
        LINK = config['LINK']
        MTR_VER = config['MTR_VER']
        link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
        LOCAL_FILE = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
        INTERVAL_FILE = f'mtr-route-data-{link_hash}-{MTR_VER}.json'
        
        # 获取步骤参数
        data = request.get_json()
        step = data.get('step', 0) if data else 0
        
        if step == 1:
            update_script = f'''
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

work_dir = r'{os.getcwd()}'
os.chdir(work_dir)

try:
    from main import fetch_data
    
    local_path = fetch_data('{LINK}', '{LOCAL_FILE}', {MTR_VER})
    print("DEBUG:LOCAL_PATH=" + str(local_path))
    
    if os.path.exists('{LOCAL_FILE}'):
        print("SUCCESS:TRUE")
    else:
        print("ERROR:文件未创建")
except Exception as e:
    print("ERROR:" + str(e))
'''
        elif step == 2:
            update_script = f'''
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

work_dir = r'{os.getcwd()}'
os.chdir(work_dir)

try:
    from main import gen_route_interval
    
    gen_route_interval('{LOCAL_FILE}', '{INTERVAL_FILE}', '{LINK}', {MTR_VER})
    
    if os.path.exists('{INTERVAL_FILE}'):
        print("SUCCESS:TRUE")
    else:
        print("ERROR:路线数据文件未创建")
except Exception as e:
    print("ERROR:" + str(e))
'''
        else:
            return jsonify({'success': False, 'error': '无效的更新步骤'})
        
        proc = subprocess.run(
            [sys.executable, '-c', update_script],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=os.getcwd(),
            encoding='utf-8',
            errors='replace'
        )
        
        all_output = proc.stdout + proc.stderr
        all_output = all_output.strip()
        
        # 查找SUCCESS或ERROR标记
        success_marker = "SUCCESS:TRUE"
        error_marker = "ERROR:"
        
        if success_marker in all_output:
            return jsonify({'success': True})
        elif error_marker in all_output:
            # 提取错误信息
            idx = all_output.find(error_marker)
            error_msg = all_output[idx + len(error_marker):].strip()
            # 移除多余的行
            error_msg = error_msg.split('\n')[0].strip()
            return jsonify({'success': False, 'error': error_msg})
        else:
            # 没有找到标记，检查是否只有调试输出
            if "DEBUG:" in all_output:
                return jsonify({'success': True})
            return jsonify({'success': False, 'error': '处理过程中出现未知错误'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': '超时（超过3分钟）'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


#=================== 时刻表生成和查询功能 ====================
def tt_gen_departure_data(data, dep_data, filename1, filename2):
    '''
    生成发车数据
    
    Args:
        data: 包含车站和线路信息的数据字典
        dep_data: 发车数据字典
        filename1: 车站时刻表数据保存路径
        filename2: 列车时刻表数据保存路径
        
    Returns:
        包含车站线路发车数据、列车数据和所有线路发车数据的元组
    '''
    station_route_dep = {}
    all_route_dep = {}
    trains = {}
    station_train_id = {}
    
    for route_id, departures in dep_data.items():
        if route_id not in data['routes']:
            continue

        route = data['routes'][route_id]
        n = route['name']
        
        try:
            eng_name = n.split('|')[1].split('|')[0]
            if eng_name == '':
                eng_name = n.split('|')[0]
        except (IndexError, AttributeError):
            eng_name = n.split('|')[0] if '|' in n else n

        durations = route.get('durations', [])
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
        dwells = [x.get('dwellTime', 0) for x in route['stations']]
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
            dwell = round(dwells[i - 1] / 1000) if i - 1 < len(dwells) else 0
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

            for i_dep, x in enumerate(departures_new):
                new_dep = (dep_time + x + 8 * 60 * 60) % 86400
                train_id = station_train_id[_station1]
                station_route_dep[_station1][eng_name].append(
                    (route_id, new_dep, (i_dep, train_id)))
                all_route_dep[_station1][train_id] = (route_id, i_dep, new_dep)
                station_train_id[_station1] += 1

            if _station1 in station_route_dep and eng_name in station_route_dep[_station1]:
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


def tt_get_timetable(data, dep_data, station_name, route_name, use_second=False):
    '''
    获取指定车站和线路的时刻表
    
    Args:
        data: 包含车站信息的数据字典
        dep_data: 发车数据
        station_name: 车站名称
        route_name: 线路名称
        use_second: 是否包含秒
        
    Returns:
        包含(线路ID, 时间)元组的列表
    '''
    station_id = tt_station_name_to_id(data, station_name)
    if station_id is None:
        return []

    if station_id not in dep_data:
        return []
    
    if route_name not in dep_data[station_id]:
        return []
    
    dep_list = dep_data[station_id][route_name]
    dep_list.sort(key=lambda x: x[1])
    output = []
    
    for d in dep_list:
        result = tt_convert_time(d[1], use_second)
        if result not in output:
            output.append((d[0], result))

    return output


def tt_get_sta_timetable(data_v3, data, station, routes, station_tt):
    '''
    获取指定车站和线路的HTML格式时刻表
    
    Args:
        data_v3: 包含线路信息的数据字典（v3格式）
        data: 包含车站和线路信息的数据字典
        station: 车站名称或短ID
        routes: 线路名称或线路名称列表
        station_tt: 车站时刻表数据
        
    Returns:
        HTML格式的时刻表字符串，或None/False表示失败
    '''
    if isinstance(routes, str):
        routes = [routes]

    station_id = None
    try:
        sta_short_id = int(station)
        station_id = tt_station_short_id_to_id(data, sta_short_id)
    except (ValueError, TypeError):
        station_id = tt_station_name_to_id(data, station)

    if station_id is None:
        return None

    route_ids = []
    for r in routes:
        route_ids += tt_route_name_to_id(data_v3, r)

    if route_ids == []:
        return None

    all_stations = data['stations']
    all_routes = data['routes']
    short_id = all_stations[station_id].get('station', '')
    try:
        short_id = int('0x' + str(short_id), 16)
    except (ValueError, TypeError):
        short_id = None

    n = all_stations[station_id]['name']
    station_name = n.split('|')[0]
    if '|' in n:
        eng_name = n.split('|')[1].split('|')[0]
    else:
        eng_name = ''

    route_colors = [hex(all_routes[x]['color'])[2:].rjust(6, '0')
                    for x in route_ids]
    route_names = [all_routes[x]['name'].split('|')[0] for x in route_ids]
    route_names = list(set(route_names))
    
    next_stations = []
    last_stations = {}
    
    for x in route_ids:
        station_ids = [y['id'] for y in all_routes[x]['stations']]
        stations_names = [all_stations[y]['name'] for y in station_ids]
        
        if station_id in station_ids:
            i = station_ids.index(station_id)
            if i != len(station_ids) - 1:
                next_station = stations_names[i + 1].split('|')[0]
                last_station = stations_names[-1].split('|')[0]
                tmp_sta = last_station
                
                if 'WIP' in last_station:
                    last_station = last_station.split('WIP')[1]
                    last_station = last_station.strip('])').strip()

                final_last_sta = last_station[:4]
                if len(last_station) > 4 and final_last_sta in list(last_stations.values()):
                    k = len(last_station)
                    final_last_sta = last_station[:2] + last_station[k - 2:k]

                last_stations[tmp_sta] = final_last_sta
                
                if next_station not in next_stations and next_station != station_name:
                    next_stations.append(next_station)

    last_count = 0
    last_sta_table = ''
    for x, y in last_stations.items():
        if x != y:
            last_sta_table += f'{y}={x} '
            last_count += 1

    output = []
    count = 0
    
    if station_id not in station_tt:
        return False
    
    for train_id, train in station_tt[station_id].items():
        if train[0] not in route_ids:
            continue

        route_id = train[0]
        t = tt_convert_time(train[2])
        output.append((route_id, t, train_id))

    if output == []:
        return False

    output.sort(key=lambda x: x[1])
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{station_name} - 时刻表</title>
    <style>
        body {{ font-family: Arial; margin: 20px; }}
        .header {{ text-align: center; margin-bottom: 20px; }}
        .station-name {{ font-size: 24px; font-weight: bold; }}
        .station-id {{ font-size: 14px; color: #666; }}
        .route-row {{ display: flex; align-items: center; padding: 10px; margin: 5px 0; border-radius: 5px; }}
        .route-color {{ width: 50px; height: 50px; border-radius: 5px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; margin-right: 15px; }}
        .route-info {{ flex: 1; }}
        .route-name {{ font-size: 16px; font-weight: bold; }}
        .route-times {{ font-size: 14px; color: #333; margin-top: 5px; }}
        .time {{ display: inline-block; padding: 3px 8px; margin: 2px; background: #f0f0f0; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="station-name">{station_name}</div>
        <div class="station-id">ID: {short_id}</div>
    </div>
'''
    for route_id, t, train_id in output:
        route = all_routes.get(route_id, {})
        route_name = route.get('name', 'Unknown').split('|')[0]
        color = '#' + hex(route.get('color', 0))[2:].rjust(6, '0')
        dest_id = route.get('stations', [{}])[-1].get('id', '')
        dest_name = all_stations.get(dest_id, {}).get('name', '终点').split('|')[0]
        if dest_name in last_stations:
            dest_name = last_stations[dest_name]
        
        if route.get('circularState') == 'CLOCKWISE':
            dest_name = '顺时针'
        elif route.get('circularState') == 'ANTICLOCKWISE':
            dest_name = '逆时针'

        html += f'''
    <div class="route-row">
        <div class="route-color" style="background: {color}">{route_name[:2] if len(route_name) >= 2 else route_name}</div>
        <div class="route-info">
            <div class="route-name">{route_name} → {dest_name}</div>
            <div class="route-times">
                <span class="time">{t}</span>
            </div>
        </div>
    </div>
'''
    html += '</body></html>'
    
    return html


def tt_get_train(data, station, train_id, station_tt, train_tt):
    '''
    获取指定列车的详细信息
    
    Args:
        data: 包含车站和线路信息的数据字典
        station: 车站名称或短ID
        train_id: 列车ID
        station_tt: 车站时刻表数据
        train_tt: 列车时刻表数据
        
    Returns:
        包含列车详细信息的字典，或False表示失败
    '''
    station_id = None
    try:
        sta_short_id = int(station)
        station_id = tt_station_short_id_to_id(data, sta_short_id)
    except (ValueError, TypeError):
        station_id = tt_station_name_to_id(data, station)

    if station_id is None:
        return False

    if station_id not in station_tt:
        return False

    if train_id not in station_tt[station_id]:
        return False

    train_info = station_tt[station_id][train_id]
    route_id = train_info[0]
    idx = train_info[1]
    
    all_stations = data['stations']
    all_routes = data['routes']
    
    if route_id not in all_routes:
        return False
    
    route = all_routes[route_id]
    route_name = route['name'].replace('|', ' / ')
    
    route_stations = route.get('stations', [])
    if idx >= len(route_stations):
        return False
    
    train_timetable = train_tt.get(route_id, [])
    if idx >= len(train_timetable):
        return False
    
    timetable = train_timetable[idx]
    
    timetable_details = []
    for i, t in enumerate(timetable):
        if i >= len(route_stations):
            break
        sta = route_stations[i]
        sta_id = sta['id']
        sta_name = all_stations.get(sta_id, {}).get('name', sta_id).split('|')[0]
        time_str = tt_convert_time(t)
        timetable_details.append({
            'station': sta_name,
            'time': time_str,
            'arrival': time_str
        })
    
    destination_id = route_stations[-1].get('id', '')
    destination_name = all_stations.get(destination_id, {}).get('name', '终点').split('|')[0]
    
    if route.get('circularState') == 'CLOCKWISE':
        destination_name = '顺时针环线'
    elif route.get('circularState') == 'ANTICLOCKWISE':
        destination_name = '逆时针环线'

    return {
        'train_id': train_id,
        'route_id': route_id,
        'route_name': route_name,
        'route_color': route.get('color', 0),
        'destination': destination_name,
        'timetable': timetable_details
    }


def tt_random_train(data, train_tt, departure_time=None):
    '''
    获取随机列车的信息
    
    Args:
        data: 包含车站和线路信息的数据字典
        train_tt: 列车时刻表数据
        departure_time: 发车时间（秒），默认为当前时间
        
    Returns:
        包含列车详细信息的字典，或None表示失败
    '''
    import random
    
    if departure_time is None:
        departure_time = int(time()) % 86400
    
    all_routes = data['routes']
    
    valid_trains = []
    for route_id, timetables in train_tt.items():
        if route_id not in all_routes:
            continue
        route = all_routes[route_id]
        for idx, timetable in enumerate(timetables):
            if len(timetable) == 0:
                continue
            first_time = timetable[0]
            if first_time >= departure_time or first_time + 3600 >= departure_time:
                valid_trains.append((route_id, idx))
    
    if not valid_trains:
        return None
    
    route_id, idx = random.choice(valid_trains)
    route = all_routes[route_id]
    timetable = train_tt[route_id][idx]
    
    all_stations = data['stations']
    route_name = route['name'].replace('|', ' / ')
    
    timetable_details = []
    for i, t in enumerate(timetable):
        if i >= len(route.get('stations', [])):
            break
        sta = route['stations'][i]
        sta_id = sta['id']
        sta_name = all_stations.get(sta_id, {}).get('name', sta_id).split('|')[0]
        time_str = tt_convert_time(t)
        timetable_details.append({
            'station': sta_name,
            'time': time_str
        })
    
    destination_id = route.get('stations', [{}])[-1].get('id', '')
    destination_name = all_stations.get(destination_id, {}).get('name', '终点').split('|')[0]
    
    if route.get('circularState') == 'CLOCKWISE':
        destination_name = '顺时针环线'
    elif route.get('circularState') == 'ANTICLOCKWISE':
        destination_name = '逆时针环线'

    return {
        'route_id': route_id,
        'route_name': route_name,
        'route_color': route.get('color', 0),
        'destination': destination_name,
        'timetable': timetable_details,
        'departure_time': tt_convert_time(timetable[0]) if timetable else None
    }


def load_timetable_data():
    '''加载时刻表数据'''
    LINK = config.get('LINK', '')
    MTR_VER = config.get('MTR_VER', 4)
    if not LINK:
        return None, None
    link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
    LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json'
    STATION_TT_PATH = f'station_timetable_{link_hash}.dat'
    TRAIN_TT_PATH = f'train_timetable_{link_hash}.dat'
    
    if not os.path.exists(LOCAL_FILE_PATH):
        return None, None
    
    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)
    
    station_tt = None
    train_tt = None
    if os.path.exists(STATION_TT_PATH):
        with open(STATION_TT_PATH, 'rb') as f:
            station_tt = pickle.load(f)
    if os.path.exists(TRAIN_TT_PATH):
        with open(TRAIN_TT_PATH, 'rb') as f:
            train_tt = pickle.load(f)
    
    return data, (station_tt, train_tt)


@app.route('/timetable')
def timetable_page():
    '''时刻表查询首页'''
    return render_template_string(TIMETABLE_INDEX_HTML)


@app.route('/timetable/station', methods=['GET', 'POST'])
def timetable_station():
    '''车站时刻表查询'''
    result = None
    error = None
    station_name = ''
    
    if request.method == 'POST':
        station_name = request.form.get('station_name', '').strip()
        route_name = request.form.get('route_name', '').strip()
        
        data, tt_data = load_timetable_data()
        if data is None:
            error = '数据未加载，请先更新车站数据'
        elif station_name:
            station_id = tt_station_name_to_id(data, station_name)
            if station_id is None:
                error = f'未找到车站: {station_name}'
            else:
                station_info = data['stations'].get(station_id, {})
                station_full_name = station_info.get('name', station_name)
                station_short_id = station_info.get('station', '')
                try:
                    station_short_id = int('0x' + str(station_short_id), 16)
                except:
                    station_short_id = None
                
                routes = data[0]['routes'] if isinstance(data, list) else data.get('routes', [])
                route_list = []
                for route in routes:
                    route_stations = route.get('stations', [])
                    station_ids = [s['id'] for s in route_stations]
                    if station_id not in station_ids:
                        continue
                    idx = station_ids.index(station_id)
                    if idx >= len(route_stations):
                        continue
                    
                    route_name_formatted = route['name'].replace('||', ' ').replace('|', ' ')
                    route_color = route.get('color', 0)
                    route_type = route.get('type', 'train_normal')
                    
                    next_station = None
                    prev_station = None
                    if idx < len(route_stations) - 1:
                        next_station = route_stations[idx + 1]
                    if idx > 0:
                        prev_station = route_stations[idx - 1]
                    
                    stations = data[0]['stations'] if isinstance(data, list) else data.get('stations', {})
                    
                    route_list.append({
                        'route_id': route['id'],
                        'route_name': route_name_formatted,
                        'route_color': route_color,
                        'route_type': route_type,
                        'station_position': idx + 1,
                        'total_stations': len(route_stations),
                        'next_station': {
                            'id': next_station['id'] if next_station else None,
                            'name': stations.get(next_station['id'], {}).get('name', '').split('|')[0] if next_station else None
                        } if next_station else None,
                        'prev_station': {
                            'id': prev_station['id'] if prev_station else None,
                            'name': stations.get(prev_station['id'], {}).get('name', '').split('|')[0] if prev_station else None
                        } if prev_station else None
                    })
                
                result = {
                    'station_id': station_id,
                    'station_name': station_full_name.split('|')[0],
                    'station_short_id': station_short_id,
                    'routes': route_list,
                    'total_routes': len(route_list)
                }
    
    return render_template_string(TIMETABLE_STATION_HTML, 
                                  result=result, error=error, 
                                  station_name=station_name)


@app.route('/timetable/random')
def timetable_random():
    '''随机列车展示'''
    data, tt_data = load_timetable_data()
    
    if data is None or tt_data[1] is None:
        return render_template_string(TIMETABLE_RANDOM_HTML, 
                                     train=None, error='时刻表数据未加载')
    
    train_tt = tt_data[1]
    train = tt_random_train(data, train_tt)
    
    if train is None:
        return render_template_string(TIMETABLE_RANDOM_HTML, 
                                     train=None, error='未找到列车数据')
    
    return render_template_string(TIMETABLE_RANDOM_HTML, 
                                 train=train, error=None)


#=================== 时刻表页面模板 ====================
TIMETABLE_INDEX_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>时刻表 - MTR路径查找器</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        header { text-align: center; padding: 30px; background: white; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); margin-bottom: 30px; }
        header h1 { color: #333; font-size: 2em; margin-bottom: 10px; }
        header p { color: #666; }
        .nav-links { display: flex; justify-content: center; gap: 15px; margin-top: 20px; flex-wrap: wrap; }
        .nav-links a { color: #667eea; text-decoration: none; padding: 10px 20px; background: #f0f4ff; border-radius: 8px; transition: all 0.3s; }
        .nav-links a:hover { background: #667eea; color: white; }
        .menu { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
        .menu-item { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); text-align: center; transition: transform 0.3s; }
        .menu-item:hover { transform: translateY(-5px); }
        .menu-item h2 { color: #333; margin-bottom: 15px; }
        .menu-item p { color: #666; margin-bottom: 20px; }
        .menu-item a { display: inline-block; padding: 12px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 10px; }
        .menu-item a:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚇 时刻表查询</h1>
            <p>查询MTR列车时刻表信息</p>
            <div class="nav-links">
                <a href="/">🏠 首页</a>
                <a href="/stations">🚉 车站列表</a>
                <a href="/routes">🛤️ 线路列表</a>
                <a href="/admin">⚙️ 控制台</a>
            </div>
        </header>
        
        <div class="menu">
            <div class="menu-item">
                <h2>🚉 车站时刻表</h2>
                <p>查询车站经过的列车信息</p>
                <a href="/timetable/station">查询</a>
            </div>
            <div class="menu-item">
                <h2>🚄 随机列车</h2>
                <p>展示随机列车的时刻表</p>
                <a href="/timetable/random">查看</a>
            </div>
        </div>
    </div>
</body>
</html>
'''


TIMETABLE_STATION_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>车站时刻表 - MTR路径查找器</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        header { text-align: center; padding: 30px; background: white; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); margin-bottom: 30px; }
        header h1 { color: #333; font-size: 2em; margin-bottom: 10px; }
        .nav-links { display: flex; justify-content: center; gap: 15px; margin-top: 20px; flex-wrap: wrap; }
        .nav-links a { color: #667eea; text-decoration: none; padding: 10px 20px; background: #f0f4ff; border-radius: 8px; transition: all 0.3s; }
        .nav-links a:hover { background: #667eea; color: white; }
        .search-box { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); margin-bottom: 30px; }
        .search-box h2 { color: #333; margin-bottom: 20px; }
        .search-form { display: flex; gap: 15px; flex-wrap: wrap; }
        .search-form input { flex: 1; min-width: 200px; padding: 15px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 1em; }
        .search-form input:focus { outline: none; border-color: #667eea; }
        .search-form button { padding: 15px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 10px; font-size: 1em; cursor: pointer; }
        .results { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }
        .results h2 { color: #333; margin-bottom: 20px; }
        .route-card { padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; margin-bottom: 15px; display: flex; gap: 15px; }
        .route-color { width: 60px; height: 60px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; flex-shrink: 0; }
        .route-info h3 { color: #333; margin-bottom: 8px; }
        .route-info p { color: #666; font-size: 0.95em; margin-bottom: 5px; }
        .route-info .badge { display: inline-block; padding: 4px 10px; background: #f0f4ff; border-radius: 4px; font-size: 0.85em; color: #667eea; margin-right: 8px; }
        .error { padding: 40px; background: #fdeaea; color: #e74c3c; border-radius: 10px; text-align: center; }
        .empty { padding: 40px; background: #f8f9fa; color: #666; border-radius: 10px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚉 车站时刻表</h1>
            <div class="nav-links">
                <a href="/">🏠 首页</a>
                <a href="/timetable">📅 时刻表首页</a>
                <a href="/timetable/random">🚄 随机列车</a>
            </div>
        </header>
        
        <div class="search-box">
            <h2>🔍 查询车站</h2>
            <form method="POST" class="search-form">
                <input type="text" name="station_name" placeholder="输入车站名称（如：香港、九龍）" value="{{ station_name }}">
                <input type="text" name="route_name" placeholder="线路名称（可选）">
                <button type="submit">查询</button>
            </form>
        </div>
        
        <div class="results">
            {% if error %}
            <div class="error">{{ error }}</div>
            {% elif result %}
            <h2>📋 {{ result.station_name }}{% if result.station_short_id %}(ID: {{ result.station_short_id }}){% endif %}</h2>
            {% if result.total_routes == 0 %}
            <div class="empty">未找到该车站的线路信息</div>
            {% else %}
            {% for route in result.routes %}
            <div class="route-card">
                <div class="route-color" style="background: #{{ '%06x'|format(route.route_color) }}">
                    {% if 'high_speed' in route.route_type %}🚄
                    {% elif 'light_rail' in route.route_type %}🚊
                    {% elif 'boat' in route.route_type %}🚢
                    {% elif 'cable' in route.route_type %}🚡
                    {% else %}🚇{% endif %}
                </div>
                <div class="route-info">
                    <h3>{{ route.route_name }}</h3>
                    <p>
                        <span class="badge">第{{ route.station_position }}/{{ route.total_stations }}站</span>
                    </p>
                    <p>
                        <strong>上一站:</strong> {{ route.prev_station.name if route.prev_station else '起点' }} |
                        <strong>下一站:</strong> {{ route.next_station.name if route.next_station else '终点' }}
                    </p>
                </div>
            </div>
            {% endfor %}
            {% endif %}
            {% else %}
            <p style="color: #666;">输入车站名称查询经过该车站的线路信息。</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''


TIMETABLE_RANDOM_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>随机列车 - MTR路径查找器</title>
    {% if config['UMAMI_SCRIPT_URL'] and config['UMAMI_WEBSITE_ID'] %}
    <script defer src="{{ config['UMAMI_SCRIPT_URL'] }}" data-website-id="{{ config['UMAMI_WEBSITE_ID'] }}"></script>
    {% endif %}
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        header { text-align: center; padding: 30px; background: white; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); margin-bottom: 30px; }
        header h1 { color: #333; font-size: 2em; margin-bottom: 10px; }
        .nav-links { display: flex; justify-content: center; gap: 15px; margin-top: 20px; flex-wrap: wrap; }
        .nav-links a { color: #667eea; text-decoration: none; padding: 10px 20px; background: #f0f4ff; border-radius: 8px; transition: all 0.3s; }
        .nav-links a:hover { background: #667eea; color: white; }
        .refresh-btn { display: inline-block; padding: 12px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 10px; margin-bottom: 30px; }
        .refresh-btn:hover { opacity: 0.9; }
        .train-card { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }
        .train-header { display: flex; align-items: center; gap: 20px; margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #e0e0e0; }
        .train-icon { width: 80px; height: 80px; border-radius: 16px; display: flex; align-items: center; justify-content: center; color: white; font-size: 2em; }
        .train-info h2 { color: #333; margin-bottom: 5px; }
        .train-info p { color: #666; }
        .timetable { margin-top: 20px; }
        .timetable h3 { color: #333; margin-bottom: 15px; }
        .station-row { display: flex; align-items: center; padding: 12px 0; border-bottom: 1px solid #f0f0f0; }
        .station-time { width: 80px; color: #667eea; font-weight: bold; }
        .station-name { color: #333; }
        .error { background: white; padding: 40px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); text-align: center; color: #e74c3c; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚄 随机列车</h1>
            <div class="nav-links">
                <a href="/">🏠 首页</a>
                <a href="/timetable">📅 时刻表首页</a>
                <a href="/timetable/station">🚉 车站时刻表</a>
            </div>
        </header>
        
        <div style="text-align: center;">
            <a href="/timetable/random" class="refresh-btn">🔄 换一列</a>
        </div>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% elif train %}
        <div class="train-card">
            <div class="train-header">
                <div class="train-icon" style="background: #{{ '%06x'|format(train.route_color) }}">
                    {% if 'high_speed' in train.route_name|lower %}🚄
                    {% elif 'light_rail' in train.route_name|lower %}🚊
                    {% elif 'boat' in train.route_name|lower %}🚢
                    {% elif 'cable' in train.route_name|lower %}🚡
                    {% else %}🚇{% endif %}
                </div>
                <div class="train-info">
                    <h2>{{ train.route_name }}</h2>
                    <p>终点站: {{ train.destination }}{% if train.departure_time %} | 首班: {{ train.departure_time }}{% endif %}</p>
                </div>
            </div>
            
            <div class="timetable">
                <h3>📍 停靠站时刻</h3>
                {% for stop in train.timetable %}
                <div class="station-row">
                    <div class="station-time">{{ stop.time }}</div>
                    <div class="station-name">{{ stop.station }}</div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% else %}
        <div class="error">加载中...</div>
        {% endif %}
    </div>
</body>
</html>
'''


def run():
    '''运行Flask应用'''
    print("启动MTR路径查找器Web服务...")
    print("访问 http://localhost:5000 使用路径查找功能")
    print(f"控制台: http://localhost:5000/admin (密码: {ADMIN_PASSWORD})")
    app.run(debug=True, host='0.0.0.0', port=5000)


if __name__ == '__main__':
    run()  # 程序入口点
