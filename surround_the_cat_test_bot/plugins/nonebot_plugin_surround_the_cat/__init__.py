from nonebot import get_plugin_config
from nonebot import on_command
from nonebot import logger
from nonebot.adapters import Message
from nonebot.adapters.console import Bot as ConsoleBot
from nonebot.adapters.console import MessageSegment as ConsoleMessageSegment
from nonebot.adapters.onebot.v11 import Bot as OnebotBot
from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.typing import T_State
from nonebot.params import ArgPlainText, CommandArg, Depends
from nonebot.plugin import PluginMetadata
import requests
import threading
import os
import random
import inspect
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-surround-the-cat",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

cachePictureList = []
usingPictureList = []
updatePictureList = []
# 条件变量，用于生产者等待消费者消费数据后开始执行
condition = threading.Condition()

os.makedirs(config.imageCacheDirectory, exist_ok=True)


def checkAndAddToCache():
    """
    检查指定路径下的文件是否存在，如果存在，则将其添加到缓存图片列表中。
    """
    for i in range(0, config.imageCacheCount):
        path = f"{config.imageCacheDirectory}/{i}.jpg"
        if (
            len(cachePictureList) < 5
            or len(cachePictureList) < config.imageCacheCount / 2
        ):
            if os.path.exists(path):
                cachePictureList.append(path)
            else:
                updatePictureList.append(path)
        else:
            updatePictureList.append(path)


def downloadPicture():
    while True:
        # 发送 HTTP GET 请求
        url = "https://api.lolicon.app/setu/v2"
        response = requests.get(url)

        # 检查请求是否成功
        if response.status_code == 200:
            # 解析 JSON 数据
            json_data = response.json()
            downloadImage(json_data["data"][0]["urls"]["original"])


def downloadImage(url):
    # 发送 HTTP GET 请求获取图片数据
    response = requests.get(url)

    # 检查请求是否成功
    if response.status_code == 200:
        # 获取条件变量的锁
        with condition:
            while len(updatePictureList) <= 0:
                # 如果缓存图片列表已满，则等待消费者消费一个数据
                condition.wait()
            localPath = updatePictureList.pop(0)
            # 将图片数据写入本地文件
            with open(localPath, "wb") as file:
                file.write(response.content)
            cachePictureList.append(localPath)
            logger.debug(f"图片下载成功，已保存到 {localPath}")


def randomJpgFile(directory):
    """
    从指定目录中随机选择一个后缀名为 .jpg 的文件，并返回文件名。

    参数：
    directory (str): 目录路径。

    返回：
    str: 随机选择的 .jpg 文件名，如果目录中不存在 .jpg 文件，则返回 None。
    """

    # 获取目录下所有指定后缀名为 .jpg 的文件
    jpg_files = [file for file in os.listdir(directory) if file.endswith(".jpg")]

    if jpg_files:
        # 随机选择一个文件
        random_jpg_file = random.choice(jpg_files)
        return random_jpg_file
    else:
        logger.error(f"{directory}目录中不存在 .jpg 文件")
        return None


def randomFile():
    with condition:
        if len(cachePictureList) <= 0:
            condition.notify_all()
            return f"{config.imageCacheDirectory}/{randomJpgFile(config.imageCacheDirectory)}"
        choiceRandomFile=cachePictureList.pop(0)
        usingPictureList.append(choiceRandomFile)
        condition.notify_all()
        return choiceRandomFile


checkAndAddToCache()
# 创建后台线程
background_thread = threading.Thread(target=downloadPicture)
background_thread.daemon = True  # 将线程设置为守护线程，使程序退出时自动结束
background_thread.start()

surroundTheCat = on_command("围猫咪")


@surroundTheCat.handle()
async def handle_function(state: T_State):
    state["picturePath"] = randomFile()


# 通过依赖注入或事件处理函数来进行业务逻辑处理


# 处理控制台回复
@surroundTheCat.handle()
async def handle_console_reply(bot: ConsoleBot, state: T_State):
    await surroundTheCat.send(state["picturePath"])


# 处理 OneBot 回复
@surroundTheCat.handle()
async def handle_onebot_reply(bot: OnebotBot, state: T_State):
    await surroundTheCat.send(state["picturePath"])


# @surroundTheCat.handle()
# async def handle_function():
#     await surroundTheCat.finish(f"{config.imageCacheDirectory}/{randomJpgFile(config.imageCacheDirectory)}")
#
# @surroundTheCat.handle()
# async def handle_private(event: PrivateMessageEvent):
#     await surroundTheCat.finish("私聊消息")
#
# @surroundTheCat.handle()
# async def handle_group(event: GroupMessageEvent):
#     await surroundTheCat.finish("群聊消息")
