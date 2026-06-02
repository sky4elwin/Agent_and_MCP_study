from fastmcp import FastMCP
import requests
import time
import threading
import re

mcp = FastMCP("Info MCP Server")

# 新浪财经免费股票 API: https://hq.sinajs.cn/list={code}
# 支持 A 股、港股、美股，无需 API Key，但需设置 Referer 请求头
SINA_API_URL = "https://hq.sinajs.cn/list="
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# 免费汇率 API (frankfurter.app，无需 API Key)
EXCHANGE_RATE_API_URL = "https://api.frankfurter.app/latest"

WEATHER_DESCRIPTIONS = {
    0: "晴朗",
    1: "大部晴朗",
    2: "局部多云",
    3: "多云",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "大冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "大冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "阵雨",
    82: "大阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷暴",
    96: "雷暴伴有小冰雹",
    99: "雷暴伴有大冰雹"
}

def get_coordinates(city: str):
    params = {
        "name": city,
        "count": 1,
        "language": "zh",
        "format": "json"
    }
    response = requests.get(OPEN_METEO_GEOCODE_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not data.get("results"):
        return None, None
    result = data["results"][0]
    return result["latitude"], result["longitude"]

def get_current_weather(lat: float, lon: float):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m"],
        "timezone": "auto",
        "forecast_days": 1
    }
    response = requests.get(OPEN_METEO_WEATHER_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def get_weather(city: str) -> dict:
    """获取指定城市的当前天气信息
    
    Args:
        city: 城市名称（中文或英文）
    
    Returns:
        包含城市、温度、天气描述、湿度和风速的字典
    """
    lat, lon = get_coordinates(city)
    if lat is None:
        return {"error": f"找不到城市: {city}"}
    
    weather_data = get_current_weather(lat, lon)
    current = weather_data.get("current", {})
    
    weather_code = current.get("weather_code", 0)
    weather_desc = WEATHER_DESCRIPTIONS.get(weather_code, "未知")
    
    return {
        "city": city,
        "temperature": current.get("temperature_2m"),
        "weather_description": weather_desc,
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m")
    }

# ============================================================
# 新浪财经股票查询
# ============================================================
# 代码格式转换
# 用户输入 → 新浪代码
_SINA_CODE_MAP = [
    (".SS", "sh"),     # 上海 A 股: 600000.SS → sh600000
    (".SZ", "sz"),     # 深圳 A 股: 000001.SZ → sz000001
    (".HK", "hk"),     # 港股: 0700.HK → hk00700
]


def _to_sina_code(symbol: str) -> str | None:
    """将用户输入的股票代码转换为新浪查询代码"""
    s = symbol.upper().strip()

    # A 股 / 港股: 匹配后缀
    for suffix, prefix in _SINA_CODE_MAP:
        if s.endswith(suffix):
            code = s.replace(suffix, "")
            code = code.lstrip("0") or "0"
            if suffix in (".SS", ".SZ"):
                return f"{prefix}{code.zfill(6)}"
            elif suffix == ".HK":
                return f"hk{code.zfill(5)}"

    # 美股 / 无后缀: 默认当作美股用 gb_ 前缀
    if "." not in s and not s.startswith(("SH", "SZ", "HK", "GB_")):
        return f"gb_{s.lower()}"

    return None


def _parse_sina_response(text: str) -> list[str]:
    """解析新浪 API 返回的 var 赋值字符串，提取逗号分隔的数据字段"""
    match = re.search(r'"([^"]*)"', text)
    if not match:
        return []
    return match.group(1).split(",")


# ============================================================
# 缓存层
# ============================================================
_stock_cache: dict[str, tuple[dict, float]] = {}
_stock_cache_lock = threading.Lock()
_CACHE_TTL = 120  # 缓存有效期（秒）


def _get_cached_stock(symbol: str) -> dict | None:
    with _stock_cache_lock:
        entry = _stock_cache.get(symbol.upper())
        if entry:
            data, timestamp = entry
            if time.time() - timestamp < _CACHE_TTL:
                return data
    return None


def _set_stock_cache(symbol: str, data: dict) -> None:
    with _stock_cache_lock:
        _stock_cache[symbol.upper()] = (data, time.time())


@mcp.tool()
def get_stock_info(symbol: str) -> dict:
    """获取指定股票的实时信息

    Args:
        symbol: 股票代码（如 AAPL、600000.SS、000001.SZ、0700.HK）

    Returns:
        包含股票价格、涨跌幅等信息的字典
    """
    # 1. 查缓存
    cached = _get_cached_stock(symbol)
    if cached is not None:
        cached["_from_cache"] = True
        return cached

    # 2. 调用新浪财经 API
    sina_code = _to_sina_code(symbol)
    if sina_code is None:
        return {"error": f"新浪财经不支持此股票代码格式: {symbol}"}

    try:
        resp = requests.get(
            f"{SINA_API_URL}{sina_code}",
            headers=SINA_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        resp.encoding = "gb2312"

        text = resp.text.strip()
        if not text or "FAILED" in text:
            return {"error": f"新浪财经未返回 {symbol} (代码:{sina_code}) 的数据，请检查代码"}

        fields = _parse_sina_response(text)
        if len(fields) < 5:
            return {"error": f"新浪财经返回数据不完整 (代码:{sina_code})"}

        # 按美股 vs A股/港股 分别解析
        if sina_code.startswith("gb_"):
            name = fields[0]
            current_price = float(fields[1]) if fields[1] else None
            change = float(fields[2]) if len(fields) > 2 and fields[2] else None
            change_pct = fields[3] if len(fields) > 3 and fields[3] else None
            prev_close = (current_price - change) if current_price is not None and change is not None else None
            result = {
                "symbol": symbol.upper(),
                "name": name,
                "current_price": current_price,
                "previous_close": round(prev_close, 2) if prev_close else None,
                "change": change,
                "change_percent": f"{change_pct}%" if change_pct else None,
                "volume": None,
                "market_cap": None,
                "pe_ratio": None,
                "day_high": float(fields[4]) if len(fields) > 4 and fields[4] else None,
                "day_low": float(fields[5]) if len(fields) > 5 and fields[5] else None,
                "fifty_two_week_high": None,
                "fifty_two_week_low": None,
                "currency": "USD",
            }
        else:
            name = fields[0]
            current_price = float(fields[3]) if len(fields) > 3 and fields[3] else None
            prev_close = float(fields[2]) if len(fields) > 2 and fields[2] else None
            change = round(current_price - prev_close, 2) if current_price and prev_close else None
            change_pct_val = float(fields[8]) if len(fields) > 8 and fields[8] else None
            result = {
                "symbol": symbol.upper(),
                "name": name,
                "current_price": current_price,
                "previous_close": prev_close,
                "change": change,
                "change_percent": f"{change_pct_val:+.2f}%" if change_pct_val is not None else None,
                "volume": None,
                "market_cap": None,
                "pe_ratio": None,
                "day_high": float(fields[4]) if len(fields) > 4 and fields[4] else None,
                "day_low": float(fields[5]) if len(fields) > 5 and fields[5] else None,
                "fifty_two_week_high": None,
                "fifty_two_week_low": None,
                "currency": "CNY" if sina_code.startswith(("sh", "sz")) else "HKD",
            }

        # 3. 写入缓存
        _set_stock_cache(symbol, result)
        return result

    except Exception as e:
        return {"error": f"查询股票 {symbol} 时发生错误: {str(e)}"}


@mcp.tool()
def get_exchange_rate(base: str, target: str) -> dict:
    """获取两种货币之间的实时汇率

    Args:
        base: 基准货币代码（如 CNY、USD、EUR、JPY、HKD）
        target: 目标货币代码（如 CNY、USD、EUR、JPY、HKD）

    Returns:
        包含基准货币、目标货币、汇率和日期的字典
    """
    base = base.upper().strip()
    target = target.upper().strip()

    try:
        resp = requests.get(
            EXCHANGE_RATE_API_URL,
            params={"from": base, "to": target},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        rate = data.get("rates", {}).get(target)
        if rate is None:
            return {"error": f"不支持的货币代码: {target}，或 {base} 无法兑换到 {target}"}

        return {
            "base": base,
            "target": target,
            "rate": rate,
            "date": data.get("date"),
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"查询汇率时网络错误: {str(e)}"}
    except Exception as e:
        return {"error": f"查询汇率时发生错误: {str(e)}"}


if __name__ == "__main__":
    print("启动信息查询 MCP Server (stdio 模式)...")
    print("提供工具: get_weather, get_stock_info, get_exchange_rate")
    print("股票数据来源: 新浪财经 (免费)")
    print("汇率数据来源: frankfurter.app (免费)")
    mcp.run()
