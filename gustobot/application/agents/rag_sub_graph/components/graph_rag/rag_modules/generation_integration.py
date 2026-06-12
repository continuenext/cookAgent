"""
生成集成模块
"""

from dotenv import load_dotenv
import os
import time
from typing import List, Generator
from openai import OpenAI
from langchain_core.documents import Document
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="GenerationIntegrationModule")
load_dotenv()

class GenerationIntegrationModule:
    """生成集成模块 - 负责答案生成"""
    def __init__(self):
        """
        初始化生成集成模块
        """
        self.model_name = os.getenv("LLM_MODEL", "qwen3-max")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))
        
        # 初始化OpenAI客户端
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        if not api_key:
            raise ValueError("请设置 LLM_API_KEY 环境变量")
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

        logger.info(f"生成模块初始化完成，模型: {self.model_name}")

    def _build_prompt(self, question: str, documents: List[Document]) -> str:
        """构建统一提示词（供流式/非流式共用）"""
        context_parts = []
        for doc in documents:
            content = doc.page_content.strip()
            if content:
                level = doc.metadata.get('retrieval_level', '')
                if level:
                    context_parts.append(f"[{level.upper()}] {content}")
                else:
                    context_parts.append(content)
        context = "\n\n".join(context_parts)

        return f"""
        作为一位专业的烹饪助手，请基于以下信息回答用户的问题。

        检索到的相关信息：
        {context}

        用户问题：{question}

        请提供准确、实用的回答。根据问题的性质：
        - 如果是询问多个菜品，请提供清晰的列表
        - 如果是询问具体制作方法，请提供详细步骤
        - 如果是一般性咨询，请提供综合性回答

        回答：
        """

    def generate_adaptive_answer(self, question: str, documents: List[Document]) -> str:
        """
        智能统一答案生成
        自动适应不同类型的查询，无需预先分类
        """
        logger.info("正在生成答案...")
        try:
            prompt = self._build_prompt(question, documents)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            return str(response.choices[0].message.content).strip()

        except Exception as e:
            logger.error(f"生成答案失败: {e}")
            return f"抱歉，生成答案时发生了错误：{str(e)}。"
    
    def generate_adaptive_answer_stream(self, question: str, documents: List[Document], max_retries: int = 3) -> Generator[str, None, None]:
        """
        LightRAG风格的流式答案生成（带重试机制）
        """
        prompt = self._build_prompt(question, documents)
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=True,
                    timeout=60  # 增加超时设置
                )
                
                # 流式输出
                if attempt == 0:
                    logger.info("开始流式生成回答...")
                else:
                    logger.info(f"第{attempt + 1}次尝试流式生成...")
                
                full_response = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        yield content  # 使用yield返回流式内容
                
                # 如果成功完成，退出重试循环
                return
                
            except Exception as e:
                logger.warning(f"流式生成第{attempt + 1}次尝试失败: {e}")
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 递增等待时间
                    logger.warning(f"连接中断，{wait_time}秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    # 所有重试都失败，使用非流式作为后备
                    logger.error("流式生成完全失败，尝试非流式后备方案")
                    
                    try:
                        fallback_response = self.generate_adaptive_answer(question, documents)
                        yield fallback_response
                        return
                    except Exception as fallback_error:
                        logger.error(f"后备生成也失败: {fallback_error}")
                        error_msg = f"抱歉，生成回答时出现网络错误，请稍后重试。错误信息：{str(e)}"
                        yield error_msg
                        return 