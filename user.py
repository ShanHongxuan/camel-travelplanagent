import os
import json
import requests
import time
from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent

load_dotenv()

API_KEY = os.getenv('FIRST_DEEPSEEK_API_KEY')

SYSTEM_PROMPT = """
你是一个旅游信息提取助手。你的任务是从用户的输入中提取旅游目的地城市和行程天数，并根据提取情况决定是否需要用户补充信息。

用户输入可能包含以下信息：
* 旅游目的地城市名称（例如：北京、上海、巴黎、东京）
* 行程天数（例如：3天、5天、一周、两周）
* 可能会有其他无关信息，请忽略。

你需要将提取到的城市名称和行程天数以 JSON 格式返回，格式如下：
{"city": "城市名称", "days": 天数, "need_more_info": boolean}
* "city" 的值：
    * 如果成功提取到城市名称，则为城市名称字符串。
    * 如果无法提取到城市名称，则为 null。
* "days" 的值：
    * 如果成功提取到行程天数，则为数字。
    * 如果无法提取到行程天数，则为 null。
* "need_more_info" 的值：
    * 如果 "city" 或 "days" 中有任何一个为 null，则为 true，表示需要用户提供更多信息。
    * 如果 "city" 和 "days" 都不为 null，则为 false，表示不需要用户提供更多信息。
* 如果提取到的天数包含"天"或"日"等字样，请将其转换为数字。
* 如果提取到的天数包含"周"或"星期"，请将其转换为7的倍数。例如，"一周"转换为7，"两周"转换为14。
* 如果用户输入中包含多个城市，请只提取第一个城市。
* 如果用户输入中包含多个天数，请只提取第一个天数。

请严格按照 JSON 格式返回结果。

**示例：**

**用户输入：**
我想去北京玩三天，顺便看看长城。

**你的输出：**
{"city": "北京", "days": 3, "need_more_info": false,"response": "信息在Navigator的数据库中查询到啦，正在努力为您生成攻略~"}

**用户输入：**
我想去北京。

**你的输出：**
{"city": "北京", "days": null, "need_more_info": true,"response": "Navigator还不知道您打算去玩几天呢，请补充你计划的行程天数~"}
"""

app = Flask(__name__)

# 服务配置
SEARCH_SERVICE_URL = "http://localhost:5002/get_travel_plan"
GENERATE_SERVICE_URL = "http://localhost:5003/generate_itinerary_html"

def create_travel_agent():
    model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-ai/DeepSeek-V3",
            url='https://api.siliconflow.cn/v1',
            model_config_dict={"max_tokens": 4096},
            api_key=os.getenv('FIRST_DEEPSEEK_API_KEY')
    )

    agent = ChatAgent(
        system_message=SYSTEM_PROMPT,
        model=model,
        message_window_size=10,
        output_language='Chinese'
    )
    return agent

travel_agent = create_travel_agent()

def get_travel_info_camel(user_input: str, agent: ChatAgent) -> dict:
    try:
        response = agent.step(user_input)
        # 回到原始状态
        agent.reset()
        if not response or not response.msgs:
            raise ValueError("模型没有返回任何消息")
        json_output = response.msgs[0].content.strip().replace("```json", "").replace("```", "").strip()
        json_output = json.loads(json_output)
        json_output["query"] = user_input
        return json_output
    except json.JSONDecodeError:
        print("Error: 模型返回的不是有效的 JSON 格式。")
        return {
            'city': None,
            'days': None,
            'need_more_info': True,
            'query': user_input,
            'response': None
        }
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {
            'city': None,
            'days': None,
            'need_more_info': True,
            'query': user_input,
            'response': None
        }

def trigger_search_service(city: str, days: int) -> dict:
    """
    触发搜索服务
    """
    try:
        print(f"调用搜索服务获取{city}{days}天的旅游计划...")
        search_data = {
            "city": city,
            "days": days
        }
        search_response = requests.post(SEARCH_SERVICE_URL, json=search_data, timeout=300)
        search_response.raise_for_status()
        return search_response.json()
    except requests.exceptions.RequestException as e:
        print(f"搜索服务调用失败: {str(e)}")
        return {"status": "error", "message": f"搜索服务调用失败: {str(e)}"}

def trigger_generate_service(city: str, days: int) -> dict:
    """
    触发生成服务
    """
    try:
        print(f"调用生成服务生成{city}{days}天的旅游HTML...")
        generate_data = {
            "city": city,
            "days": days
        }
        generate_response = requests.post(GENERATE_SERVICE_URL, json=generate_data, timeout=300)
        generate_response.raise_for_status()
        return generate_response.json()
    except requests.exceptions.RequestException as e:
        print(f"生成服务调用失败: {str(e)}")
        return {"status": "error", "message": f"生成服务调用失败: {str(e)}"}

def process_complete_pipeline(city: str, days: int) -> dict:
    """
    处理完整的流程：搜索 -> 生成
    """
    # 1. 调用搜索服务
    search_result = trigger_search_service(city, days)
    if search_result.get("status") == "error":
        return search_result
    
    # 等待搜索服务完成
    print("搜索服务已完成，等待5秒后继续...")
    time.sleep(5)
    
    # 2. 调用生成服务
    generate_result = trigger_generate_service(city, days)
    if generate_result.get("error"):
        return {"status": "error", "message": generate_result.get("error")}
    
    # 3. 返回最终结果
    return {
        "status": "success",
        "search_result": search_result,
        "generate_result": {
            "file_path": generate_result.get("file_path", ""),
            "html_generated": True
        }
    }

@app.route('/extract_travel_info', methods=['POST'])
def extract_travel_info():
    try:
        request_data = request.get_json()
        if not request_data or 'query' not in request_data:
            return jsonify({'error': '请求数据无效'}), 400

        result = get_travel_info_camel(request_data['query'], travel_agent)
        response = {
            'city': result['city'],
            'days': result['days'],
            'need_more_info': result['need_more_info'],
            'query': result['query'],
            'response': result['response']
        }
        
        # 如果提取到了完整的信息，自动触发后续流程
        if not result['need_more_info'] and result['city'] and result['days']:
            pipeline_result = process_complete_pipeline(result['city'], result['days'])
            response['pipeline_result'] = pipeline_result
        
        response_json = json.dumps(response, ensure_ascii=False)
        return Response(response_json, status=200, mimetype='application/json; charset=utf-8')
    except Exception as e:
        return jsonify({'error': f'服务器内部错误: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
