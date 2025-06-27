# 智能旅游助手系统

这是一个集成了AI聊天咨询和一键攻略生成的综合性旅游助手系统，为用户提供全方位的旅游规划服务。

## 系统概述

系统包含两个主要功能模块：

1. **智能旅游聊天助手** - 基于AI的交互式旅游咨询服务
2. **一键攻略生成器** - 自动化的旅游攻略生成系统

## 功能特色

### 🤖 智能旅游聊天助手
- **多模态交互**：支持文字、图片上传和分析
- **知识库检索**：支持PDF文档上传，构建专属旅游知识库
- **四种咨询模式**：
  - 纯文字咨询
  - 图片+文字咨询  
  - 知识库+文字咨询
  - 全功能模式
- **智能评估**：AI自动评估回答质量并优化
- **专业领域**：专注于旅游相关问题的专业回答

### 🗺️ 一键攻略生成器
- **自然语言输入**：支持自然语言描述旅行需求
- **智能解析**：自动提取目的地和旅行天数
- **完整攻略**：生成包含行程、景点、美食的完整HTML攻略
- **多日规划**：支持多天旅行的详细日程安排

## 系统架构

### 聊天助手模块
```
智能旅游聊天助手 (Streamlit App)
├── 文本回答Agent (DeepSeek-V3)
├── 图像理解Agent (Qwen2.5-VL-72B)  
├── 评估Agent (DeepSeek-R1)
├── 知识库系统 (Qdrant + SentenceTransformer)
└── 用户界面 (Streamlit)
```

### 攻略生成模块
```
一键攻略生成系统 (Flask App - 端口5000)
├── User服务 (端口5001) - 用户输入解析
├── Search服务 (端口5002) - 旅游信息搜索
├── Generate服务 (端口5003) - HTML攻略生成
└── 中枢服务 (端口5000) - 服务协调
```

## 环境配置

### 必需的API密钥
在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
QWEN_API_KEY=your_qwen_api_key
```

### 依赖安装
```bash
pip install streamlit
pip install camel-ai
pip install python-dotenv
pip install pillow
pip install requests
pip install flask
pip install qdrant-client
pip install sentence-transformers
```

## 启动方法

### 方法1：完整系统启动

1. **启动攻略生成服务**（按顺序）：
```bash
# 终端1 - 启动User服务
python user.py

# 终端2 - 启动Search服务  
python search.py

# 终端3 - 启动Generate服务
python generate.py

# 终端4 - 启动Web中枢服务
python web_central.py
```

2. **启动聊天助手**：
```bash
# 终端5 - 启动聊天助手
streamlit run chat_ui.py
```

### 方法2：单独启动聊天助手
```bash
streamlit run chat_ui.py
```

## 使用指南

### 🤖 使用聊天助手

1. **访问地址**：http://localhost:8501
2. **选择模式**：在侧边栏选择合适的咨询模式
3. **上传文件**：
   - 图片：支持PNG、JPG、JPEG格式
   - 知识库：支持PDF格式文档
4. **提问咨询**：输入旅游相关问题
5. **跳转功能**：点击"访问本地服务"按钮跳转到攻略生成器

### 🗺️ 使用攻略生成器

1. **访问地址**：http://localhost:5000
2. **输入需求**：例如"我想去北京玩三天"
3. **等待生成**：系统自动处理并生成攻略
4. **查看结果**：生成的HTML文件保存在`storage`目录

## 使用示例

### 聊天助手示例
```
用户：上传了一张天安门的照片，问"这个地方什么时候去最好？"
助手：根据图片识别出天安门，结合旅游知识推荐最佳游览时间和注意事项

用户：上传旅游攻略PDF，问"根据文档推荐北京三日游路线"
助手：检索文档内容，结合AI知识生成详细的三日游方案
```

### 攻略生成器示例
```
输入："我想去杭州旅游2天"
输出：完整的HTML攻略文件，包含：
- 第1天：西湖景区游览路线
- 第2天：灵隐寺、宋城主题公园
- 美食推荐：东坡肉、西湖醋鱼等
- 实用信息：交通、住宿建议
```

## 文件结构

```
旅游助手系统/
├── chat_ui.py                         # 聊天助手主程序
├── web_central.py                  # 攻略生成Web服务
├── user.py                         # 用户输入解析服务
├── search.py                       # 信息搜索服务
├── generate.py                     # 攻略生成服务（网页生成）
├── central.py                      # 命令行版本中枢
├── .env                            # 环境变量配置
├── local_data/                     # 知识库文件存储
├── storage_travel_kb/         # 向量数据库存储
├── storage/                        # 生成的攻略文件
└── README.md                       # 本文档
```

## 技术栈

### 聊天助手
- **前端**：Streamlit
- **AI模型**：DeepSeek-V3、Qwen2.5-VL、DeepSeek-R1
- **向量数据库**：Qdrant
- **嵌入模型**：SentenceTransformer (e5-large-v2)
- **框架**：CAMEL-AI

### 攻略生成器
- **后端**：Flask
- **服务架构**：微服务架构
- **数据格式**：JSON → HTML

## 常见问题

### Q1: 聊天助手无法启动
**A**: 检查以下项目：
- 确认已安装所有依赖包
- 检查API密钥是否正确设置
- 确认网络连接正常

### Q2: 攻略生成器服务连接失败
**A**: 确保按顺序启动所有服务：
1. user.py (端口5001)
2. search.py (端口5002) 
3. generate.py (端口5003)
4. web_central.py (端口5000)

### Q3: 知识库文件上传失败
**A**: 检查以下项目：
- 确认文件格式为PDF
- 检查local_data目录是否存在
- 确认有足够的磁盘空间

### Q4: 图片分析功能异常
**A**: 
- 确认图片格式为PNG/JPG/JPEG
- 检查Qwen API密钥是否有效
- 确认网络连接稳定

### Q5: 生成的攻略文件在哪里？
**A**: HTML攻略文件保存在`storage/`目录下，文件名格式为`{城市}{天数}天旅游攻略.html`


## 贡献指南

欢迎提交Issue和Pull Request来改进系统功能。


---

**享受您的智能旅游规划体验！** 🏖️✈️🗺️