import os
import json
import re
import time
import hashlib
from flask import Flask, request, jsonify
import requests
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential

from camel.configs import QwenConfig
from camel.models import ModelFactory
from camel.types import ModelPlatformType   
from camel.toolkits import SearchToolkit
from camel.agents import ChatAgent
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# 环境变量
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
os.environ["SEARCH_ENGINE_ID"] = os.getenv("SEARCH_ENGINE_ID")

# 确保存储目录存在
os.makedirs("storage", exist_ok=True)
os.makedirs("storage/cache", exist_ok=True)

# 模型初始化
try:
    model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-ai/DeepSeek-V3",
            url='https://api.siliconflow.cn/v1',
            model_config_dict={"max_tokens": 8192},
            api_key=os.getenv('DEEPSEEK_API_KEY')
    )

    tools_list = [
        *SearchToolkit().get_tools(),
    ]

    sys_msg = """
    你是一位专业的旅游规划师。请你根据用户输入的旅行需求，包括旅行天数、景点/美食的距离、描述、图片URL、预计游玩/就餐时长等信息，为用户提供一个详细的行程规划。

    请遵循以下要求：
    1. 按照 Day1、Day2、... 的形式组织输出，直到满足用户指定的天数。
    2. 每一天的行程请从早餐开始，食物尽量选用当地特色小吃美食，列出上午活动、午餐、下午活动、晚餐、夜间活动（若有），并在末尾总结住宿或返程安排。
    3. 对每个景点或美食，提供其基本信息： 
       - 名称
       - 描述
       - 预计游玩/就餐时长（如果用户未提供，可以不写或自行估计）
       - 图片URL（如果有）
    4. 请调用在线搜索工具在行程中对移动或出行所需时长做出合理估计。
    5. 输出语言为中文。
    6. 保持回复简洁、有条理，但必须包含用户想要的所有信息。
    """

    agent = ChatAgent(
        system_message=sys_msg,
        model=model,
        message_window_size=10,
        output_language='Chinese',
        tools=tools_list
    )
    
    print("模型和工具初始化成功")
except Exception as e:
    print(f"模型初始化失败: {str(e)}")
    agent = None

# 生成缓存键
def generate_cache_key(data):
    """根据输入数据生成缓存键"""
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.md5(data_str.encode()).hexdigest()

# 检查缓存
def get_from_cache(cache_key):
    """从缓存获取数据"""
    cache_file = f"storage/cache/{cache_key}.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            print(f"从缓存加载数据: {cache_key}")
            return cache_data
        except Exception as e:
            print(f"读取缓存失败: {str(e)}")
    return None

# 保存到缓存
def save_to_cache(cache_key, data):
    """保存数据到缓存"""
    cache_file = f"storage/cache/{cache_key}.json"
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"数据已保存到缓存: {cache_key}")
    except Exception as e:
        print(f"保存缓存失败: {str(e)}")

def create_usr_msg(data: dict) -> str:
    """
    同你原先的实现，用于生成给大模型的用户输入消息
    """
    city = data.get("city", "")
    days_str = data.get("days", "1")
    try:
        days = int(days_str)
    except ValueError:
        days = 1

    lines = []
    lines.append(f"我准备去{city}旅行，共 {days} 天。下面是我提供的旅行信息：\n")
    
    scenic_spots = data.get("景点", [])
    foods = data.get("美食", [])

    if scenic_spots:
        lines.append("- 景点：")
        for i, spot in enumerate(scenic_spots, 1):
            lines.append(f"  {i}. {spot.get('name', '未知景点名称')}")
            if '距离' in spot:
                lines.append(f"     - 距离：{spot['距离']}")
            if 'describe' in spot:
                lines.append(f"     - 描述：{spot['describe']}")
            if '图片url' in spot:
                lines.append(f"     - 图片URL：{spot['图片url']}")

    if foods:
        lines.append("\n- 美食：")
        for i, food in enumerate(foods, 1):
            lines.append(f"  {i}. {food.get('name', '未知美食名称')}")
            if 'describe' in food:
                lines.append(f"     - 描述：{food['describe']}")
            if '图片url' in food:
                lines.append(f"     - 图片URL：{food['图片url']}")

    lines.append(f"""
    \n请你根据以上信息，规划一个 {days} 天的行程表。
    从每天的早餐开始，到晚餐结束，列出一天的行程，包括对出行方式或移动距离的简单说明。
    如果有多种景点组合，你可以给出最优的路线推荐。请按以下格式输出：

    Day1:
    - 早餐：
    - 上午：
    - 午餐：
    - 下午：
    - 晚餐：
    ...

    Day2:
    ...

    Day{days}:
    ...
    """
    )
    return "\n".join(lines)

def fix_exclamation_link(text: str) -> str:
    """
    先把类似 ![](http://xx.jpg) 的写法，提取出其中的 http://xx.jpg，
    替换成纯 http://xx.jpg
    """
    # 处理 ![xxx](http://xx.jpg) 格式
    md_pattern = re.compile(r'!\[.*?\]\((https?://\S+)\)')
    text = md_pattern.sub(lambda m: m.group(1), text)
    
    # 处理 ![](http://xx.jpg) 格式
    md_pattern_empty = re.compile(r'!\[\]\((https?://\S+)\)')
    text = md_pattern_empty.sub(lambda m: m.group(1), text)
    
    return text

def convert_picurl_to_img_tag(text: str, width: int = 300, height: int = 200) -> str:
    """
    将文本中的图片URL替换为带样式的HTML img标签，并让图片居中显示和统一大小
    兼容多种格式：
    1. ![](url) - Markdown图片
    2. - 图片URL：http://url - 文本中的URL描述
    3. 直接出现的URL (http://xxx.jpg)
    """
    # 第一步：把 ![](url) 变成纯 url
    text_fixed = fix_exclamation_link(text)

    # 第二步：处理 "- 图片URL：http://xxx" 格式
    pattern1 = re.compile(r'-\s*图片URL：\s*(https?://\S+)')
    text_fixed = pattern1.sub(
        rf'''
        <div style="text-align: center;">
            <img src="\1" alt="图片" style="width: {width}px; height: {height}px;" />
        </div>
        ''',
        text_fixed
    )
    
    # 第三步：处理 "图片URL：http://xxx" 格式（没有前面的"-"）
    pattern2 = re.compile(r'图片URL：\s*(https?://\S+)')
    text_fixed = pattern2.sub(
        rf'''
        <div style="text-align: center;">
            <img src="\1" alt="图片" style="width: {width}px; height: {height}px;" />
        </div>
        ''',
        text_fixed
    )
    
    # 第四步：处理可能直接出现的图片URL（以http开头，以jpg/png/gif/jpeg等结尾的URL）
    pattern3 = re.compile(r'(https?://\S+\.(jpg|jpeg|png|gif|webp))\b')
    text_fixed = pattern3.sub(
        rf'''
        <div style="text-align: center;">
            <img src="\1" alt="图片" style="width: {width}px; height: {height}px;" />
        </div>
        ''',
        text_fixed
    )
    
    return text_fixed

def generate_cards_html(data_dict):
    """
    生成景点和美食卡片的 HTML 片段
    """
    spots = data_dict.get("景点", [])
    foods = data_dict.get("美食", [])

    html_parts = []
    # 景点推荐
    html_parts.append("<h2>景点推荐</h2>")
    if spots:
        html_parts.append('<div class="card-container">')
        for spot in spots:
            name = spot.get("name", "")
            desc = spot.get("describe", "")
            distance = spot.get("距离", "")
            url = spot.get("图片url", "")
            card_html = f"""
            <div class="card">
            <div class="card-image">
                <img src="{url}" alt="{name}" />
            </div>
            <div class="card-content">
                <h3>{name}</h3>
                <p><strong>距离:</strong> {distance}</p>
                <p>{desc}</p>
            </div>
            </div>
            """
            html_parts.append(card_html)
        html_parts.append("</div>")
    else:
        html_parts.append("<p>暂无景点推荐</p>")

    # 美食推荐
    html_parts.append("<h2>美食推荐</h2>")
    if foods:
        html_parts.append('<div class="card-container">')
        for food in foods:
            name = food.get("name", "")
            desc = food.get("describe", "")
            url = food.get("图片url", "")
            card_html = f"""
            <div class="card">
            <div class="card-image">
                <img src="{url}" alt="{name}" />
            </div>
            <div class="card-content">
                <h3>{name}</h3>
                <p>{desc}</p>
            </div>
            </div>
            """
            html_parts.append(card_html)
        html_parts.append("</div>")
    else:
        html_parts.append("<p>暂无美食推荐</p>")

    return "\n".join(html_parts)

def generate_html_report(itinerary_text, data_dict):
    """
    将多日行程文本 + 景点美食卡片，合并生成完整HTML
    """
    html_parts = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append("<html><head><meta charset='utf-8'><title>旅行推荐</title>")
    # 可以内联一些 CSS 样式
    html_parts.append("<style>")
    html_parts.append("""
    body {
       font-family: "Microsoft YaHei", sans-serif;
       margin: 20px;
       background-color: #f8f8f8;
       line-height: 1.6;
    }
    h1, h2 {
       color: #333;
    }
    .itinerary-text {
       background-color: #fff;
       padding: 20px;
       border-radius: 8px;
       box-shadow: 0 2px 5px rgba(0,0,0,0.1);
       margin-bottom: 30px;
    }
    .card-container {
       display: flex;
       flex-wrap: wrap;
       gap: 20px;
       margin: 20px 0;
    }
    .card {
       flex: 0 0 calc(300px);
       border: 1px solid #ccc;
       border-radius: 10px;
       overflow: hidden;
       box-shadow: 0 2px 5px rgba(0,0,0,0.1);
       background-color: #fff;
    }
    .card-image {
       width: 100%;
       height: 200px;
       overflow: hidden;
       background: #f8f8f8;
       text-align: center;
    }
    .card-image img {
       max-width: 100%;
       max-height: 100%;
       object-fit: cover;
    }
    .card-content {
       padding: 10px 15px;
    }
    .card-content h3 {
       margin-top: 0;
       margin-bottom: 10px;
       font-size: 18px;
    }
    .card-content p {
       margin: 5px 0;
    }
    .image-center {
        text-align: center;
        margin: 20px 0;
    }
    .image-center img {
        width: 300px;
        height: 200px;
        object-fit: cover;
    }
    """)
    html_parts.append("</style></head><body>")

    # 标题
    html_parts.append("<h1>旅行行程与推荐</h1>")

    # 行程文本
    html_parts.append('<div class="itinerary-text">')
    for line in itinerary_text.split("\n"):
        if not line.strip():
            continue
        if line.strip().startswith("Day"):
            html_parts.append(f"<h2>{line.strip()}</h2>")
        else:
            html_parts.append(f"<p>{line}</p>")
    html_parts.append('</div>')

    # 景点/美食卡片
    cards_html = generate_cards_html(data_dict)
    html_parts.append(cards_html)

    html_parts.append("</body></html>")
    return "\n".join(html_parts)

def save_html_file(city: str, days: str, html_content: str) -> str:
    """
    保存HTML内容到文件
    
    Args:
        city: 城市名
        days: 旅行天数
        html_content: HTML内容
        
    Returns:
        str: 保存的文件路径
    """
    # 确保storage目录存在
    storage_dir = "storage"
    if not os.path.exists(storage_dir):
        os.makedirs(storage_dir)
        
    # 生成文件名
    filename = f"{storage_dir}/{city}{days}天旅游攻略.html"
    
    # 保存HTML内容
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    return filename

# 使用重试装饰器的函数
@retry(
    stop=stop_after_attempt(3),  # 最多重试3次
    wait=wait_exponential(multiplier=2, min=4, max=20),  # 指数退避，最小等待4秒，最大20秒
    reraise=True  # 重试失败后重新抛出原始异常
)
def generate_itinerary_with_retry(usr_msg):
    """使用重试机制调用大模型生成行程"""
    if not agent:
        raise ValueError("模型未初始化成功，无法生成行程")
    
    print("开始调用大模型生成行程...")
    try:
        response = agent.step(usr_msg)
        print("大模型调用成功")
        return response
    except Exception as e:
        print(f"大模型调用失败，准备重试: {str(e)}")
        raise

@app.route("/generate_itinerary_html", methods=["POST"])
def generate_itinerary_html():
    """
    请求 JSON 格式：
    {
      "city": "成都",
      "days": "3"
    }
    返回生成的HTML文件路径和内容
    """
    req_data = request.json or {}
    city = req_data.get("city", "")
    days = req_data.get("days", "1")
    
    print(f"收到请求：生成{city}{days}天旅游攻略HTML")

    # 生成缓存键
    cache_key = generate_cache_key({"city": city, "days": days})
    
    # 检查缓存
    cached_result = get_from_cache(cache_key)
    if cached_result:
        print(f"使用缓存结果：{cache_key}")
        return jsonify(cached_result), 200

    json_filename = f"storage/{city}{days}天旅游信息.json"
    if not os.path.exists(json_filename):
        print(f"错误：文件 {json_filename} 不存在")
        # 尝试在当前目录和上级目录查找文件
        current_dir = os.path.dirname(os.path.abspath(__file__))
        alt_paths = [
            os.path.join(current_dir, "storage", f"{city}{days}天旅游信息.json"),
            os.path.join(os.path.dirname(current_dir), "storage", f"{city}{days}天旅游信息.json")
        ]
        
        found = False
        for path in alt_paths:
            if os.path.exists(path):
                json_filename = path
                print(f"找到替代文件路径：{json_filename}")
                found = True
                break
                
        if not found:
            return jsonify({"error": f"文件 {json_filename} 不存在，请检查输入的目的地和天数！"}), 404

    try:
        print(f"读取JSON文件：{json_filename}")
        with open(json_filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"JSON解析错误：{json_filename}")
        return jsonify({"error": f"文件 {json_filename} 格式错误，请检查文件内容！"}), 400

    try:
        # 1. 生成用户输入
        usr_msg = create_usr_msg(data)
        print("已生成用户输入")
        
        # 2. 调用大模型（带重试机制）
        try:
            print("开始调用大模型...")
            response = generate_itinerary_with_retry(usr_msg)
            model_output = response.msgs[0].content
            print("大模型调用成功")
        except Exception as e:
            print(f"调用大模型失败: {str(e)}")
            # 如果API调用失败，使用备用方案生成简单行程
            print("使用备用方案生成行程")
            model_output = generate_fallback_itinerary(data)
        
        # 3. 将模型输出中的图片URL替换成 <img ... />
        print("处理图片URL")
        end_output = convert_picurl_to_img_tag(model_output)

        # 4. 生成完整 HTML 报告
        print("生成HTML报告")
        html_content = generate_html_report(end_output, data)

        # 5. 保存HTML文件
        print("保存HTML文件")
        saved_file = save_html_file(city, days, html_content)

        # 6. 保存结果到缓存
        result = {
            "file_path": saved_file,
            "html_content": html_content
        }
        print(f"保存结果到缓存：{cache_key}")
        save_to_cache(cache_key, result)

        # 7. 返回文件路径和HTML内容
        print(f"成功生成HTML：{saved_file}")
        return jsonify(result), 200
        
    except Exception as e:
        print(f"生成行程时出错: {str(e)}")
        return jsonify({"error": f"生成行程时出错: {str(e)}"}), 500

def generate_fallback_itinerary(data):
    """
    当API调用失败时，生成一个简单的备用行程
    """
    city = data.get("city", "")
    days_str = data.get("days", "1")
    try:
        days = int(days_str)
    except ValueError:
        days = 1
    
    spots = data.get("景点", [])
    foods = data.get("美食", [])
    
    itinerary = []
    itinerary.append(f"# {city}{days}天旅游行程\n")
    
    spots_per_day = max(1, min(3, len(spots) // days))
    foods_per_day = max(1, min(3, len(foods) // days))
    
    spot_index = 0
    food_index = 0
    
    for day in range(1, days + 1):
        itinerary.append(f"\n## Day{day}:")
        
        # 早餐
        if food_index < len(foods):
            food = foods[food_index]
            itinerary.append(f"- 早餐：{food.get('name', '当地特色早餐')}")
            food_index = (food_index + 1) % len(foods)
        else:
            itinerary.append("- 早餐：当地特色早餐")
        
        # 上午活动
        itinerary.append("- 上午：")
        for _ in range(spots_per_day):
            if spot_index < len(spots):
                spot = spots[spot_index]
                itinerary.append(f"  * {spot.get('name', '景点')}：{spot.get('describe', '著名景点')}")
                spot_index = (spot_index + 1) % len(spots)
        
        # 午餐
        if food_index < len(foods):
            food = foods[food_index]
            itinerary.append(f"- 午餐：{food.get('name', '当地特色午餐')}")
            food_index = (food_index + 1) % len(foods)
        else:
            itinerary.append("- 午餐：当地特色午餐")
        
        # 下午活动
        itinerary.append("- 下午：")
        for _ in range(spots_per_day):
            if spot_index < len(spots):
                spot = spots[spot_index]
                itinerary.append(f"  * {spot.get('name', '景点')}：{spot.get('describe', '著名景点')}")
                spot_index = (spot_index + 1) % len(spots)
        
        # 晚餐
        if food_index < len(foods):
            food = foods[food_index]
            itinerary.append(f"- 晚餐：{food.get('name', '当地特色晚餐')}")
            food_index = (food_index + 1) % len(foods)
        else:
            itinerary.append("- 晚餐：当地特色晚餐")
        
        # 住宿
        itinerary.append("- 住宿：舒适酒店")
    
    return "\n".join(itinerary)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)