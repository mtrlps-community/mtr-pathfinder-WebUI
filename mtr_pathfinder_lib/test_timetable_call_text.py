from mtr_timetable import main_text_timetable
import hashlib

# 测试车站名称
station_name = 'Spawn'
# 出发时间（一天内的秒数）
departure_time = 0  # 0表示当前时间
# 在线线路图网址，结尾删除"/"
LINK: str = "https://letsplay.minecrafttransitrailway.com/system-map"

link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
LOCAL_FILE_PATH = f'mtr-original-data-{link_hash}-mtr4-v4.json'
DATABASE_PATH = './'


result = main_text_timetable(LOCAL_FILE_PATH, DATABASE_PATH, departure_time, station_name)

print(result)

with open("timetable_return.txt", "w", encoding="utf-8") as file:
    file.write(str(result))