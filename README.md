<<<<<<< develop
```
# 使用requirements.txt安装所有依赖（推荐）
pip3 install -r requirements.txt

# 或手动安装所有依赖
pip3 install -U Flask fonttools networkx OpenCC==1.1.1 Pillow Requests
```

| 环境变量 | 默认值 | 类型 | 描述 |
|---------|--------|------|------|
| `LINK` | `https://letsplay.minecrafttransitrailway.com/system-map` | 字符串 | MTR模组在线线路图网址，结尾删除"/" |
| `MTR_VER` | `4` | 整数 | MTR模组版本（3或4） |
| `MAX_HOUR` | `3` | 整数 | 旅途的最长时间（仅适用于MTR 4.0实时寻路） |
| `MAX_WILD_BLOCKS` | `1500` | 整数 | 两个站点之间非出站换乘（越野）的最远步行距离 |
| `TRANSFER_ADDITION` | `{}` | 对象 | 手动增加出站换乘，格式："车站": ["出站换乘的车站", ...], ... |
| `WILD_ADDITION` | `{}` | 对象 | 手动增加非出站换乘（越野），格式："车站": ["非出站换乘的车站", ...], ... |
| `STATION_TABLE` | `{}` | 对象 | 车站昵称到实际名称的映射，格式："车站昵称": "车站实际名称", ... |
| `ORIGINAL_IGNORED_LINES` | `[]` | 数组 | 未开通或禁止乘坐的路线列表，格式：["线路1", "线路2", ...] |
| `CONSOLE_PASSWORD` | `admin` | 字符串 | 管理员控制台密码 |
| `UMAMI_SCRIPT_URL` | `''` | 字符串 | Umami脚本URL |
| `UMAMI_WEBSITE_ID` | `''` | 字符串 | Umami网站ID |
=======
```bash
pip3 install -U networkx requests flask opencc-python-reimplemented
```

| 配置项 | 环境变量 | 默认值 |
|--------|---------|--------|
| 地图链接 | `MTR_LINK` | `https://letsplay.minecrafttransitrailway.com/system-map` |
| MTR版本 | `MTR_VER` | `4` |
| Umami脚本URL | `MTR_UMAMI_SCRIPT_URL` | `''` |
| Umami网站ID | `MTR_UMAMI_WEBSITE_ID` | `''` |
| 控制台密码 | `MTR_ADMIN_PASSWORD` | `admin` |
>>>>>>> main
