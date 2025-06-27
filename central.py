import requests
import json
import time
import os

class CentralService:
    def __init__(self):
        # 服务地址
        self.user_service_url = "http://localhost:5001/extract_travel_info"
        self.search_service_url = "http://localhost:5002/get_travel_plan"
        self.generate_service_url = "http://localhost:5003/generate_itinerary_html"
        
        # 确保存储目录存在
        os.makedirs("storage", exist_ok=True)
    
    def process_user_query(self, user_query):
        """处理用户查询并协调三个服务"""
        print(f"接收到用户查询: {user_query}")
        
        try:
            # 第一步：发送到user服务
            print("1. 发送查询到用户服务...")
            user_data = {"query": user_query}
            user_response = requests.post(self.user_service_url, json=user_data)
            
            if user_response.status_code != 200:
                return {"error": f"用户服务请求失败: {user_response.status_code}", "details": user_response.text}
            
            user_result = user_response.json()
            print(f"用户服务返回: {json.dumps(user_result, ensure_ascii=False)}")
            
            # 检查是否需要更多信息
            if user_result.get("need_more_info", True):
                return {"status": "need_more_info", "message": user_result.get("response"), "missing": user_result}
            
            # 第二步：发送到search服务
            print("2. 发送到搜索服务...")
            print("这可能需要较长时间，请耐心等待...")
            search_data = {
                "city": user_result.get("city"),
                "days": user_result.get("days")
            }
            
            search_response = requests.post(self.search_service_url, json=search_data)
            
            if search_response.status_code != 200:
                return {"error": f"搜索服务请求失败: {search_response.status_code}", "details": search_response.text}
            
            search_result = search_response.json()
            print(f"搜索服务返回成功，已生成旅游信息JSON文件")
            
            # 第三步：发送到generate服务
            print("3. 发送到生成服务...")
            print("正在生成HTML页面，请耐心等待...")
            generate_data = {
                "city": user_result.get("city"),
                "days": str(user_result.get("days"))
            }
            
            generate_response = requests.post(self.generate_service_url, json=generate_data)
            
            if generate_response.status_code != 200:
                return {"error": f"生成服务请求失败: {generate_response.status_code}", "details": generate_response.text}
            
            generate_result = generate_response.json()
            print(f"生成服务返回成功，HTML文件已保存")
            
            # 返回最终结果
            return {
                "status": "success",
                "message": f"已为您生成{user_result.get('city')}{user_result.get('days')}天的旅游攻略",
                "file_path": generate_result.get("file_path"),
                "city": user_result.get("city"),
                "days": user_result.get("days")
            }
            
        except requests.exceptions.ConnectionError as e:
            return {"error": f"连接服务失败，请确保所有服务都已启动: {str(e)}"}
        except Exception as e:
            return {"error": f"处理请求时发生错误: {str(e)}"}

def main():
    central = CentralService()
    
    print("旅游攻略生成系统已启动")
    print("请输入您的旅行需求（如：我想去北京玩三天）")
    print("注意：搜索和生成服务可能需要较长时间，请耐心等待")
    
    while True:
        try:
            user_input = input("> ")
            if user_input.lower() in ["exit", "quit", "q"]:
                break
                
            result = central.process_user_query(user_input)
            
            if "error" in result:
                print(f"错误: {result['error']}")
            elif result.get("status") == "need_more_info":
                print(f"需要更多信息: {result['message']}")
            else:
                print(f"成功: {result['message']}")
                print(f"攻略已保存到: {result['file_path']}")
                
        except KeyboardInterrupt:
            print("\n程序已退出")
            break
        except Exception as e:
            print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    main() 