import streamlit as st
from camel.messages import BaseMessage as bm
from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.types import ModelPlatformType
import os
from PIL import Image
from dotenv import load_dotenv
from camel.embeddings import SentenceTransformerEncoder
from camel.storages import QdrantStorage
from camel.retrievers import VectorRetriever
import tempfile
import shutil

load_dotenv()

# 页面配置
st.set_page_config(
    page_title="智能旅游助手",
    page_icon="🏖️",
    layout="wide"
)

# 确保本地数据目录存在
if not os.path.exists('local_data'):
    os.makedirs('local_data')

# 初始化知识库组件
@st.cache_resource
def initialize_knowledge_base():
    """初始化知识库相关组件"""
    try:
        # 初始化嵌入模型
        embedding_model = SentenceTransformerEncoder(model_name='intfloat/e5-large-v2')
        
        # 初始化向量存储
        vector_storage = QdrantStorage(
            vector_dim=embedding_model.get_output_dim(),
            collection="travel_collection",
            path="storage_travel_kb",
            collection_name="旅游知识库"
        )
        
        # 初始化向量检索器
        vector_retriever = VectorRetriever(
            embedding_model=embedding_model,
            storage=vector_storage
        )
        
        return vector_retriever, embedding_model, vector_storage
    except Exception as e:
        st.error(f"知识库初始化失败：{str(e)}")
        return None, None, None

# 初始化模型和Agent（使用缓存避免重复创建）
@st.cache_resource
def initialize_agents():
    # API 配置检查
    deepseek_api_key = os.getenv('DEEPSEEK_API_KEY')
    qwen_api_key = os.getenv('QWEN_API_KEY')
    
    if not deepseek_api_key or not qwen_api_key:
        st.error("❌ 请设置环境变量 DEEPSEEK_API_KEY 和 QWEN_API_KEY")
        st.stop()
    
    api_base = "https://api.siliconflow.cn/v1"
    
    # 设置环境变量
    os.environ["OPENAI_API_KEY"] = deepseek_api_key
    os.environ["OPENAI_API_BASE"] = api_base
    
    # 创建文本回答者模型（DeepSeek-V3）
    answerer_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="deepseek-ai/DeepSeek-V3",
        url=api_base,
        api_key=deepseek_api_key,
        model_config_dict={"max_tokens": 4096}
    )
    
    # 创建图像理解模型（Qwen2.5-VL-72B-Instruct）
    vision_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="Qwen/Qwen2.5-VL-72B-Instruct",
        url='https://api-inference.modelscope.cn/v1/',
        api_key=qwen_api_key,
        model_config_dict={"max_tokens": 4096},
    )
    
    # 创建评估者模型（DeepSeek-R1）
    evaluator_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="deepseek-ai/DeepSeek-V3",
        url=api_base,
        api_key=deepseek_api_key,
        model_config_dict={"max_tokens": 1024}
    )
    
    # 文本回答者 Agent
    answerer_agent = ChatAgent(
        system_message=bm.make_assistant_message(
            role_name="智能旅游助手",
            content="""
            你是一个 AI 旅游助手，请用中文详细回答用户的问题。你对旅游行业有深入的了解，能够根据用户的需求提供详细的旅游方案。
            当用户提供图片时，你会收到图片的描述信息，请结合图片内容和用户问题提供相关的旅游建议。
            当提供了知识库信息时，请优先参考知识库内容来回答问题，并结合你的旅游知识提供全面的建议。
            你只对旅游方面的问题有回应，如果用户的问题与旅游无关，请礼貌地告诉用户你只对旅游方面的问题有回应。
            """
        ),
        model=answerer_model,
        message_window_size=10
    )
    
    # 图像理解 Agent
    vision_agent = ChatAgent(
        system_message=bm.make_assistant_message(
            role_name="图像分析师",
            content="你是一个图像分析专家，请仔细观察图片并用中文详细描述图片的内容，特别关注与旅游相关的元素，如景点、建筑、自然风光、文化特色等。"
        ),
        model=vision_model,
        output_language='中文'
    )
    
    # 评估者 Agent
    evaluator_agent = ChatAgent(
        system_message=bm.make_assistant_message(
            role_name="评估专家",
            content="你是一个 AI 评估员，评价ai对用户问题的回答质量以及符合用户需求程度，请对回答进行打分（1~10），并说明原因。注意打分时输出单个数字然后空格加上理由，不需要类似于'x分'这样的后缀。"
        ),
        model=evaluator_model,
        message_window_size=10
    )
    
    # 知识库助手 Agent
    kb_agent = ChatAgent(
        system_message=bm.make_assistant_message(
            role_name="知识库助手",
            content="""
            你是一个帮助回答问题的助手，
            我会给你原始查询和检索到的上下文，
            根据检索到的上下文回答原始查询，
            如果你无法回答问题就说我不知道。
            请用中文回答，并专注于旅游相关的信息。
            """
        ),
        model=answerer_model,
        output_language='中文'
    )
    
    return answerer_agent, vision_agent, evaluator_agent, kb_agent

def process_uploaded_file(uploaded_file, vector_retriever):
    """处理上传的文件并添加到知识库"""
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name
        
        # 将文件复制到local_data目录
        local_file_path = os.path.join('local_data', uploaded_file.name)
        shutil.copy2(tmp_file_path, local_file_path)
        
        # 处理文件并添加到向量数据库
        vector_retriever.process(content=local_file_path)
        
        # 清理临时文件
        os.unlink(tmp_file_path)
        
        return True, local_file_path
    except Exception as e:
        return False, str(e)

def query_knowledge_base(query, vector_retriever, top_k=3):
    """查询知识库"""
    try:
        retrieved_info = vector_retriever.query(query=query, top_k=top_k)
        return retrieved_info
    except Exception as e:
        st.error(f"知识库查询失败：{str(e)}")
        return []

def analyze_image(image, vision_agent):
    """分析上传的图片"""
    try:
        vision_msg = bm.make_user_message(
            role_name="User", 
            content="请详细描述这张图片的内容，特别关注与旅游相关的元素", 
            image_list=[image]
        )
        
        response = vision_agent.step(vision_msg)
        
        # 检查响应是否有效
        if not response or not hasattr(response, 'msgs') or not response.msgs:
            st.error("图片分析失败：API返回空响应")
            return None
            
        image_description = response.msgs[0].content
        return image_description
    except Exception as e:
        st.error(f"图片分析失败：{str(e)}")
        return None

def process_question_with_knowledge(user_question, image_description, vector_retriever, answerer_agent, kb_agent, evaluator_agent, use_kb=True):
    """处理包含知识库检索的用户问题"""
    knowledge_info = ""
    
    # 如果启用知识库，先检索相关信息
    if use_kb and vector_retriever:
        try:
            retrieved_info = query_knowledge_base(user_question, vector_retriever)
            if retrieved_info:
                knowledge_texts = [info['text'] for info in retrieved_info]
                knowledge_info = "\n\n".join(knowledge_texts)
        except Exception as e:
            st.warning(f"知识库检索失败，将使用基础模式：{str(e)}")
    
    # 构建完整问题
    full_question = f"用户问题：{user_question}\n\n"
    
    if image_description:
        full_question += f"图片描述：{image_description}\n\n"
    
    if knowledge_info:
        full_question += f"知识库相关信息：\n{knowledge_info}\n\n"
    
    full_question += "请结合以上信息回答用户的旅游相关问题。"
    
    usr_msg = bm.make_user_message(
        role_name='用户',
        content=full_question
    )
    
    max_retries = 3
    attempts = 0
    final_answer = None
    is_satisfied = False
    process_log = []
    
    while attempts < max_retries and not is_satisfied:
        attempts += 1
        process_log.append(f"🔄 尝试第 {attempts} 次生成回答...")
        
        try:
            # Step 1: 回答者生成答案
            answer_response = answerer_agent.step(usr_msg)
            
            # 检查回答响应是否有效
            if not answer_response or not hasattr(answer_response, 'msgs') or not answer_response.msgs:
                process_log.append("❌ 回答生成失败：API返回空响应")
                final_answer = "抱歉，我无法生成回答，请稍后重试。"
                break
                
            answer_content = answer_response.msgs[0].content
            process_log.append(f"【回答者回复】\n{answer_content}")
            
            # Step 2: 构造评估请求
            evaluation_prompt = f"""
请评估以下问答过程的质量：

【用户提问】
{user_question}

【图片信息】
{image_description if image_description else "无图片"}

【知识库信息】
{knowledge_info if knowledge_info else "未使用知识库"}

【回答者回复】
{answer_content}

【评分标准】
请从准确性、完整性、清晰度等方面进行打分（1~10），并简要说明理由。

请只返回一个数字 + 简要理由。
"""
            
            evaluation_msg = bm.make_user_message(
                role_name='评估器',
                content=evaluation_prompt
            )
            
            # Step 3: 评估者分析回答质量
            try:
                evaluation_response = evaluator_agent.step(evaluation_msg)
                
                # 检查评估响应是否有效
                if not evaluation_response or not hasattr(evaluation_response, 'msgs') or not evaluation_response.msgs:
                    process_log.append("⚠️ 评估失败：API返回空响应，默认通过")
                    final_answer = answer_content
                    is_satisfied = True
                    break
                    
                evaluation_content = evaluation_response.msgs[0].content.strip()
                process_log.append(f"【评估结果】\n{evaluation_content}")
                
                # Step 4: 判断是否满意
                try:
                    score = int(evaluation_content.split()[0])
                    if score >= 6:
                        is_satisfied = True
                        final_answer = answer_content
                        process_log.append(f"✅ 评分达标（{score}分），生成完成！")
                    else:
                        improve_msg = bm.make_user_message(
                            role_name='评估反馈',
                            content=f"你的回答得分 {score} 分，不够理想。请根据以下建议改进：{evaluation_content}"
                        )
                        answerer_agent.update_messages(improve_msg)
                        process_log.append(f"❌ 评分不达标（{score}分），准备重新生成...")
                except (ValueError, IndexError) as e:
                    process_log.append(f"⚠️ 无法解析评分，默认通过：{str(e)}")
                    final_answer = answer_content
                    is_satisfied = True
                    
            except Exception as e:
                process_log.append(f"⚠️ 评估过程出错，默认通过：{str(e)}")
                final_answer = answer_content
                is_satisfied = True
                
        except Exception as e:
            process_log.append(f"❌ 第{attempts}次尝试失败：{str(e)}")
            if attempts == max_retries:
                final_answer = "抱歉，系统遇到问题，请稍后重试。"
    
    # 如果所有尝试都失败了，提供默认回答
    if final_answer is None:
        final_answer = "抱歉，我无法为您提供满意的回答，请稍后重试或重新描述您的问题。"
        process_log.append("❌ 所有尝试都失败，返回默认回答")
    
    return final_answer, process_log, knowledge_info

# 主界面
def main():
    st.title("🏖️ 智能旅游助手")
    st.markdown("支持文字问答、图片分析和知识库检索的旅游咨询服务")
    st.markdown("---")
    
    # 初始化agents和知识库
    try:
        answerer_agent, vision_agent, evaluator_agent, kb_agent = initialize_agents()
        vector_retriever, embedding_model, vector_storage = initialize_knowledge_base()
    except Exception as e:
        st.error(f"初始化失败：{str(e)}")
        st.stop()
    
    # 侧边栏设置
    with st.sidebar:
        st.header("⚙️ 功能设置")
        st.info("这是一个专门回答旅游相关问题的AI助手，支持图片上传、知识库检索和分析")
        
        # 功能选择
        st.subheader("📋 功能模式")
        mode = st.radio(
            "选择咨询模式：",
            ["纯文字咨询", "图片+文字咨询", "知识库+文字咨询", "全功能模式"],
            index=0
        )
        st.markdown("---")
        st.subheader("🔗 网页生成")
        st.markdown(
            "🌐 [一键生成攻略](http://localhost:5000)",
            help="点击跳转到 localhost:5000"
        )
        # 知识库设置
        if mode in ["知识库+文字咨询", "全功能模式"]:
            st.subheader("📚 知识库管理")
            
            # 文件上传
            uploaded_kb_file = st.file_uploader(
                "上传PDF文件到知识库",
                type=['pdf'],
                help="支持PDF格式的旅游相关文档"
            )
            
            if uploaded_kb_file is not None:
                if st.button("📥 添加到知识库"):
                    with st.spinner("正在处理文件并添加到知识库..."):
                        success, result = process_uploaded_file(uploaded_kb_file, vector_retriever)
                        if success:
                            st.success(f"✅ 文件已成功添加到知识库：{result}")
                            st.session_state.kb_files_count = st.session_state.get('kb_files_count', 0) + 1
                        else:
                            st.error(f"❌ 文件添加失败：{result}")
            
            # 知识库统计
            kb_count = st.session_state.get('kb_files_count', 0)
            st.metric("知识库文件数", kb_count)
        
        # 示例问题
        st.subheader("💡 示例问题")
        if mode == "纯文字咨询":
            example_questions = [
                "推荐一个适合家庭出游的海边城市",
                "去日本旅游需要准备什么？",
                "预算5000元的国内三日游推荐",
                "什么时候去新疆旅游最合适？"
            ]
        elif mode == "图片+文字咨询":
            example_questions = [
                "这个地方适合什么时候去旅游？",
                "分析一下这个景点的特色",
                "根据图片推荐类似的旅游目的地",
                "这里有什么值得体验的活动？"
            ]
        elif mode == "知识库+文字咨询":
            example_questions = [
                "根据知识库信息推荐旅游路线",
                "知识库中有哪些景点介绍？",
                "查询特定地区的旅游攻略",
                "根据文档推荐最佳旅游时间"
            ]
        else:  # 全功能模式
            example_questions = [
                "结合图片和知识库推荐旅游方案",
                "这个景点在知识库中有相关介绍吗？",
                "根据图片和文档分析旅游价值",
                "综合信息制定详细旅游计划"
            ]
        
        for i, question in enumerate(example_questions):
            if st.button(question, key=f"example_{i}"):
                st.session_state.user_input = question
    
    # 主要内容区域
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("💬 咨询区域")
        
        # 图片上传区域
        uploaded_image = None
        if mode in ["图片+文字咨询", "全功能模式"]:
            st.subheader("📸 上传图片")
            uploaded_file = st.file_uploader(
                "选择一张旅游相关的图片",
                type=['png', 'jpg', 'jpeg'],
                help="支持PNG、JPG、JPEG格式"
            )
            
            if uploaded_file is not None:
                uploaded_image = Image.open(uploaded_file)
                st.image(uploaded_image, caption="上传的图片", use_container_width=True)
        
        # 用户输入
        user_input = st.text_area(
            "请输入您的旅游相关问题：",
            height=100,
            placeholder=f"例如：{example_questions[0]}",
            key="user_input"
        )
        
        # 提交按钮
        if st.button("🚀 提交咨询", type="primary"):
            if user_input.strip():
                image_description = None
                use_kb = mode in ["知识库+文字咨询", "全功能模式"]
                
                # 如果有图片，先分析图片
                if uploaded_image is not None:
                    with st.spinner("正在分析图片..."):
                        image_description = analyze_image(uploaded_image, vision_agent)
                        if image_description:
                            st.success("✅ 图片分析完成")
                        else:
                            st.error("❌ 图片分析失败，将继续处理文字问题")
                
                # 处理问题
                with st.spinner("正在思考答案，请稍候..."):
                    final_answer, process_log, knowledge_info = process_question_with_knowledge(
                        user_input, image_description, vector_retriever if use_kb else None, 
                        answerer_agent, kb_agent, evaluator_agent, use_kb
                    )
                
                # 存储结果到session state
                st.session_state.final_answer = final_answer
                st.session_state.process_log = process_log
                st.session_state.user_question = user_input
                st.session_state.image_description = image_description
                st.session_state.uploaded_image = uploaded_image
                st.session_state.knowledge_info = knowledge_info
            else:
                st.warning("请输入问题后再提交！")
    
    with col2:
        st.subheader("📊 使用统计")
        
        # 问题统计
        if 'question_count' not in st.session_state:
            st.session_state.question_count = 0
        st.metric("已回答问题", st.session_state.question_count)
        
        # 图片统计
        if 'image_count' not in st.session_state:
            st.session_state.image_count = 0
        st.metric("已分析图片", st.session_state.image_count)
        
        # 知识库统计
        kb_count = st.session_state.get('kb_files_count', 0)
        st.metric("知识库文件", kb_count)
    
    # 显示结果
    if hasattr(st.session_state, 'final_answer') and st.session_state.final_answer:
        st.markdown("---")
        st.subheader("✅ 咨询结果")
        
        # 显示上传的图片（如果有）
        if hasattr(st.session_state, 'uploaded_image') and st.session_state.uploaded_image:
            col_img, col_desc = st.columns([1, 1])
            with col_img:
                st.image(st.session_state.uploaded_image, caption="您上传的图片", use_container_width=True)
            
            with col_desc:
                if hasattr(st.session_state, 'image_description') and st.session_state.image_description:
                    with st.expander("🔍 图片分析结果", expanded=True):
                        st.write(st.session_state.image_description)
        
        # 显示知识库信息（如果有）
        if hasattr(st.session_state, 'knowledge_info') and st.session_state.knowledge_info:
            with st.expander("📚 知识库检索结果", expanded=False):
                st.write(st.session_state.knowledge_info)
        
        # 用户问题
        with st.expander("📝 您的问题", expanded=True):
            st.write(st.session_state.user_question)
        
        # 最终答案
        st.success("**AI旅游助手回答：**")
        st.write(st.session_state.final_answer)
        
        # 处理过程（可折叠）
        with st.expander("🔍 查看处理过程"):
            for log_entry in st.session_state.process_log:
                st.text(log_entry)
        
        # 反馈区域
        st.subheader("📝 反馈")
        feedback_col1, feedback_col2 = st.columns(2)
        
        with feedback_col1:
            if st.button("👍 满意"):
                st.success("感谢您的反馈！")
                st.session_state.question_count += 1
                if hasattr(st.session_state, 'uploaded_image') and st.session_state.uploaded_image:
                    st.session_state.image_count += 1
        
        with feedback_col2:
            if st.button("👎 不满意"):
                st.info("我们会继续改进，感谢您的反馈！")

if __name__ == "__main__":
    main()
