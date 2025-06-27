import requests
import json
import time
import os
from flask import Flask, request, jsonify, render_template, redirect, url_for

app = Flask(__name__)

class CentralService:
    def __init__(self):
        # 服务地址
        self.user_service_url = "http://localhost:5001/extract_travel_info"
        self.search_service_url = "http://localhost:5002/get_travel_plan"
        self.generate_service_url = "http://localhost:5003/generate_itinerary_html"
        
        # 确保存储目录存在
        os.makedirs("storage", exist_ok=True)
        
        # 创建templates目录
        os.makedirs("templates", exist_ok=True)
    
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
                "html_content": generate_result.get("html_content"),
                "city": user_result.get("city"),
                "days": user_result.get("days")
            }
            
        except requests.exceptions.ConnectionError as e:
            return {"error": f"连接服务失败，请确保所有服务都已启动: {str(e)}"}
        except Exception as e:
            return {"error": f"处理请求时发生错误: {str(e)}"}

central_service = CentralService()

# 创建首页模板
@app.route('/')
def index():
    # 创建templates目录（如果不存在）
    os.makedirs("templates", exist_ok=True)
    
    # 检查模板文件是否存在，如果不存在则创建
    template_path = os.path.join("templates", "index.html")
    if not os.path.exists(template_path):
        with open(template_path, "w", encoding="utf-8") as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>旅游攻略生成系统</title>
    <style>
        body {
            font-family: "Microsoft YaHei", Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .form-container {
            background-color: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        input[type="text"] {
            width: 100%;
            padding: 12px;
            margin: 8px 0;
            box-sizing: border-box;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            width: 100%;
        }
        button:hover {
            background-color: #45a049;
        }
        .message {
            padding: 10px;
            margin-top: 20px;
            border-radius: 4px;
        }
        .success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .info {
            background-color: #e2f3f7;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        .examples {
            margin-top: 20px;
            background-color: #fff;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .loading {
            display: none;
            text-align: center;
            margin-top: 20px;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 2s linear infinite;
            margin: 0 auto;
            margin-bottom: 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
    <script>
        function showLoading() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('submitBtn').disabled = true;
            return true;
        }
    </script>
</head>
<body>
    <h1>旅游攻略生成系统</h1>
    
    <div class="form-container">
        <form action="/process" method="post" onsubmit="return showLoading()">
            <label for="query">请输入您的旅行需求：</label>
            <input type="text" id="query" name="query" placeholder="例如：我想去北京玩三天" required>
            <button type="submit" id="submitBtn">生成攻略</button>
        </form>
    </div>
    
    <div id="loading" class="loading">
        <div class="spinner"></div>
        <p>正在生成旅游攻略，这可能需要几分钟时间，请耐心等待...</p>
    </div>
    
    {% if message %}
    <div class="message {{ message_type }}">
        <p>{{ message }}</p>
        {% if file_path %}
        <p>您的攻略已生成，<a href="/view/{{ file_path | urlencode }}" target="_blank">点击查看</a></p>
        {% endif %}
    </div>
    {% endif %}
    
    <div class="examples">
        <h3>示例输入：</h3>
        <ul>
            <li>我想去北京玩三天</li>
            <li>打算去上海旅游一周</li>
            <li>计划去杭州旅行2天</li>
            <li>我想去成都</li>
        </ul>
        <p><b>注意：</b>生成过程可能需要几分钟时间，尤其是在首次生成特定城市的攻略时。请耐心等待，不要关闭或刷新页面。</p>
    </div>
</body>
</html>""")
    
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    user_query = request.form.get('query', '')
    if not user_query:
        return render_template('index.html', 
                              message="请输入有效的查询内容", 
                              message_type="error")
    
    result = central_service.process_user_query(user_query)
    
    if "error" in result:
        return render_template('index.html', 
                              message=result["error"], 
                              message_type="error",
                              query=user_query)
    elif result.get("status") == "need_more_info":
        return render_template('index.html', 
                              message=result["message"], 
                              message_type="info",
                              query=user_query)
    else:
        # 如果文件路径存在，则保存相对路径用于显示
        file_path = result.get("file_path", "")
        if file_path:
            file_path = os.path.basename(file_path)
            
        return render_template('index.html', 
                              message=result["message"], 
                              message_type="success",
                              file_path=file_path,
                              query=user_query)

@app.route('/view/<filename>')
def view_file(filename):
    # 构建完整文件路径
    file_path = os.path.join("storage", filename)
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return "文件不存在", 404
    
    # 读取HTML内容
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 直接返回HTML内容
    return html_content

if __name__ == '__main__':
    # 确保templates目录存在
    os.makedirs("templates", exist_ok=True)
    
    print("旅游攻略生成系统Web界面已启动")
    print("请访问 http://localhost:5000 使用系统")
    print("注意：搜索和生成服务可能需要较长时间，请耐心等待")
    app.run(debug=True) 