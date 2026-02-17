import requests
import json

# API URL
API_URL = 'http://localhost:5000/api/find_route'

params = {
    # 出发、到达车站
    'start': 'Spawn',
    'end': 'Sundogs',
    
    # 寻路参数
    'algorithm': 'real',  # default, theory, real
    'ignored_lines': [],
    'avoid_stations': [],
    'disable_high_speed': True,
    'disable_boat': False,
    'enable_wild': False,
    'only_lrt': False
}

# 发送POST请求并打印原始响应
if __name__ == '__main__':
    print(f"调用API: {API_URL}")
    print(f"参数: {json.dumps(params, ensure_ascii=False, indent=2)}")
    print("=" * 70)
    
    try:
        # 发送POST请求
        response = requests.post(API_URL, json=params)
        response.raise_for_status()  # 检查请求是否成功
        
        # 打印原始JSON结果
        print("原始API响应:")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except requests.exceptions.RequestException as e:
        print(f"API调用失败: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
