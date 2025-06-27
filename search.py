from camel.toolkits import SearchToolkit
from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.loaders import Firecrawl
from typing import List, Dict, Any
from flask import Flask, request, jsonify
import json
import os
from dotenv import load_dotenv
import requests
import time
import random
from duckduckgo_search.exceptions import RatelimitException
import logging

load_dotenv()

os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
os.environ["SEARCH_ENGINE_ID"] = os.getenv("SEARCH_ENGINE_ID")
os.environ["FIRECRAWL_API_KEY"] = os.getenv("FIRECRAWL_API_KEY")
os.environ["DEEPSEEK_API_KEY"] = os.getenv("DEEPSEEK_API_KEY")
os.environ["PIXABAY_API_KEY"] = os.getenv("PIXABAY_API_KEY")
os.environ["UNSPLASH_ACCESS_KEY"] = os.getenv("UNSPLASH_ACCESS_KEY")

app = Flask(__name__)

class TravelPlanner:
    def __init__(self, city: str, days: int):
        
        #定义地点和时间，设置默认值
        self.city = city
        self.days = days
        self.res = None        

        # 初始化模型和智能体
        self.model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-ai/DeepSeek-V3",
            url='https://api.siliconflow.cn/v1',
            model_config_dict={"max_tokens": 4096},
            api_key=os.getenv('DEEPSEEK_API_KEY')
        )
        # 初始化各种工具
        #重排序模型
        self.reranker_agent = ChatAgent(
            system_message="你是一搜索质量打分专家，要从{搜索结果}里找出和{query}里最相关的2条结果，保存他们的结果，保留result_id、title、description、url，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        #景点抓取agent
        self.attraction_agent = ChatAgent(
            system_message="你是一个旅游信息提取专家，要根据内容提取出景点信息并返回json格式，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        #美食抓取agent
        self.food_agent = ChatAgent(
            system_message="你是一个旅游信息提取专家，要根据内容提取出美食信息并返回json格式，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        #base攻略生成agent
        self.base_guide_agent = ChatAgent(
            system_message="你是一个旅游攻略生成专家，要根据内容生成一个旅游攻略，严格以json格式输出",
            model=self.model,
            output_language='中文'
        )
        # self.firecrawl = Firecrawl()#后续功能
        self.search_toolkit = SearchToolkit()

    def search_pixabay_image(self, query: str) -> str:
        """通过Pixabay API搜索图片"""
        try:
            api_key = os.getenv("PIXABAY_API_KEY")
            if not api_key:
                print("Pixabay API密钥未设置")
                return ""
            
            url = "https://pixabay.com/api/"
            params = {
                "key": api_key,
                "q": query,
                "image_type": "photo",
                "orientation": "horizontal",
                "category": "places,food,travel",
                "min_width": 640,
                "min_height": 480,
                "safesearch": "true",
                "per_page": 3,
                "order": "popular"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get("hits") and len(data["hits"]) > 0:
                # 优先选择中等尺寸的图片
                image_url = data["hits"][0].get("webformatURL") or data["hits"][0].get("largeImageURL")
                print(f"Pixabay找到图片: {image_url}")
                return image_url
            else:
                print("Pixabay未找到相关图片")
                return ""
                
        except requests.exceptions.RequestException as e:
            print(f"Pixabay API请求错误: {str(e)}")
            return ""
        except Exception as e:
            print(f"Pixabay搜索出错: {str(e)}")
            return ""

    def search_unsplash_image(self, query: str) -> str:
        """通过Unsplash API搜索图片"""
        try:
            access_key = os.getenv("UNSPLASH_ACCESS_KEY")
            if not access_key:
                print("Unsplash Access Key未设置")
                return ""
            
            url = "https://api.unsplash.com/search/photos"
            headers = {
                "Authorization": f"Client-ID {access_key}"
            }
            params = {
                "query": query,
                "page": 1,
                "per_page": 3,
                "orientation": "landscape",
                "order_by": "relevant"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get("results") and len(data["results"]) > 0:
                # 选择regular尺寸的图片
                image_url = data["results"][0]["urls"].get("regular") or data["results"][0]["urls"].get("small")
                print(f"Unsplash找到图片: {image_url}")
                return image_url
            else:
                print("Unsplash未找到相关图片")
                return ""
                
        except requests.exceptions.RequestException as e:
            print(f"Unsplash API请求错误: {str(e)}")
            return ""
        except Exception as e:
            print(f"Unsplash搜索出错: {str(e)}")
            return ""

    def search_image_with_retry(self, query: str, max_retries: int = 3) -> str:
        """通过Pixabay和Unsplash API搜索图片，带重试机制"""
        for attempt in range(max_retries):
            try:
                print(f"搜索图片 (尝试 {attempt + 1}/{max_retries}): {query}")
                
                # 添加随机延迟，避免频率限制
                if attempt > 0:  # 第一次尝试不延迟
                    delay = random.uniform(1, 3)  # 1-3秒随机延迟
                    print(f"等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                
                # 优先尝试Pixabay
                image_url = self.search_pixabay_image(query)
                if image_url:
                    return image_url
                
                # 如果Pixabay没找到，尝试Unsplash
                print("Pixabay未找到图片，尝试Unsplash...")
                time.sleep(1)  # API之间的间隔
                image_url = self.search_unsplash_image(query)
                if image_url:
                    return image_url
                
                print(f"两个API都未找到图片 (尝试 {attempt + 1})")
                
            except Exception as e:
                print(f"搜索图片时出错 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2 + random.uniform(1, 3)
                    print(f"等待 {wait_time:.1f} 秒后重试...")
                    time.sleep(wait_time)
        
        print("所有尝试都失败，返回空字符串")
        return ""

    def get_placeholder_image(self, item_type: str, item_name: str) -> str:
        """返回占位符图片URL"""
        placeholder_images = {
            "景点": "https://via.placeholder.com/400x300/4CAF50/white?text=景点图片",
            "美食": "https://via.placeholder.com/400x300/FF9800/white?text=美食图片", 
            "美食店铺": "https://via.placeholder.com/400x300/2196F3/white?text=店铺图片"
        }
        return placeholder_images.get(item_type, "https://via.placeholder.com/400x300/gray/white?text=暂无图片")

    def extract_json_from_response(self,response_content: str) -> List[Dict[str, Any]]:
            """从LLM响应中提取JSON内容"""
            try:
                # 找到JSON内容的开始和结束位置
                start = response_content.find('```json\n') + 8
                end = response_content.find('\n```', start)
                if start == -1 or end == -1:
                    print("未找到JSON内容的标记")
                    return []
                
                json_str = response_content[start:end].strip()
                print(f"提取的JSON字符串: {json_str}")  # 调试信息
                
                # 解析 JSON 字符串
                parsed = json.loads(json_str)
                
                # 处理不同的JSON结构
                if isinstance(parsed, dict) and "related_results" in parsed:
                    return parsed["related_results"]
                elif isinstance(parsed, list):
                    return parsed
                else:
                    print("未找到预期的JSON结构")
                    return []
                
            except json.JSONDecodeError as e:
                print(f"解析JSON失败: {str(e)}")
                print(f"原始内容: {response_content}")
                return []
            except Exception as e:
                print(f"发生错误: {str(e)}")
                return []

    def search_and_rerank(self) -> Dict[str, Any]:
        """多次搜索并重排序，整合信息"""
        city = self.city
        days = self.days
        all_results = {}
    
        # 第一次搜索：旅游攻略
        try:
            query = f"{city}{days}天旅游攻略 最佳路线"
            search_results = self.search_toolkit.search_google(query=query, num_result_pages=5)
            prompt = f"请从以下搜索结果中筛选出最相关的{self.days}条{city}{days}天旅游攻略信息，并按照相关性排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            response = self.reranker_agent.step(prompt)
            all_results["guides"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"旅游攻略搜索失败: {str(e)}")
            all_results["guides"] = []
        
        # 第二次搜索：必去景点
        try:
            query = f"{city} 必去景点 top10 著名景点"
            search_results = self.search_toolkit.search_google(query=query, num_result_pages=5)
            prompt = f"请从以下搜索结果中筛选出最多{self.days}条{city}最值得去的景点信息，并按照热门程度排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            response = self.reranker_agent.step(prompt)
            all_results["attractions"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"景点搜索失败: {str(e)}")
            all_results["attractions"] = []
        
        # 第三次搜索：必吃美食
        try:
            query = f"{city} 必吃美食 特色小吃 推荐"
            search_results = self.search_toolkit.search_google(query=query, num_result_pages=5)
            prompt = f"请从以下搜索结果中筛选出最多{self.days}条{city}最具特色的美食信息，并按照推荐度排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            response = self.reranker_agent.step(prompt)
            all_results["must_eat"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"必吃美食搜索失败: {str(e)}")
            all_results["must_eat"] = []
        
        # 第四次搜索：特色美食
        try:
            query = f"{city} 特色美食 地方小吃 传统美食"
            search_results = self.search_toolkit.search_google(query=query, num_result_pages=5)
            prompt = f"请从以下搜索结果中筛选出最多{self.days}条{city}独特的地方特色美食信息，并按照特色程度排序：\n{json.dumps(search_results, ensure_ascii=False, indent=2)}"
            response = self.reranker_agent.step(prompt)
            all_results["local_food"] = self.extract_json_from_response(response.msgs[0].content)
        except Exception as e:
            print(f"特色美食搜索失败: {str(e)}")
            all_results["local_food"] = []
        
        # 整合所有信息
        final_result = {
            "city": city,
            "days": days,
            "travel_info": {
                "guides": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["guides"]
                ],
                "attractions": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["attractions"]
                ],
                "must_eat": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["must_eat"]
                ],
                "local_food": [
                    {
                        "result_id": item.get("result_id"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "long_description": item.get("long_description"),
                    }
                    for item in all_results["local_food"]
                ]
            }
        }
        
        return final_result
    
    def extract_attractions_and_food(self) -> Dict:
        travel_info = self.search_and_rerank()

        # 提供一个base攻略路线，直接根据整个travel_info生成
        prompt = f"""
        参考以下信息，生成一个{self.city}{self.days}天攻略路线，直接根据整个travel_info生成
        {travel_info}
        【输出格式】
        {{
            "base_guide": "攻略内容"
        }}
        """
        base_guide = self.base_guide_agent.step(prompt)
        print(f"这是base攻略: {base_guide.msgs[0].content}")

        """提取景点和美食信息"""
        # 从描述中提取具体的景点和美食
        attractions_text = " ".join([item["description"] for item in travel_info["travel_info"]["attractions"] + travel_info["travel_info"]["guides"]])
        print(f"这是景点信息: {attractions_text}")
        food_text = " ".join([
            item["description"] 
            for item in travel_info["travel_info"]["must_eat"] + travel_info["travel_info"]["local_food"]
        ])
        print(f"这是美食信息: {food_text}")
        # 使用LLM提取并整理信息
        attractions_prompt = f"""
        请从以下文本中提取出具体的景点名称，注意不能遗漏景点信息，要尽量多提取景点信息，并为每个景点提供简短描述：
        {attractions_text}
        请以JSON格式返回，格式如下：
        {{
            "attractions": [
                {{"name": "景点名称", "description": "简短描述"}}
            ]
        }}
        """
        
        food_prompt = f"""
        请从以下文本中提取出具体的美食名称或者美食店铺，注意不能遗漏美食信息，要尽量多提取美食信息，并为每个美食和店铺提供简短描述：
        {food_text}
        请以JSON格式返回，格式如下：
        {{
            "foods": [
                {{"name": "美食名称", "description": "简短描述"}}
            ],
            "food_shop": [
                {{"name": "美食店铺", "description": "简短描述"}}
            ]
        }}
        """
        
        # 使用attraction_agent处理提取
        attractions_response = self.attraction_agent.step(attractions_prompt)
        foods_response = self.food_agent.step(food_prompt)
        
        print(f"这是景点信息: {attractions_response.msgs[0].content}")
        print(f"这是美食信息: {foods_response.msgs[0].content}")
        
        return {
            "base_guide": base_guide.msgs[0].content,
            "attractions": attractions_response.msgs[0].content,
            "foods": foods_response.msgs[0].content
        }
    
    def generate_html(self):
        """调用generate.py的接口自动生成HTML网页"""
        try:
            # 构建请求数据
            data = {
                "city": self.city,
                "days": str(self.days)
            }
            
            # 调用generate.py的API
            generate_url = "http://localhost:5003/generate_itinerary_html"
            print(f"正在调用generate生成HTML，请求数据: {data}")
            
            # 使用更长的超时时间
            response = requests.post(generate_url, json=data, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                print(f"HTML生成成功，文件保存在: {result.get('file_path', '未知路径')}")
                return result
            else:
                print(f"HTML生成失败，状态码: {response.status_code}")
                print(f"错误信息: {response.text}")
                return None
        except requests.exceptions.Timeout:
            print("调用generate API超时，可能需要手动生成HTML")
            print(f"请手动访问: http://localhost:5003/generate_itinerary_html 并提供参数: {{'city': '{self.city}', 'days': '{self.days}'}}")
            return None
        except requests.exceptions.ConnectionError:
            print("连接generate服务失败，请确保generate.py正在运行")
            print(f"请手动访问: http://localhost:5003/generate_itinerary_html 并提供参数: {{'city': '{self.city}', 'days': '{self.days}'}}")
            return None
        except Exception as e:
            print(f"生成HTML时发生未知错误: {str(e)}")
            return None
            
    def process_attractions_and_food(self) -> Dict:
        def clean_json_string(json_str: str) -> str:
            """清理JSON字符串，移除markdown代码块标记"""
            # 移除 ```json 开头
            if '```json' in json_str:
                json_str = json_str.split('```json')[-1]
            # 移除 ``` 结尾
            if '```' in json_str:
                json_str = json_str.split('```')[0]
            return json_str.strip()
        
        city = self.city
        """处理景点和美食信息，添加图片URL"""
        # 获取原始数据
        results = self.extract_attractions_and_food()
        
        # 解析JSON字符串
        base_guide = json.loads(clean_json_string(results['base_guide']))
        attractions_data = json.loads(clean_json_string(results['attractions']))
        foods_data= json.loads(clean_json_string(results['foods']))
        foods_list = foods_data['foods']
        food_shops_list = foods_data['food_shop']
        
        # 创建结果字典
        result = {
            "city": city,
            "days": self.days,
            "base路线": base_guide,
            "景点": [],
            "美食": [],
            "美食店铺": []
        }
        
        print(f"开始处理 {len(attractions_data['attractions'])} 个景点...")
        
        # 处理景点信息 - 添加延迟和重试机制
        for i, attraction in enumerate(attractions_data['attractions']):
            print(f"处理景点 {i+1}/{len(attractions_data['attractions'])}: {attraction['name']}")
            
            # 搜索图片（通过Pixabay和Unsplash API）
            search_query = f"{city} {attraction['name']}"
            image_url = self.search_image_with_retry(search_query)
            
            # 如果搜索失败，使用占位符
            if not image_url:
                print(f"为 {attraction['name']} 使用占位符图片")
                image_url = self.get_placeholder_image("景点", attraction['name'])
            
            attraction_with_image = {
                "name": attraction['name'],
                "describe": attraction['description'],
                "图片url": image_url,
            }
            result['景点'].append(attraction_with_image)
            
            # 在处理项目之间添加延迟（除了最后一个）
            if i < len(attractions_data['attractions']) - 1:
                delay = random.uniform(1, 2)  # 1-2秒延迟
                print(f"等待 {delay:.1f} 秒后处理下一个景点...")
                time.sleep(delay)
        
        print(f"开始处理 {len(foods_list)} 个美食...")
        
        # 处理美食信息 - 添加延迟和重试机制
        for i, food in enumerate(foods_list):
            print(f"处理美食 {i+1}/{len(foods_list)}: {food['name']}")
            
            # 搜索图片（通过Pixabay和Unsplash API）
            search_query = f"{city} {food['name']} food"
            image_url = self.search_image_with_retry(search_query)
            
            # 如果搜索失败，使用占位符
            if not image_url:
                print(f"为 {food['name']} 使用占位符图片")
                image_url = self.get_placeholder_image("美食", food['name'])
            
            food_with_image = {
                "name": food["name"],
                "describe": food["description"],
                "图片url": image_url,
            }
            result['美食'].append(food_with_image)
            
            # 在处理项目之间添加延迟（除了最后一个）
            if i < len(foods_list) - 1:
                delay = random.uniform(1, 2)  # 1-2秒延迟
                print(f"等待 {delay:.1f} 秒后处理下一个美食...")
                time.sleep(delay)
        
        print(f"开始处理 {len(food_shops_list)} 个美食店铺...")
        
        # 处理美食店铺信息 - 添加延迟和重试机制
        for i, food_shop in enumerate(food_shops_list):
            print(f"处理美食店铺 {i+1}/{len(food_shops_list)}: {food_shop['name']}")
            
            # 搜索图片（通过Pixabay和Unsplash API）
            search_query = f"{city} {food_shop['name']} restaurant"
            image_url = self.search_image_with_retry(search_query)
            
            # 如果搜索失败，使用占位符
            if not image_url:
                print(f"为 {food_shop['name']} 使用占位符图片")
                image_url = self.get_placeholder_image("美食店铺", food_shop['name'])
            
            food_shop_with_image = {
                "name": food_shop["name"],
                "describe": food_shop["description"],
                "图片url": image_url,
            }
            result['美食店铺'].append(food_shop_with_image)
            
            # 在处理项目之间添加延迟（除了最后一个）
            if i < len(food_shops_list) - 1:
                delay = random.uniform(1, 2)  # 1-2秒延迟
                print(f"等待 {delay:.1f} 秒后处理下一个美食店铺...")
                time.sleep(delay)
        
        try:
            # 获取当前脚本所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 创建storage目录路径
            storage_dir = os.path.join(current_dir, "storage")
            # 确保storage目录存在
            os.makedirs(storage_dir, exist_ok=True)
            
            # 生成文件名（使用城市名和日期）
            filename = os.path.join(storage_dir, f"{self.city}{self.days}天旅游信息.json")
            
            # 将结果写入JSON文件
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            print(f"旅游攻略已保存到文件：{filename}")
            
            # 自动调用generate生成HTML
            self.generate_html()
        except Exception as e:
            print(f"保存JSON文件时出错: {str(e)}")
        
        return result

@app.route('/get_travel_plan', methods=['POST'])
def get_travel_plan():
   try:
       # 获取请求数据
       data = request.get_json()
       
       # 验证输入数据
       if not data or 'city' not in data or 'days' not in data:
           return jsonify({
               'status': 'error',
               'message': '请求必须包含city和days参数'
           }), 400
           
       city = data['city']
       days = data['days']
       
       # 验证days是否为整数
       try:
           days = int(days)
       except ValueError:
           return jsonify({
               'status': 'error',
               'message': 'days参数必须为整数'
           }), 400
           
       # 创建TravelPlanner实例并获取结果
       travel_planner = TravelPlanner(city=city, days=days)
       results = travel_planner.process_attractions_and_food()
       
       return jsonify({
           'status': 'success',
           'data': results
       })
       
   except Exception as e:
       return jsonify({
           'status': 'error',
           'message': f'处理请求时发生错误: {str(e)}'
       }), 500

if __name__ == '__main__':
   app.run(host='0.0.0.0', port=5002, debug=True)
