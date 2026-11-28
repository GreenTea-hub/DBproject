"""参数校验。负责人：P3。所有接口只接受白名单内的枚举值。"""

RELATION_TYPES = ["君臣", "兄弟", "敌对", "亲族", "师徒", "同僚"]
FACTIONS = ["魏", "蜀", "吴", "群雄"]


class ParamError(Exception):
    """参数不合法，由接口层捕获后返回 400。"""


def to_int(value, default, minimum=None, maximum=None, field="参数"):
    if value is None or value == "":
        return default
    try:
        num = int(value)
    except (TypeError, ValueError):
        raise ParamError(f"{field} 必须是整数")
    if minimum is not None:
        num = max(minimum, num)
    if maximum is not None:
        num = min(maximum, num)
    return num


def parse_page(args, default_size=20, max_size=100):
    page = to_int(args.get("page"), 1, 1, field="page")
    size = to_int(args.get("size"), default_size, 1, max_size, field="size")
    return page, size


def require(args, *names):
    missing = [n for n in names if not args.get(n)]
    if missing:
        raise ParamError("缺少参数：" + "、".join(missing))


def clean_name(name):
    """人物名做基础清洗：去空白，限制长度，避免把奇怪输入直接塞进 Cypher。"""
    name = (name or "").strip()
    if not name:
        raise ParamError("人物名不能为空")
    if len(name) > 32 or any(ch in name for ch in "{}()[]<>|\"'"):
        raise ParamError("人物名包含非法字符")
    return name


def clean_relation_types(raw):
    """types=君臣,兄弟 -> ["君臣", "兄弟"]；非法值直接忽略。"""
    if not raw:
        return []
    parts = [p.strip() for p in str(raw).replace("，", ",").split(",")]
    return [p for p in parts if p in RELATION_TYPES]


def clean_faction(raw):
    """阵营过滤只接受四个枚举值；空值表示不过滤。

    与 types 的“非法值忽略”不同，faction 传错通常意味着前端选项或调用方
    拼写有问题，直接 400 比静默返回空列表更容易定位。
    """
    value = (raw or "").strip()
    if not value:
        return ""
    if value not in FACTIONS:
        raise ParamError("faction 只能是：" + "、".join(FACTIONS))
    return value
