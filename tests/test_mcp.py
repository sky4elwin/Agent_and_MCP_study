import pytest
from weather_agent_demo.mcp_server import get_weather, get_stock_info
from weather_agent_demo.mcp_server import _to_sina_code, _parse_sina_response


# ============================================================
# _to_sina_code 测试
# ============================================================

def test_sina_code_us():
    assert _to_sina_code("AAPL") == "gb_aapl"


def test_sina_code_shanghai():
    assert _to_sina_code("600000.SS") == "sh600000"


def test_sina_code_shenzhen():
    assert _to_sina_code("000001.SZ") == "sz000001"


def test_sina_code_hk():
    assert _to_sina_code("0700.HK") == "hk00700"


def test_sina_code_unsupported():
    assert _to_sina_code("7203.T") is None


# ============================================================
# _parse_sina_response 测试
# ============================================================

SINA_MOCK_US = 'var hq_str_gb_aapl="Apple Inc.,185.50,2.50,1.37,186.00,183.50,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0";'


def test_parse_sina_response():
    fields = _parse_sina_response(SINA_MOCK_US)
    assert fields[0] == "Apple Inc."
    assert fields[1] == "185.50"


# ============================================================
# get_weather 测试
# ============================================================

class DummyResp:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP error")


def test_get_weather_success(monkeypatch):
    def fake_get(url, params=None, timeout=None, headers=None):
        if "geocoding" in url or "search" in url:
            return DummyResp({"results": [{"latitude": 39.9, "longitude": 116.4}]})
        if "forecast" in url:
            return DummyResp({
                "current": {
                    "temperature_2m": 22.5,
                    "relative_humidity_2m": 60,
                    "weather_code": 2,
                    "wind_speed_10m": 3.2
                }
            })
        return DummyResp({}, 404)

    monkeypatch.setattr("weather_agent_demo.mcp_server.requests.get", fake_get)
    result = get_weather("北京")
    assert result["city"] == "北京"
    assert result["temperature"] == 22.5
    assert result["weather_description"] == "局部多云"
    assert result["humidity"] == 60
    assert result["wind_speed"] == 3.2


def test_get_weather_city_not_found(monkeypatch):
    def fake_get(url, params=None, timeout=None, headers=None):
        return DummyResp({"results": []})

    monkeypatch.setattr("weather_agent_demo.mcp_server.requests.get", fake_get)
    result = get_weather("NoSuchCity")
    assert "error" in result
    assert "NoSuchCity" in result["error"]


# ============================================================
# get_stock_info 测试 (新浪财经)
# ============================================================

SINA_US_RESP = 'var hq_str_gb_aapl="Apple Inc.,185.50,2.50,1.37,186.00,183.50,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0";'
SINA_CN_RESP = 'var hq_str_sh600000="浦发银行,10.50,10.30,10.65,10.80,10.20,0,0,3.40,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0";'


class SinaRespUS:
    encoding = ""
    text = SINA_US_RESP
    def raise_for_status(self): pass


class SinaRespCN:
    encoding = ""
    text = SINA_CN_RESP
    def raise_for_status(self): pass


class SinaRespFail:
    encoding = ""
    text = ""
    def raise_for_status(self): pass


class SinaRespError:
    encoding = ""
    text = "FAILED"
    def raise_for_status(self): pass


def test_get_stock_info_us(monkeypatch):
    """测试美股查询"""
    import weather_agent_demo.mcp_server as server
    server._stock_cache.clear()
    monkeypatch.setattr("weather_agent_demo.mcp_server.requests.get",
                        lambda url, headers=None, timeout=None: SinaRespUS())
    result = get_stock_info("AAPL")
    assert result["symbol"] == "AAPL"
    assert result["name"] == "Apple Inc."
    assert result["current_price"] == 185.50
    assert result["change"] == 2.50
    assert result["change_percent"] == "1.37%"
    assert result["currency"] == "USD"


def test_get_stock_info_a_share(monkeypatch):
    """测试 A 股查询"""
    import weather_agent_demo.mcp_server as server
    server._stock_cache.clear()
    monkeypatch.setattr("weather_agent_demo.mcp_server.requests.get",
                        lambda url, headers=None, timeout=None: SinaRespCN())
    result = get_stock_info("600000.SS")
    assert result["symbol"] == "600000.SS"
    assert result["name"] == "浦发银行"
    assert result["current_price"] == 10.65
    assert result["previous_close"] == 10.30
    assert result["change_percent"] == "+3.40%"
    assert result["currency"] == "CNY"


def test_get_stock_info_unsupported_code(monkeypatch):
    """测试不支持的代码格式"""
    import weather_agent_demo.mcp_server as server
    server._stock_cache.clear()
    result = get_stock_info("7203.T")
    assert "error" in result
    assert "不支持" in result["error"]


def test_get_stock_info_empty_response(monkeypatch):
    """测试空响应"""
    import weather_agent_demo.mcp_server as server
    server._stock_cache.clear()
    monkeypatch.setattr("weather_agent_demo.mcp_server.requests.get",
                        lambda url, headers=None, timeout=None: SinaRespFail())
    result = get_stock_info("ZZZZZZZ")
    assert "error" in result
