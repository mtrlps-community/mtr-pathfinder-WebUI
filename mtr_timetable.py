'''
Generate station departures and train timetables for Minecraft Transit Railway.
'''

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from statistics import mode
# from io import BytesIO
# from time import time
# import base64
import json
import pickle
import random

# from html2image import Html2Image
from opencc import OpenCC
# from PIL import Image

# tt_hti = Html2Image(browser='chrome')
tt_opencc1 = OpenCC('s2t')
tt_opencc2 = OpenCC('t2jp')
tt_opencc3 = OpenCC('t2s')
tt_opencc4 = OpenCC('jp2t')

# EXPRESS_TABLE = {'CFR||FAST Up': '快速',
#                  'CFR||FAST Down': '快速',
#                  'CTG Intercity Southwest||Junee > Yongsan': '特急',
#                  'CTG Intercity Southwest||Yongsan > Junee': '特急',
#                  'CrossCountry||Airport - Seowonju 12': '',
#                  }

# 区间快速 - 西武池袋快速 #00CCFF
# 快速 - 京王调布快速 #0F4E8C
# 区间准急 - 京急品川有列 #6600CC
# # 准急 - 小田急町田通勤准急 #00C290
# 准急 - 东急涩谷急行 #FC4226
# 区间急行 - 京王调布区间急行 #D3C427
# 急行 - 京王调布急行 #05B08D
# 特急 - JR八王子特急 #CB3550
# 卧铺列车 - JR八王子特急 #CB3550
# 快特 - 小田急小田原快急 #FF8F0C
EXPRESS_TABLE = {'CFR||MED': '快速',
                 'CFR||FAST': '急行',
                 'CFR||NIGHT': '卧铺特急',
                 'CTG Intercity Southwest': '特急',
                 'CTG Intercity Southwest': '特急',
                 'Grand Central': '快速特急',
                 'CrossCountry': '特急',
                 'Einsburg Express': '特急',
                #  'CrossCountry||Portsmouth - Carmine 02': '急行',
                #  'CrossCountry||Portsmouth-Kirkenkessie 05': '急行',
                 'CrossCountry||Mimatsu->Portsmouth 11': '急行',
                 'CrossCountry||Portsmouth->Mimatsu 11': '急行',
                 'CrossCountry||Seowonju - Airport 12': '快速',
                 'CrossCountry||Airport - Seowonju 12': '快速',
                 'CrossCountry||Liskeard Intl - Portsmouth Express 01': '快速特急',
                 'CrossCountry||Portsmouth - Liskeard Intl Express 01': '快速特急',
                 'First Great Western||Brighton > Seoul Express': '特急',
                 'First Great Western||Seoul>Brighton Express': '特急',
                 'First Great Western||Portsmouth>Yongsan Semifast': '急行',
                 'First Great Western||Yongsan>Portsmouth Semifast': '急行',
                 'ITX 청춘|ITX Cheongchun': '特急',
                 'KTX-이음|KTX-EUM': '快速特急',
                 'Moszyan Railways Intercity Direct': '快速特急',
                 'Nightjet': '卧铺快特',
                 'Moszyan Railways Intercity': '特急',
                 'Moszyan Railways Sprinter||4400': '区间快速',
                 '虹灣綫|Sinus Line||Exp': '急行',
                 '東側南北綫|Eastern North-South Line||RSE': '区间准急',
                 '東側南北綫|Eastern North-South Line||Semi-Exp': '准急',
                 '東側南北綫|Eastern North-South Line||REXP': '区间急行',
                 '東側南北綫|Eastern North-South Line||Exp': '急行',
                 '東側南北綫S特急': '特急',
                 '大立綫': '特急',
                 '歐洲之星|Eurostar': '特急',
                 '縞野輕鐵|Shimano LRT||AC01': '区间快速',
                 '花越綫|Hana-Koshi Line||快速': '快速',
                 '花越綫|Hana-Koshi Line||特快': '特急',
                 '西南列車|South West Trains||Brighton-Portsmouth Semifast': '特急',
                 '西南列車|South West Trains||Portsmouth - Brighton Semifast': '特急',
                 '觀光綫|Sightseeing Line||K1S': '区间快速',
                 '觀光綫|Sightseeing Line||K1X': '区间快速',
                 '觀光綫|Sightseeing Line||K3S': '区间快速',
                 '觀光綫|Sightseeing Line||K3X': '区间快速',
                 '藍星花越綫|CyanEX Hana-Koshi Line||22S': '快速',
                 '藍星花越綫|CyanEX Hana-Koshi Line||22X': '快速',
                 '錦繡城特快|Fairview Express': '特急',
                 '麗蓮輕鐵|Lilac Light Rail||771X': '区间急行',
                 '麗蓮輕鐵|Lilac Light Rail||P300': '特急',
                 '麗蓮輕鐵|Lilac Light Rail||P300S': '特急',
                 'KTT': '特急',
                 '六花西鐵|Rikka West Rail||Mimatsu -> Rikkashi <EXPRESS>': '急行',
                 '六花西鐵|Rikka West Rail||Rikkashi -> Mimatsu <EXPRESS>': '急行',
                 '西米德蘭鐵路|West Midlands Railway||Krestona -> Worcester Semifast': '急行',
                 '西米德蘭鐵路|West Midlands Railway||Worcester -> Krestona Semifast': '急行',
                 '六花西鐵|Rikka West Rail||Cheongnyangni -> Pungyang': '区间快速',
                 '六花西鐵|Rikka West Rail||Pungyang -> Cheongnyangni': '区间快速',
                 '六花西鐵|Rikka West Rail||Pungyang -> Seoul': '区间急行',
                 '六花西鐵|Rikka West Rail||Seoul -> Pungyang': '区间急行'}

COLOR_TABLE = {'区间快速': '#00CCFF',
               '快速': '#0F4E8C',
               '区间准急': '#6600CC',
               '准急': '#FC4226',
            #    '准急': '#00C290',
               '区间急行': '#D3C427',
               '急行': '#05B08D',
               '特急': '#CB3550',
               '快速特急': '#FF8F0C',
               '卧铺特急': '#CB3550',
               '卧铺快特': '#FF8F0C'}
COLOR_TABLE = OrderedDict(COLOR_TABLE)


def route_name_to_id(data: dict, route_name: str) -> list[str]:
    '''
    Convert one route's name to its ID.
    '''
    for route in data[0]['routes']:
        if route_name == route['id']:
            return [route_name]

    route_name = route_name.lower()
    result = []
    for route in data[0]['routes']:
        output: str = route['id']
        n: str = route['name']
        number: str = route['number']
        route_names = [n, n.split('|')[0]]
        if ('||' in n and n.count('|') > 2) or \
                ('||' not in n and n.count('|') > 0):
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


def get_close_matches(words, possibilities, cutoff=0.2):
    result = [(-1, None)]
    s = SequenceMatcher()
    for word in words:
        s.set_seq2(word)
        for x, y in possibilities:
            s.set_seq1(x)
            if s.real_quick_ratio() >= cutoff and \
                    s.quick_ratio() >= cutoff:
                ratio = s.ratio()
                if ratio >= cutoff:
                    result.append((ratio, y))

    return max(result)[1]


def station_name_to_id(data: dict, sta: str,
                       fuzzy_compare=True) -> str:
    '''
    Convert a station's name to its ID.
    '''
    sta = sta.lower()
    tra1 = tt_opencc1.convert(sta)
    sta_try = [sta, tra1, tt_opencc2.convert(tra1)]

    all_names = []
    stations = data['stations']
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

    if has_station is False and fuzzy_compare is True:
        output = get_close_matches(sta_try, all_names)

    return output


def station_short_id_to_id(data: dict, short_id: int) -> str:
    '''
    Convert one station's short ID to its ID.
    '''
    short_id = hex(short_id)[2:]
    stations = data['stations']
    output = None
    for station_id, station_dict in stations.items():
        if short_id == station_dict['station']:
            output = station_id
            break

    return output


def convert_time(t, use_second=False):
    if use_second is True:
        hour = str(t // (60 * 60)).rjust(2, '0')
        minute = str((t % 3600) // 60).rjust(2, '0')
        second = str(t % 60).rjust(2, '0')
        result = ':'.join([hour, minute, second])
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
        result = ':'.join([hour, minute])

    return result


def get_timetable(data, dep_data, station_name, route_name, use_second=False):
    station_id = station_name_to_id(data, station_name)
    data = dep_data[station_id][route_name]
    data.sort(key=lambda x: x[1])
    output = []
    for d in data:
        result = convert_time(d[1], use_second)
        if result not in output:
            output.append((d[0], result))

    return output


def get_train(data, station, train_id: int,
              station_tt: dict[str, dict[str, tuple]],
              train_tt: dict[str, list[tuple]]):
    station_id = None
    try:
        sta_short_id = int(station)
        station_id = station_short_id_to_id(data, sta_short_id)
    except ValueError:
        station_id = station_name_to_id(data, station)

    if station_id is None:
        return None

    try:
        route_id, i, dep = station_tt[station_id][train_id]
    except KeyError:
        return False

    train: list = train_tt[route_id][i]
    all_stations = data['stations']
    route_data = data['routes'][route_id]
    route_name: str = route_data['name']
    route_name = route_name.replace('||', ' ').replace('|', ' ')
    route_stations = route_data['stations']

    timetable = [convert_time(x % 86400, use_second=True) for x in train]
    output = []
    msg = tuple()
    _t2 = 2 ** 32
    for i, x in enumerate(route_stations):
        if i == 0:
            t1 = None
        else:
            try:
                t1 = timetable.pop(0)
                train.pop(0)
            except IndexError:
                continue

        if i == len(route_stations) - 1:
            t2 = None
            _t2 = None
        else:
            try:
                t2 = timetable.pop(0)
                _t2 = train.pop(0)
            except IndexError:
                continue

        if _t2 is not None and _t2 % 86400 == dep % 86400:
            # 停站
            msg = (all_stations[x['id']]['name'].split('|')[0], )

        station_name = all_stations[x['id']]['name']
        output.append((station_name.split('|')[0], t1, t2, x['id']))

    return route_name, output, msg


def route_random_train(data_v3, data, route, trains: dict[str, list],
                       departure_time: int = None):
    route_id = route_name_to_id(data_v3, route)
    if route_id == []:
        return None

    all_stations = data['stations']
    tz = 8
    if departure_time is None:
        dtz = timezone(timedelta(hours=tz))
        t1 = datetime.now().replace(year=1970, month=1, day=1)
        try:
            t1 = t1.astimezone(dtz).replace(tzinfo=timezone.utc)
        except OSError:
            t1 = t1.replace(tzinfo=timezone.utc)

        departure_time = round(t1.timestamp())

    departure_time %= 86400

    # route = trains[route_id]
    # route_data = data['routes'][route_id]
    # if len(route) == 0:
    #     return False

    # train = [-1]
    # tries = 3000
    # while (departure_time < min(train) or departure_time > max(train)) and \
    #         (departure_time + 86400 < min(train) or
    #          departure_time + 86400 > max(train)):
    #     train = random.choice(route)
    #     tries -= 1
    #     if tries == 0:
    #         break

    # if train == [-1]:
    #     train = random.choice(route)

    all_trains = [(x, trains[x]) for x in route_id if x in trains]
    train = [-1]
    tries = 3000
    while (departure_time < min(train) or departure_time > max(train)) and \
            (departure_time + 86400 < min(train) or
             departure_time + 86400 > max(train)):
        route = random.choice(all_trains)
        if len(route[1]) == 0:
            continue

        train = random.choice(route[1])
        route_data = data['routes'][route[0]]
        tries -= 1
        if tries == 0:
            break

        if len(train) == 0:
            continue

    if train == [-1]:
        route = [0, 0]
        tries = 1000
        while len(route[1]) == 0 or len(train) == 0:
            route = random.choice(all_trains)
            train = random.choice(route)
            route_data = data['routes'][route[0]]
            tries -= 1
            if tries == 0:
                break

    route_name: str = route_data['name']
    route_name = route_name.replace('||', ' ').replace('|', ' ')
    route_stations = route_data['stations']

    timetable = [convert_time(x % 86400, use_second=True) for x in train]
    output = []
    msg = tuple()
    _t2 = 2 ** 32
    for i, x in enumerate(route_stations):
        if i == 0:
            t1 = None
            _t1 = None
        else:
            t1 = timetable.pop(0)
            _t1 = train.pop(0)

        if _t1 is not None and _t2 is not None and \
                (_t2 <= departure_time <= _t1 or
                 _t2 <= departure_time + 86400 <= _t1):
            # 运行
            last_id = all_stations[route_stations[i - 1]['id']]
            msg = ((last_id['name'].split('|')[0],
                    all_stations[x['id']]['name'].split('|')[0]))

        if i == len(route_stations) - 1:
            t2 = None
            _t2 = None
        else:
            t2 = timetable.pop(0)
            _t2 = train.pop(0)

        if _t1 is not None and _t2 is not None and \
                (_t1 < departure_time < _t2 or
                 _t1 < departure_time + 86400 < _t2):
            # 停站
            msg = (all_stations[x['id']]['name'].split('|')[0], )

        station_name = all_stations[x['id']]['name']
        output.append((station_name.split('|')[0], t1, t2, x['id']))

    return route_name, output, msg


def random_train(data, trains: dict[str, list], departure_time: int = None):
    all_stations = data['stations']
    tz = 8
    if departure_time is None:
        dtz = timezone(timedelta(hours=tz))
        t1 = datetime.now().replace(year=1970, month=1, day=1)
        try:
            t1 = t1.astimezone(dtz).replace(tzinfo=timezone.utc)
        except OSError:
            t1 = t1.replace(tzinfo=timezone.utc)

        departure_time = round(t1.timestamp())

    departure_time %= 86400

    all_trains = list(trains.items())
    train = [-1]
    tries = 3000
    while (departure_time < min(train) or departure_time > max(train)) and \
            (departure_time + 86400 < min(train) or
             departure_time + 86400 > max(train)):
        route = random.choice(all_trains)
        if len(route[1]) == 0:
            continue

        route_data = data['routes'][route[0]]
        # if route_data['hidden'] is True:
        #     continue

        train = random.choice(route[1])
        tries -= 1
        if tries == 0:
            break

    route_name: str = route_data['name']
    route_name = route_name.replace('||', ' ').replace('|', ' ')
    route_stations = route_data['stations']

    timetable = [convert_time(x % 86400, use_second=True) for x in train]
    output = []
    msg = tuple()
    _t2 = 2 ** 32
    for i, x in enumerate(route_stations):
        if i == 0:
            t1 = None
            _t1 = None
        else:
            t1 = timetable.pop(0)
            _t1 = train.pop(0)

        if _t1 is not None and _t2 is not None and \
                (_t2 <= departure_time <= _t1 or
                 _t2 <= departure_time + 86400 <= _t1):
            # 运行
            last_id = all_stations[route_stations[i - 1]['id']]
            msg = ((last_id['name'].split('|')[0],
                    all_stations[x['id']]['name'].split('|')[0]))

        if i == len(route_stations) - 1:
            t2 = None
            _t2 = None
        else:
            t2 = timetable.pop(0)
            _t2 = train.pop(0)

        if _t1 is not None and _t2 is not None and \
                (_t1 < departure_time < _t2 or
                 _t1 < departure_time + 86400 < _t2):
            # 停站
            msg = (all_stations[x['id']]['name'].split('|')[0], )

        station_name = all_stations[x['id']]['name']
        output.append((station_name.split('|')[0], t1, t2, x['id']))

    return route_name, output, msg


def generate_train_html(data, template_file, route_name,
                        stations_and_time, highlight):
    with open(template_file, 'r', encoding='utf-8') as f:
        html = f.read()

    template = ''
    for i, (sta_name, arr, dep, sta_id) in enumerate(stations_and_time):
        if i == 0:
            continue
        elif i == len(stations_and_time) - 1:
            continue

        template_1 = '''<li class="stops-list ">
<dl class="stops">
<dt class="station-name">
<a href="/xxx" class="station-name-link">{{station}}</a>
</dt>
<dd class="from-to-time">{{arrival_time}}到<br>{{departure_time}}发
</dd>
<dd class="diagram-link"><a href="/timetable/station/{{id}}">[时刻表]</a>
</dd>
</dl>
</li>
'''
        template_2 = '''<li class="stops-list focus">
<dl class="stops">
<dt class="station-name">
<a href="/xxx" class="station-name-link">{{station}}</a>
</dt>
<dd class="from-to-time">{{arrival_time}}到<br>{{departure_time}}发
</dd>
<dd class="diagram-link"><a href="/timetable/station/{{id}}">[时刻表]</a>
</dd>
</dl>
</li>
'''
        if sta_name in highlight:
            last_sta = stations_and_time[i - 1][0]
            next_sta = stations_and_time[i + 1][0]
            if len(highlight) == 1 or highlight == (last_sta, sta_name) or \
                    highlight == (sta_name, next_sta):
                template_1 = template_2

        template_1 = template_1.replace('{{station}}', sta_name)
        if arr == dep:
            template_1 = template_1.replace('<br>{{departure_time}}发', '')
        template_1 = template_1.replace('{{arrival_time}}', arr)
        template_1 = template_1.replace('{{departure_time}}', dep)
        station_id = data['stations'][sta_id]['station']
        station_id = str(int('0x' + str(station_id), 16))
        template_1 = template_1.replace('{{id}}', station_id)
        template += template_1

    origin = stations_and_time[0][0]
    if len(highlight) > 0 and origin == highlight[0]:
        html = html.replace('{{focus_1}}', 'focus')
    else:
        html = html.replace('{{focus_1}}', '')

    destination = stations_and_time[-1][0]
    if len(highlight) > 0 and destination == highlight[-1]:
        html = html.replace('{{focus_2}}', 'focus')
    else:
        html = html.replace('{{focus_2}}', '')

    origin_id = data['stations'][stations_and_time[0][3]]['station']
    origin_id = str(int('0x' + str(origin_id), 16))
    destination_id = data['stations'][stations_and_time[-1][3]]['station']
    destination_id = str(int('0x' + str(destination_id), 16))

    html = html.replace('{{focus_2}}', 'focus')
    html = html.replace('{{origin}}', origin)
    html = html.replace('{{depart_time}}', stations_and_time[0][2])
    html = html.replace('{{id_1}}', origin_id)
    html = html.replace('{{destination}}', destination)
    html = html.replace('{{arrive_time}}', stations_and_time[-1][1])
    html = html.replace('{{id_2}}', destination_id)
    html = html.replace('{{route_name}}', route_name)
    html = html.replace('{{time_now}}', datetime.now().strftime('%H:%M:%S'))
    html = html.replace('{{template}}', template)
    return html, (600, 100 + 57 * len(stations_and_time))

    # with open(filename, 'w', encoding='utf-8') as f:
    #     f.write(html)

    # return filename


def main_route_random_train(LOCAL_FILE_PATH, LOCAL_FILE_PATH_V3,
                            DATABASE_PATH, route_name,
                            departure_time=None) -> tuple[str, tuple]:
    '''
    Main function. You can call it in your own code.
    Output: the generated html and size 生成的 html 字符串和尺寸
    '''
    with open(DATABASE_PATH + 'train_timetable_data.dat', 'rb') as f:
        database = pickle.load(f)

    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)

    with open(LOCAL_FILE_PATH_V3, encoding='utf-8') as f:
        data_v3 = json.load(f)

    train_data = route_random_train(data_v3, data, route_name,
                                    database, departure_time)
    if not isinstance(train_data, tuple):
        return train_data

    html, size = generate_train_html(
        data, DATABASE_PATH + 'timetable_template.htm', *train_data)
    return html, size


def main_random_train(LOCAL_FILE_PATH, DATABASE_PATH,
                      departure_time=None) -> tuple[str, tuple]:
    '''
    Main function. You can call it in your own code.
    Output: the generated html and size 生成的 html 字符串和尺寸
    '''
    with open(DATABASE_PATH + 'train_timetable_data.dat', 'rb') as f:
        database = pickle.load(f)

    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)

    try:
        train_data = random_train(data, database, departure_time)
    except IndexError:
        train_data = random_train(data, database, departure_time)

    html, size = generate_train_html(
        data, DATABASE_PATH + 'timetable_template.htm', *train_data)
    return html, size
    # t = int(time())
    # tt_hti.screenshot(
    #     html_str=html,
    #     css_file=[DATABASE_PATH + x for x in ('base.css', 'header.css',
    #                                           'list.css', 'footer.css')],
    #     save_as=f'timetable_{t}.png', size=(960, 960)
    # )
    # image = Image.open(fr'{DATABASE_PATH}\timetable_{t}.png')
    # output_buffer = BytesIO()
    # image.save(output_buffer, 'png')
    # byte_data = output_buffer.getvalue()
    # base64_str = base64.b64encode(byte_data).decode('utf-8')


def main_train(LOCAL_FILE_PATH, DATABASE_PATH_1, DATABASE_PATH_2,
               template_path, station_name, train_id) -> tuple[str, tuple]:
    '''
    Main function. You can call it in your own code.
    Output: the generated html and size 生成的 html 字符串和尺寸
    '''
    with open(DATABASE_PATH_1 + 'train_timetable_data.dat', 'rb') as f:
        train_timetable = pickle.load(f)

    with open(DATABASE_PATH_2 + 'station_timetable_data.dat', 'rb') as f:
        station_timetable = pickle.load(f)

    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)

    train_data = get_train(data, station_name, train_id,
                           station_timetable, train_timetable)
    if not isinstance(train_data, tuple):
        return train_data

    html, size = generate_train_html(
        data, template_path, *train_data)
    return html, size


def get_text_timetable(data, station, departure_time: int,
                       station_tt: dict[str, dict[str, tuple]]):
    station_id = None
    try:
        sta_short_id = int(station)
        station_id = station_short_id_to_id(data, sta_short_id)
    except ValueError:
        station_id = station_name_to_id(data, station)

    if station_id is None:
        return None

    output = ''
    dep_dict: dict[str, list] = {}
    for train_id, (route_id, i, dep) in station_tt[station_id].items():
        if route_id not in dep_dict:
            dep_dict[route_id] = []

        dep_dict[route_id].append((dep, train_id, i))
        dep_dict[route_id].append((dep + 86400, train_id, i))

    k = list(dep_dict.items())
    k.sort(key=lambda x: data['routes'][x[0]]['name'])
    for route_id, x in k:
        x.sort()
        route_data = data['routes'][route_id]
        route_name: str = route_data['name']
        route_name = route_name.replace('||', ' ').replace('|', ' ')
        count = 1
        template = f'{route_name}: '
        for y in x:
            dep = y[0]
            train_id = y[1]
            if dep > departure_time:
                dep_time = convert_time(dep % 86400, use_second=True)
                template += f'{dep_time}({train_id}), '
                count += 1
                if count == 3:
                    template = template[:-2] + '\n'
                    output += template
                    break

    station_data = data['stations'][station_id]
    original_station_name = station_data['name'].split('|')[0]
    short_id = station_data['station']
    short_id = int('0x' + str(short_id), 16)
    result = f'{original_station_name}站 - ID: {short_id}\n{output}'
    return tt_opencc3.convert(tt_opencc4.convert(result))


def main_text_timetable(LOCAL_FILE_PATH, DATABASE_PATH,
                        departure_time, station_name) -> str:
    with open(DATABASE_PATH + 'station_timetable_data.dat', 'rb') as f:
        station_timetable = pickle.load(f)

    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)

    return get_text_timetable(data, station_name,
                              departure_time, station_timetable)


def get_sta_timetable(data_v3, data, station, routes, template_file,
                      station_tt: dict[str, dict[str, tuple]]):
    if isinstance(routes, str):
        routes = [routes]

    station_id = None
    try:
        sta_short_id = int(station)
        station_id = station_short_id_to_id(data, sta_short_id)
    except ValueError:
        station_id = station_name_to_id(data, station)

    if station_id is None:
        return None

    route_ids = []
    for r in routes:
        route_ids += route_name_to_id(data_v3, r)

    if route_ids == []:
        return None

    all_stations = data['stations']
    all_routes = data['routes']
    short_id = all_stations[station_id]['station']
    short_id = int('0x' + str(short_id), 16)

    with open(template_file, 'r', encoding='utf-8') as f:
        html = f.read()

    n: str = all_stations[station_id]['name']
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
        station_ids: list[str] = [y['id'] for y in all_routes[x]['stations']]
        stations_names: list[str] = [all_stations[y]['name']
                                     for y in station_ids]
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
                if len(last_station) > 4 and \
                        final_last_sta in list(last_stations.values()):
                    k = len(last_station)
                    final_last_sta = last_station[:2] + last_station[k - 2:k]

                last_stations[tmp_sta] = final_last_sta
                if next_station not in next_stations and \
                        next_station != station_name:
                    next_stations.append(next_station)

                # if last_station not in next_stations:
                #     next_stations.append(last_station)

    last_count = 0
    last_sta_table = ''
    for x, y in last_stations.items():
        if x != y:
            last_sta_table += f'<li class="dest-nofte__item">{y}={x}</li>\n'
            last_count += 1

    output = []
    height = 220 + last_count * 39
    count = 0
    for train_id, train in station_tt[station_id].items():
        if train[0] not in route_ids:
            continue

        route_id = train[0]
        t = convert_time(train[2])
        output.append((route_id, t, train_id))

    if output == []:
        return False

    output.sort(key=lambda x: x[1])
    template = ''
    template1 = '''<li class="time-frame">
<a href="/timetable/train/{{station_short_id}}/{{train_id}}" style="color:{{color}}">
<span class="ruby-top">
{{level}}
</span>
<span class="time">{{minute}}</span>
<span class="ruby-dest">{{dest}}</span>
</a></li>'''
    last_hour = ''
    express_table = list(EXPRESS_TABLE.items())
    express_table.sort(key=lambda x: len(x[0]), reverse=True)
    for route_id, t, train_id in output:
        route_name = all_routes[route_id]['name']
        for name, level in express_table:
            if name in route_name:
                color = COLOR_TABLE[level]
                if len(level) == 2:
                    level = level[0]
                elif len(level) == 3:
                    level = level[0] + level[1]
                elif len(level) == 4:
                    level = level[0] + level[2]
                break
        else:
            color = '#000000'
            level = ''

        # level += ' ' + str(train_id)
        destination_id = all_routes[route_id]['stations'][-1]['id']
        destination: str = all_stations[destination_id]['name']
        dest = last_stations[destination.split('|')[0]]
        if all_routes[route_id]['circularState'] == 'CLOCKWISE':
            dest = '顺时针'
        elif all_routes[route_id]['circularState'] == 'ANTICLOCKWISE':
            dest = '逆时针'

        count += 1
        if count % 13 == 0:
            height += 64
        hour = t[:2]
        if hour != last_hour:
            if count % 13 != 0:
                height += 64
            height += 12 * 2
            count = 0
            last_hour = hour
            template += f'''</ul>
</dd>
</dl>
<dl>
<dt class="diagram-frame__hour border">{hour}</dt>
<dd class="diagram-frame__min">
<ul class="operation-frame">'''

        template2 = template1
        template2 = template2.replace('{{station_short_id}}', str(short_id))
        template2 = template2.replace('{{train_id}}', str(train_id))
        template2 = template2.replace('{{minute}}', t[3:])
        template2 = template2.replace('{{dest}}', dest)
        template2 = template2.replace('{{color}}', color)
        template2 = template2.replace(
            '{{level}}', f'<span class="ruby-name ">{level}</span>')
        # if color != '#000000':
        #     template2 = template2.replace(
        #         '{{level}}', f'<span class="ruby-name ">{level}</span>')
        # else:
        #     template2 = template2.replace('{{level}}', '')

        template += template2

    template += '</ul></dd></dl>'
    type_table = ''
    template3 = '<li class="train-type-note__type" style="color : '
    for train_type, type_color in COLOR_TABLE.items():
        if len(train_type) == 2:
            short = train_type[0]
        elif len(train_type) == 3:
            short = train_type[0] + train_type[1]
        elif len(train_type) == 4:
            short = train_type[0] + train_type[2]

        type_table += f'{template3}{type_color}">{short}:{train_type}</li>\n'

    html = html.replace('{{station_name}}', station_name)
    html = html.replace('{{short_id}}', str(short_id))
    html = html.replace('{{eng_name}}', eng_name)
    html = html.replace('{{route_name}}', '/'.join(route_names))
    html = html.replace('{{route_color}}', mode(route_colors))
    html = html.replace('{{direction_1}}', '/'.join(next_stations))
    html = html.replace('{{type_table}}', type_table)
    html = html.replace('{{last_sta_table}}', last_sta_table)
    html = html.replace('{{template}}', template)
    return html, (1000, height)


def main_sta_timetable(LOCAL_FILE_PATH, LOCAL_FILE_PATH_2, template_path,
                       DATABASE_PATH, station_name, route_names) -> str:
    with open(DATABASE_PATH + 'station_timetable_data.dat', 'rb') as f:
        station_timetable = pickle.load(f)

    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data_v3 = json.load(f)

    with open(LOCAL_FILE_PATH_2, encoding='utf-8') as f:
        data = json.load(f)

    return get_sta_timetable(data_v3, data, station_name, route_names,
                             template_path, station_timetable)


def get_sta_directions(data, station, template_file):
    MAX_DIST = 30

    def min_dist(tuple1, tuples):
        dists = []
        for tuple2 in tuples:
            dist = 0
            for i in range(3):
                dist += abs(tuple1[i] - tuple2[i])

            dists.append(dist)
            # dists.append(abs(tuple1[0] - tuple2[0]))
            # dists.append(abs(tuple1[2] - tuple2[2]))

        return min(dists), dists.index(min(dists))

    def find_connected_components(graph: dict[str]):
        visited = set()
        components = []

        def dfs(node, component: set):
            visited.add(node)
            component.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, component)

        for node in graph:
            if node not in visited:
                component = set()
                dfs(node, component)
                components.append(tuple(sorted(component)))

        return components

    station_id = None
    try:
        sta_short_id = int(station)
        station_id = station_short_id_to_id(data, sta_short_id)
    except ValueError:
        station_id = station_name_to_id(data, station)

    if station_id is None:
        return None

    routes: list[str] = data['station_routes'][station_id]
    same_direction: dict[str, list] = {}
    for route_id1 in routes:
        route_data1 = data['routes'][route_id1]
        # if route_data1['hidden'] is True:
        #     continue

        stations1 = route_data1['stations']
        station_ids1 = [x['id'] for x in route_data1['stations']]
        i1 = station_ids1.index(station_id)
        if i1 == len(station_ids1) - 1:
            continue

        if route_id1 not in same_direction:
            same_direction[route_id1] = []

        for route_id2 in routes:
            if route_id1 == route_id2:
                continue

            route_data2 = data['routes'][route_id2]
            # if route_data2['hidden'] is True:
            #     continue

            if route_data1['type'] != route_data2['type']:
                if not ('train_normal' in [route_data1['type'],
                                           route_data2['type']] and
                        'train_high_speed' in [route_data1['type'],
                                               route_data2['type']]):
                    continue

            stations2 = route_data2['stations']
            station_ids2 = [x['id'] for x in route_data2['stations']]
            i2 = station_ids2.index(station_id)
            if i2 == len(station_ids2) - 1:
                continue

            if route_id2 not in same_direction:
                same_direction[route_id2] = []

            if route_id2 in same_direction[route_id1]:
                continue

            plat1 = (stations1[i1]['x'], stations1[i1]['y'],
                     stations1[i1]['z'])
            plat2 = (stations2[i2]['x'], stations2[i2]['y'],
                     stations2[i2]['z'])
            if plat1 == plat2:
                same_direction[route_id1].append(route_id2)
                continue

            plats1 = [(sta['x'], sta['y'], sta['z'])
                      for sta in stations1[i1 + 1:-1]]
            plats2 = [(sta['x'], sta['y'], sta['z'])
                      for sta in stations2[i2 + 1:-1]]
            if plats1 == []:
                plats1 = [(sta['x'], sta['y'], sta['z'])
                          for sta in [stations1[-1]]]
                plats2 = [(sta['x'], sta['y'], sta['z'])
                          for sta in stations2[i2 + 1:]]

            if plats2 == []:
                plats1 = [(sta['x'], sta['y'], sta['z'])
                          for sta in stations1[i1 + 1:]]
                plats2 = [(sta['x'], sta['y'], sta['z'])
                          for sta in [stations2[-1]]]

            if plats1 == [] or plats2 == []:
                continue

            if min_dist(plats1[0], plats2)[0] > MAX_DIST and \
                    min_dist(plats2[0], plats1)[0] > MAX_DIST:
                continue

            for x in plats1:
                min_distance = min_dist(x, plats2)
                if min_distance[0] <= MAX_DIST:
                    same_direction[route_id1].append(route_id2)
                    break

    components = find_connected_components(same_direction)
    result = []
    result_2 = []
    for x in components:
        t: tuple[str] = tuple(data['routes'][y]['name'] for y in x)
        t2 = tuple(x.split('|')[0] for x in t)
        result.append(t)
        result_2.append(t2)

    graph: dict[str, list] = {}
    graph_2: dict[str, list] = {}
    graph_3: dict[str, list] = {}
    for i1, x1 in enumerate(result_2):
        item1_1 = result[i1]
        if item1_1 not in graph:
            graph[item1_1] = []

        item1_2 = result_2[i1]
        if item1_2 not in graph_2:
            graph_2[item1_2] = []

        item1_3 = components[i1]
        if item1_3 not in graph_3:
            graph_3[item1_3] = []

        if i1 == len(result_2) - 1:
            break

        for i2, x2 in enumerate(result_2[i1 + 1:]):
            i2 += i1 + 1
            have_same = len([x for x in x1 if x in x2]) > 0

            item2_1 = result[i2]
            if item2_1 not in graph:
                graph[item2_1] = []

            if have_same is True:
                graph[item1_1].append(item2_1)
                graph[item2_1].append(item1_1)

            item2_2 = result_2[i2]
            if item2_2 not in graph_2:
                graph_2[item2_2] = []

            if have_same is True:
                graph_2[item1_2].append(item2_2)
                graph_2[item2_2].append(item1_2)

            item2_3 = components[i2]
            if item2_3 not in graph_3:
                graph_3[item2_3] = []

            if have_same is True:
                graph_3[item1_3].append(item2_3)
                graph_3[item2_3].append(item1_3)

    same_ids = find_connected_components(graph)
    same_ids_2 = find_connected_components(graph_2)
    same_ids_3 = find_connected_components(graph_3)
    sta_data = data['stations'][station_id]
    sta_name = sta_data['name'].split('|')[0]
    short_id = int('0x' + sta_data['station'], 16)

    with open(template_file, 'r', encoding='utf-8') as f:
        html = f.read()

    sta_directions_table = {}
    template = ''
    # template1 = '<li><span class="dest-link"><a>({{id}}) {{sta}}方向</a></span></li>\n'
    template1 = '<li><span class="dest-link"><a href="/timetable/station/{{short_id}}/{{id}}">({{id}}) {{sta}}方向</a></span></li>\n'.replace('{{short_id}}', str(short_id))
    count = 1
    height = 87
    for index, routes in enumerate(same_ids):
        all_routes = set(y for x in same_ids_2[index] for y in x)
        all_names = '/<br>&nbsp;'.join(sorted(all_routes))
        template += f'''<dl class="line-list "><dt>
<span class="line-name">
{all_names}</span>
</dt><dd><ul class="dest-list">\n'''
        all_route_ids = same_ids_3[index]
        for x in all_route_ids:
            next_stations = []
            last_stations = []
            for z in x:
                route_data = data['routes'][z]
                if route_data['circularState'] == 'CLOCKWISE':
                    dest = '顺时针'
                    last_stations.append(dest)
                    continue
                elif route_data['circularState'] == 'ANTICLOCKWISE':
                    dest = '逆时针'
                    last_stations.append(dest)
                    continue

                station_ids: list[str] = [
                    y['id'] for y in route_data['stations']]
                stations_names: list[str] = [data['stations'][y]['name']
                                             for y in station_ids]
                if station_id not in station_ids:
                    continue

                i = station_ids.index(station_id)
                if i != len(station_ids) - 1:
                    next_station = stations_names[i + 1].split('|')[0]
                    last_station = stations_names[-1].split('|')[0]
                    if 'WIP' in last_station:
                        last_station = last_station.split('WIP')[1]
                        last_station = last_station.strip('])').strip()

                    if last_station not in last_stations and \
                            last_station != sta_name:
                        last_stations.append(last_station)

                    if next_station not in next_stations and \
                            next_station != sta_name:
                        next_stations.append(next_station)

            last_stations.sort()
            if last_stations == []:
                continue

            template2 = template1.replace('{{sta}}', '/'.join(last_stations))
            template2 = template2.replace('{{id}}', str(count))
            template += template2
            sta_directions_table[count] = x
            count += 1

        template += '</ul></dd></dl>\n'
        height += 120

    html = html.replace('{{template}}', template)
    html = html.replace('{{station}}', f'{sta_name} ({short_id})')
    return html, (800, height), sta_directions_table


def main_get_sta_directions(LOCAL_FILE_PATH_2, station, template_path):
    with open(LOCAL_FILE_PATH_2, encoding='utf-8') as f:
        data = json.load(f)

    return get_sta_directions(data, station, template_path)
