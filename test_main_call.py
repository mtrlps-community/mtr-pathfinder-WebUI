from mtr_pathfinder import main
import hashlib

LINK = "https://letsplay.minecrafttransitrailway.com/system-map"   # MTR系统地图链接
link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
MTR_VER = 4   # MTR版本号（3或4）

main(
    station1 = "Spawn",   # 起点站名称
    station2 = "Sundogs",   # 终点站名称
    LINK = LINK,
    LOCAL_FILE_PATH = f'mtr-station-data-{link_hash}-{MTR_VER}.json',   # 本地车站数据文件路径
    INTERVAL_PATH = f'mtr-route-data-{link_hash}-{MTR_VER}.json',   # 路线间隔数据文件路径
    BASE_PATH = "mtr_pathfinder_data",   # 生成图片的基础路径
    PNG_PATH = "mtr_pathfinder_data",   # PNG图片保存路径
    MAX_WILD_BLOCKS = 1500,   # 最大越野行走块数
    TRANSFER_ADDITION = {},   # 换乘时间附加（{线路: 附加时间}）
    WILD_ADDITION = {},   # 越野时间附加（{线路: 附加时间}）
    STATION_TABLE = {},   # 车站名称映射表（用于名称转换）
    ORIGINAL_IGNORED_LINES = [],   # 原始忽略线路列表
    UPDATE_DATA = False,   # 是否更新车站和路线数据
    GEN_ROUTE_INTERVAL = False,   # 是否生成路线间隔数据
    IGNORED_LINES = [],   # 要忽略的线路列表
    AVOID_STATIONS = [],   # 要避开的车站列表
    CALCULATE_HIGH_SPEED = True,   # 是否计算高速列车路线
    CALCULATE_BOAT = True,   # 是否计算船只路线
    CALCULATE_WALKING_WILD = False,   # 是否计算步行越野路线
    ONLY_LRT = False,   # 是否只考虑轻轨路线
    IN_THEORY = False,   # 是否使用理论时间计算（不考虑实际间隔）
    DETAIL = False,   # 是否显示详细路线信息
    MTR_VER = MTR_VER,
    show=True   # 是否显示生成的路线图
    )