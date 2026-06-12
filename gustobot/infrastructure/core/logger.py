import logging
import sys
from colorama import init, Fore, Style

# 初始化 colorama（macOS 兼容）
init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """日志格式化器"""
    
    # 设置不同日志级别的颜色
    COLORS = {
        logging.DEBUG: Fore.CYAN, # 青蓝色
        logging.INFO: Fore.GREEN, # 绿色
        logging.WARNING: Fore.YELLOW, # 黄色
        logging.ERROR: Fore.RED, # 红色
        logging.CRITICAL: Fore.RED + Style.BRIGHT # 亮红色
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelno, Fore.WHITE) # 默认白色
        message = super().format(record) # 获取原始日志消息
        return f"{color}{message}{Style.RESET_ALL}" # 添加颜色并重置样式

def get_logger(service: str = "Root"):
    logger = logging.getLogger(service)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout) # 输出到控制台
        handler.setLevel(logging.DEBUG)  # 设置处理器级别
        formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s') # 定义日志格式
        handler.setFormatter(formatter) # 设置处理器格式
        logger.addHandler(handler) # 添加处理器到日志器
        logger.setLevel(logging.DEBUG)  # 设置日志器级别
    return logger

if __name__ == "__main__":
    # 简单测试日志输出
    logger = get_logger("TestLogger")
    logger.debug("这是调试信息")    # 青蓝色
    logger.info("这是信息")        # 绿色
    logger.warning("这是警告")      # 黄色
    logger.error("这是错误")        # 红色
    logger.critical("这是严重错误")  # 亮红色